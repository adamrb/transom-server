"""Noisy-recording path: noise measure, enhancement plumbing, engine wiring."""

import os
import stat
from pathlib import Path

import numpy as np
import pytest

from app.engines import enhance
from app.engines.enhance import Enhancer, EnhancePlan, cut_regions, noise_spread_db, speech_regions, write_wav
from app.engines.local_whisper import LocalWhisperEngine

SR = enhance.SAMPLE_RATE


def _quiet_room_speech(seconds=6.0, seed=0):
    """Bursts of a loud tone over a faint noise floor: large loud/quiet spread."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    floor = rng.normal(0, 0.003, t.size)
    gate = ((t % 1.0) < 0.5).astype(np.float32)  # half-second bursts
    return (floor + gate * 0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _car_speech(seconds=6.0, seed=0):
    """The same bursts under a noise floor nearly as loud as the speech."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * SR)) / SR
    floor = rng.normal(0, 0.25, t.size)
    gate = ((t % 1.0) < 0.5).astype(np.float32)
    return (floor + gate * 0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_noise_spread_separates_quiet_room_from_car():
    quiet = noise_spread_db(_quiet_room_speech())
    car = noise_spread_db(_car_speech())
    assert quiet > 25
    assert car < 10


def test_noise_spread_ignores_digital_silence_and_empty():
    assert noise_spread_db(np.zeros(0, dtype=np.float32)) == 0.0
    assert noise_spread_db(np.zeros(SR, dtype=np.float32)) == 0.0
    # Leading zeros (recorder started before the mic opened) don't inflate it.
    padded = np.concatenate([np.zeros(SR, dtype=np.float32), _car_speech()])
    assert noise_spread_db(padded) == pytest.approx(noise_spread_db(_car_speech()), abs=1.0)


def test_enhancer_policy_modes():
    assert Enhancer("auto", spread_db=15).wants(8.0)
    assert not Enhancer("auto", spread_db=15).wants(30.0)
    assert Enhancer("always").wants(30.0)
    assert not Enhancer("off").wants(1.0)
    assert not Enhancer("off").enabled
    with pytest.raises(ValueError):
        Enhancer("sometimes")


def test_enhancer_missing_binary_degrades_to_none(tmp_path, caplog):
    wav = tmp_path / "in.wav"
    write_wav(wav, _car_speech())
    enh = Enhancer("always", binary=str(tmp_path / "nope"))
    assert enh.plan(wav, tmp_path / "work") is None
    assert "not found" in caplog.text


def test_cut_regions_and_speech_region_merging(monkeypatch):
    wav = np.arange(SR * 4, dtype=np.float32)
    assert cut_regions(wav, []).size == 0
    cut = cut_regions(wav, [(0.0, 1.0), (3.0, 4.0)])
    assert cut.size == 2 * SR and cut[SR] == 3 * SR
    # Silero chunks closer than max_gap_s are merged into one region.
    fake_chunks = [
        {"start": 0, "end": SR},
        {"start": int(1.4 * SR), "end": 2 * SR},
        {"start": 5 * SR, "end": 6 * SR},
    ]
    monkeypatch.setattr("faster_whisper.vad.get_speech_timestamps", lambda wav, opts: fake_chunks)
    assert speech_regions(wav, max_gap_s=1.0, min_region_s=0.0) == [(0.0, 2.0), (5.0, 6.0)]
    # Short regions are stretched to min_region_s (clamped to the audio end)
    # and re-merged where the stretch made them touch.
    long_wav = np.zeros(SR * 40, dtype=np.float32)
    assert speech_regions(long_wav, max_gap_s=1.0, min_region_s=2.5) == [(0.0, 2.5), (5.0, 7.5)]
    assert speech_regions(long_wav, max_gap_s=1.0, min_region_s=6.0) == [(0.0, 11.0)]
    assert speech_regions(np.zeros(SR * 7, dtype=np.float32), max_gap_s=1.0, min_region_s=6.0) == [(0.0, 7.0)]
    # Defaults: gaps up to 10 s merge, regions run at least 10 s.
    assert speech_regions(long_wav) == [(0.0, 10.0)]


def _fake_deep_filter(tmp_path: Path) -> str:
    """A 'deep-filter' that copies its input to the output dir (deep-filter's
    own CLI contract: `deep-filter -o OUT_DIR INPUT.wav`)."""
    script = tmp_path / "deep-filter"
    script.write_text(
        "#!/bin/sh\nout=''\nwhile [ $# -gt 0 ]; do case \"$1\" in -o) out=$2; shift 2;; *) in=$1; shift;; esac; done\n"
        "cp \"$in\" \"$out/$(basename \"$in\")\"\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def test_enhancer_plan_runs_binary_and_locates_speech(tmp_path, monkeypatch):
    wav_path = tmp_path / "rec.wav"
    write_wav(wav_path, _car_speech())
    monkeypatch.setattr(
        enhance, "speech_regions", lambda wav, **kw: [(0.0, 0.5), (1.0, 1.5)]
    )
    enh = Enhancer("auto", spread_db=15, binary=_fake_deep_filter(tmp_path))
    plan = enh.plan(wav_path, tmp_path / "work")
    assert plan is not None
    assert plan.regions == [(0.0, 0.5), (1.0, 1.5)]
    assert plan.clip_timestamps == [0.0, 0.5, 1.0, 1.5]
    assert plan.enhanced_path.is_file()
    assert plan.enhanced.shape == plan.original.shape
    stats = plan.stats()
    assert stats["enhanced"] is True and stats["speech_regions"] == 2 and stats["speech_seconds"] == 1.0
    assert stats["noise_spread_db"] < 15


def test_enhancer_plan_skips_clean_recordings(tmp_path):
    wav_path = tmp_path / "rec.wav"
    write_wav(wav_path, _quiet_room_speech())
    enh = Enhancer("auto", spread_db=15, binary=_fake_deep_filter(tmp_path))
    assert enh.plan(wav_path, tmp_path / "work") is None


class _FakeSegment:
    def __init__(self, start, end, text):
        self.start, self.end, self.text, self.words = start, end, text, []


class _FakeInfo:
    duration = 10.0
    language = "en"


class _FakeWhisper:
    """Records the transcribe() kwargs and returns one segment."""

    def __init__(self):
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append(kwargs)
        return iter([_FakeSegment(0.0, 1.0, "hello")]), _FakeInfo()


def _plan(tmp_path, regions):
    enhanced = tmp_path / "enhanced.wav"
    enhanced.write_bytes(b"")
    wav = np.zeros(SR, dtype=np.float32)
    return EnhancePlan(original=wav, enhanced=wav, enhanced_path=enhanced, regions=regions,
                       noise_spread_db=8.1, seconds=1.5)


def test_whisper_engine_uses_clip_timestamps_from_plan(tmp_path, monkeypatch):
    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", vad_filter=True)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return _plan(tmp_path, [(0.0, 2.5), (4.0, 6.0)])

    engine.enhancer = _Enh()
    result = engine._transcribe_sync(tmp_path / "rec.mp3")
    kw = fake.calls[0]
    assert kw["vad_filter"] is False
    assert kw["clip_timestamps"] == [0.0, 2.5, 4.0, 6.0]
    assert result.stats["enhanced"] is True
    assert result.stats["noise_spread_db"] == 8.1
    assert result.stats["speech_seconds"] == 4.5
    assert result.text == "hello"


def test_whisper_engine_without_plan_keeps_vad(tmp_path, monkeypatch):
    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", vad_filter=True)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return None

    engine.enhancer = _Enh()
    result = engine._transcribe_sync(tmp_path / "rec.mp3")
    kw = fake.calls[0]
    assert kw["vad_filter"] is True
    assert kw["clip_timestamps"] == "0"
    assert "enhanced" not in result.stats


def test_whisper_engine_plan_without_regions_falls_back_to_vad(tmp_path, monkeypatch):
    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", vad_filter=True)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return _plan(tmp_path, [])

    engine.enhancer = _Enh()
    engine._transcribe_sync(tmp_path / "rec.mp3")
    kw = fake.calls[0]
    assert kw["vad_filter"] is True and kw["clip_timestamps"] == "0"


def test_whisper_engine_diarizes_on_enhanced_copy(tmp_path, monkeypatch):
    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", diarization=True, enhance_diarize=True)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)
    seen = []
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: seen.append(path) or [(0.0, 1.0, "A")])
    plan = _plan(tmp_path, [(0.0, 1.0)])

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return plan

    engine.enhancer = _Enh()
    engine._transcribe_sync(tmp_path / "rec.mp3")
    assert seen == [plan.enhanced_path]

    engine.enhance_diarize = False
    engine._transcribe_sync(tmp_path / "rec.mp3")
    assert seen[-1] == tmp_path / "rec.mp3"


def test_build_engine_passes_enhancer(monkeypatch):
    from app.config import Settings
    from app.engines import build_engine

    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENGINE", "local")
    monkeypatch.setenv("PB_STT_ENHANCE", "always")
    monkeypatch.setenv("PB_STT_ENHANCE_SPREAD_DB", "12.5")
    monkeypatch.setenv("PB_STT_ENHANCE_DIARIZE", "false")
    engine = build_engine(Settings())
    assert engine.enhancer is not None and engine.enhancer.mode == "always"
    assert engine.enhancer.spread_db == 12.5
    assert engine.enhance_diarize is False

    monkeypatch.setenv("PB_STT_ENHANCE", "off")
    assert build_engine(Settings()).enhancer is None


def test_settings_warn_when_binary_missing(monkeypatch, tmp_path):
    from app.config import Settings

    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENGINE", "local")
    monkeypatch.setenv("PB_STT_ENHANCE", "auto")
    monkeypatch.setenv("PB_STT_ENHANCE_BIN", str(tmp_path / "missing"))
    assert any("deep-filter" in w for w in Settings().validate())
    # Storage-only installs (transcription off) never hear about the binary.
    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "false")
    assert not any("deep-filter" in w for w in Settings().validate())
    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENHANCE", "off")
    assert not any("deep-filter" in w for w in Settings().validate())
    monkeypatch.setenv("PB_STT_ENHANCE", "maybe")
    assert any("PB_STT_ENHANCE=" in w for w in Settings().validate())


