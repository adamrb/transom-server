"""Worker mode: the OpenAI-compatible transcription endpoint, the fallback
engine, remote result parsing, and shared-GPU housekeeping."""

import asyncio
import json
import os
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="pb-test-")
os.environ.update(
    PB_DATA_DIR=_TMP,
    PB_AUTH_TOKENS="test-token-1",
    PB_TRANSCRIBE_ENABLED="false",
    PB_MAX_UPLOAD_MB="1",
)

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings
from app.engines import FallbackEngine, build_engine
from app.engines.base import Alternate, EngineError, EngineResult, Segment
from app.engines.local_whisper import LocalWhisperEngine
from app.engines.openai_compat import OpenAICompatEngine

AUTH = {"Authorization": "Bearer test-token-1"}


class _Engine:
    name = "fake"
    language = None

    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    async def transcribe(self, audio_path, hotwords=None, progress=None):
        self.calls.append((Path(audio_path).suffix, hotwords, Path(audio_path).stat().st_size))
        if self.error:
            raise self.error
        return self.result


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def _result():
    return EngineResult(
        text="Speaker 1: hello there\nSpeaker 2: hi", duration=4.0, language="en", model="m",
        segments=[Segment(0.0, 2.0, "hello there", "Speaker 1"), Segment(2.0, 4.0, "hi", "Speaker 2")],
        stats={"engine": "local", "enhanced": True},
    )


def test_transcription_endpoint_requires_auth(client):
    r = client.post("/v1/audio/transcriptions", files={"file": ("a.mp3", b"xx", "audio/mpeg")})
    assert r.status_code == 401
    r = client.post("/api/v1/audio/transcriptions", files={"file": ("a.mp3", b"xx", "audio/mpeg")})
    assert r.status_code == 401


def test_transcription_endpoint_503_without_engine(client):
    assert main.transcriber.engine is None
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"xx", "audio/mpeg")})
    assert r.status_code == 503


def test_transcription_endpoint_verbose_json_with_speakers(client, monkeypatch):
    engine = _Engine(result=_result())
    monkeypatch.setattr(main.transcriber, "engine", engine)
    r = client.post(
        "/v1/audio/transcriptions", headers=AUTH,
        files={"file": ("rec.mp3", b"\xff\xfb" * 100, "audio/mpeg")},
        data={"model": "whisper-1", "response_format": "verbose_json", "prompt": "Morgan, Priya"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"].startswith("Speaker 1: hello there")
    assert body["duration"] == 4.0 and body["language"] == "en"
    assert body["segments"] == [
        {"id": 0, "start": 0.0, "end": 2.0, "text": "hello there", "speaker": "Speaker 1"},
        {"id": 1, "start": 2.0, "end": 4.0, "text": "hi", "speaker": "Speaker 2"},
    ]
    assert body["stats"]["enhanced"] is True and "consensus" not in body
    suffix, hotwords, size = engine.calls[0]
    assert suffix == ".mp3" and hotwords == "Morgan, Priya" and size == 200
    # The temp file is gone afterwards.
    assert not list(Path(tempfile.gettempdir()).glob("pb-stt-*"))


def test_transcription_endpoint_json_text_and_errors(client, monkeypatch):
    engine = _Engine(result=_result())
    monkeypatch.setattr(main.transcriber, "engine", engine)
    r = client.post("/api/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"x", "audio/mpeg")})
    assert r.status_code == 200 and r.json() == {"text": _result().text}
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"x", "audio/mpeg")},
                    data={"response_format": "text"})
    assert r.status_code == 200 and r.text == _result().text
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"x", "audio/mpeg")},
                    data={"response_format": "srt"})
    assert r.status_code == 400
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"", "audio/mpeg")})
    assert r.status_code == 400
    r = client.post("/v1/audio/transcriptions", headers=AUTH,
                    files={"file": ("a.mp3", b"x" * (1024 * 1024 + 1), "audio/mpeg")})
    assert r.status_code == 413
    monkeypatch.setattr(main.transcriber, "engine", _Engine(error=EngineError("GPU on fire")))
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"x", "audio/mpeg")})
    assert r.status_code == 502 and "GPU on fire" in r.json()["detail"]


