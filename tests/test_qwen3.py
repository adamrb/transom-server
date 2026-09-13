"""Qwen3-ASR engine: chunking, decoding into segments and words, alternates,
factory wiring — with the transformers models faked."""

import asyncio
from pathlib import Path

import numpy as np
import pytest

from app.engines import enhance
from app.engines.base import EngineResult, Segment
from app.engines.enhance import EnhancePlan, speech_chunks
from app.engines.qwen3_asr import Qwen3AsrEngine

SR = 16000


def test_speech_chunks_merge_and_split(monkeypatch):
    wav = np.zeros(SR * 100, dtype=np.float32)
    fake = [{"start": 0, "end": 5 * SR}, {"start": 6 * SR, "end": 20 * SR}, {"start": 21 * SR, "end": 45 * SR},
            {"start": 50 * SR, "end": 95 * SR}]
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda wav, opts: fake)
    got = speech_chunks(wav, max_s=30.0)
    # 0-5 and 6-20 merge (20 s span); 21-45 would push past 30 so starts anew;
    # 50-95 is one 45 s stretch and is split at 30 s.
    assert got == [(0.0, 20.0), (21.0, 45.0), (50.0, 80.0), (80.0, 95.0)]
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda wav, opts: [])
    assert speech_chunks(wav, 30.0) == []


class _FakeProcessor:
    def __init__(self):
        self.calls = []

    def apply_chat_template(self, conversations, **kw):
        self.calls.append((len(conversations), conversations, kw))
        return _Inputs(len(conversations))

    def decode(self, gen, return_format="parsed"):
        n = gen.shape[0]
        return [{"transcription": f"chunk {i} text", "language": "English"} for i in range(n)]


class _Inputs(dict):
    def __init__(self, n):
        super().__init__(input_ids=_Arr((n, 7)))

    def to(self, *a, **k):
        return self


class _Arr:
    def __init__(self, shape):
        self.shape = shape

    def __getitem__(self, item):
        return self


class _FakeModel:
    device = "cuda"
    dtype = "bf16"

    def generate(self, **kw):
        n = kw["input_ids"].shape[0]
        return _Gen(n)


class _Gen:
    def __init__(self, n):
        self.shape = (n, 20)

    def __getitem__(self, item):
        return self


def _engine(monkeypatch, **kw):
    engine = Qwen3AsrEngine(model="fake/qwen", aligner=None, **kw)
    engine._processor = _FakeProcessor()
    engine._model = _FakeModel()
    engine.device_used = "cuda"
    monkeypatch.setattr(engine, "_load_model", lambda: engine._model)
    monkeypatch.setattr("app.engines.qwen3_asr.probe_duration", lambda p: 60.0)
    wav = np.zeros(SR * 60, dtype=np.float32)
    monkeypatch.setattr("app.engines.qwen3_asr.decode_waveform", lambda p: wav)
    monkeypatch.setattr("app.engines.qwen3_asr.speech_chunks", lambda w, s: [(0.0, 10.0), (12.0, 30.0), (31.0, 55.0)])
    import sys, types
    sys.modules.setdefault("torch", types.SimpleNamespace(inference_mode=lambda: _Ctx(), cuda=types.SimpleNamespace(is_available=lambda: False)))
    return engine


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_qwen3_decodes_chunks_into_segments(monkeypatch):
    engine = _engine(monkeypatch, batch_size=2, language="en")
    result = asyncio.run(engine.transcribe(Path("a.mp3"), hotwords="Morgan, Priya"))
    assert [s.text for s in result.segments] == ["chunk 0 text", "chunk 1 text", "chunk 0 text"]  # 2 batches
    assert [(s.start, s.end) for s in result.segments] == [(0.0, 10.0), (12.0, 30.0), (31.0, 55.0)]
    assert result.language == "en" and result.duration == 60.0 and result.model == "fake/qwen"
    assert result.stats["engine"] == "qwen3" and result.stats["chunks"] == 3 and result.stats["device"] == "cuda"
    # Two batches of sizes 2 and 1; the vocabulary rides in as the system
    # message and the forced language as the assistant prefill.
    calls = engine._processor.calls
    assert [c[0] for c in calls] == [2, 1]
    conv = calls[0][1][0]
    assert conv[0]["role"] == "system" and conv[0]["content"][0]["text"] == "Vocabulary: Morgan, Priya."
    assert conv[1]["role"] == "user" and conv[1]["content"][0]["type"] == "audio"
    assert conv[2] == {"role": "assistant", "content": [{"type": "text", "text": "language English<asr_text>"}]}
    assert calls[0][2]["continue_final_message"] is True
    # No vocabulary, no forced language: no system turn, empty prefill.
    engine2 = _engine(monkeypatch)
    asyncio.run(engine2.transcribe(Path("a.mp3")))
    conv = engine2._processor.calls[0][1][0]
    assert conv[0]["role"] == "user" and conv[-1]["content"][0]["text"] == ""


