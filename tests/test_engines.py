"""Unit tests for the transcription engine layer (no models required)."""

import asyncio
from pathlib import Path

import pytest

from app.benchmark import normalize_words, print_table, word_error_rate
from app.config import Settings
from app.engines import build_engine
from app.engines.base import EngineResult, Segment, render_text
from app.engines.local_whisper import LocalWhisperEngine
from app.engines.openai_compat import OpenAICompatEngine

# ── render_text ──────────────────────────────────────────────────────────────


def test_render_text_without_speakers_uses_fallback():
    segs = [Segment(0, 1, "hello"), Segment(1, 2, "world")]
    assert render_text(segs, fallback="full text") == "full text"
    assert render_text(segs) == "hello world"
    assert render_text([], fallback="only text") == "only text"


def test_render_text_with_speakers_labels_turns():
    segs = [
        Segment(0, 1, "hi there", speaker="Speaker 1"),
        Segment(1, 2, "how are you", speaker="Speaker 1"),
        Segment(2, 3, "fine thanks", speaker="Speaker 2"),
        Segment(3, 4, "", speaker="Speaker 2"),  # empty text skipped
        Segment(4, 5, "great", speaker="Speaker 1"),
    ]
    out = render_text(segs)
    assert "Speaker 1: hi there how are you" in out
    assert "Speaker 2: fine thanks" in out
    assert out.rstrip().endswith("Speaker 1: great")


def test_render_text_unlabeled_segment_between_speakers():
    segs = [Segment(0, 1, "a", speaker="Speaker 1"), Segment(1, 2, "b", speaker=None)]
    out = render_text(segs)
    assert "Speaker 1: a" in out and "Unknown speaker: b" in out


# ── diarization speaker assignment ───────────────────────────────────────────


class _FakeTurn:
    def __init__(self, start, end):
        self.start, self.end = start, end


class _FakeAnnotation:
    def __init__(self, turns):
        self._turns = turns

    def itertracks(self, yield_label=True):
        for start, end, label in self._turns:
            yield _FakeTurn(start, end), None, label


def test_diarization_assigns_speaker_by_overlap(monkeypatch, tmp_path):
    engine = LocalWhisperEngine(diarization=True)
    turns = [(0.0, 5.0, "A"), (5.0, 10.0, "B"), (10.0, 12.0, "A")]
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: turns)

    segments = [
        Segment(0.5, 4.0, "first"),
        Segment(4.5, 7.0, "second"),   # overlaps A(0.5s) and B(2.0s) -> B
        Segment(10.1, 11.0, "third"),  # back to A
        Segment(None, None, "no timestamps"),
    ]
    engine._apply_diarization(tmp_path / "x.wav", segments, words=[])

    # Labels normalized in order of appearance: A -> Speaker 1, B -> Speaker 2
    assert segments[0].speaker == "Speaker 1"
    assert segments[1].speaker == "Speaker 2"
    assert segments[2].speaker == "Speaker 1"
    assert segments[3].speaker is None


def test_diarization_word_level_splits_segment_at_speaker_change(monkeypatch, tmp_path):
    """One coarse whisper segment spans two speakers; B's turn is the shorter.
    Segment-level assignment would hand the whole thing to A. With word
    timestamps the segment is split at the boundary and B's words survive."""
    engine = LocalWhisperEngine(diarization=True)
    turns = [(0.0, 6.0, "A"), (6.0, 8.0, "B")]
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: turns)
    segments = [Segment(0.0, 8.0, "Now say something. No, I won't.")]
    words = [(0.0, 1.0, " Now", 0), (1.0, 2.0, " say", 0), (2.0, 5.9, " something.", 0),
             (6.1, 7.0, " No,", 0), (7.0, 7.5, " I", 0), (7.5, 8.0, " won't.", 0)]
    engine._apply_diarization(tmp_path / "x.wav", segments, words)
    assert [(s.speaker, s.text) for s in segments] == [
        ("Speaker 1", "Now say something."),
        ("Speaker 2", "No, I won't."),
    ]
    assert (segments[0].start, segments[0].end) == (0.0, 5.9)
    assert (segments[1].start, segments[1].end) == (6.1, 8.0)


