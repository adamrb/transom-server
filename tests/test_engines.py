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
from app.engines.parakeet import ParakeetEngine

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


def test_fit_hotwords_trims_at_term_boundary_keeping_the_front():
    class Enc:
        def __init__(self, ids): self.ids = ids
    class Tok:
        def encode(self, s): return Enc(list(s))  # one token per character
    class Model:
        hf_tokenizer = Tok()
    engine = LocalWhisperEngine()
    hw = "Morgan Ashford, Nebulite, Bianca Ferrante, Zed"
    assert engine._fit_hotwords(Model(), hw, max_tokens=len(" Morgan Ashford, Nebulite")) == "Morgan Ashford, Nebulite"
    assert engine._fit_hotwords(Model(), hw, max_tokens=1000) == hw
    assert engine._fit_hotwords(Model(), None) is None


def _spawn_diar_worker_env(monkeypatch, engine) -> dict:
    """Run _ensure_diar_worker with a fake Popen; return the env it was given."""
    import subprocess
    seen = {}

    class FakeProc:
        def __init__(self):
            class Out:
                def readline(self_inner): return "READY\n"
            self.stdout = Out()
        def kill(self): pass

    def fake_popen(cmd, env=None, **kwargs):
        seen["env"] = env
        return FakeProc()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)
    engine._ensure_diar_worker()
    engine._diar_proc = None
    return seen["env"]


def test_diarization_worker_follows_engine_device_by_default(monkeypatch):
    env = _spawn_diar_worker_env(monkeypatch, LocalWhisperEngine(diarization=True, device="cuda"))
    assert env["PB_STT_DEVICE"] == "cuda"


def test_diarization_worker_takes_its_own_device(monkeypatch):
    env = _spawn_diar_worker_env(
        monkeypatch, LocalWhisperEngine(diarization=True, device="cuda", diarization_device="cpu"))
    assert env["PB_STT_DEVICE"] == "cpu"
    env = _spawn_diar_worker_env(
        monkeypatch, ParakeetEngine(diarization=True, device="auto", diarization_device="cpu"))
    assert env["PB_STT_DEVICE"] == "cpu"


def test_build_engine_passes_diarize_device():
    s = _settings(PB_STT_ENGINE="local", PB_STT_DEVICE="cuda", PB_STT_DIARIZE_DEVICE="CPU",
                  PB_STT_DIARIZE="true", PB_STT_HF_TOKEN="x", PB_TRANSCRIBE_ENABLED="true")
    assert build_engine(s).diarization_device == "cpu"
    s = _settings(PB_STT_ENGINE="local", PB_STT_DIARIZE_DEVICE="", PB_TRANSCRIBE_ENABLED="true")
    assert build_engine(s).diarization_device is None


# ── parakeet engine ──────────────────────────────────────────────────────────


class _Chunk:
    """Stand-in for onnx-asr's TimestampedSegmentResult."""

    def __init__(self, start, end, text, tokens=None, timestamps=None):
        self.start, self.end, self.text = start, end, text
        self.tokens, self.timestamps = tokens, timestamps


def _parakeet_with_fakes(monkeypatch, chunks, duration_s=60.0, **kwargs):
    """A ParakeetEngine whose model loading, audio decode and recognition are
    replaced: decode yields ``duration_s`` of silence, recognition yields the
    given chunks."""
    engine = ParakeetEngine(**kwargs)

    def fake_load():
        engine._model, engine._vad = object(), object()
        engine.device_used = "cpu"
        return engine._model

    monkeypatch.setattr(engine, "_load_model", fake_load)
    monkeypatch.setattr(engine, "_decode_waveform", lambda path: [0.0] * int(duration_s * 16_000))
    monkeypatch.setattr(engine, "_recognize", lambda wav, enhanced=None: iter(chunks))
    monkeypatch.setattr("app.engines.parakeet.probe_duration", lambda path: duration_s)
    return engine