def test_parakeet_proxy_vad_segments_enhanced_and_cuts_original():
    """The proxy VAD finds speech on the enhanced copy and hands the ORIGINAL
    samples of those regions to the recognizer, clamped to the original's
    length."""
    pytest.importorskip("onnx_asr")
    from app.engines.parakeet import _ProxyVad

    original = np.arange(SR * 4, dtype=np.float32)  # sample value == index
    enhanced = np.zeros(SR * 4 + 7, dtype=np.float32)  # resampler drift: 7 extra samples

    class _InnerVad:
        def __init__(self):
            self.seen = None

        def segment_batch(self, waveforms, waveforms_len, sample_rate, **kwargs):
            self.seen = (waveforms.shape, int(waveforms_len[0]), kwargs)
            yield iter([(0, SR), (2 * SR, SR * 4 + 7)])

    class _Res:
        def __init__(self, text):
            self.text, self.timestamps, self.tokens, self.logprobs = text, None, None, None

    class _Asr:
        def __init__(self):
            self.batches = []

        def recognize_batch(self, waveforms, waveforms_len, **kwargs):
            self.batches.append([w[:n] for w, n in zip(waveforms, waveforms_len)])
            return [_Res(f"chunk{i}") for i in range(len(waveforms))]

    inner, asr = _InnerVad(), _Asr()
    proxy = _ProxyVad(inner, enhanced)
    out = proxy.recognize_batch(asr, original[None, :], np.array([original.size]), SR, {}, batch_size=4,
                                min_silence_duration_ms=600)
    results = list(next(iter(out)))
    assert inner.seen[0] == (1, enhanced.size) and inner.seen[2] == {"min_silence_duration_ms": 600}
    assert [(r.start, r.end, r.text) for r in results] == [(0.0, 1.0, "chunk0"), (2.0, 4.0, "chunk1")]
    cut = asr.batches[0]
    assert cut[0][0] == 0 and cut[0][-1] == SR - 1
    assert cut[1][0] == 2 * SR and cut[1][-1] == SR * 4 - 1  # clamped, not padded