def test_diarization_words_outside_turns_inherit_neighbour(monkeypatch, tmp_path):
    """A lead-in word before the first turn and a word in a gap must not become
    an unlabeled turn of their own; they take the next (else previous) label."""
    engine = LocalWhisperEngine(diarization=True)
    turns = [(1.0, 3.0, "A"), (4.0, 6.0, "B")]
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: turns)
    segments = [Segment(0.0, 7.0, "x")]
    words = [(0.0, 0.5, " like", 0),         # before any turn -> next label A
             (1.0, 2.9, " lettuce", 0),
             (3.2, 3.8, " and", 0),          # gap between A and B -> next label B
             (4.0, 5.9, " well", 0),
             (6.2, 7.0, " done.", 0)]        # after the last turn -> previous label B
    engine._apply_diarization(tmp_path / "x.wav", segments, words)
    assert [(s.speaker, s.text) for s in segments] == [
        ("Speaker 1", "like lettuce"), ("Speaker 2", "and well done.")]


def test_diarization_keeps_whisper_segment_boundaries_within_a_turn(monkeypatch, tmp_path):
    """One speaker across two whisper segments stays two segments (timestamps
    remain useful); rendering merges same-speaker neighbours into a turn."""
    engine = LocalWhisperEngine(diarization=True)
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: [(0.0, 10.0, "A")])
    segments = [Segment(0.0, 5.0, "first part"), Segment(5.0, 10.0, "second part")]
    words = [(0.0, 2.0, " first", 0), (2.0, 5.0, " part", 0),
             (5.0, 7.0, " second", 1), (7.0, 10.0, " part", 1)]
    engine._apply_diarization(tmp_path / "x.wav", segments, words)
    assert [(s.speaker, s.text, s.start, s.end) for s in segments] == [
        ("Speaker 1", "first part", 0.0, 5.0), ("Speaker 1", "second part", 5.0, 10.0)]
    assert render_text(segments, fallback="") .count("Speaker 1:") == 1


def test_diarization_no_turns_leaves_segments_untouched(monkeypatch, tmp_path):
    engine = LocalWhisperEngine(diarization=True)
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: [])
    segments = [Segment(0, 1, "x")]
    engine._apply_diarization(tmp_path / "x.wav", segments, words=[])
    assert segments[0].speaker is None


# ── openai-compat parsing ────────────────────────────────────────────────────


def test_openai_engine_parses_verbose_json():
    engine = OpenAICompatEngine(base_url="http://x/v1", model="whisper-1")
    result = engine._parse(
        {"text": "hello world", "language": "en", "duration": 10.0,
         "segments": [{"start": 0, "end": 5, "text": " hello "},
                      {"start": 5, "end": 10, "text": "world"}]},
        elapsed=2.0,
    )
    assert result.text == "hello world"
    assert [s.text for s in result.segments] == ["hello", "world"]
    assert result.language == "en"
    assert result.stats["rtf"] == 0.2


def test_openai_engine_parses_plain_json():
    engine = OpenAICompatEngine(base_url="http://x/v1")
    result = engine._parse({"text": "just text"}, elapsed=1.0)
    assert result.text == "just text" and result.segments == []


# ── engine factory ───────────────────────────────────────────────────────────


def _settings(**env):
    import os
    old = dict(os.environ)
    os.environ.update(env)
    try:
        return Settings()
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_build_engine_local():
    s = _settings(PB_STT_ENGINE="local", PB_STT_MODEL="tiny", PB_TRANSCRIBE_ENABLED="true")
    engine = build_engine(s)
    assert isinstance(engine, LocalWhisperEngine) and engine.model_name == "tiny"


def test_build_engine_openai():
    s = _settings(PB_STT_ENGINE="openai", PB_TRANSCRIBE_BASE_URL="http://stt/v1",
                  PB_TRANSCRIBE_ENABLED="true")
    assert isinstance(build_engine(s), OpenAICompatEngine)


def test_build_engine_openai_without_url_disables():
    s = _settings(PB_STT_ENGINE="openai", PB_TRANSCRIBE_BASE_URL="", PB_TRANSCRIBE_ENABLED="true")
    assert build_engine(s) is None


def test_build_engine_disabled():
    s = _settings(PB_TRANSCRIBE_ENABLED="false")
    assert build_engine(s) is None


def test_build_engine_unknown_raises():
    s = _settings(PB_STT_ENGINE="banana", PB_TRANSCRIBE_ENABLED="true")
    with pytest.raises(ValueError):
        build_engine(s)


