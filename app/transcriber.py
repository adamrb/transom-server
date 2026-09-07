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
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import Settings
from .db import Store, utcnow_iso
from .engines import EngineError, TranscriptionEngine, build_engine
from .highlights import build_highlights, highlights_for_prompt, highlights_markdown, parse_marks
from .router import Router

log = logging.getLogger("plaud-bridge.transcriber")

POLL_INTERVAL_S = 5

# The summary prompt asks the model to open with "Title: ..." on its own line.
# Models are inconsistent about decoration ("**Title:** Foo", "# Title: Foo"),
# so the match is lenient about heading marks, bold marks and case. The value
# may be empty (a bare "Title:" label) so the caller can fall back sensibly.
_TITLE_LINE_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\*\*)?\s*title\s*:\s*(.*?)\s*(?:\*\*)?\s*$", re.IGNORECASE
)
_TITLE_EDGE_CHARS = " \t*#\"'`“”‘’"
TITLE_MAX_CHARS = 120


@dataclass(frozen=True)
class Summary:
    """Result of one summarization call: both fields None when the feature is
    off or the call failed, so callers never have to special-case that."""

    title: str | None = None
    text: str | None = None


def _clean_title(raw: str) -> str | None:
    # Titles are shown in list rows, H1s and YAML frontmatter, so they must be
    # single-line plain text: drop markdown marks and quotes, collapse all
    # whitespace (including any newline), and never return an empty string.
    t = raw.replace("**", "")
    t = re.sub(r"\s+", " ", t).strip().strip(_TITLE_EDGE_CHARS).strip()
    return t[:TITLE_MAX_CHARS].strip() or None


def _split_title(text: str | None) -> tuple[str | None, str]:
    """Split an LLM summary into (title, body).

    A leading "Title: X" line is consumed: the body is what follows, with
    leading blank lines removed. Without such a line the first non-empty line
    (stripped of heading/bold marks) is used as the title and the WHOLE text
    is kept as the body, so no content is ever lost on older-style output."""
    if not text or not text.strip():
        return None, ""
    lines = text.split("\n")
    idx = next(i for i, line in enumerate(lines) if line.strip())
    m = _TITLE_LINE_RE.match(lines[idx])
    if m:
        rest = lines[idx + 1:]
        while rest and not rest[0].strip():
            rest.pop(0)
        body = "\n".join(rest).rstrip()
        title = _clean_title(m.group(1))
        if title is None and body:
            # "Title:" with nothing after it: fall back to the body's first line
            # rather than leaving the recording untitled.
            title = _clean_title(body.split("\n", 1)[0])
        return title, body
    return _clean_title(lines[idx]), text.strip()