def test_qwen3_words_from_aligner_feed_diarization(monkeypatch):
    engine = _engine(monkeypatch, diarization=True)
    engine._aligner = object()
    # The aligner returns normalized tokens ("0" for "0", but imagine "314" for
    # "3.14"); the words handed on carry the recognized text's own tokens.
    monkeypatch.setattr(engine, "_align", lambda clip, text, lang: [(0.5, 1.0, "chunk"), (1.0, 1.5, "zero"), (1.5, 2.0, "text")])
    seen = {}

    def fake_diar(path, segments, words):
        seen["words"] = list(words)
        for s in segments:
            s.speaker = "Speaker 1"

    monkeypatch.setattr(engine, "_apply_diarization", fake_diar)
    result = asyncio.run(engine.transcribe(Path("a.mp3")))
    # Word times are absolute (chunk start + offset), text is the original token,
    # and each word is tagged with its segment index.
    assert seen["words"][0] == (0.5, 1.0, " chunk", 0)
    assert seen["words"][1] == (1.0, 1.5, " 0", 0)
    assert seen["words"][3] == (12.5, 13.0, " chunk", 1)
    assert all(s.speaker == "Speaker 1" for s in result.segments)
    assert result.text.startswith("Speaker 1: chunk 0 text")


def test_qwen3_unaligned_or_mismatched_chunks_survive_diarization(monkeypatch):
    """A chunk the aligner could not time (or timed with a different token
    count) is kept as one segment-level word, so the mixin's word-level
    rebuild does not drop it."""
    from app.engines.qwen3_asr import Qwen3AsrEngine as E

    assert E._words_for(3, 10.0, 15.0, "Hello, world! 3.14", []) == [(10.0, 15.0, " Hello, world! 3.14", 3)]
    assert E._words_for(3, 10.0, 15.0, "Hello, world! 3.14", [(0, 1, "hello"), (1, 2, "world"), (2, 3, "3"), (3, 4, "14")]) \
        == [(10.0, 15.0, " Hello, world! 3.14", 3)]
    assert E._words_for(0, 10.0, 15.0, "Hello, world!", [(0.0, 1.0, "hello"), (1.0, 2.0, "world")]) \
        == [(10.0, 11.0, " Hello,", 0), (11.0, 12.0, " world!", 0)]
    # End to end through the real mixin: chunk 1 aligned, chunk 2 not.
    engine = _engine(monkeypatch, diarization=True)
    engine._aligner = object()
    calls = {"n": 0}

    def align(clip, text, lang):
        calls["n"] += 1
        return [(0.1, 0.5, "chunk"), (0.5, 0.9, "x"), (0.9, 1.3, "text")] if calls["n"] == 1 else []

    monkeypatch.setattr(engine, "_align", align)
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: [(0.0, 11.0, "A"), (11.0, 60.0, "B")])
    result = asyncio.run(engine.transcribe(Path("a.mp3")))
    texts = [s.text for s in result.segments]
    assert "chunk 0 text" in texts[0] or texts[0].startswith("chunk")
    assert sum(1 for t in texts if "chunk" in t) >= 3  # all three chunks still present
    assert {s.speaker for s in result.segments} == {"Speaker 1", "Speaker 2"}