# ── local engine guards ──────────────────────────────────────────────────────


def test_local_engine_missing_dependency_message(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def block_fw(name, *a, **k):
        if name == "faster_whisper":
            raise ImportError("nope")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", block_fw)
    engine = LocalWhisperEngine(model="tiny")
    from app.engines.base import EngineError

    with pytest.raises(EngineError, match="faster-whisper is not installed"):
        asyncio.run(engine.transcribe(tmp_path / "a.wav"))


# ── benchmark helpers ────────────────────────────────────────────────────────


def test_wer_perfect_and_total():
    assert word_error_rate("hello world", "hello world") == 0.0
    assert word_error_rate("hello world", "") == 1.0
    assert word_error_rate("", "") == 0.0


def test_wer_substitution_and_normalization():
    # 1 substitution over 4 words; punctuation/case ignored
    assert word_error_rate("The quick brown fox.", "the quick brown dog") == 0.25
    assert normalize_words("Hello, World!") == ["hello", "world"]


def test_bench_model_uses_engine(monkeypatch, tmp_path):
    from app import benchmark
    from app.engines import local_whisper

    class FakeEngine:
        load_seconds = 1.5

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def transcribe(self, path):
            return EngineResult(
                text="fake", segments=[], language="en", duration=10.0,
                model=self.kwargs["model"],
                stats={"transcribe_seconds": 2.0},
            )

    monkeypatch.setattr(local_whisper, "LocalWhisperEngine", FakeEngine)
    row = asyncio.run(benchmark.bench_model(
        tmp_path / "a.wav", "tiny", "cpu", "int8", False, None))
    assert row["status"] == "ok"
    assert row["speed"] == 5.0  # 10 s audio / 2 s wall
    assert row["load_s"] == 1.5


def test_bench_model_reports_failure(monkeypatch, tmp_path):
    from app import benchmark
    from app.engines import local_whisper

    class BoomEngine:
        load_seconds = None

        def __init__(self, **kwargs): ...

        async def transcribe(self, path):
            raise RuntimeError("model exploded")

    monkeypatch.setattr(local_whisper, "LocalWhisperEngine", BoomEngine)
    row = asyncio.run(benchmark.bench_model(tmp_path / "a.wav", "tiny", "cpu", "auto", False, None))
    assert row["status"] == "fail" and "model exploded" in row["error"]


def test_print_table_smoke(capsys):
    print_table(
        [{"model": "tiny", "device": "cpu", "status": "ok", "load_s": 1, "transcribe_s": 2,
          "speed": 5.0, "language": "en"},
         {"model": "big", "device": "cpu", "status": "fail", "error": "boom"}],
        has_wer=False,
    )
    out = capsys.readouterr().out
    assert "tiny" in out and "FAILED — boom" in out


def test_diarization_cumulative_overlap_beats_single_turn(monkeypatch, tmp_path):
    # Speaker A has two short turns inside the segment (total 2.0s); speaker B
    # one longer turn (1.5s). Cumulative overlap must pick A.
    engine = LocalWhisperEngine(diarization=True)
    turns = [(0.0, 1.0, "A"), (1.0, 2.5, "B"), (2.5, 3.5, "A")]
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: turns)
    segments = [Segment(0.0, 3.5, "who said this")]
    engine._apply_diarization(tmp_path / "x.wav", segments, words=[])
    assert segments[0].speaker == "Speaker 1"  # A appears first -> Speaker 1


def test_build_engine_backcompat_external_url_defaults_to_openai():
    s = _settings(PB_TRANSCRIBE_BASE_URL="http://stt/v1", PB_TRANSCRIBE_ENABLED="true",
                  PB_STT_ENGINE="")
    assert isinstance(build_engine(s), OpenAICompatEngine)


def test_duration_probe_rejects_before_model_load():
    fixture = Path(__file__).parent / "fixtures" / "speech.wav"
    engine = LocalWhisperEngine(model="tiny", max_duration_s=2)
    probed = engine._probe_duration(fixture)
    assert probed and 3 < probed < 10
    from app.engines.base import EngineError

    with pytest.raises(EngineError, match="over the"):
        engine._transcribe_sync(fixture)
    assert engine._model is None  # rejected before loading the model


def test_wer_apostrophe_normalization():
    assert word_error_rate("don't stop", "don’t stop") == 0.0
