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
"""

import hashlib
import hmac
import json
import logging
import re
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from .config import settings
from .db import Store, utcnow_iso
from .plaud import PlaudAuthError, PlaudClient
from .transcriber import Transcriber

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("plaud-bridge")

VERSION = "0.1.0"

store: Store | None = None
transcriber: Transcriber | None = None
plaud_client: PlaudClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, transcriber, plaud_client
    settings.recordings_dir.mkdir(parents=True, exist_ok=True)
    store = Store(settings.db_path)
    for warning in settings.validate():
        log.warning("config: %s", warning)
    if settings.plaud_client_id and settings.plaud_secret_key:
        plaud_client = PlaudClient(
            settings.plaud_api_base, settings.plaud_client_id, settings.plaud_secret_key
        )
    transcriber = Transcriber(settings, store)
    transcriber.start()
    yield
    await transcriber.stop()


app = FastAPI(title="Plaud Bridge", version=VERSION, lifespan=lifespan)


def require_auth(request: Request) -> None:
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
    if not token or not any(hmac.compare_digest(token, t) for t in settings.auth_tokens):
        raise HTTPException(status_code=401, detail="invalid or missing bearer token")


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
        raise HTTPException(status_code=502, detail=str(exc))


def _public(rec: dict) -> dict:
    rec = dict(rec)
    rec.pop("audio_path", None)
    rec.pop("transcript_path", None)
    return rec


@app.post("/api/v1/recordings", dependencies=[Depends(require_auth)])
async def upload_recording(file: UploadFile, metadata: str = Form("{}")):
    try:
        meta = json.loads(metadata)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="metadata is not valid JSON")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    hasher = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=413, detail=f"file exceeds {settings.max_upload_mb} MB")
        hasher.update(chunk)
        chunks.append(chunk)
    if size == 0:
        raise HTTPException(status_code=400, detail="empty file")
    sha256 = hasher.hexdigest()

    existing = store.find_by_sha256(sha256)
    if existing:
        return JSONResponse({"id": existing["id"], "duplicate": True}, status_code=200)

    device_sn = meta.get("device_sn")
    session_id = meta.get("session_id")
    if device_sn is not None and session_id is not None:
        existing = store.find_by_session(str(device_sn), int(session_id))
        if existing:
            return JSONResponse({"id": existing["id"], "duplicate": True}, status_code=200)

    uploaded_at = utcnow_iso()
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", file.filename or "recording.mp3")
    subdir = settings.recordings_dir / uploaded_at[:4] / uploaded_at[5:7]
    subdir.mkdir(parents=True, exist_ok=True)
    audio_path = subdir / f"{sha256[:16]}_{safe_name}"
    with audio_path.open("wb") as fh:
        for chunk in chunks:
            fh.write(chunk)

    rec_id = store.insert_recording(
        device_sn=str(device_sn) if device_sn is not None else None,
        session_id=int(session_id) if session_id is not None else None,
        filename=safe_name,
        sha256=sha256,
        size_bytes=size,
        duration_s=meta.get("duration_s"),
        started_at=meta.get("started_at"),
        source=meta.get("source"),
        uploaded_at=uploaded_at,
        audio_path=str(audio_path),
        status="pending",
    )
    transcriber.wake.set()
    log.info("stored recording %s (%s, %.1f MB)", rec_id, safe_name, size / 1e6)
    return JSONResponse({"id": rec_id, "duplicate": False}, status_code=201)


@app.get("/api/v1/recordings", dependencies=[Depends(require_auth)])
async def list_recordings(limit: int = 100, offset: int = 0, status: str | None = None):
    return {"recordings": [_public(r) for r in store.list(limit=min(limit, 500), offset=offset, status=status)]}


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
    store.update(rec_id, status="pending", attempts=0, error=None)
    transcriber.wake.set()
    return {"id": rec_id, "status": "pending"}
