"""Worker pipeline tests using a fake engine (no models, no network)."""

import asyncio
import json
from pathlib import Path

import pytest

from app.config import Settings
from app.db import Store, utcnow_iso
from app.engines.base import EngineError, EngineResult, Segment
from app.transcriber import Transcriber


class FakeEngine:
    name = "fake"

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0

    async def transcribe(self, audio_path: Path) -> EngineResult:
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def make_env(tmp_path, monkeypatch, **extra):
    monkeypatch.setenv("PB_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PB_AUTH_TOKENS", "t")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)
    return Settings()


def insert_recording(store: Store, tmp_path: Path, **overrides) -> str:
    audio = tmp_path / "rec.mp3"
    audio.write_bytes(b"fake-audio")
    fields = dict(
        device_sn="881A", session_id=1, filename="rec.mp3", sha256=overrides.pop("sha256", "x" * 64),
        size_bytes=10, duration_s=None, started_at="2026-09-06T12:00:00Z", source="test",
        uploaded_at=utcnow_iso(), audio_path=str(audio), status="pending",
    )
    fields.update(overrides)
    return store.insert_recording(**fields)


def test_successful_transcription_persists_everything(tmp_path, monkeypatch):
    settings = make_env(tmp_path, monkeypatch, PB_MARKDOWN_EXPORT_DIR=str(tmp_path / "notes"))
    store = Store(settings.db_path)
    engine = FakeEngine(result=EngineResult(
        text="Speaker 1: hello\nSpeaker 2: hi",
        segments=[Segment(0, 1, "hello", speaker="Speaker 1"),
                  Segment(1, 2, "hi", speaker="Speaker 2")],
        language="en", duration=2.0, model="tiny", stats={"rtf": 0.1},
    ))
    t = Transcriber(settings, store, engine=engine)
    rec_id = insert_recording(store, tmp_path)

    asyncio.run(t._process(store.get(rec_id)))

    rec = store.get(rec_id)
    assert rec["status"] == "done"
    assert rec["transcript_text"].startswith("Speaker 1: hello")
    assert rec["duration_s"] == 2.0

    transcript = json.loads(Path(rec["transcript_path"]).read_text())
    assert transcript["engine"] == "fake"
    assert transcript["segments"][0]["speaker"] == "Speaker 1"
    assert transcript["stats"] == {"rtf": 0.1}

    md_files = list((tmp_path / "notes").glob("*.md"))
    assert len(md_files) == 1
    md = md_files[0].read_text()
    assert "Speaker 2: hi" in md and 'device_sn: "881A"' in md


def test_engine_error_marks_failed_and_counts_attempts(tmp_path, monkeypatch):
    settings = make_env(tmp_path, monkeypatch)
    store = Store(settings.db_path)
    t = Transcriber(settings, store, engine=FakeEngine(error=EngineError("STT down")))
    rec_id = insert_recording(store, tmp_path)

    asyncio.run(t._process(store.get(rec_id)))
    rec = store.get(rec_id)
    assert rec["status"] == "failed" and rec["attempts"] == 1 and "STT down" in rec["error"]

    # Retry path picks it up again until max attempts
    pending = store.next_pending(max_attempts=3)
    assert pending and pending["id"] == rec_id
    asyncio.run(t._process(pending))
    asyncio.run(t._process(store.next_pending(max_attempts=3)))
    assert store.get(rec_id)["attempts"] == 3
    assert store.next_pending(max_attempts=3) is None  # exhausted


def test_no_engine_marks_stored(tmp_path, monkeypatch):
    settings = make_env(tmp_path, monkeypatch, PB_TRANSCRIBE_ENABLED="false")
    store = Store(settings.db_path)
    t = Transcriber(settings, store, engine=None)
    rec_id = insert_recording(store, tmp_path)
    asyncio.run(t._process(store.get(rec_id)))
    assert store.get(rec_id)["status"] == "stored"


def test_deleted_mid_transcription_discards_result(tmp_path, monkeypatch):
    settings = make_env(tmp_path, monkeypatch)
    store = Store(settings.db_path)
    engine = FakeEngine(result=EngineResult(text="x", duration=1.0))
    t = Transcriber(settings, store, engine=engine)
    rec_id = insert_recording(store, tmp_path)
    row = store.get(rec_id)
    store.delete(rec_id)  # user deletes while "in flight"

    asyncio.run(t._process(row))
    assert store.get(rec_id) is None
    assert not list(tmp_path.glob("*.transcript.json"))


def test_startup_recovers_stuck_transcribing_rows(tmp_path, monkeypatch):
    settings = make_env(tmp_path, monkeypatch)
    store = Store(settings.db_path)
    rec_id = insert_recording(store, tmp_path, status="transcribing")

    t = Transcriber(settings, store, engine=FakeEngine(result=EngineResult(text="ok")))

    async def run():
        t.start()  # resets stuck 'transcribing' rows to 'pending', then works the queue
        try:
            for _ in range(100):
                if store.get(rec_id)["status"] == "done":
                    return True
                await asyncio.sleep(0.05)
            return False
        finally:
            await t.stop()

    assert asyncio.run(run()) is True


def test_summary_written_when_enabled(tmp_path, monkeypatch):
    settings = make_env(tmp_path, monkeypatch, PB_SUMMARY_ENABLED="true",
                        PB_SUMMARY_BASE_URL="http://llm/v1", PB_SUMMARY_MODEL="m")
    store = Store(settings.db_path)
    engine = FakeEngine(result=EngineResult(text="long transcript", duration=1.0))
    t = Transcriber(settings, store, engine=engine)

    async def fake_summarize(text):
        return f"Title\nSummary of: {text}"

    monkeypatch.setattr(t, "_summarize", fake_summarize)
    rec_id = insert_recording(store, tmp_path)
    asyncio.run(t._process(store.get(rec_id)))
    rec = store.get(rec_id)
    assert rec["summary"].startswith("Title")
    transcript = json.loads(Path(rec["transcript_path"]).read_text())
    assert transcript["summary"].startswith("Title")
