"""Plaud Bridge server — self-hosted sync target for the Plaud Bridge Android app.

Endpoints (all under /api/v1, Bearer-token auth except /health):
  GET  /health                          liveness check
  GET  /auth/check                      validates a client token
  POST /plaud/user-token                mint a Plaud SDK user token
  POST /recordings                      multipart upload from the app
  GET  /recordings                      list recordings
  GET  /recordings/lookup               find by device_sn + session_id
  GET  /recordings/{id}                 metadata
  GET  /recordings/{id}/audio           audio file
  GET  /recordings/{id}/transcript      transcript JSON (409 while pending)
  POST /recordings/{id}/retranscribe    reset a recording for the worker
  GET  /routes                          list AI routing routes
  POST /routes                          create a route
  PUT  /routes/{id}                     update a route
  DELETE /routes/{id}                   delete a route
  GET  /router/status                   router enabled/configured/model
  GET  /routing/log                     recent router runs with deliveries
  GET  /recordings/{id}/routing         runs + deliveries for one recording
  POST /recordings/{id}/route           rerun the router for a recording
  POST /deliveries/{id}/retry           re-execute a delivery's action
"""

import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from .config import settings
from .db import Store, utcnow_iso
from .plaud import PlaudAuthError, PlaudClient
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
    router_engine = Router(settings, store)
    transcriber = Transcriber(settings, store, router=router_engine)
    transcriber.start()
    yield
    await transcriber.stop()


app = FastAPI(title="Plaud Bridge", version=VERSION, lifespan=lifespan)

PUBLIC_PATHS = {"/api/v1/health"}


def _token_ok(request: Request) -> bool:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        return False
    return any(hmac.compare_digest(token, t) for t in settings.auth_tokens)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Reject unauthenticated API requests before any body parsing happens."""
    path = request.url.path
    if path.startswith("/api/") and path not in PUBLIC_PATHS and not _token_ok(request):
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


def _public(rec: dict) -> dict:
    rec = dict(rec)
    rec.pop("audio_path", None)
    rec.pop("transcript_path", None)
    text = rec.pop("transcript_text", None)
    rec["has_transcript"] = rec["status"] == "done"
    rec["text_preview"] = (text or "")[:240] or None
    return rec


class UploadMetadata(BaseModel):
    model_config = {"extra": "ignore"}

    session_id: int | None = Field(default=None, ge=0, le=2**62)
    device_sn: str | None = Field(default=None, max_length=64)
    started_at: str | None = Field(default=None, max_length=40)
    duration_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    source: str | None = Field(default=None, max_length=64)


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


@app.get("/api/v1/recordings", dependencies=[Depends(require_auth)])
async def list_recordings(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10**9),
    status: str | None = Query(None, max_length=20),
    q: str | None = Query(None, max_length=200),
):
    return {
        "recordings": [
            _public(r) for r in store.list(limit=limit, offset=offset, status=status, query=q)
        ]
    }


@app.get("/api/v1/stats", dependencies=[Depends(require_auth)])
async def stats():
    return store.stats()


@app.get("/api/v1/recordings/lookup", dependencies=[Depends(require_auth)])
async def lookup_recording(device_sn: str, session_id: int):
    rec = store.find_by_session(device_sn, session_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    return _public(rec)


@app.get("/api/v1/recordings/{rec_id}", dependencies=[Depends(require_auth)])
async def get_recording(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    return _public(rec)


@app.get("/api/v1/recordings/{rec_id}/audio", dependencies=[Depends(require_auth)])
async def get_audio(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(rec["audio_path"], media_type="audio/mpeg", filename=rec["filename"])


@app.get("/api/v1/recordings/{rec_id}/transcript", dependencies=[Depends(require_auth)])
async def get_transcript(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    if rec["status"] != "done" or not rec["transcript_path"]:
        raise HTTPException(status_code=409, detail=f"transcript not ready (status: {rec['status']})")
    with open(rec["transcript_path"]) as fh:
        return json.load(fh)


@app.post("/api/v1/recordings/{rec_id}/retranscribe", dependencies=[Depends(require_auth)])
async def retranscribe(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    if rec.get("transcript_path"):
        Path(rec["transcript_path"]).unlink(missing_ok=True)
    store.update(
        rec_id, status="pending", attempts=0, error=None,
        transcript_text=None, summary=None, transcript_path=None,
    )
    transcriber.wake.set()
    return {"id": rec_id, "status": "pending"}


@app.delete("/api/v1/recordings/{rec_id}", dependencies=[Depends(require_auth)])
async def delete_recording(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
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


def _delivery_public(delivery: dict) -> dict:
    delivery = dict(delivery)
    delivery["payload"] = json.loads(delivery["payload"] or "{}")
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
    for run in store.list_router_runs(limit=limit):
        run["deliveries"] = store.deliveries_for_recording(run["recording_id"])
        runs.append(_run_public(run))
    return {"runs": runs}


@app.get("/api/v1/recordings/{rec_id}/routing", dependencies=[Depends(require_auth)])
async def recording_routing(rec_id: str):
    if not store.get(rec_id):
        raise HTTPException(status_code=404, detail="not found")
    return {
        "runs": [_run_public(r) for r in store.router_runs_for_recording(rec_id)],
        "deliveries": [_delivery_public(d) for d in store.deliveries_for_recording(rec_id)],
    }


@app.post("/api/v1/recordings/{rec_id}/route", dependencies=[Depends(require_auth)])
async def rerun_router(rec_id: str):
    rec = store.get(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="not found")
    if not rec.get("transcript_text"):
        raise HTTPException(status_code=409, detail=f"no transcript yet (status: {rec['status']})")
    run = await router_engine.route_recording(rec)
    return _run_public(run)


@app.post("/api/v1/deliveries/{delivery_id}/retry", dependencies=[Depends(require_auth)])
async def retry_delivery(delivery_id: str):
    delivery = store.get_delivery(delivery_id)
    if not delivery:
        raise HTTPException(status_code=404, detail="delivery not found")
    return _delivery_public(await router_engine.retry_delivery(delivery))


# ── Web dashboard ────────────────────────────────────────────────────────────
STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
async def dashboard():
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")