def test_enhancer_plan_rejects_over_limit_before_enhancing(tmp_path):
    from app.engines.base import EngineError

    wav_path = tmp_path / "rec.wav"
    write_wav(wav_path, _car_speech(seconds=6.0))
    ran = tmp_path / "ran"
    script = tmp_path / "deep-filter"
    script.write_text(f"#!/bin/sh\ntouch {ran}\nexit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    enh = Enhancer("always", binary=str(script))
    with pytest.raises(EngineError, match="over the"):
        enh.plan(wav_path, tmp_path / "work", max_duration_s=5.0)
    assert not ran.exists()


def test_whisper_engine_vad_off_decodes_everything_but_still_diarizes_on_copy(tmp_path, monkeypatch):
    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", vad_filter=False, diarization=True)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)
    seen = []
    monkeypatch.setattr(engine, "_run_diarizer", lambda path: seen.append(path) or [(0.0, 1.0, "A")])
    plan = _plan(tmp_path, [(0.0, 2.5)])

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return plan

    engine.enhancer = _Enh()
    result = engine._transcribe_sync(tmp_path / "rec.mp3")
    kw = fake.calls[0]
    assert kw["vad_filter"] is False and kw["clip_timestamps"] == "0"
    assert seen == [plan.enhanced_path]
    assert result.stats["enhanced"] is True


def test_find_binary_resolves_explicit_relative_paths(tmp_path, monkeypatch):
    from app.engines.enhance import find_binary

    script = tmp_path / "deep-filter"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.chdir(tmp_path)
    assert find_binary("./deep-filter") == str(script.resolve())
    assert find_binary(str(script)) == str(script.resolve())
    assert find_binary("./missing") is None
    monkeypatch.setenv("PATH", str(tmp_path))
    assert find_binary(None) == str(script)


def test_whisper_engine_collects_alternates_for_consensus(tmp_path, monkeypatch):
    from app.engines import local_whisper as lw

    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", consensus=True, consensus_parakeet_model="pk-model",
                                consensus_atten_db=12.0)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)
    plan = _plan(tmp_path, [(0.0, 5.0)])
    partial = tmp_path / "partial-a12.wav"
    partial.write_bytes(b"")
    asked = []
    plan.partial_copy = lambda db: asked.append(db) or partial

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return plan

    class _FakeParakeet:
        def __init__(self, **kw):
            self.kw = kw
            self.loaded = False

        def _load_model(self):
            self.loaded = True

        def _decode(self, audio_path, progress, plan_):
            assert plan_ is plan and progress is None
            from app.engines.base import EngineResult
            return EngineResult(text="pk", segments=[_seg for _seg in [
                __import__("app.engines.base", fromlist=["Segment"]).Segment(0.0, 5.0, "parakeet heard this")]])

    monkeypatch.setattr("app.engines.parakeet.ParakeetEngine", _FakeParakeet)
    engine.enhancer = _Enh()
    result = engine._transcribe_sync(tmp_path / "rec.mp3")
    assert asked == [12.0]
    assert [a.name.split(" ")[0] for a in result.alternates] == ["whisper", "parakeet"]
    assert result.alternates[0].segments[0].text == "hello"  # the fake model's answer on the partial copy
    assert result.alternates[1].segments[0].text == "parakeet heard this"
    assert result.stats["alternates_seconds"] >= 0 and len(result.stats["alternates"]) == 2
    # The partial-copy decode went to the same clips, without VAD.
    assert fake.calls[1]["clip_timestamps"] == [0.0, 5.0] and fake.calls[1]["vad_filter"] is False
    # Parakeet was built for the CPU, without diarization, and is kept warm.
    pk = engine._alt_parakeet
    assert pk.kw["device"] == "cpu" and pk.kw["diarization"] is False and pk.kw["model"] == "pk-model" and pk.loaded
    engine._transcribe_sync(tmp_path / "rec.mp3")
    assert engine._alt_parakeet is pk