def test_transcription_endpoint_runs_consensus_when_alternates_exist(client, monkeypatch):
    result = _result()
    result.alternates = [Alternate("parakeet", [Segment(0.0, 2.0, "hello there!")])]
    monkeypatch.setattr(main.transcriber, "engine", _Engine(result=result))

    async def fake_consensus(segments, alternates):
        from app.consensus import ConsensusResult
        segments[0].text = "hello there!"
        return ConsensusResult(changed=1, calls=1, systems=[a.name for a in alternates])

    monkeypatch.setattr(main.transcriber, "_consensus", fake_consensus)
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"x", "audio/mpeg")},
                    data={"response_format": "verbose_json"})
    body = r.json()
    assert body["segments"][0]["text"] == "hello there!"
    assert body["consensus"]["segments_changed"] == 1 and body["consensus"]["systems"] == ["parakeet"]
    assert body["text"].startswith("Speaker 1: hello there!")


# ── remote result parsing ─────────────────────────────────────────────────────

def test_openai_engine_parses_speakers_and_remote_stats():
    engine = OpenAICompatEngine(base_url="http://x/v1", model="whisper-1")
    result = engine._parse(
        {"text": "x", "language": "en", "duration": 10.0,
         "segments": [{"start": 0, "end": 5, "text": " hello ", "speaker": "Speaker 1"},
                      {"start": 5, "end": 10, "text": "world"}],
         "stats": {"engine": "local", "enhanced": True, "noise_spread_db": 8.1},
         "consensus": {"segments_changed": 3}},
        elapsed=2.0,
    )
    assert [s.speaker for s in result.segments] == ["Speaker 1", None]
    assert result.stats["remote"]["noise_spread_db"] == 8.1
    assert result.stats["remote_consensus"] == {"segments_changed": 3}
    assert result.text.startswith("\nSpeaker 1: hello") or "Speaker 1: hello" in result.text


# ── fallback engine ───────────────────────────────────────────────────────────

def test_fallback_engine_uses_fallback_on_primary_failure():
    primary = _Engine(error=EngineError("tunnel down"))
    primary.name = "openai"
    fallback = _Engine(result=_result())
    fallback.name = "local"
    engine = FallbackEngine(primary, fallback)
    assert engine.name == "openai"
    result = asyncio.run(engine.transcribe(Path(__file__), hotwords="hw"))
    assert result.text.startswith("Speaker 1") and len(primary.calls) == 1 and len(fallback.calls) == 1
    assert result.stats["fallback_from"] == "openai" and "tunnel down" in result.stats["fallback_reason"]
    # Healthy primary: fallback untouched, no fallback stats.
    primary2 = _Engine(result=_result())
    fallback2 = _Engine(result=_result())
    r2 = asyncio.run(FallbackEngine(primary2, fallback2).transcribe(Path(__file__)))
    assert "fallback_from" not in r2.stats and fallback2.calls == []


def test_build_engine_wraps_fallback(monkeypatch):
    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENGINE", "openai")
    monkeypatch.setenv("PB_TRANSCRIBE_BASE_URL", "http://worker/v1")
    monkeypatch.setenv("PB_STT_FALLBACK_ENGINE", "local")
    monkeypatch.setenv("PB_STT_MODEL", "tiny")
    engine = build_engine(Settings())
    assert isinstance(engine, FallbackEngine)
    assert isinstance(engine.primary, OpenAICompatEngine) and isinstance(engine.fallback, LocalWhisperEngine)
    assert engine.name == "openai" and engine.fallback.model_name == "tiny"
    # Same engine twice, or an unknown name, means no wrapper.
    monkeypatch.setenv("PB_STT_FALLBACK_ENGINE", "openai")
    assert isinstance(build_engine(Settings()), OpenAICompatEngine)
    monkeypatch.setenv("PB_STT_FALLBACK_ENGINE", "cloud9")
    assert isinstance(build_engine(Settings()), OpenAICompatEngine)
    assert any("PB_STT_FALLBACK_ENGINE=" in w for w in Settings().validate())
    monkeypatch.setenv("PB_STT_FALLBACK_ENGINE", "")
    assert isinstance(build_engine(Settings()), OpenAICompatEngine)


# ── shared-GPU housekeeping ───────────────────────────────────────────────────

class _FakeSegment:
    def __init__(self, start, end, text):
        self.start, self.end, self.text, self.words = start, end, text, []


class _FakeInfo:
    duration = 10.0
    language = "en"


class _FakeWhisper:
    def transcribe(self, path, **kwargs):
        return iter([_FakeSegment(0.0, 1.0, "hello")]), _FakeInfo()