def test_build_engine_parakeet():
    s = _settings(PB_STT_ENGINE="parakeet", PB_STT_PARAKEET_MODEL="nemo-parakeet-tdt-0.6b-v2",
                  PB_STT_PARAKEET_QUANT="int8", PB_STT_PARAKEET_SEGMENT_S="25",
                  PB_STT_DIARIZE="true", PB_STT_HF_TOKEN="x", PB_TRANSCRIBE_ENABLED="true")
    engine = build_engine(s)
    assert isinstance(engine, ParakeetEngine)
    assert engine.model_name == "nemo-parakeet-tdt-0.6b-v2"
    assert engine.quantization == "int8"
    assert engine.max_segment_s == 25.0
    assert engine.diarization is True


def test_build_engine_parakeet_defaults():
    s = _settings(PB_STT_ENGINE="parakeet", PB_TRANSCRIBE_ENABLED="true", PB_STT_PARAKEET_QUANT="")
    engine = build_engine(s)
    assert engine.model_name == "nemo-parakeet-tdt-0.6b-v3"
    assert engine.quantization is None  # empty env var means "no quantization"


def test_parakeet_words_from_tokens_groups_subwords_and_offsets():
    # Chunk starts at 100 s; tokens are onnx-asr NeMo pieces (leading space =
    # new word), timestamps relative to the chunk start.
    tokens = [" The", " I", "ce", "X", " from", " N", "v", "id", "ia", ",", " ok", "."]
    stamps = [0.08, 0.16, 0.24, 0.40, 0.88, 1.04, 1.20, 1.28, 1.52, 2.00, 2.40, 2.56]
    words = ParakeetEngine._words_from_tokens(100.0, 103.0, tokens, stamps)
    assert [w[2] for w in words] == [" The", " IceX", " from", " Nvidia,", " ok."]
    # Each word runs from its first token to the next word's first token.
    assert words[0][:2] == (100.08, 100.16)
    assert words[1][:2] == (100.16, 100.88)
    assert words[3][:2] == (101.04, 102.40)
    # The last word ends at the chunk end.
    assert words[4][:2] == (102.40, 103.0)


def test_parakeet_words_from_tokens_edge_cases():
    assert ParakeetEngine._words_from_tokens(0.0, 1.0, None, None) == []
    assert ParakeetEngine._words_from_tokens(0.0, 1.0, [], []) == []
    # A first piece without a leading space still starts a word, and a
    # timestamp past the chunk end is clamped so the word never leaves it.
    words = ParakeetEngine._words_from_tokens(10.0, 11.0, ["hi", " there"], [0.0, 5.0])
    assert words == [(10.0, 11.0, " hi"), (11.0, 11.05, " there")]


def test_parakeet_transcribe_builds_segments_and_reports_progress(monkeypatch):
    chunks = [
        _Chunk(0.5, 4.0, " Hello there. "),
        _Chunk(4.2, 5.0, "   "),  # VAD chunk the model heard nothing in
        _Chunk(10.0, 14.0, "Second part"),
    ]
    engine = _parakeet_with_fakes(monkeypatch, chunks, duration_s=20.0)
    monkeypatch.setattr("app.engines.parakeet.PROGRESS_INTERVAL_S", 0.0)
    reports = []
    result = asyncio.run(engine.transcribe(Path("a.mp3"), hotwords="Zed, Nebulite",
                                           progress=lambda stage, frac: reports.append((stage, frac))))
    assert [s.text for s in result.segments] == ["Hello there.", "Second part"]
    assert (result.segments[0].start, result.segments[0].end) == (0.5, 4.0)
    assert result.text == "Hello there. Second part"
    assert result.duration == 20.0
    assert result.model == "nemo-parakeet-tdt-0.6b-v3"
    assert result.stats["engine"] == "parakeet" and result.stats["device"] == "cpu"
    assert "transcribe_seconds" in result.stats and "diarize_seconds" not in result.stats
    assert reports and reports[0][0] == "transcribing"
    assert all(0.0 <= frac <= 0.99 for _, frac in reports)
    assert reports[-1][1] == pytest.approx(14.0 / 20.0)