def test_qwen3_collects_alternates_on_noisy_recordings(monkeypatch, tmp_path):
    class _Helper:
        model_name = "large-v3"
        language = None
        beam_size = 5
        consensus_parakeet_model = "pk"

        def _load_model(self):
            return self

        def _fit_hotwords(self, model, hw):
            return hw

        def transcribe(self, path, **kw):
            self.kw = kw
            return iter([_S(0.0, 5.0, "whisper heard this")]), None

        def _parakeet(self):
            return self

        def _decode(self, path, progress, plan):
            return EngineResult(text="pk", segments=[Segment(0.0, 5.0, "parakeet heard this")])

    class _S:
        def __init__(self, s, e, t):
            self.start, self.end, self.text = s, e, t

    helper = _Helper()
    engine = _engine(monkeypatch, consensus=True, alternates_engine=helper)
    enhanced = tmp_path / "enhanced.wav"
    enhanced.write_bytes(b"")
    wav = np.zeros(SR * 60, dtype=np.float32)
    plan = EnhancePlan(original=wav, enhanced=wav, enhanced_path=enhanced, regions=[(0.0, 55.0)],
                       noise_spread_db=8.1, seconds=1.0)

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return plan

    engine.enhancer = _Enh()
    result = asyncio.run(engine.transcribe(Path("a.mp3"), hotwords="Morgan"))
    assert [a.name.split(" ")[0] for a in result.alternates] == ["whisper", "parakeet"]
    assert helper.kw["clip_timestamps"] == [0.0, 55.0] and helper.kw["vad_filter"] is False
    assert helper.kw["hotwords"] == "Morgan"
    assert result.stats["enhanced"] is True and len(result.stats["alternates"]) == 2


def test_qwen3_rejects_over_limit_audio(monkeypatch):
    engine = _engine(monkeypatch, max_duration_s=10)
    from app.engines.base import EngineError
    with pytest.raises(EngineError):
        asyncio.run(engine.transcribe(Path("a.mp3")))


