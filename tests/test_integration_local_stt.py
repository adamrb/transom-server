"""Integration test: real faster-whisper inference on the bundled fixture.

Runs the actual built-in engine (tiny model, CPU, ~75 MB download on first
run) against tests/fixtures/speech.wav and scores it against the reference
transcript. Marked `integration` — CI runs `pytest -m "not integration"`;
run locally/in-container with plain `pytest` to include it.
"""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("faster_whisper", reason="requirements-stt.txt not installed")

from app.benchmark import word_error_rate
from app.engines.base import EngineError
from app.engines.local_whisper import LocalWhisperEngine

FIXTURES = Path(__file__).parent / "fixtures"

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def engine():
    return LocalWhisperEngine(model="tiny", device="cpu", compute_type="int8")


def test_real_transcription_of_fixture(engine):
    result = asyncio.run(engine.transcribe(FIXTURES / "speech.wav"))
    reference = (FIXTURES / "speech_reference.txt").read_text()

    assert result.text.strip(), "empty transcript"
    assert result.segments, "no segments"
    assert result.language == "en"
    assert result.duration and 3 < result.duration < 10
    # tiny + synthetic TTS voice: allow generous WER, but it must be recognizably right
    assert word_error_rate(reference, result.text) < 0.5
    assert "fox" in result.text.lower()
    # timestamps sane and ordered
    starts = [s.start for s in result.segments]
    assert starts == sorted(starts) and starts[0] >= 0
    # perf stats populated
    assert result.stats["transcribe_seconds"] > 0
    assert result.stats["engine"] == "local"


def test_model_stays_warm_across_calls(engine):
    first_load = engine.load_seconds
    asyncio.run(engine.transcribe(FIXTURES / "speech.wav"))
    assert engine.load_seconds == first_load  # not reloaded


def test_duration_limit_enforced(tmp_path):
    limited = LocalWhisperEngine(model="tiny", device="cpu", compute_type="int8",
                                 max_duration_s=2)
    with pytest.raises(EngineError, match="over the"):
        asyncio.run(limited.transcribe(FIXTURES / "speech.wav"))


def test_benchmark_cli_end_to_end(tmp_path, capsys):
    from app.benchmark import main

    out_json = tmp_path / "bench.json"
    rc = main([
        str(FIXTURES / "speech.wav"),
        "--models", "tiny",
        "--device", "cpu",
        "--compute", "int8",
        "--reference", str(FIXTURES / "speech_reference.txt"),
        "--json", str(out_json),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "tiny" in out and "wer" in out
    import json

    data = json.loads(out_json.read_text())
    assert data["results"][0]["status"] == "ok"
    assert data["results"][0]["wer"] < 0.5