class Transcriber:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        engine: "TranscriptionEngine | None" = None,
        router: "Router | None" = None,
    ):
        self.settings = settings
        self.store = store
        self.engine = engine if engine is not None else build_engine(settings)
        self.router = router if router is not None else Router(settings, store)
        self.wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._router_tasks: set[asyncio.Task] = set()

    def start(self) -> None:
        # Recover rows left mid-flight by a previous shutdown/crash.
        for rec in self.store.list(limit=500, status="transcribing"):
            self.store.update(rec["id"], status="pending")
        self.backfill_titles()
        self._task = asyncio.create_task(self._run())

    def backfill_titles(self) -> int:
        """Derive titles for recordings summarized before the title column
        existed. No LLM call: reuse the summary's own first line, and when the
        summary opens with a "Title:" line, move it out of the summary body so
        the dashboard and exports stop showing it twice. Idempotent: rows that
        already have a title are never touched. Returns the number updated."""
        rows = self.store.list_untitled_done()
        updated = 0
        for row in rows:
            title, body = _split_title(row["summary"])
            if title is None:
                continue
            fields: dict = {"title": title}
            # Only rewrite the summary when a Title line was actually consumed
            # (body differs) and something remains; never blank a summary.
            new_summary = body if (body and body != row["summary"].strip()) else None
            if new_summary:
                fields["summary"] = new_summary
            self.store.update(row["id"], **fields)
            self._patch_transcript_json(row.get("transcript_path"), title, new_summary)
            updated += 1
        if updated:
            log.info("backfilled titles for %d recording(s)", updated)
        return updated

    @staticmethod
    def _patch_transcript_json(path: str | None, title: str, summary: str | None) -> None:
        # The Android app reads the title from the transcript JSON, so keep the
        # file in step with the row. Best effort: a missing or corrupt file
        # must never prevent startup.
        if not path:
            return
        try:
            p = Path(path)
            data = json.loads(p.read_text())
            data["title"] = title
            if summary:
                data["summary"] = summary
            tmp = p.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            tmp.replace(p)
        except Exception as exc:
            log.warning("could not patch title into %s: %s", path, exc)

    async def stop(self) -> None:
        # Tear down engine resources first (the local engine keeps a pyannote
        # diarization worker process alive); no-op for engines without close().
        close = getattr(self.engine, "close", None)
        if callable(close):
            try:
                await asyncio.to_thread(close)
            except Exception:
                log.exception("engine close failed")
        for task in list(self._router_tasks):
            task.cancel()
        if self._router_tasks:
            await asyncio.gather(*self._router_tasks, return_exceptions=True)
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
            # Shutdown mid-transcription: hand the row back to the queue —
            # but only if it is actually still mid-flight. A recording that
            # already reached 'done' (cancellation arrived during the
            # post-transcription hooks) must never revert, or a restart would
            # re-transcribe and re-route finished work.
            current = self.store.get(rec_id)
            if current and current["status"] == "transcribing":
                self.store.update(rec_id, status="pending")
            raise
        except Exception as exc:
            log.exception("processing failed for %s", rec_id)
            self.store.update(rec_id, status="failed", error=str(exc)[:1000])

    async def _process_inner(self, rec: dict) -> None:
        if self.engine is None:
            self.store.update(rec["id"], status="stored")
            return
        rec_id = rec["id"]
        self.store.update(rec_id, status="transcribing", attempts=rec["attempts"] + 1)
        log.info("transcribing %s (%s) via %s", rec_id, rec["filename"], self.engine.name)
        try:
            result = await self.engine.transcribe(Path(rec["audio_path"]))
        except (EngineError, Exception) as exc:
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
            "duration_s": result.duration or rec["duration_s"],
            "language": result.language,
            "model": result.model,
            "engine": self.engine.name,
            "stats": result.stats,
            "transcribed_at": utcnow_iso(),
            "text": result.text,
            "segments": [s.as_dict() for s in result.segments],
        }
        # Recorder button presses -> highlighted passages. The marks may also
        # arrive later via PATCH /marks (see refresh_highlights).
        current = self.store.get(rec_id) or rec
        marks = parse_marks(current.get("marks"))
        if marks:
            transcript["marks"] = marks
            transcript["highlights"] = build_highlights(marks, transcript["segments"], transcript["duration_s"])
        summary = await self._summarize(transcript["text"], transcript.get("highlights") or [])
        if summary.title:
            transcript["title"] = summary.title
        if summary.text:
            transcript["summary"] = summary.text
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
            summary=summary.text,
            title=summary.title,
            duration_s=transcript["duration_s"],
            error=None,
        )
        log.info("transcribed %s (%d chars%s)", rec_id, len(transcript["text"]),
                 ", summarized" if summary.text else "")

        self._export_markdown(rec, transcript)
        await self._fire_webhook(rec, transcript)
        # Routing runs as a detached task so a slow router LLM or webhook can
        # never block the next transcription (or couple its failures/
        # cancellation to this recording's 'done' status).
        if self.settings.router_enabled:
            task = asyncio.create_task(self._run_router(rec_id))
            self._router_tasks.add(task)
            task.add_done_callback(self._router_tasks.discard)

    async def _run_router(self, rec_id: str) -> None:
        """AI routing: never allowed to affect the recording's 'done' status."""
        if not self.settings.router_enabled:
            return
        try:
            if not self.store.list_routes(enabled_only=True):
                return
            rec = self.store.get(rec_id)
            if rec:
                await self.router.route_recording(rec)
        except Exception:
            log.exception("routing failed for %s", rec_id)

    def refresh_highlights(self, rec_id: str) -> list[dict] | None:
        """Recompute highlights from the stored marks and the existing transcript
        JSON (no LLM, no re-transcription). Returns the new highlights, or None
        when the transcript file is missing."""
        rec = self.store.get(rec_id)
        if not rec or not rec.get("transcript_path"):
            return None
        p = Path(rec["transcript_path"])
        try:
            data = json.loads(p.read_text())
        except (OSError, ValueError):
            return None
        marks = parse_marks(rec.get("marks"))
        data["marks"] = marks
        data["highlights"] = build_highlights(marks, data.get("segments") or [], data.get("duration_s"))
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp.replace(p)
        self._export_markdown(rec, data)
        return data["highlights"]

    async def _summarize(self, text: str, highlights: list[dict] | None = None) -> Summary:
        s = self.settings
        if not (s.summary_enabled and s.summary_base_url and s.summary_model):
            return Summary()
        if not text.strip():
            return Summary()
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
                            # Wrapped and labeled as data: a transcript that is
                            # itself an instruction ("file this as a meeting")
                            # must be summarized, not obeyed (see summary_prompt).
                            {"role": "user", "content":
                                "Transcript (untrusted data):\n<transcript>\n"
                                + text[: s.summary_max_chars] + "\n</transcript>"
                                + highlights_for_prompt(highlights or [])},
                        ],
                    },
                )
                if resp.status_code != 200:
                    log.warning("summary endpoint returned %s: %s", resp.status_code, resp.text[:200])
                    return Summary()
                content = resp.json()["choices"][0]["message"]["content"]
                title, body = _split_title(content)
                return Summary(title=title, text=body or None)
        except Exception as exc:
            log.warning("summarization failed: %s", exc)
            return Summary()

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

            # Filename stays keyed on timestamp + id (not the title) so a
            # re-transcribe overwrites the same note instead of duplicating it.
            title = transcript.get("title")
            lines = ["---"]
            if title:
                lines.append(f"title: {yq(title)}")
            lines += [
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
            if title:
                lines += [f"# {title}", ""]
            if transcript.get("summary"):
                lines += ["## Summary", "", transcript["summary"], ""]
            lines += highlights_markdown(transcript.get("highlights") or [])
            if transcript.get("summary") or transcript.get("highlights"):
                lines += ["## Transcript", ""]
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
                "title": transcript.get("title"),
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