def test_whisper_engine_alternate_failures_are_skipped(tmp_path, monkeypatch):
    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", consensus=True, consensus_parakeet_model=None, consensus_atten_db=6.0)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)
    plan = _plan(tmp_path, [(0.0, 5.0)])

    def boom(db):
        raise RuntimeError("deep-filter exploded")

    plan.partial_copy = boom

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return plan

    engine.enhancer = _Enh()
    result = engine._transcribe_sync(tmp_path / "rec.mp3")
    assert result.alternates == [] and "alternates" not in result.stats and result.text == "hello"


def test_whisper_engine_no_alternates_on_clean_recordings(tmp_path, monkeypatch):
    fake = _FakeWhisper()
    engine = LocalWhisperEngine(model="tiny", consensus=True)
    monkeypatch.setattr(engine, "_load_model", lambda: fake)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)

    class _Enh:
        def plan(self, path, work_dir, max_duration_s=None):
            return None

    engine.enhancer = _Enh()
    result = engine._transcribe_sync(tmp_path / "rec.mp3")
    assert result.alternates == [] and len(fake.calls) == 1


def test_enhance_partial_copy_passes_attenuation_flag(tmp_path):
    from app.engines.enhance import EnhancePlan, enhance

    seen = tmp_path / "args"
    script = tmp_path / "deep-filter"
    script.write_text(
        "#!/bin/sh\necho \"$@\" >> " + str(seen) + "\nout=''\nwhile [ $# -gt 0 ]; do case \"$1\" in -o) out=$2; shift 2;; "
        "-a) shift 2;; -D) shift;; *) in=$1; shift;; esac; done\ncp \"$in\" \"$out/$(basename \"$in\")\"\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    wav = _car_speech(seconds=2.0)
    work = tmp_path / "work"
    full = enhance(wav, work, str(script))
    assert full.shape == wav.shape
    plan = EnhancePlan(original=wav, enhanced=full, enhanced_path=work / "enhanced.wav", regions=[(0.0, 2.0)],
                       noise_spread_db=8.0, seconds=1.0, work_dir=work, binary=str(script))
    partial = plan.partial_copy(12.0)
    assert partial.is_file() and partial.name == "partial-a12.wav"
    lines = seen.read_text().splitlines()
    assert "-a" not in lines[0].split() and "-a 12" in lines[1] and "-D" in lines[1].split()
    # The plan built by Enhancer.plan carries what partial_copy needs.
    assert EnhancePlan(wav, full, work / "e.wav", [], 8.0, 1.0).work_dir is None
    with pytest.raises(Exception):
        EnhancePlan(wav, full, work / "e.wav", [], 8.0, 1.0).partial_copy(12.0)


def test_build_engine_enables_consensus_only_with_enhancer_and_llm(monkeypatch):
    from app.config import Settings
    from app.engines import build_engine

    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENGINE", "local")
    monkeypatch.setenv("PB_STT_ENHANCE", "auto")
    monkeypatch.setenv("PB_STT_CONSENSUS", "auto")
    monkeypatch.setenv("PB_CLEANUP_BASE_URL", "http://llm/v1")
    monkeypatch.setenv("PB_CLEANUP_MODEL", "m")
    monkeypatch.setenv("PB_STT_CONSENSUS_ATTEN_DB", "9")
    engine = build_engine(Settings())
    assert engine.consensus is True and engine.consensus_atten_db == 9.0
    assert engine.consensus_parakeet_model == "nemo-parakeet-tdt-0.6b-v2"
    monkeypatch.setenv("PB_STT_CONSENSUS_ATTEN_DB", "off")
    monkeypatch.setenv("PB_STT_CONSENSUS_PARAKEET_MODEL", "off")
    engine = build_engine(Settings())
    assert engine.consensus_atten_db is None and engine.consensus_parakeet_model is None
    monkeypatch.setenv("PB_STT_CONSENSUS", "off")
    assert build_engine(Settings()).consensus is False
    monkeypatch.setenv("PB_STT_CONSENSUS", "auto")
    monkeypatch.delenv("PB_CLEANUP_BASE_URL")
    monkeypatch.delenv("PB_SUMMARY_BASE_URL", raising=False)
    s = Settings()
    assert build_engine(s).consensus is False
    assert any("PB_STT_CONSENSUS=auto needs" in w for w in s.validate())
