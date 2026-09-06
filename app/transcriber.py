"""Background transcription worker.

Polls the store for pending recordings, sends the audio to a configurable
OpenAI-compatible endpoint (POST {base}/audio/transcriptions), writes the
transcript as JSON (+ optional markdown export), and fires an optional
webhook so downstream automation can react to new transcripts.
"""

import asyncio
import json
import logging
from pathlib import Path

import httpx

from .config import Settings
from .db import Store, utcnow_iso

log = logging.getLogger("plaud-bridge.transcriber")

POLL_INTERVAL_S = 5


class Transcriber:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store
        self.wake = asyncio.Event()
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while True:
            try:
                rec = self.store.next_pending(self.settings.transcribe_max_attempts)
                if rec is None:
                    self.wake.clear()
                    try:
                        await asyncio.wait_for(self.wake.wait(), timeout=POLL_INTERVAL_S * 12)
                    except TimeoutError:
                        pass
                    continue
                await self._process(rec)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("worker loop error")
                await asyncio.sleep(POLL_INTERVAL_S)

    async def _process(self, rec: dict) -> None:
        if not self.settings.transcribe_enabled or not self.settings.transcribe_base_url:
            self.store.update(rec["id"], status="stored")
            return
        rec_id = rec["id"]
        self.store.update(rec_id, status="transcribing", attempts=rec["attempts"] + 1)
        log.info("transcribing %s (%s)", rec_id, rec["filename"])
        try:
            result = await self._call_endpoint(Path(rec["audio_path"]))
        except Exception as exc:
            log.warning("transcription failed for %s: %s", rec_id, exc)
            self.store.update(rec_id, status="failed", error=str(exc)[:1000])
            return

        transcript_path = Path(rec["audio_path"]).with_suffix(".transcript.json")
        transcript = {
            "recording_id": rec_id,
            "device_sn": rec["device_sn"],
            "session_id": rec["session_id"],
            "filename": rec["filename"],
            "started_at": rec["started_at"],
            "duration_s": result.get("duration") or rec["duration_s"],
            "language": result.get("language"),
            "model": self.settings.transcribe_model,
            "transcribed_at": utcnow_iso(),
            "text": result.get("text", ""),
            "segments": [
                {"start": s.get("start"), "end": s.get("end"), "text": s.get("text", "").strip()}
                for s in result.get("segments") or []
            ],
        }
        transcript_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2))
        self.store.update(rec_id, status="done", transcript_path=str(transcript_path), error=None)
        log.info("transcribed %s (%d chars)", rec_id, len(transcript["text"]))

        self._export_markdown(rec, transcript)
        await self._fire_webhook(rec, transcript)

    async def _call_endpoint(self, audio_path: Path) -> dict:
        base = self.settings.transcribe_base_url.rstrip("/")
        url = f"{base}/audio/transcriptions"
        headers = {}
        if self.settings.transcribe_api_key:
            headers["Authorization"] = f"Bearer {self.settings.transcribe_api_key}"

        async with httpx.AsyncClient(timeout=self.settings.transcribe_timeout_s) as client:
            for response_format in ("verbose_json", "json"):
                data = {"model": self.settings.transcribe_model, "response_format": response_format}
                if self.settings.transcribe_language:
                    data["language"] = self.settings.transcribe_language
                with audio_path.open("rb") as fh:
                    resp = await client.post(
                        url, headers=headers, data=data,
                        files={"file": (audio_path.name, fh, "audio/mpeg")},
                    )
                if resp.status_code == 200:
                    return resp.json()
                # Some servers reject verbose_json; retry once with plain json.
                if response_format == "verbose_json" and resp.status_code in (400, 422):
                    continue
                raise RuntimeError(f"endpoint returned {resp.status_code}: {resp.text[:300]}")
        raise RuntimeError("unreachable")

    def _export_markdown(self, rec: dict, transcript: dict) -> None:
        out_dir = self.settings.markdown_export_dir
        if not out_dir:
            return
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            stamp = (rec["started_at"] or rec["uploaded_at"]).replace(":", "-")
            md_path = out_dir / f"plaud-{stamp}-{rec['id'][:8]}.md"
            lines = [
                "---",
                f"recording_id: {rec['id']}",
                f"device_sn: {rec['device_sn'] or ''}",
                f"session_id: {rec['session_id'] if rec['session_id'] is not None else ''}",
                f"recorded: {rec['started_at'] or ''}",
                f"uploaded: {rec['uploaded_at']}",
                f"duration_s: {transcript.get('duration_s') or ''}",
                f"language: {transcript.get('language') or ''}",
                "source: plaud-bridge",
                "---",
                "",
                transcript["text"].strip(),
                "",
            ]
            md_path.write_text("\n".join(lines))
        except Exception:
            log.exception("markdown export failed for %s", rec["id"])

    async def _fire_webhook(self, rec: dict, transcript: dict) -> None:
        url = self.settings.webhook_url
        if not url:
            return
        headers = {}
        if self.settings.webhook_auth_header:
            name, _, value = self.settings.webhook_auth_header.partition(":")
            headers[name.strip()] = value.strip()
        payload = {
            "event": "transcription.completed",
            "recording": {
                "id": rec["id"],
                "device_sn": rec["device_sn"],
                "session_id": rec["session_id"],
                "filename": rec["filename"],
                "started_at": rec["started_at"],
                "uploaded_at": rec["uploaded_at"],
                "duration_s": transcript.get("duration_s"),
            },
            "transcript": {
                "language": transcript.get("language"),
                "text": transcript["text"],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 300:
                    log.warning("webhook returned %s for %s", resp.status_code, rec["id"])
        except Exception as exc:
            log.warning("webhook failed for %s: %s", rec["id"], exc)
