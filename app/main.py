"""Plaud Bridge server — self-hosted sync target for the Plaud Bridge Android app.

Endpoints (all under /api/v1, Bearer-token auth except /health):
  GET  /health                          liveness check
  GET  /auth/check                      validates a client token
  POST /plaud/user-token                mint a Plaud SDK user token
  POST /recordings                      multipart upload from the app
  GET  /recordings                      list recordings
  GET  /recordings/lookup               find by device_sn + session_id
  GET  /recordings/{id}                 metadata
  GET  /recordings/{id}/audio           audio file (bearer OR signed link; Range supported)
  POST /recordings/{id}/audio-link      mint a signed, 1-hour streaming URL for the audio
  GET  /recordings/{id}/transcript      transcript JSON (409 while pending)
  PATCH /recordings/{id}/speakers       rename speakers ("Speaker 1" -> "Alex")
  POST /recordings/{id}/retranscribe    reset a recording for the worker
  POST /audio/transcriptions            OpenAI-compatible STT with this server's engine (also /v1/audio/transcriptions)
  GET  /routes                          list AI routing routes
  POST /routes                          create a route
  PUT  /routes/{id}                     update a route
  DELETE /routes/{id}                   delete a route
  GET  /router/status                   router enabled/configured/model
  GET  /routing/log                     recent router runs with deliveries
  GET  /recordings/{id}/routing         runs + deliveries for one recording
  POST /recordings/{id}/route           rerun the router for a recording
  POST /recordings/{id}/route/preview   dry run: the decision only, nothing delivered or recorded
  POST /deliveries/{id}/retry           re-execute a delivery's action
  POST /apk                             upload/replace the hosted Android APK
  GET  /apk/info                        hosted-APK manifest (404 if none)
  GET  /apk/file                        download the hosted APK
  DELETE /apk                           unhost the current APK
"""

import asyncio
import hashlib
import hmac
import secrets
import json
import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import tempfile
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import Body, Depends, FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from .config import settings
from .db import Store, utcnow_iso
from .formatting import MAX_SPEAKER_NAME_CHARS, build_paragraphs, speaker_labels
from .highlights import parse_marks
from .plaud import PlaudAuthError, PlaudClient
from .automations_summary import summarize_automations
from .router import Router, folder_error
from .transcriber import Transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("plaud-bridge")

VERSION = "0.1.0"

store: Store | None = None
transcriber: Transcriber | None = None
plaud_client: PlaudClient | None = None
router_engine: Router | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, transcriber, plaud_client, router_engine
    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.db_path)
    for warning in settings.validate():
        log.warning("config: %s", warning)
    if settings.plaud_client_id and settings.plaud_secret_key:
        plaud_client = PlaudClient(
            settings.plaud_api_base, settings.plaud_client_id, settings.plaud_secret_key
        )
    install_bundled_apk()
    router_engine = Router(settings, store)
    transcriber = Transcriber(settings, store, router=router_engine)
    transcriber.start()
    yield
    await transcriber.stop()


app = FastAPI(title="Plaud Bridge", version=VERSION, lifespan=lifespan)

PUBLIC_PATHS = {"/api/v1/health"}
LOGIN_REQUEST_TTL_S = 180
MAX_PENDING_LOGIN_REQUESTS = 200
MAX_PENDING_PER_CLIENT = 5


def _client_key(request: Request) -> str:
    """Client identity for the login-request cap. X-Forwarded-For is only
    believed when the socket peer is a trusted reverse proxy (PB_TRUSTED_PROXIES,
    default: loopback and private ranges, which is where NPM lives), and then
    only its LAST entry, the one that proxy appended. Anything a caller can
    write into the header itself is ignored, so rotating it cannot mint fresh
    per-client budgets."""
    peer = request.client.host if request.client else "unknown"
    xff = request.headers.get("x-forwarded-for", "")
    if xff and settings.is_trusted_proxy(peer):
        last = xff.split(",")[-1].strip()
        if last:
            return last[:64]
    return peer[:64]


def _is_public(path: str, method: str) -> bool:
    """Health, plus the two halves of the QR handshake a not-yet-signed-in
    browser must reach: creating a login request and polling it. Approval,
    session listing and revocation stay authenticated."""
    if path in PUBLIC_PATHS:
        return True
    if path == "/api/v1/login-requests" and method == "POST":
        return True
    return path.startswith("/api/v1/login-requests/") and not path.endswith("/approve") and method == "GET"


_RESULT_PATH_RE = re.compile(r"^/api/v1/deliveries/([A-Za-z0-9_-]{8,64})/result$")


def _result_callback_ok(request: Request) -> bool:
    """Delivery-result callbacks authenticate with the per-attempt capability
    from their payload. Checked in the middleware, before FastAPI reads or
    validates the body, so an unauthenticated caller cannot make the server
    parse anything."""
    if request.method != "POST":
        return False
    m = _RESULT_PATH_RE.match(request.url.path)
    if not m or store is None:
        return False
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    delivery = store.get_delivery(m.group(1))
    if not delivery or not delivery.get("result_token_hash"):
        return False
    return hmac.compare_digest(hashlib.sha256(token.encode()).hexdigest(), delivery["result_token_hash"])


def _session_for(token: str) -> dict | None:
    if store is None:
        return None
    return store.session_by_hash(hashlib.sha256(token.encode()).hexdigest())


# ── signed audio links ───────────────────────────────────────────────────────
# A browser <audio> element cannot send a bearer header, so the dashboard asks
# for a short-lived link instead: the same audio path with sig+exp query params.
# The signing key is derived from the configured API token (no extra config);
# signatures are checked against every configured token so rotation does not
# cut a link off mid-playback.

AUDIO_LINK_TTL_S = 60 * 60
_AUDIO_PATH_RE = re.compile(r"^/api/v1/recordings/([A-Za-z0-9_-]{1,64})/audio$")
_AUDIO_LINK_EXPIRED = "This audio link has expired. Reload the recording to get a new one."


def _audio_link_key(token: str) -> bytes:
    return hmac.new(token.encode(), b"plaud-bridge:audio-link:v1", hashlib.sha256).digest()


def _audio_link_sig(rec_id: str, exp: int, token: str) -> str:
    return hmac.new(_audio_link_key(token), f"{rec_id}:{exp}".encode(), hashlib.sha256).hexdigest()


def _audio_link_ok(rec_id: str, sig: str | None, exp: str | None) -> bool:
    if not sig or not exp or not _AUDIO_PATH_RE.match(f"/api/v1/recordings/{rec_id}/audio"):
        return False
    try:
        exp_i = int(exp)
    except ValueError:
        return False
    if exp_i <= int(time.time()) or exp_i > int(time.time()) + AUDIO_LINK_TTL_S + 60:
        return False
    return any(hmac.compare_digest(sig, _audio_link_sig(rec_id, exp_i, t)) for t in settings.auth_tokens)


def _audio_link_request(request: Request) -> tuple[str, bool] | None:
    """(rec_id, valid) when this is a GET for an audio file that presents a
    signed link; None when it is not a signed-link request at all."""
    m = _AUDIO_PATH_RE.match(request.url.path)
    if request.method != "GET" or not m or "sig" not in request.query_params:
        return None
    rec_id = m.group(1)
    return rec_id, _audio_link_ok(rec_id, request.query_params.get("sig"), request.query_params.get("exp"))