def test_idle_unload_drops_models_after_quiet_period(tmp_path, monkeypatch):
    engine = LocalWhisperEngine(model="tiny", idle_unload_s=1)
    loads = []

    def fake_load():
        if engine._model is None:
            loads.append(1)
            engine._model = _FakeWhisper()
        return engine._model

    monkeypatch.setattr(engine, "_load_model", fake_load)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)

    async def run():
        r1 = await engine.transcribe(tmp_path / "a.mp3")
        assert r1.text == "hello" and engine._model is not None
        await asyncio.sleep(1.6)
        assert engine._model is None  # unloaded while idle
        r2 = await engine.transcribe(tmp_path / "b.mp3")
        assert r2.text == "hello" and len(loads) == 2

    asyncio.run(run())


def test_no_idle_unload_by_default(tmp_path, monkeypatch):
    engine = LocalWhisperEngine(model="tiny")
    monkeypatch.setattr(engine, "_load_model", lambda: _FakeWhisper())
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 10.0)

    async def run():
        await engine.transcribe(tmp_path / "a.mp3")
        assert engine._idle_task is None

    asyncio.run(run())


def test_low_vram_loads_whisper_on_cpu(monkeypatch):
    import app.engines.local_whisper as lw

    created = []

    class _WM:
        def __init__(self, name, device, compute_type, cpu_threads):
            created.append((device, compute_type))

    import types, sys
    fake_mod = types.SimpleNamespace(WhisperModel=_WM)
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)
    monkeypatch.setattr(lw, "gpu_free_mb", lambda: 1500)
    engine = LocalWhisperEngine(model="large-v3", device="cuda", compute_type="float16", min_free_vram_mb=6000,
                                diarization=True)
    spawned = []
    monkeypatch.setattr(engine, "_ensure_diar_worker", lambda: spawned.append(engine._diar_device()))
    engine._load_model()
    assert created == [("cpu", "auto")] and engine.device_used == "cpu"
    # The pyannote worker, which would have followed whisper's device, is kept off the busy GPU too.
    assert spawned == ["cpu"]
    # Enough memory: the GPU is used as configured; no threshold: never checked.
    monkeypatch.setattr(lw, "gpu_free_mb", lambda: 20000)
    engine2 = LocalWhisperEngine(model="large-v3", device="cuda", compute_type="float16", min_free_vram_mb=6000)
    engine2._load_model()
    assert created[-1] == ("cuda", "float16") and engine2.device_used == "cuda"
    monkeypatch.setattr(lw, "gpu_free_mb", lambda: (_ for _ in ()).throw(AssertionError("must not be called")))
    LocalWhisperEngine(model="large-v3", device="cuda", compute_type="float16")._load_model()


def test_gpu_free_mb_handles_missing_nvidia_smi(monkeypatch):
    import app.engines.local_whisper as lw

    def boom(*a, **k):
        raise OSError("no nvidia-smi")

    monkeypatch.setattr(lw.subprocess, "run", boom)
    assert lw.gpu_free_mb() is None


def test_gpu_free_mb_queries_the_visible_device(monkeypatch):
    import subprocess as sp

    import app.engines.local_whisper as lw

    seen = []

    class _Out:
        returncode = 0
        stdout = "21000\n"

    def fake_run(cmd, **kw):
        seen.append(cmd)
        return _Out()

    monkeypatch.setattr(lw.subprocess, "run", fake_run)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    assert lw.gpu_free_mb() == 21000 and "--id=0" in seen[-1]
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "1,2")
    lw.gpu_free_mb()
    assert "--id=1" in seen[-1]
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "GPU-c8523d25-d1d0-d4ce-1010-0d35a09b07fb")
    lw.gpu_free_mb()
    assert "--id=GPU-c8523d25-d1d0-d4ce-1010-0d35a09b07fb" in seen[-1]


def test_transcription_endpoint_streams_heartbeats_and_late_errors(client, monkeypatch):
    """A slow engine gets keepalive whitespace ahead of the JSON; a failure
    after the first byte arrives as an error object, which the openai engine
    turns into an EngineError."""
    monkeypatch.setattr(main, "TRANSCRIBE_HEARTBEAT_S", 0.05)

    class _Slow(_Engine):
        async def transcribe(self, audio_path, hotwords=None, progress=None):
            await asyncio.sleep(0.2)
            return await super().transcribe(audio_path, hotwords, progress)

    monkeypatch.setattr(main.transcriber, "engine", _Slow(result=_result()))
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"x", "audio/mpeg")},
                    data={"response_format": "verbose_json"})
    assert r.status_code == 200
    assert r.text.startswith(" ") and r.json()["duration"] == 4.0  # heartbeats, then valid JSON

    class _SlowFail(_Engine):
        async def transcribe(self, audio_path, hotwords=None, progress=None):
            await asyncio.sleep(0.2)
            raise EngineError("worker exploded")

    monkeypatch.setattr(main.transcriber, "engine", _SlowFail())
    r = client.post("/v1/audio/transcriptions", headers=AUTH, files={"file": ("a.mp3", b"x", "audio/mpeg")},
                    data={"response_format": "verbose_json"})
    assert r.status_code == 200 and "worker exploded" in r.json()["error"]

    import httpx
    engine = OpenAICompatEngine(base_url="http://w/v1")
    resp = httpx.Response(200, text='  {"error": "transcription failed: worker exploded"}')
    body = json.loads(resp.text.strip())
    assert "error" in body and "text" not in body  # what the engine refuses