def test_parakeet_ignores_forced_language_and_says_so(monkeypatch, caplog):
    import logging

    engine = _parakeet_with_fakes(monkeypatch, [_Chunk(0.0, 1.0, "ciao")], duration_s=1.0, language="en")
    with caplog.at_level(logging.WARNING, logger="plaud-bridge.engine.parakeet"):
        result = asyncio.run(engine.transcribe(Path("a.mp3")))
        asyncio.run(engine.transcribe(Path("b.mp3")))
    assert result.language is None  # never claims the configured language
    assert sum("PB_TRANSCRIBE_LANGUAGE=en is ignored" in r.message for r in caplog.records) == 1


def test_parakeet_diarization_splits_chunk_at_speaker_change(monkeypatch):
    # One 6 s chunk; the speaker changes at 3 s, between "one two" and "three four".
    chunk = _Chunk(0.0, 6.0, "one two three four",
                   tokens=[" one", " two", " three", " four"], timestamps=[0.2, 1.4, 3.2, 4.6])
    engine = _parakeet_with_fakes(monkeypatch, [chunk], duration_s=6.0, diarization=True)
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: [(0.0, 3.0, "A"), (3.0, 6.0, "B")])
    reports = []
    result = asyncio.run(engine.transcribe(Path("a.mp3"), progress=lambda s, f: reports.append(s)))
    assert [(s.speaker, s.text) for s in result.segments] == [("Speaker 1", "one two"), ("Speaker 2", "three four")]
    assert result.segments[1].start == 3.2
    assert "Speaker 1: one two" in result.text and "Speaker 2: three four" in result.text
    assert "diarizing" in reports


def test_parakeet_diarization_failure_keeps_transcript(monkeypatch):
    chunk = _Chunk(0.0, 2.0, "hello", tokens=[" hello"], timestamps=[0.1])
    engine = _parakeet_with_fakes(monkeypatch, [chunk], duration_s=2.0, diarization=True)

    def boom(path):
        raise RuntimeError("CUDA out of memory")

    monkeypatch.setattr(engine, "_run_diarizer", boom)
    result = asyncio.run(engine.transcribe(Path("a.mp3")))
    assert result.text == "hello" and result.segments[0].speaker is None


def test_parakeet_recognizer_error_becomes_engine_error(monkeypatch):
    from app.engines.base import EngineError

    def failing():
        raise RuntimeError("onnxruntime exploded")
        yield  # pragma: no cover - makes this a generator

    engine = _parakeet_with_fakes(monkeypatch, [], duration_s=5.0)
    monkeypatch.setattr(engine, "_recognize", lambda wav, enhanced=None: failing())
    with pytest.raises(EngineError, match="parakeet transcription failed: onnxruntime exploded"):
        asyncio.run(engine.transcribe(Path("a.mp3")))


def test_parakeet_rejects_long_audio_before_loading(monkeypatch):
    from app.engines.base import EngineError

    engine = ParakeetEngine(max_duration_s=60)
    monkeypatch.setattr("app.engines.parakeet.probe_duration", lambda path: 120.0)
    with pytest.raises(EngineError, match="over the"):
        asyncio.run(engine.transcribe(Path("long.mp3")))
    assert engine._model is None


def test_parakeet_missing_dependency_message(monkeypatch):
    import builtins
    from app.engines.base import EngineError

    real_import = builtins.__import__

    def block(name, *a, **k):
        if name == "onnx_asr":
            raise ImportError("nope")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", block)
    monkeypatch.setattr("app.engines.parakeet.probe_duration", lambda path: 1.0)
    engine = ParakeetEngine()
    with pytest.raises(EngineError, match="onnx-asr is not installed"):
        asyncio.run(engine.transcribe(Path("a.wav")))