def _token_ok(request: Request) -> bool:
    """A configured token (PB_AUTH_TOKENS) or a live browser session minted by
    the phone's QR approval. Session ids are remembered on the request so
    /auth/logout can revoke exactly the caller."""
    auth = request.headers.get("Authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    if any(hmac.compare_digest(token, t) for t in settings.auth_tokens):
        return True
    sess = _session_for(token)
    if sess is None:
        return False
    request.state.session_id = sess["id"]
    # Cheap liveness signal for the "signed-in computers" list; once a minute is plenty.
    if (sess.get("last_used_at") or "") < utcnow_iso()[:16]:
        store.touch_session(sess["id"])
    return True


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Reject unauthenticated API requests before any body parsing happens."""
    path = request.url.path
    if ((path.startswith("/api/") or path.startswith("/v1/")) and not _is_public(path, request.method)
            and not _token_ok(request) and not _result_callback_ok(request)):
        link = _audio_link_request(request)
        if link is not None and not link[1]:
            # A link that was valid once: tell the player to fetch a fresh one.
            return JSONResponse({"detail": _AUDIO_LINK_EXPIRED}, status_code=403)
        if link is None:
            return JSONResponse(
                {"detail": "invalid or missing bearer token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
    return response


def require_auth(request: Request) -> None:
    # Defense in depth behind auth_middleware (covers direct route calls in tests).
    if not _token_ok(request):
        raise HTTPException(
            status_code=401,
            detail="invalid or missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "service": "plaud-bridge", "version": VERSION}


class LoginRequestBody(BaseModel):
    model_config = {"extra": "ignore"}
    label: str | None = Field(default=None, max_length=120)


@app.post("/api/v1/login-requests", status_code=201)
async def create_login_request(request: Request, body: LoginRequestBody | None = None):
    """Public: a signed-out browser asks for a QR login. The id is the only
    secret in the QR; it is 192 random bits and lives three minutes. Pending
    requests are capped per client (so one caller cannot exhaust the slots
    and lock everyone else out) and globally."""
    client = _client_key(request)
    pending_total = store.purge_login_requests()
    if store.count_pending_login_requests(client) >= MAX_PENDING_PER_CLIENT:
        raise HTTPException(status_code=429, detail="too many pending login requests from this client")
    if pending_total >= MAX_PENDING_LOGIN_REQUESTS:
        raise HTTPException(status_code=429, detail="too many pending login requests")
    req_id = secrets.token_urlsafe(24)
    expires = (datetime.now(timezone.utc) + timedelta(seconds=LOGIN_REQUEST_TTL_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
    label = " ".join((body.label if body and body.label else "").split())[:120] or None
    store.insert_login_request(req_id, expires, label, client)
    return {"id": req_id, "expires_at": expires, "poll_seconds": 2}


@app.get("/api/v1/login-requests/{req_id}")
async def poll_login_request(req_id: str):
    """Public: the browser polls until the phone approves. The minted token is
    handed over exactly once; the request row is deleted in the same step."""
    req = store.get_login_request(req_id)
    if not req or req["expires_at"] <= utcnow_iso():
        if req:
            store.delete_login_request(req_id)
        return {"status": "expired"}
    if req["status"] == "approved" and req.get("token"):
        store.delete_login_request(req_id)
        return {"status": "approved", "token": req["token"]}
    return {"status": "pending"}


@app.post("/api/v1/login-requests/{req_id}/approve", dependencies=[Depends(require_auth)])
async def approve_login_request(req_id: str, body: LoginRequestBody | None = None):
    """The phone (or any signed-in client) approves a scanned QR: mint a
    session token for that browser. The master token never leaves the phone."""
    req = store.get_login_request(req_id)
    if not req or req["expires_at"] <= utcnow_iso():
        raise HTTPException(status_code=404, detail="login request expired or unknown")
    if req["status"] != "pending":
        raise HTTPException(status_code=409, detail="login request already used")
    token = secrets.token_urlsafe(32)
    label = (body.label if body and body.label else None) or req.get("label") or "Web browser"
    session_id = store.insert_session(hashlib.sha256(token.encode()).hexdigest(), label)
    if not store.approve_login_request(req_id, token):
        store.revoke_session(session_id)
        raise HTTPException(status_code=409, detail="login request already used")
    return {"status": "approved", "label": label, "session_id": session_id}


@app.get("/api/v1/sessions", dependencies=[Depends(require_auth)])
async def list_sessions(request: Request):
    current = getattr(request.state, "session_id", None)
    return {"sessions": [{**s_, "current": s_["id"] == current} for s_ in store.list_sessions()]}


@app.delete("/api/v1/sessions/{session_id}", dependencies=[Depends(require_auth)])
async def revoke_session(session_id: str):
    if not store.revoke_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    return Response(status_code=204)


@app.post("/api/v1/auth/logout", dependencies=[Depends(require_auth)])
async def logout(request: Request):
    """Revoke the calling browser's session (no-op for a configured token)."""
    sid = getattr(request.state, "session_id", None)
    if sid:
        store.revoke_session(sid)
    return Response(status_code=204)


@app.get("/api/v1/auth/check", dependencies=[Depends(require_auth)])
async def auth_check():
    return Response(status_code=204)


class UserTokenRequest(BaseModel):
    user_id: str = Field(min_length=6, max_length=120)
    expires_in: int = Field(default=86400, ge=300, le=30 * 86400)


@app.post("/api/v1/plaud/user-token", dependencies=[Depends(require_auth)])
async def plaud_user_token(body: UserTokenRequest):
    if plaud_client is None:
        raise HTTPException(
            status_code=503,
            detail="Plaud credentials not configured (PB_PLAUD_CLIENT_ID / PB_PLAUD_SECRET_KEY)",
        )
    try:
        return await plaud_client.get_user_token(body.user_id, body.expires_in)
    except PlaudAuthError as exc:
        log.error("plaud auth error: %s", exc)
        raise HTTPException(status_code=502, detail="Plaud partner API request failed (see server logs)")


# Failure text people can act on. The raw exception string (`error_detail`)
# stays available behind a disclosure; the sentence is what a list row shows.
# Order matters: the first matching rule wins.
_FRIENDLY_ERRORS: list[tuple[tuple[str, ...], str]] = [
    (("over the", "too long", "max_duration", "duration_s"), "The recording is too long to transcribe."),
    (("no audio decoded", "decode", "ffmpeg", "invalid data", "could not read", "unsupported format",
      "no such file", "not found", "is a directory", "permission denied", "audio file"),
     "Couldn't read the audio file."),
    (("summar",), "Summary failed, transcript is ready."),
    (("diariz",), "Couldn't identify speakers."),
    (("timed out", "timeout"), "Transcription took too long and was stopped."),
    (("not installed", "not configured", "unknown pb_stt_engine", "not set"),
     "Transcription isn't set up on the server."),
    (("connect", "unreachable", "refused", "endpoint returned", "name or service", "network"),
     "Couldn't reach the transcription service."),
    (("out of memory", "cuda", "cudnn", "cublas"), "The transcription engine ran out of resources."),
]


def friendly_error(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    low = str(raw).lower()
    for needles, sentence in _FRIENDLY_ERRORS:
        if any(n in low for n in needles):
            return sentence
    return "Transcription failed."


def _public(rec: dict) -> dict:
    rec = dict(rec)
    rec.pop("audio_path", None)
    rec.pop("transcript_path", None)
    text = rec.pop("transcript_text", None)
    # `error` is a sentence for people; the raw exception text moves to
    # `error_detail` (the DB column keeps the raw string).
    raw_error = rec.get("error")
    rec["error_detail"] = raw_error or None
    rec["error"] = friendly_error(raw_error)
    rec["has_transcript"] = rec["status"] == "done"
    # Finished, but the audio held no speech (silence, a pocket recording).
    rec["no_speech"] = rec["status"] == "done" and not (text or "").strip()
    rec["text_preview"] = (text or "")[:240] or None
    rec["marks"] = parse_marks(rec.get("marks"))  # stored as JSON text, served as a list
    # Live progress: stage + 0..1 fraction while transcribing, "queued" while waiting.
    if rec["status"] == "transcribing":
        rec["stage"] = rec.get("stage") or "transcribing"
    elif rec["status"] == "pending":
        rec["stage"], rec["progress"] = "queued", None
    else:
        rec["stage"], rec["progress"] = None, None
    return rec


class UploadMetadata(BaseModel):
    model_config = {"extra": "ignore"}

    session_id: int | None = Field(default=None, ge=0, le=2**62)
    device_sn: str | None = Field(default=None, max_length=64)
    started_at: str | None = Field(default=None, max_length=40)
    duration_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    source: str | None = Field(default=None, max_length=64)
    # Recorder button presses, seconds from the start of the recording.
    marks: list[float] | None = Field(default=None, max_length=500)


class MarksBody(BaseModel):
    marks: list[float] = Field(max_length=500)


class RecordingPatch(BaseModel):
    model_config = {"extra": "forbid"}
    title: str = Field(min_length=1, max_length=120)


@app.post("/api/v1/recordings", dependencies=[Depends(require_auth)])
async def upload_recording(file: UploadFile, metadata: str = Form("{}", max_length=4096)):
    try:
        meta = UploadMetadata.model_validate_json(metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid metadata: {exc}")
    if meta.started_at:
        try:
            datetime.fromisoformat(meta.started_at.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="started_at is not an ISO-8601 timestamp")

    # Stream to a temp file in the target filesystem while hashing, then rename.
    max_bytes = settings.max_upload_mb * 1024 * 1024
    hasher = hashlib.sha256()
    size = 0
    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(dir=settings.recordings_dir, suffix=".part", delete=False)
    try:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(status_code=413, detail=f"file exceeds {settings.max_upload_mb} MB")
            hasher.update(chunk)
            tmp.write(chunk)
        tmp.close()
        if size == 0:
            raise HTTPException(status_code=400, detail="empty file")
        sha256 = hasher.hexdigest()

        existing = store.find_by_sha256(sha256)
        if not existing and meta.device_sn is not None and meta.session_id is not None:
            existing = store.find_by_session(meta.device_sn, meta.session_id)
        if existing:
            return JSONResponse({"id": existing["id"], "duplicate": True}, status_code=200)

        uploaded_at = utcnow_iso()
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "recording.mp3")[:120]
        subdir = settings.recordings_dir / uploaded_at[:4] / uploaded_at[5:7]
        subdir.mkdir(parents=True, exist_ok=True)
        audio_path = subdir / f"{sha256[:16]}_{safe_name}"
        os.replace(tmp.name, audio_path)
    finally:
        # Covers error paths AND duplicate-return paths; no-op after os.replace.
        if not tmp.closed:
            tmp.close()
        Path(tmp.name).unlink(missing_ok=True)

    try:
        rec_id = store.insert_recording(
            device_sn=meta.device_sn,
            session_id=meta.session_id,
            filename=safe_name,
            sha256=sha256,
            size_bytes=size,
            duration_s=meta.duration_s,
            started_at=meta.started_at,
            source=meta.source,
            marks=json.dumps(parse_marks(meta.marks)) if meta.marks else None,
            uploaded_at=uploaded_at,
            audio_path=str(audio_path),
            status="pending",
        )
    except sqlite3.IntegrityError:
        # Concurrent identical upload won the race; treat as duplicate and
        # drop our just-renamed copy if the winner owns a different path.
        existing = store.find_by_sha256(sha256)
        if existing:
            if existing["audio_path"] != str(audio_path):
                audio_path.unlink(missing_ok=True)
            return JSONResponse({"id": existing["id"], "duplicate": True}, status_code=200)
        raise
    transcriber.wake.set()
    log.info("stored recording %s (%s, %.1f MB)", rec_id, safe_name, size / 1e6)
    return JSONResponse({"id": rec_id, "duplicate": False}, status_code=201)


SNIPPET_CHARS = 160


def _snippet(text: str, query: str, width: int = SNIPPET_CHARS) -> str | None:
    """About `width` characters around the first case-insensitive hit of
    `query` in `text`, cut at word boundaries where possible and ellipsised
    where trimmed. None when the query does not occur."""
    if not text or not query:
        return None
    flat = " ".join(text.split())
    hit = flat.lower().find(query.lower())
    if hit < 0:
        return None
    if len(flat) <= width:
        return flat
    lead = max(0, (width - len(query)) // 2)
    start = max(0, hit - lead)
    end = min(len(flat), start + width)
    start = max(0, end - width)
    if start > 0:
        # Move to the next word boundary, unless that would swallow the hit.
        sp = flat.find(" ", start, hit)
        if sp >= 0:
            start = sp + 1
    if end < len(flat):
        sp = flat.rfind(" ", max(hit + len(query), start), end)
        if sp > hit + len(query):
            end = sp
    piece = flat[start:end].strip()
    return ("…" if start > 0 else "") + piece + ("…" if end < len(flat) else "")


def _search_match(rec: dict, query: str | None) -> tuple[str | None, str | None]:
    """Which field a list search hit and a snippet of it: title, summary, then
    transcript. A hit on the file name only counts as the title (that is what
    the row shows when there is no title)."""
    if not query:
        return None, None
    for field, key in (("title", "title"), ("summary", "summary"), ("transcript", "transcript_text"),
                       ("title", "filename")):
        snippet = _snippet(rec.get(key) or "", query)
        if snippet is not None:
            return field, snippet
    return None, None


@app.get("/api/v1/recordings", dependencies=[Depends(require_auth)])
async def list_recordings(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10**9),
    status: str | None = Query(None, max_length=20),
    q: str | None = Query(None, max_length=200),
):
    q = (q or "").strip() or None
    items = []
    for r in store.list(limit=limit, offset=offset, status=status, query=q):
        field, snippet = _search_match(r, q)
        item = _public(r)
        item["match_field"], item["match_snippet"] = field, snippet
        items.append(item)
    _attach_automations(items)
    return {"recordings": items}


def _attach_automations(items: list[dict]) -> None:
    """`automations`: what the latest router run did with each recording, for
    list rows (see automations_summary). Two queries for the whole page."""
    runs = store.latest_router_runs([i["id"] for i in items])
    deliveries = store.deliveries_for_runs([r["id"] for r in runs.values()])
    for item in items:
        run = runs.get(item["id"])
        if run:
            run = _run_public(run)
            public_deliveries = [_delivery_public(d) for d in deliveries.get(run["id"], [])]
        else:
            public_deliveries = []
        item["automations"] = summarize_automations(run, public_deliveries)


@app.get("/api/v1/stats", dependencies=[Depends(require_auth)])
async def stats():
    return store.stats()


@app.get("/api/v1/recordings/lookup", dependencies=[Depends(require_auth)])
async def lookup_recording(device_sn: str, session_id: int):
    rec = store.find_by_session(device_sn, session_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    item = _public(rec)
    _attach_automations([item])
    return item


@app.get("/api/v1/recordings/{rec_id}", dependencies=[Depends(require_auth)])
async def get_recording(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    item = _public(rec)
    _attach_automations([item])
    return item


def _audio_media_type(filename: str | None) -> str:
    guessed, _ = mimetypes.guess_type(filename or "")
    return guessed if guessed and guessed.startswith("audio/") else "audio/mpeg"


@app.get("/api/v1/recordings/{rec_id}/audio")
async def get_audio(rec_id: str, request: Request):
    """The audio file. Accepts the bearer header (the app) OR a signed link
    from POST /audio-link (the dashboard's <audio> element). Range requests
    get 206 partial content so players can seek without downloading it all."""
    link = _audio_link_request(request)
    if not _token_ok(request):
        if link is None:
            raise HTTPException(status_code=401, detail="invalid or missing bearer token",
                                headers={"WWW-Authenticate": "Bearer"})
        if not link[1]:
            raise HTTPException(status_code=403, detail=_AUDIO_LINK_EXPIRED)
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    if not Path(rec["audio_path"]).is_file():
        raise HTTPException(status_code=404, detail="The audio file is missing on the server.")
    # FileResponse handles Range (206 / 416) and sets Accept-Ranges: bytes.
    return FileResponse(rec["audio_path"], media_type=_audio_media_type(rec["filename"]),
                        filename=rec["filename"])


@app.post("/api/v1/recordings/{rec_id}/audio-link", dependencies=[Depends(require_auth)])
async def audio_link(rec_id: str):
    """A URL for the audio that works without a header for one hour (an
    <audio src>). Signed with a key derived from the server's API token."""
    if not store.get(rec_id):
        raise HTTPException(status_code=404, detail="Recording not found.")
    if not settings.auth_tokens:
        raise HTTPException(status_code=503, detail="Audio links need an access token configured on the server.")
    exp = int(time.time()) + AUDIO_LINK_TTL_S
    sig = _audio_link_sig(rec_id, exp, settings.auth_tokens[0])
    return {"url": f"/api/v1/recordings/{rec_id}/audio?sig={sig}&exp={exp}", "expires_at": exp}


def _transcript_view(rec: dict) -> dict:
    """The transcript document as clients read it, with the derived fields
    (no_speech, paragraphs for pre-reader-layout files, speaker list)."""
    if rec["status"] != "done" or not rec["transcript_path"]:
        raise HTTPException(status_code=409, detail="The transcript isn't ready yet.")
    try:
        with open(rec["transcript_path"]) as fh:
            transcript = json.load(fh)
    except (OSError, ValueError):
        raise HTTPException(status_code=409, detail="The transcript file is missing on the server.")
    transcript["no_speech"] = not (transcript.get("text") or "").strip()
    if "paragraphs" not in transcript:  # documents written before the reader layout existed
        # Renames are applied to the segments themselves, so derived paragraphs carry them.
        transcript["paragraphs"] = build_paragraphs(transcript.get("segments") or [], transcript.get("highlights") or [])
    transcript["speakers"] = speaker_labels(transcript)
    transcript.setdefault("speaker_names", {})
    return transcript


@app.get("/api/v1/recordings/{rec_id}/transcript", dependencies=[Depends(require_auth)])
async def get_transcript(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    return _transcript_view(rec)


class SpeakerRenames(BaseModel):
    model_config = {"extra": "forbid"}
    renames: dict[str, str] = Field(min_length=1, max_length=50)


@app.patch("/api/v1/recordings/{rec_id}/speakers", dependencies=[Depends(require_auth)])
async def rename_speakers(rec_id: str, body: SpeakerRenames):
    """Give speakers names: {"renames": {"Speaker 1": "Alex"}}. Labels not in
    the transcript are ignored; a blank new name is refused. The names stick
    (segments, paragraphs, text, exported note, and a speaker_names map that
    survives highlight refreshes)."""
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    if rec["status"] != "done" or not rec["transcript_path"]:
        raise HTTPException(status_code=409, detail="The transcript isn't ready yet.")
    renames: dict[str, str] = {}
    for old, new in body.renames.items():
        new = " ".join(new.split())
        if not new:
            raise HTTPException(status_code=422, detail="A speaker name can't be blank.")
        if len(new) > MAX_SPEAKER_NAME_CHARS:
            raise HTTPException(status_code=422, detail=f"Speaker names are limited to {MAX_SPEAKER_NAME_CHARS} characters.")
        renames[old] = new
    if transcriber.rename_speakers(rec_id, renames) is None:
        raise HTTPException(status_code=409, detail="The transcript file is missing on the server.")
    return _transcript_view(store.get(rec_id) or rec)


class VocabEntryBody(BaseModel):
    term: str = Field(min_length=1, max_length=64)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    source: Literal["manual", "obsidian"] = "manual"
    weight: int | None = Field(default=None, ge=0, le=10**6)


class VocabularyBody(BaseModel):
    entries: list[VocabEntryBody] = Field(max_length=600)  # == vocabulary.MAX_ENTRIES


@app.get("/api/v1/vocabulary", dependencies=[Depends(require_auth)])
async def get_vocabulary():
    from .vocabulary import hotwords_string, normalize, to_editor_text

    entries = normalize(store.list_vocabulary())
    return {"entries": [e.as_dict() for e in entries], "editor_text": to_editor_text(entries),
            "hotwords": hotwords_string(entries)}


@app.put("/api/v1/vocabulary", dependencies=[Depends(require_auth)])
async def put_vocabulary(body: VocabularyBody):
    """Replace the whole list (what the editors save). The editors work in
    plain text and do not carry weights, so an entry without a weight keeps
    the weight it already had."""
    from .vocabulary import normalize

    have = {e["term"].lower(): e.get("weight") or 0 for e in store.list_vocabulary()}
    items = []
    for e in body.entries:
        d = e.model_dump()
        if d.get("weight") is None:
            d["weight"] = have.get(d["term"].strip().lower(), 0)
        items.append(d)
    entries = normalize(items)
    store.replace_vocabulary([e.as_dict() for e in entries])
    return {"entries": [e.as_dict() for e in entries]}


@app.post("/api/v1/vocabulary/import", dependencies=[Depends(require_auth)])
async def import_vocabulary(body: VocabularyBody):
    """Merge entries in (used by contrib/vocab_from_obsidian.py). Existing
    terms and aliases are kept; new terms and aliases are added."""
    from .vocabulary import merge, normalize

    existing = normalize(store.list_vocabulary())
    incoming = normalize([e.model_dump() for e in body.entries])
    merged = merge(existing, incoming)
    store.replace_vocabulary([e.as_dict() for e in merged])
    return {"entries": [e.as_dict() for e in merged], "added": len(merged) - len(existing)}


@app.patch("/api/v1/recordings/{rec_id}", dependencies=[Depends(require_auth)])
async def patch_recording(rec_id: str, body: RecordingPatch):
    """Rename a recording (the app's native Library and the dashboard). The
    title also lands in the transcript JSON so exports and the app's cached
    transcript agree with the row."""
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    title = " ".join(body.title.split())
    if not title:
        raise HTTPException(status_code=422, detail="title must not be blank")
    store.update(rec_id, title=title)
    if rec.get("transcript_path"):
        Transcriber._patch_transcript_json(rec["transcript_path"], title, None)
    return _public(store.get(rec_id))


@app.patch("/api/v1/recordings/{rec_id}/marks", dependencies=[Depends(require_auth)])
async def set_marks(rec_id: str, body: MarksBody):
    """Replace the recorder button-press marks (seconds from start). Used by the
    app when marks arrive after the upload (e.g. the device disconnected before
    they could be read). If the transcript already exists its highlights are
    recomputed in place, no re-transcription needed."""
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    marks = parse_marks(body.marks)
    store.update(rec_id, marks=json.dumps(marks))
    # Re-read AFTER writing: if the transcriber finished in between, it may have
    # committed with the old marks, and it is now our job to refresh.
    rec = store.get(rec_id) or rec
    highlights = None
    if rec["status"] == "done" and rec.get("transcript_path"):
        highlights = transcriber.refresh_highlights(rec_id)
    return {"id": rec_id, "marks": marks, "highlights": highlights}


@app.get("/api/v1/recordings/{rec_id}/export.md", dependencies=[Depends(require_auth)])
async def export_markdown(rec_id: str):
    """Markdown rendering of the transcript for the dashboard's Export button
    (same layout the Android app produces on-device)."""
    from urllib.parse import quote

    from .export import safe_filename, transcript_markdown

    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    if rec["status"] != "done" or not rec["transcript_path"]:
        raise HTTPException(status_code=409, detail="The transcript isn't ready yet.")
    with open(rec["transcript_path"]) as fh:
        transcript = json.load(fh)
    title = rec.get("title") or transcript.get("title") or rec["filename"]
    md = transcript_markdown(
        title=title,
        recorded=rec.get("started_at") or rec.get("uploaded_at"),
        duration_s=transcript.get("duration_s") or rec.get("duration_s"),
        summary=transcript.get("summary") or rec.get("summary"),
        text=transcript.get("text") or "",
        highlights=transcript.get("highlights") or [],
        paragraphs=transcript.get("paragraphs")
        or build_paragraphs(transcript.get("segments") or [], transcript.get("highlights") or []),
    )
    base = safe_filename(title)
    ascii_name = base.encode("ascii", "ignore").decode() or "transcript"
    return Response(
        md, media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition":
                 f'attachment; filename="{ascii_name}.md"; filename*=UTF-8\'\'{quote(base)}.md'},
    )


@app.post("/api/v1/recordings/{rec_id}/retranscribe", dependencies=[Depends(require_auth)])
async def retranscribe(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    if rec.get("transcript_path"):
        Path(rec["transcript_path"]).unlink(missing_ok=True)
    store.update(
        rec_id, status="pending", attempts=0, error=None,
        transcript_text=None, summary=None, title=None, transcript_path=None,
    )
    transcriber.wake.set()
    return {"id": rec_id, "status": "pending"}


# ── OpenAI-compatible transcription (worker mode) ───────────────────────────
#
# Another plaud-bridge (or anything speaking the OpenAI audio API) can send a
# file here and get this server's engine — enhancement, consensus alternates
# and speaker diarization included — as verbose_json. This is how a GPU box
# elsewhere becomes the transcription worker for the server that holds the
# recordings: point that server's PB_STT_ENGINE=openai at this URL.

_TRANSCRIBE_FORMATS = ("json", "verbose_json", "text")


async def _transcribe_upload(file: UploadFile, language: str | None, prompt: str | None, response_format: str):
    if transcriber is None or transcriber.engine is None:
        raise HTTPException(status_code=503, detail="transcription is disabled on this server")
    if response_format not in _TRANSCRIBE_FORMATS:
        raise HTTPException(status_code=400, detail=f"response_format must be one of {', '.join(_TRANSCRIBE_FORMATS)}")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    suffix = Path(file.filename or "audio").suffix[:8] or ".bin"
    tmp = tempfile.NamedTemporaryFile(prefix="pb-stt-", suffix=suffix, delete=False)
    size = 0
    try:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(status_code=413, detail=f"file exceeds {settings.max_upload_mb} MB")
            tmp.write(chunk)
        tmp.close()
        if size == 0:
            raise HTTPException(status_code=400, detail="empty file")
        engine = transcriber.engine
        # The engine decodes in its configured language (PB_TRANSCRIBE_LANGUAGE
        # or auto-detect); a different per-request `language` is noted, not
        # honoured — the models are loaded once with one configuration.
        if language and getattr(engine, "language", None) not in (None, language):
            log.info("transcription API: language=%s requested, engine is configured for %s",
                     language, getattr(engine, "language", None))
        try:
            result = await engine.transcribe(Path(tmp.name), hotwords=prompt or None, progress=None)
        except Exception as exc:
            log.warning("transcription API request failed: %s", exc)
            raise HTTPException(status_code=502, detail=f"transcription failed: {str(exc)[:300]}")
        consensus = None
        if result.alternates and result.segments:
            consensus = await transcriber._consensus(result.segments, result.alternates)
            if consensus.changed:
                result.text = render_text_public(result.segments)
    finally:
        Path(tmp.name).unlink(missing_ok=True)
    if response_format == "text":
        return Response(result.text, media_type="text/plain")
    if response_format == "json":
        return {"text": result.text}
    body = {
        "task": "transcribe",
        "language": result.language,
        "duration": result.duration,
        "text": result.text,
        "segments": [
            {"id": i, "start": s.start, "end": s.end, "text": s.text, **({"speaker": s.speaker} if s.speaker else {})}
            for i, s in enumerate(result.segments)
        ],
        "stats": result.stats,
    }
    if consensus is not None:
        body["consensus"] = consensus.as_dict()
    return body


def render_text_public(segments) -> str:
    from .engines import render_text

    return render_text(segments, fallback=" ".join(s.text for s in segments if s.text))


@app.post("/api/v1/audio/transcriptions", dependencies=[Depends(require_auth)])
@app.post("/v1/audio/transcriptions", dependencies=[Depends(require_auth)])
async def transcribe_audio(
    file: UploadFile,
    model: str = Form("whisper-1", max_length=200),
    language: str | None = Form(None, max_length=16),
    prompt: str | None = Form(None, max_length=4000),
    response_format: str = Form("json", max_length=32),
):
    return await _transcribe_upload(file, language, prompt, response_format)


@app.delete("/api/v1/recordings/{rec_id}", dependencies=[Depends(require_auth)])
async def delete_recording(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    for key in ("audio_path", "transcript_path"):
        if rec.get(key):
            Path(rec[key]).unlink(missing_ok=True)
    store.delete(rec_id)
    log.info("deleted recording %s", rec_id)
    return Response(status_code=204)


# ── AI routing ───────────────────────────────────────────────────────────────


class RouteBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=4000)
    action_type: Literal["webhook", "markdown", "none"]
    action_config: dict = Field(default_factory=dict)
    enabled: bool = True


def _validated_action_config(action_type: str, config: dict) -> str:
    """Validate the per-action config shape; return it as canonical JSON."""
    def bad(msg: str):
        raise HTTPException(status_code=400, detail=f"invalid action_config: {msg}")

    if action_type == "webhook":
        url = config.get("url")
        if not isinstance(url, str) or not url.lower().startswith(("http://", "https://")):
            bad("webhook requires a 'url' starting with http:// or https://")
        if len(url) > 2048:
            bad("url too long")
        auth = config.get("auth_header")
        if auth is not None and (not isinstance(auth, str) or ":" not in auth or len(auth) > 512):
            bad("auth_header must be a 'Name: value' string")
        out = {"url": url}
        if auth:
            out["auth_header"] = auth
        return json.dumps(out)
    if action_type == "markdown":
        folder = config.get("folder")
        if not isinstance(folder, str) or not folder or len(folder) > 128:
            bad("markdown requires a 'folder' string (1-128 chars)")
        if err := folder_error(folder):
            bad(err)
        return json.dumps({"folder": folder})
    # "none"
    if config:
        bad("'none' routes take no action_config")
    return json.dumps({})


def _route_public(route: dict) -> dict:
    route = dict(route)
    route["action_config"] = json.loads(route["action_config"] or "{}")
    route["enabled"] = bool(route["enabled"])
    return route


# The runner reports 'queued' again when a job actually starts, so silence is
# measured from the last report. The worst honest silence is a job waiting
# behind a full runner queue: bundled defaults are 16 slots x 600 s = 160 min,
# so six hours of silence means the consumer is gone, not busy.
QUEUED_RESULT_TTL_S = 6 * 60 * 60


def _delivery_public(delivery: dict) -> dict:
    delivery = dict(delivery)
    delivery.pop("result_token_hash", None)
    # The action snapshot can hold a webhook auth header; readers only need the type.
    delivery.pop("action_config", None)
    # The stored payload holds the whole transcript and the result capability;
    # readers only need to know it exists. Both the app and the dashboard
    # poll this while a delivery is working, so keep the response small.
    raw = delivery.pop("payload", None) or ""
    delivery["payload_bytes"] = len(raw)
    # A consumer that never reports (no callback support) must not look like
    # it is working forever: after the TTL the outcome is simply unknown, and
    # the retry endpoint accepts it (see retry_delivery).
    if delivery.get("result_status") == "queued" and delivery.get("result_at"):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(delivery["result_at"].replace("Z", "+00:00"))).total_seconds()
        except ValueError:
            age = 0
        if age > QUEUED_RESULT_TTL_S:
            delivery["result_status"] = "unknown"
            delivery["result_summary"] = "No result was reported"
    return delivery


def _run_public(run: dict) -> dict:
    run = dict(run)
    run["decision"] = json.loads(run["decision"]) if run.get("decision") else None
    if "deliveries" in run:
        run["deliveries"] = [_delivery_public(d) for d in run["deliveries"]]
    return run


@app.get("/api/v1/routes", dependencies=[Depends(require_auth)])
async def list_routes():
    return {"routes": [_route_public(r) for r in store.list_routes()]}


@app.post("/api/v1/routes", dependencies=[Depends(require_auth)])
async def create_route(body: RouteBody):
    config_json = _validated_action_config(body.action_type, body.action_config)
    if store.get_route_by_name(body.name):
        raise HTTPException(status_code=409, detail=f"route named {body.name!r} already exists")
    now = utcnow_iso()
    route_id = store.insert_route(
        name=body.name,
        description=body.description,
        action_type=body.action_type,
        action_config=config_json,
        enabled=int(body.enabled),
        created_at=now,
        updated_at=now,
    )
    return JSONResponse(_route_public(store.get_route(route_id)), status_code=201)


@app.put("/api/v1/routes/{route_id}", dependencies=[Depends(require_auth)])
async def update_route(route_id: str, body: RouteBody):
    if not store.get_route(route_id):
        raise HTTPException(status_code=404, detail="route not found")
    config_json = _validated_action_config(body.action_type, body.action_config)
    existing = store.get_route_by_name(body.name)
    if existing and existing["id"] != route_id:
        raise HTTPException(status_code=409, detail=f"route named {body.name!r} already exists")
    store.update_route(
        route_id,
        name=body.name,
        description=body.description,
        action_type=body.action_type,
        action_config=config_json,
        enabled=int(body.enabled),
        updated_at=utcnow_iso(),
    )
    return _route_public(store.get_route(route_id))


@app.delete("/api/v1/routes/{route_id}", dependencies=[Depends(require_auth)])
async def delete_route(route_id: str):
    if not store.get_route(route_id):
        raise HTTPException(status_code=404, detail="route not found")
    store.delete_route(route_id)
    return Response(status_code=204)


@app.get("/api/v1/router/status", dependencies=[Depends(require_auth)])
async def router_status():
    return {
        "enabled": settings.router_enabled,
        "configured": router_engine.configured,
        "model": settings.router_model,
    }


@app.get("/api/v1/routing/log", dependencies=[Depends(require_auth)])
async def routing_log(limit: int = Query(50, ge=1, le=200)):
    runs = []
    recs: dict[str, dict | None] = {}
    for run in store.list_router_runs(limit=limit):
        run["deliveries"] = store.deliveries_for_run(run["id"])
        rid = run.get("recording_id")
        if rid not in recs:
            recs[rid] = store.get(rid) if rid else None
        rec = recs[rid]
        # Enough for the activity log to name the recording (the id alone is
        # unreadable, especially on a phone). None when the recording was deleted.
        run["recording"] = {
            "id": rec["id"], "title": rec.get("title"), "filename": rec["filename"],
            "started_at": rec["started_at"],
        } if rec else None
        run["recording_title"] = rec.get("title") if rec else None
        run["recording_deleted"] = rec is None
        run["recorded_at"] = (rec.get("started_at") or rec.get("uploaded_at")) if rec else None
        runs.append(_run_public(run))
    return {"runs": runs}


@app.get("/api/v1/recordings/{rec_id}/routing", dependencies=[Depends(require_auth)])
async def recording_routing(rec_id: str):
    if not store.get(rec_id):
        raise HTTPException(status_code=404, detail="Recording not found.")
    runs = []
    for run in store.router_runs_for_recording(rec_id):
        run["deliveries"] = store.deliveries_for_run(run["id"])
        runs.append(_run_public(run))
    return {
        "runs": runs,
        "deliveries": [_delivery_public(d) for d in store.deliveries_for_recording(rec_id)],
    }


class RerunBody(BaseModel):
    model_config = {"extra": "ignore"}

    # What the user wants done this time ("file this as a work meeting", "just
    # summarize, don't file"). Trusted: typed by the user in the app, not
    # spoken in the recording. Passed to the router LLM and to the actions.
    instructions: str | None = Field(default=None, max_length=2000)


@app.post("/api/v1/recordings/{rec_id}/route", dependencies=[Depends(require_auth)])
async def rerun_router(
    rec_id: str, request: Request, response: Response, body: RerunBody | None = Body(default=None)
):
    """Run the router again. Routing is synchronous and its deliveries have side
    effects (notes written, agents started), so a client that lost the response
    must not create a second run by re-sending: with an Idempotency-Key header
    the same key returns the run it already produced (also while that run is
    still in progress, by awaiting it)."""
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    if not rec.get("transcript_text"):
        raise HTTPException(status_code=409, detail="This recording has no transcript yet.")
    instructions = (body.instructions or "").strip() or None if body else None
    key = request.headers.get("Idempotency-Key")
    if key is None:
        return _run_public(await router_engine.route_recording(rec, instructions=instructions))
    if not _IDEMPOTENCY_KEY_RE.fullmatch(key):
        raise HTTPException(status_code=400, detail="Idempotency-Key must be 8-128 chars of [A-Za-z0-9_-]")
    slot = (rec_id, key)
    fut = _route_inflight.get(slot)
    if fut is not None:
        # A concurrent duplicate: wait for the first request's run instead of starting
        # another. Checked before the table: the run row exists from the moment the first
        # request inserts it, while its deliveries may still be executing.
        run = await asyncio.shield(fut)
        response.headers["Idempotent-Replayed"] = "true"
        return _run_public(dict(run))
    existing = store.router_run_by_key(rec_id, key)
    if existing:
        existing["deliveries"] = store.deliveries_for_run(existing["id"])
        response.headers["Idempotent-Replayed"] = "true"
        return _run_public(existing)
    fut = asyncio.get_running_loop().create_future()
    _route_inflight[slot] = fut
    try:
        run = await router_engine.route_recording(rec, idempotency_key=key, instructions=instructions)
        fut.set_result(run)
    except BaseException as exc:  # let concurrent waiters fail the same way
        fut.set_exception(exc)
        raise
    finally:
        _route_inflight.pop(slot, None)
    return _run_public(run)


_IDEMPOTENCY_KEY_RE = re.compile(r"[A-Za-z0-9_-]{8,128}")
_route_inflight: dict[tuple[str, str], "asyncio.Future"] = {}


@app.post("/api/v1/recordings/{rec_id}/route/preview", dependencies=[Depends(require_auth)])
async def preview_router(rec_id: str, body: RerunBody | None = Body(default=None)):
    """Dry run: what would automations do with this recording? Runs the routing
    decision only. Nothing is delivered, no run is recorded, no side effects.
    The contract's route_id/route_name/reason describe the first match;
    `matches` lists every route the model picked."""
    if not settings.router_enabled:
        raise HTTPException(status_code=409, detail="Automations are turned off on the server")
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recording not found.")
    if not rec.get("transcript_text"):
        raise HTTPException(status_code=409, detail="This recording has no transcript yet.")
    if not router_engine.configured:
        raise HTTPException(status_code=409, detail="Automations are not set up on the server.")
    instructions = (body.instructions or "").strip() or None if body else None
    routes = store.list_routes(enabled_only=True)
    matched: list[dict] = []
    if routes:
        matched, error = await router_engine.decide(rec, routes, instructions)
        if error:
            log.warning("automations preview failed for %s: %s", rec_id, error)
            raise HTTPException(status_code=502, detail="Couldn't run automations. Try again.")
    by_name = {r["name"]: r for r in routes}
    matches = [{"route_id": by_name[m["name"]]["id"], "route_name": m["name"], "reason": m.get("reason")}
               for m in matched if m["name"] in by_name]
    first = matches[0] if matches else {"route_id": None, "route_name": None, "reason": None}
    return {**first, "model": settings.router_model, "matches": matches}


class DeliveryResultBody(BaseModel):
    model_config = {"extra": "ignore"}
    status: Literal["queued", "done", "failed"]
    summary: str | None = Field(default=None, max_length=2000)
    # Callers using a general bridge token (dashboards, tools) should say which
    # attempt they observed; a result token is already bound to its attempt.
    attempt: int | None = Field(default=None, ge=1, le=10**6)


@app.post("/api/v1/deliveries/{delivery_id}/result")
async def report_delivery_result(delivery_id: str, body: DeliveryResultBody, request: Request):
    """The agent runner (or any webhook consumer) reports what it did with a
    delivery. Authentication is the per-attempt result token from the payload
    (so consumers never hold a general bridge token); a bridge token works too.
    'done' is terminal: it also clears a failed hand-off (e.g. the 202 was lost
    in transit) so completed work cannot be retried by accident; 'failed' marks
    the delivery failed so it can be retried."""
    auth = request.headers.get("Authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    delivery = store.get_delivery(delivery_id)
    presented = hashlib.sha256(token.encode()).hexdigest()
    if not delivery or not (
        (delivery.get("result_token_hash") and hmac.compare_digest(presented, delivery["result_token_hash"]))
        or _token_ok(request)
    ):
        # Same answer for unknown id and wrong token: no oracle for delivery ids.
        raise HTTPException(status_code=404, detail="delivery not found")
    summary = " ".join((body.summary or "").split())[:2000] or None
    if delivery.get("result_status") in ("done", "failed"):
        # Terminal for this attempt: a duplicate of the same outcome is
        # idempotent, anything else (including a late heartbeat) is refused so
        # an out-of-order callback cannot reopen finished work or hide a failure.
        # A retry mints a new token, so the next attempt reports afresh.
        if body.status == delivery["result_status"]:
            return _result_view(delivery)
        raise HTTPException(status_code=409, detail=f"result already reported as {delivery['result_status']}")
    fields = {"result_status": body.status, "result_summary": summary, "result_at": utcnow_iso()}
    if body.status == "failed":
        fields.update(status="failed", last_error=(summary or "agent reported failure")[:1000])
    else:
        # 'done' and 'queued' both prove the consumer has the job: the hand-off
        # is fine even if its 202 was lost, so nothing here may be retried.
        fields.update(status="ok", last_error=None)
    # One conditional UPDATE decides concurrent callbacks: the row must still
    # be open (not terminal) and, for a result-token caller, the token must
    # still be the current attempt's.
    used_result_token = bool(delivery.get("result_token_hash")) and hmac.compare_digest(presented, delivery["result_token_hash"])
    # A result token identifies its attempt by itself; a bridge-token caller
    # must say which attempt it observed so a retry in flight cannot inherit
    # a stale outcome.
    if used_result_token:
        expected_attempt = delivery.get("attempts")
    elif body.attempt is not None:
        expected_attempt = body.attempt
    else:
        raise HTTPException(status_code=422, detail="attempt is required when reporting with a bridge token")
    changed = store.apply_delivery_result(
        delivery_id, delivery["result_token_hash"] if used_result_token else None, expected_attempt, fields
    )
    if not changed:
        current = store.get_delivery(delivery_id) or delivery
        if current.get("result_status") in ("done", "failed"):
            if body.status == current["result_status"]:
                return _result_view(current)
            raise HTTPException(status_code=409, detail=f"result already reported as {current['result_status']}")
        raise HTTPException(status_code=401, detail="result token no longer valid for this delivery")
    return _result_view(store.get_delivery(delivery_id))


def _result_view(delivery: dict) -> dict:
    """What a result-token holder gets back: the outcome fields only. The
    capability is scoped to reporting, so it must not read the delivery's
    action configuration (webhook auth headers) or anything else."""
    return {k: delivery.get(k) for k in ("id", "status", "result_status", "result_summary", "result_at")}


@app.post("/api/v1/deliveries/{delivery_id}/retry", dependencies=[Depends(require_auth)])
async def retry_delivery(delivery_id: str):
    delivery = store.get_delivery(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="delivery not found")
    stale = _delivery_public(delivery).get("result_status") == "unknown"
    if delivery["status"] != "failed" and not stale:
        raise HTTPException(
            status_code=409,
            detail=f"only failed deliveries (or hand-offs that never reported a result) can be retried (status: {delivery['status']})",
        )
    # The cutoff travels into the atomic claim so a heartbeat racing this
    # request cannot let a live job be duplicated.
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=QUEUED_RESULT_TTL_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
    retried = await router_engine.retry_delivery(delivery, stale_before=cutoff if stale else None)
    if retried is None:  # lost a race with a concurrent retry
        raise HTTPException(status_code=409, detail="delivery is already being retried")
    return _delivery_public(retried)


# ── Android app distribution ─────────────────────────────────────────────────
# One hosted release at a time (the latest); prior APK files stay on disk.
# The manifest is a plain JSON file next to the APKs, replaced atomically.


class ApkMetadata(BaseModel):
    model_config = {"extra": "ignore"}

    version_code: int = Field(gt=0, le=2**31 - 1)
    version_name: str = Field(min_length=1, max_length=50)
    min_sdk: int | None = Field(default=None, ge=1, le=1000)
    notes: str | None = Field(default=None, max_length=2000)


def _apk_manifest_path() -> Path:
    return settings.apk_dir / "latest.json"


def _read_apk_manifest() -> dict | None:
    try:
        with open(_apk_manifest_path()) as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_apk_manifest(manifest: dict) -> None:
    """Atomic replace (tmp + rename) so readers never see a partial manifest."""
    path = _apk_manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".json.part")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(manifest, fh, indent=2)
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _install_apk_file(
    src: Path, original_name: str, meta: ApkMetadata,
    sha256: str | None = None, size: int | None = None,
) -> dict:
    """Validate `src`, move it into place as the hosted APK, write the manifest.

    `src` must live on the apk-dir filesystem (it is renamed, not copied).
    Raises ValueError on validation failures; caller maps to HTTP as needed.
    """
    with open(src, "rb") as fh:
        if fh.read(2) != b"PK":
            raise ValueError("not an APK (file does not start with ZIP magic bytes)")
    if sha256 is None or size is None:
        hasher = hashlib.sha256()
        size = 0
        with open(src, "rb") as fh:
            while chunk := fh.read(1024 * 1024):
                hasher.update(chunk)
                size += len(chunk)
        sha256 = hasher.hexdigest()
    if size == 0:
        raise ValueError("empty file")
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name or "app.apk")[:120]
    if not safe_name.lower().endswith(".apk"):
        safe_name += ".apk"
    settings.apk_dir.mkdir(parents=True, exist_ok=True)
    apk_path = settings.apk_dir / f"{meta.version_code}-{safe_name}"
    os.replace(src, apk_path)
    manifest = {
        "version_code": meta.version_code,
        "version_name": meta.version_name,
        "filename": apk_path.name,
        "sha256": sha256,
        "size_bytes": size,
        "uploaded_at": utcnow_iso(),
        "min_sdk": meta.min_sdk,
        "notes": meta.notes,
    }
    _write_apk_manifest(manifest)
    return manifest


def install_bundled_apk() -> None:
    """Auto-publish an APK baked into the image (PB_BUNDLED_APK_DIR) at startup.

    Expects exactly one *.apk plus a manifest.json ({version_code, version_name,
    notes?}). Installs it as the hosted APK when nothing is hosted yet or the
    hosted version_code is lower. Never raises — a bad bundle logs a warning.
    """
    d = settings.bundled_apk_dir
    tmp_name: str | None = None
    try:
        if not d.is_dir():
            return
        apks = sorted(d.glob("*.apk"))
        meta_path = d / "manifest.json"
        if not apks and not meta_path.exists():
            return
        if len(apks) != 1 or not meta_path.exists():
            log.warning(
                "bundled apk: %s must contain exactly one *.apk plus manifest.json "
                "(found %d apks, manifest %s) — skipping",
                d, len(apks), "present" if meta_path.exists() else "missing",
            )
            return
        meta = ApkMetadata.model_validate_json(meta_path.read_text())
        current = _read_apk_manifest()
        if current and current["version_code"] >= meta.version_code:
            log.info(
                "bundled apk (code %s) is not newer than hosted (code %s) — keeping hosted",
                meta.version_code, current["version_code"],
            )
            return
        settings.apk_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=settings.apk_dir, suffix=".part")
        os.close(fd)
        shutil.copyfile(apks[0], tmp_name)
        manifest = _install_apk_file(Path(tmp_name), apks[0].name, meta)
        log.info(
            "bundled apk installed: %s (code %s, %s)",
            manifest["version_name"], manifest["version_code"], manifest["filename"],
        )
    except Exception as exc:  # startup must survive any bundle problem
        log.warning("bundled apk install failed: %s", exc)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)


@app.post("/api/v1/apk", dependencies=[Depends(require_auth)])
async def upload_apk(file: UploadFile, metadata: str = Form(..., max_length=4096)):
    try:
        meta = ApkMetadata.model_validate_json(metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid metadata: {exc}")
    current = _read_apk_manifest()
    if current and meta.version_code < current["version_code"]:
        raise HTTPException(
            status_code=409,
            detail=f"version_code {meta.version_code} is lower than the hosted "
                   f"{current['version_code']} — DELETE the hosted release first to roll back",
        )

    # Stream to a temp file in the target filesystem while hashing, then rename.
    max_bytes = settings.apk_max_upload_mb * 1024 * 1024
    hasher = hashlib.sha256()
    size = 0
    settings.apk_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(dir=settings.apk_dir, suffix=".part", delete=False)
    try:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                raise HTTPException(status_code=413, detail=f"file exceeds {settings.apk_max_upload_mb} MB")
            hasher.update(chunk)
            tmp.write(chunk)
        tmp.close()
        if size == 0:
            raise HTTPException(status_code=400, detail="empty file")
        try:
            manifest = _install_apk_file(
                Path(tmp.name), file.filename or "app.apk", meta,
                sha256=hasher.hexdigest(), size=size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    finally:
        # Covers error paths; no-op after the installer's os.replace.
        if not tmp.closed:
            tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
    log.info("hosted apk updated: %s (code %s, %.1f MB)",
             manifest["version_name"], manifest["version_code"], size / 1e6)
    return JSONResponse(manifest, status_code=201)


@app.get("/api/v1/apk/info", dependencies=[Depends(require_auth)])
async def apk_info():
    manifest = _read_apk_manifest()
    if not manifest:
        raise HTTPException(status_code=404, detail="no APK hosted")
    return manifest


@app.get("/api/v1/apk/file", dependencies=[Depends(require_auth)])
async def apk_file():
    manifest = _read_apk_manifest()
    if not manifest:
        raise HTTPException(status_code=404, detail="no APK hosted")
    path = settings.apk_dir / manifest["filename"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="hosted APK file is missing on disk")
    return FileResponse(
        path,
        media_type="application/vnd.android.package-archive",
        filename=manifest["filename"],
    )


@app.delete("/api/v1/apk", dependencies=[Depends(require_auth)])
async def delete_apk():
    manifest = _read_apk_manifest()
    if not manifest:
        raise HTTPException(status_code=404, detail="no APK hosted")
    (settings.apk_dir / manifest["filename"]).unlink(missing_ok=True)
    _apk_manifest_path().unlink(missing_ok=True)
    log.info("unhosted apk %s (code %s)", manifest["filename"], manifest["version_code"])
    return Response(status_code=204)


# ── Web dashboard ────────────────────────────────────────────────────────────
# The React app (web/) builds into app/static: index.html plus hashed assets under
# app/static/assets and the fonts under app/static/fonts. The Docker image builds it;
# a dev checkout may not have run `npm run build` yet, so both routes tolerate its absence.
STATIC_DIR = Path(__file__).parent / "static"

if STATIC_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
else:
    log.warning("web app not built: %s is missing (run `npm run build` in web/)", STATIC_DIR)

_UNBUILT_HTML = (
    "<!doctype html><meta charset='utf-8'><title>Plaud Bridge</title>"
    "<body style='font-family:system-ui;padding:32px;max-width:520px'>"
    "<h1>Plaud Bridge</h1><p>The web app has not been built on this server yet. "
    "Run <code>npm ci &amp;&amp; npm run build</code> in <code>web/</code>, or rebuild the Docker image.</p>"
)


@app.get("/", include_in_schema=False)
async def dashboard():
    index = STATIC_DIR / "index.html"
    if not index.is_file():
        return Response(_UNBUILT_HTML, media_type="text/html", status_code=503)
    # The entry document must never be cached: its asset names change with every build.
    return FileResponse(index, media_type="text/html", headers={"Cache-Control": "no-cache"})
