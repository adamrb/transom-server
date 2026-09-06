"""Background transcription worker.

Polls the store for pending recordings, sends the audio to a configurable
OpenAI-compatible endpoint (POST {base}/audio/transcriptions), writes the
transcript as JSON (+ optional markdown export), and fires an optional
webhook so downstream automation can react to new transcripts.
"""

import asyncio
import json
import logging
import re
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
        # Recover rows left mid-flight by a previous shutdown/crash.
        for rec in self.store.list(limit=500, status="transcribing"):
            self.store.update(rec["id"], status="pending")
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
                # Clear before querying so a wake fired mid-query isn't lost.
                self.wake.clear()
                rec = self.store.next_pending(self.settings.transcribe_max_attempts)
                if rec is None:
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
        rec_id = rec["id"]
        try:
            await self._process_inner(rec)
        except asyncio.CancelledError:
            # Shutdown mid-transcription: hand the row back to the queue.
            self.store.update(rec_id, status="pending")
            raise
        except Exception as exc:
            log.exception("processing failed for %s", rec_id)
            self.store.update(rec_id, status="failed", error=str(exc)[:1000])

    async def _process_inner(self, rec: dict) -> None:
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
        summary = await self._summarize(transcript["text"])
        if summary:
            transcript["summary"] = summary
        if self.store.get(rec_id) is None:
            # Deleted from the dashboard while we were transcribing; drop the result.
            log.info("recording %s deleted mid-transcription, discarding result", rec_id)
            return
        tmp_path = transcript_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(transcript, ensure_ascii=False, indent=2))
        tmp_path.replace(transcript_path)
        self.store.update(
            rec_id,
            status="done",
            transcript_path=str(transcript_path),
            transcript_text=transcript["text"],
            summary=summary,
            error=None,
        )
        log.info("transcribed %s (%d chars%s)", rec_id, len(transcript["text"]),
                 ", summarized" if summary else "")

        self._export_markdown(rec, transcript)
        await self._fire_webhook(rec, transcript)

    async def _summarize(self, text: str) -> str | None:
        s = self.settings
        if not (s.summary_enabled and s.summary_base_url and s.summary_model):
            return None
        if not text.strip():
            return None
        headers = {}
        if s.summary_api_key:
            headers["Authorization"] = f"Bearer {s.summary_api_key}"
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(
                    f"{s.summary_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json={
                        "model": s.summary_model,
                        "messages": [
                            {"role": "system", "content": s.summary_prompt},
                            {"role": "user", "content": text[: s.summary_max_chars]},
                        ],
                    },
                )
                if resp.status_code != 200:
                    log.warning("summary endpoint returned %s: %s", resp.status_code, resp.text[:200])
                    return None
                return resp.json()["choices"][0]["message"]["content"].strip() or None
        except Exception as exc:
            log.warning("summarization failed: %s", exc)
            return None

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
            stamp = re.sub(r"[^0-9TZ-]", "-", (rec["started_at"] or rec["uploaded_at"]))[:24]
            md_path = out_dir / f"plaud-{stamp}-{rec['id'][:8]}.md"

            def yq(value) -> str:  # YAML-safe scalar via JSON quoting
                return json.dumps("" if value is None else str(value), ensure_ascii=False)

            lines = [
                "---",
                f"recording_id: {yq(rec['id'])}",
                f"device_sn: {yq(rec['device_sn'])}",
                f"session_id: {yq(rec['session_id'])}",
                f"recorded: {yq(rec['started_at'])}",
                f"uploaded: {yq(rec['uploaded_at'])}",
                f"duration_s: {yq(transcript.get('duration_s'))}",
                f"language: {yq(transcript.get('language'))}",
                "source: plaud-bridge",
                "---",
                "",
            ]
            if transcript.get("summary"):
                lines += ["## Summary", "", transcript["summary"], "", "## Transcript", ""]
            lines += [transcript["text"].strip(), ""]
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
                "summary": transcript.get("summary"),
            },
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code >= 300:
                    log.warning("webhook returned %s for %s", resp.status_code, rec["id"])
        except Exception as exc:
            log.warning("webhook failed for %s: %s", rec["id"], exc)