def test_openai_engine_accepts_heartbeat_prefixed_json(monkeypatch):
    import httpx

    engine = OpenAICompatEngine(base_url="http://w/v1", model="whisper-1")

    def handler(request):
        return httpx.Response(200, text='   \n {"text": "hi", "segments": [{"start": 0, "end": 1, "text": "hi"}]}')

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    result = asyncio.run(engine.transcribe(Path(__file__)))
    assert result.text == "hi" and result.segments[0].end == 1

    def failing(request):
        return httpx.Response(200, text=' {"error": "transcription failed: boom"}')

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(failing), **kw))
    with pytest.raises(EngineError, match="boom"):
        asyncio.run(engine.transcribe(Path(__file__)))


def test_consensus_parakeet_device_is_configurable(monkeypatch):
    monkeypatch.setenv("PB_TRANSCRIBE_ENABLED", "true")
    monkeypatch.setenv("PB_STT_ENGINE", "local")
    monkeypatch.setenv("PB_STT_CONSENSUS_PARAKEET_DEVICE", "cuda")
    assert build_engine(Settings()).consensus_parakeet_device == "cuda"
    monkeypatch.delenv("PB_STT_CONSENSUS_PARAKEET_DEVICE")
    assert build_engine(Settings()).consensus_parakeet_device == "cpu"


def test_openai_engine_rejects_empty_or_non_object_bodies(monkeypatch):
    import httpx

    engine = OpenAICompatEngine(base_url="http://w/v1")
    real = httpx.AsyncClient
    for text in ("   ", "", "[1, 2]"):
        monkeypatch.setattr(httpx, "AsyncClient",
                            lambda **kw: real(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=text)), **kw))
        with pytest.raises(EngineError):
            asyncio.run(engine.transcribe(Path(__file__)))


def test_consensus_parakeet_respects_vram_guard(monkeypatch):
    import app.engines.local_whisper as lw

    built = []

    class _PK:
        def __init__(self, **kw):
            built.append(kw["device"])

        def _load_model(self):
            pass

    monkeypatch.setattr("app.engines.parakeet.ParakeetEngine", _PK)
    monkeypatch.setattr(lw, "gpu_free_mb", lambda: 2000)
    e = LocalWhisperEngine(model="tiny", consensus_parakeet_device="cuda", min_free_vram_mb=8000)
    e._parakeet()
    assert built == ["cpu"]
    monkeypatch.setattr(lw, "gpu_free_mb", lambda: 30000)
    e2 = LocalWhisperEngine(model="tiny", consensus_parakeet_device="cuda", min_free_vram_mb=8000)
    e2._parakeet()
    assert built[-1] == "cuda"
    # Whisper itself ended up on the CPU: parakeet follows regardless of free memory.
    e3 = LocalWhisperEngine(model="tiny", consensus_parakeet_device="cuda", min_free_vram_mb=8000)
    e3.device_used = "cpu"
    e3._parakeet()
    assert built[-1] == "cpu"


def test_transcription_stream_keeps_running_task_alive(tmp_path):
    """A client that disconnects mid-stream must not cancel the inference
    task; the upload is removed once the task finishes on its own."""
    path = tmp_path / "up.mp3"
    path.write_bytes(b"x")
    finished = asyncio.Event()

    async def work():
        await finished.wait()
        return {"text": "late"}

    async def run():
        task = asyncio.create_task(work())
        gen = main._transcribe_stream(task, path, "json")
        assert await gen.__anext__() == b" "
        await gen.aclose()  # the client went away
        await asyncio.sleep(0)
        assert not task.cancelled() and path.exists()
        finished.set()
        await task
        await asyncio.sleep(0)
        assert not path.exists()

    asyncio.run(run())