def test_parakeet_choose_providers():
    cuda, cpu = "CUDAExecutionProvider", "CPUExecutionProvider"
    assert ParakeetEngine._choose_providers("auto", [cuda, cpu]) == [cuda, cpu]
    assert ParakeetEngine._choose_providers("cuda", [cuda, cpu]) == [cuda, cpu]
    assert ParakeetEngine._choose_providers("cpu", [cuda, cpu]) == [cpu]
    assert ParakeetEngine._choose_providers("auto", [cpu]) == [cpu]
    assert ParakeetEngine._choose_providers("cuda", [cpu]) == [cpu]  # warns, runs on CPU


def _parakeet_load_harness(monkeypatch, available, warm_up_fails):
    """Drive _load_model with fake sessions: records the providers each
    session set was created with and whether the GPU warm-up 'ran'."""
    engine = ParakeetEngine(device="auto")
    created: list[list[str]] = []
    monkeypatch.setattr(engine, "_ensure_diar_worker", lambda: None)
    monkeypatch.setattr(engine, "_available_providers", lambda: available)
    monkeypatch.setattr(engine, "_create_sessions",
                        lambda providers: (created.append(list(providers)) or (f"model:{providers[0]}", "vad")))

    def warm_up(model):
        if warm_up_fails:
            raise RuntimeError("CUDA error cudaErrorNoKernelImageForDevice:no kernel image is available")

    monkeypatch.setattr(engine, "_warm_up", warm_up)
    monkeypatch.setattr(engine, "_detect_device", lambda model, providers: "cuda" if providers[0].startswith("CUDA") else "cpu")
    # onnxruntime.preload_dlls must not touch the real machine here
    import onnxruntime
    monkeypatch.setattr(onnxruntime, "preload_dlls", lambda *a, **k: None, raising=False)
    return engine, created


def test_parakeet_falls_back_to_cpu_when_the_gpu_has_no_kernels(monkeypatch):
    cuda, cpu = "CUDAExecutionProvider", "CPUExecutionProvider"
    engine, created = _parakeet_load_harness(monkeypatch, [cuda, cpu], warm_up_fails=True)
    engine._load_model()
    assert created == [[cuda, cpu], [cpu]]
    assert engine.device_used == "cpu" and engine._model == f"model:{cpu}"


def test_parakeet_keeps_the_gpu_when_warm_up_passes(monkeypatch):
    cuda, cpu = "CUDAExecutionProvider", "CPUExecutionProvider"
    engine, created = _parakeet_load_harness(monkeypatch, [cuda, cpu], warm_up_fails=False)
    engine._load_model()
    assert created == [[cuda, cpu]]
    assert engine.device_used == "cuda"
    # Second call reuses the loaded model
    engine._load_model()
    assert len(created) == 1


def test_parakeet_cpu_only_box_skips_warm_up(monkeypatch):
    cpu = "CPUExecutionProvider"
    engine, created = _parakeet_load_harness(monkeypatch, [cpu], warm_up_fails=True)
    engine._load_model()  # warm-up would raise, but it is only run for CUDA
    assert created == [[cpu]] and engine.device_used == "cpu"


def test_parakeet_detect_device_asks_the_session():
    class Sess:
        def __init__(self, providers): self._p = providers
        def get_providers(self): return self._p
    class Asr:
        def __init__(self, providers): self._encoder = Sess(providers)
    class Model:
        def __init__(self, providers): self.asr = Asr(providers)
    cuda, cpu = "CUDAExecutionProvider", "CPUExecutionProvider"
    assert ParakeetEngine._detect_device(Model([cuda, cpu]), [cuda, cpu]) == "cuda"
    # Requested CUDA, onnxruntime quietly fell back: report what really runs.
    assert ParakeetEngine._detect_device(Model([cpu]), [cuda, cpu]) == "cpu"
    assert ParakeetEngine._detect_device(object(), [cpu]) == "cpu"