def test_build_engine_qwen3(monkeypatch):
    from app.config import Settings
    from app.engines import build_engine
    from app.engines.local_whisper import LocalWhisperEngine

    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENGINE", "qwen3")
    monkeypatch.setenv("PB_STT_MODEL", "large-v3")
    monkeypatch.setenv("PB_STT_QWEN_CHUNK_S", "25")
    monkeypatch.setenv("PB_STT_QWEN_BATCH", "8")
    monkeypatch.setenv("PB_STT_ENHANCE", "auto")
    monkeypatch.setenv("PB_STT_CONSENSUS", "auto")
    monkeypatch.setenv("PB_CLEANUP_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("PB_CLEANUP_MODEL", "m")
    engine = build_engine(Settings())
    assert isinstance(engine, Qwen3AsrEngine)
    assert engine.chunk_s == 25.0 and engine.batch_size == 8 and engine.aligner_name == "Qwen/Qwen3-ForcedAligner-0.6B-hf"
    assert engine.consensus is True and isinstance(engine.alternates_engine, LocalWhisperEngine)
    assert engine.alternates_engine.model_name == "large-v3" and engine.alternates_engine.diarization is False
    monkeypatch.setenv("PB_STT_QWEN_ALIGNER", "off")
    monkeypatch.setenv("PB_STT_CONSENSUS", "off")
    engine = build_engine(Settings())
    assert engine.aligner_name is None and engine.consensus is False and engine.alternates_engine is None


def test_qwen3_cohere_alternate_uses_same_chunks(monkeypatch, tmp_path):
    """Cohere decodes the primary's silence-cut chunks so its segments carry
    the chunk times; batches fold multi-piece outputs back per clip."""
    import sys, types
    from app.engines.qwen3_asr import Qwen3AsrEngine

    engine = Qwen3AsrEngine(model="m", aligner=None, consensus=True, consensus_cohere_model="Cohere/x", batch_size=2)
    engine.device_used = "cuda"

    class _Inputs(dict):
        def to(self, *a, **k):
            return self

    class _Proc:
        def __call__(self, clips, sampling_rate, return_tensors, language):
            assert language == "en" and sampling_rate == SR
            d = _Inputs(input_features=len(clips))
            d["audio_chunk_index"] = [[i] for i in range(len(clips))]
            return d

        def batch_decode(self, out, skip_special_tokens=True):
            return [f"cohere {i}" for i in range(out)]

    class _Model:
        device, dtype = "cuda", "bf16"

        def generate(self, input_features, max_new_tokens):
            return input_features  # count stands in for the generated ids

    engine._cohere, engine._cohere_processor = _Model(), _Proc()
    monkeypatch.setitem(sys.modules, "torch", types.SimpleNamespace(inference_mode=lambda: _Ctx()))
    wav = np.zeros(SR * 60, dtype=np.float32)
    segs = engine._cohere_segments(wav, [(0.0, 10.0), (12.0, 30.0), (31.0, 55.0)], "en")
    assert [(s.start, s.end, s.text) for s in segs] == [(0.0, 10.0, "cohere 0"), (12.0, 30.0, "cohere 1"), (31.0, 55.0, "cohere 0")]


def test_build_engine_qwen3_cohere_setting(monkeypatch):
    from app.config import Settings
    from app.engines import build_engine

    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENGINE", "qwen3")
    monkeypatch.setenv("PB_STT_ENHANCE", "auto")
    monkeypatch.setenv("PB_STT_CONSENSUS", "auto")
    monkeypatch.setenv("PB_CLEANUP_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("PB_CLEANUP_MODEL", "m")
    assert build_engine(Settings()).consensus_cohere_model == "CohereLabs/cohere-transcribe-03-2026"
    monkeypatch.setenv("PB_STT_CONSENSUS_COHERE_MODEL", "off")
    assert build_engine(Settings()).consensus_cohere_model is None
    monkeypatch.delenv("PB_STT_CONSENSUS_COHERE_MODEL")
    monkeypatch.setenv("PB_STT_CONSENSUS", "off")
    assert build_engine(Settings()).consensus_cohere_model is None


def test_qwen3_cohere_skipped_for_unsupported_language(monkeypatch, tmp_path):
    from app.engines.qwen3_asr import Qwen3AsrEngine

    class _Helper:
        model_name, language, beam_size, consensus_parakeet_model = "w", None, 5, None

        def _load_model(self):
            raise RuntimeError("whisper unavailable in this test")

    engine = Qwen3AsrEngine(model="m", aligner=None, consensus=True, alternates_engine=_Helper(),
                            consensus_cohere_model="Cohere/x")
    called = []
    monkeypatch.setattr(engine, "_cohere_segments", lambda wav, chunks, lang: called.append(lang) or [])
    monkeypatch.setattr("app.engines.qwen3_asr.speech_chunks", lambda w, s: [(0.0, 1.0)])
    wav = np.zeros(SR, dtype=np.float32)
    plan = EnhancePlan(original=wav, enhanced=wav, enhanced_path=tmp_path / "e.wav", regions=[(0.0, 1.0)],
                       noise_spread_db=8.0, seconds=1.0)
    engine._alternates(Path("a.mp3"), None, plan, "sv")   # Swedish: Qwen knows it, Cohere does not
    assert called == []
    engine._alternates(Path("a.mp3"), None, plan, "de")
    assert called == ["de"]
    engine._alternates(Path("a.mp3"), None, plan, None)   # nothing detected, nothing forced: skipped
    assert called == ["de"]
