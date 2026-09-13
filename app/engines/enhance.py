"""Noisy-recording support: noise measurement, DeepFilterNet enhancement and
speech-region detection on the enhanced signal.

Why this exists: a Plaud recorder in a car, a restaurant or a windy street
returns audio whose noise floor sits only a few dB under the speech. Silero VAD
(the gate both built-in engines use to skip silence) then classifies most of
the speech as noise and the recognizer never sees it — a six-minute
conversation came back as 80 words. Feeding the recognizer the DENOISED audio
is not the answer either: speech enhancers remove noise by also removing parts
of the speech, and Whisper (trained on noisy web audio) transcribes the raw
signal better than the cleaned one. Measured on that recording, faster-whisper
large-v3-turbo gave 697 words from the raw audio and 543 garbled ones from the
DeepFilterNet output.

So the enhanced signal is used only for what it is good at: deciding WHERE the
speech is. VAD on the enhanced audio found 220 s of speech where VAD on the
raw audio found 25 s. The recognizer is then pointed at those regions of the
ORIGINAL audio (faster-whisper ``clip_timestamps``; parakeet's VAD cut), which
keeps the anti-hallucination benefit of skipping silence on long recordings.

The enhancer is DeepFilterNet 3 via its standalone ``deep-filter`` binary
(static, CPU, no Python dependencies — the ``deepfilternet`` package pins a
torchaudio the CUDA image cannot satisfy). It runs about 5x realtime on a
desktop CPU, so it only runs when the recording measures as noisy.

Noise measure: the spread between loud and quiet 30 ms frames (90th minus 10th
percentile of frame RMS in dB). Speech over a quiet room spans 25–45 dB across
the recordings this was calibrated on; the car recording measured 8 dB. A
recording with barely any speech measures low too, and then the enhancement
merely costs CPU time.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
import wave
from pathlib import Path
from typing import TYPE_CHECKING

from .base import EngineError

if TYPE_CHECKING:  # numpy is an STT dependency; config validation imports this module without it
    import numpy as np

log = logging.getLogger("plaud-bridge.engine.enhance")

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 480  # 30 ms at 16 kHz, the Silero VAD frame
DEFAULT_BIN = "deep-filter"
# Frames quieter than this are treated as digital silence (a recorder that
# writes zeros before the microphone opens) and left out of the spread.
SILENCE_DB = -90.0


def decode_waveform(audio_path: Path) -> np.ndarray:
    """Decode any container PyAV reads into mono 16 kHz float32."""
    try:
        import av
        import numpy as np
    except ImportError as exc:  # faster-whisper depends on PyAV and numpy; be explicit anyway
        raise EngineError("PyAV / numpy are not installed") from exc
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)
    chunks: list[np.ndarray] = []
    try:
        with av.open(str(audio_path)) as container:
            for frame in container.decode(audio=0):
                for rframe in resampler.resample(frame):
                    chunks.append(rframe.to_ndarray()[0])
            for rframe in resampler.resample(None):
                chunks.append(rframe.to_ndarray()[0])
    except av.error.FFmpegError as exc:  # pragma: no cover - depends on the file
        raise EngineError(f"could not decode {audio_path.name}: {exc}") from exc
    if not chunks:
        raise EngineError(f"no audio decoded from {audio_path.name}")
    return np.concatenate(chunks).astype(np.float32, copy=False)


def noise_spread_db(wav: np.ndarray) -> float:
    """Spread in dB between the loud and the quiet 30 ms frames of ``wav``
    (90th minus 10th percentile of frame RMS). Small = the noise floor is close
    to the speech level. Returns 0.0 for empty or all-silent input."""
    import numpy as np

    n = (len(wav) // FRAME_SAMPLES) * FRAME_SAMPLES
    if n == 0:
        return 0.0
    frames = wav[:n].reshape(-1, FRAME_SAMPLES).astype(np.float32)
    rms = np.sqrt((frames * frames).mean(axis=1))
    db = 20.0 * np.log10(rms + 1e-9)
    db = db[db > SILENCE_DB]
    if db.size == 0:
        return 0.0
    p10, p90 = np.percentile(db, [10, 90])
    return float(p90 - p10)


def write_wav(path: Path, wav: np.ndarray, sample_rate: int = SAMPLE_RATE) -> None:
    """Write a float32 waveform as 16-bit PCM WAV (what deep-filter reads)."""
    import numpy as np

    pcm = (np.clip(wav, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


def find_binary(configured: str | None = None) -> str | None:
    """Resolve the deep-filter executable: an explicit path, else PATH lookup."""
    candidate = configured or DEFAULT_BIN
    if "/" in candidate:  # an explicit path, relative or absolute
        path = Path(candidate).resolve()
        return str(path) if path.is_file() else None
    return shutil.which(candidate)


def enhance(wav: np.ndarray, work_dir: Path, binary: str, timeout_s: float | None = None) -> np.ndarray:
    """Run DeepFilterNet over ``wav`` and return the enhanced 16 kHz waveform.

    ``work_dir`` holds the intermediate WAVs (the binary works on files); the
    caller owns and removes it. The binary resamples to 48 kHz internally and
    writes 48 kHz back, so the result is resampled here. ``-D`` makes it
    compensate its STFT/look-ahead delay so the output stays on the original
    timeline (regions found on it are applied to the original); the few
    samples it still leaves unflushed at the tail are zero-padded back."""
    work_dir.mkdir(parents=True, exist_ok=True)
    src = work_dir / "input.wav"
    out_dir = work_dir / "out"
    out_dir.mkdir(exist_ok=True)
    write_wav(src, wav)
    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [binary, "-D", "-o", str(out_dir), str(src)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError(f"deep-filter timed out after {timeout_s}s") from exc
    except OSError as exc:
        raise EngineError(f"could not run deep-filter ({binary}): {exc}") from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        raise EngineError(f"deep-filter failed ({proc.returncode}): {' | '.join(tail)}")
    out = out_dir / src.name
    if not out.is_file():
        raise EngineError("deep-filter produced no output file")
    enhanced = decode_waveform(out)
    if len(enhanced) < len(wav):
        import numpy as np

        enhanced = np.concatenate([enhanced, np.zeros(len(wav) - len(enhanced), dtype=np.float32)])
    elif len(enhanced) > len(wav):
        enhanced = enhanced[: len(wav)]
    log.info("deep-filter enhanced %.0fs of audio in %.1fs", len(wav) / SAMPLE_RATE, time.monotonic() - t0)
    return enhanced


def speech_regions(
    wav: np.ndarray,
    threshold: float = 0.5,
    min_silence_ms: int = 500,
    speech_pad_ms: int = 300,
    max_gap_s: float = 10.0,
    min_region_s: float = 10.0,
) -> list[tuple[float, float]]:
    """Silero VAD speech regions of ``wav`` as (start, end) seconds, shaped for
    a recognizer that decodes each region on its own.

    Regions are merged across gaps up to ``max_gap_s`` and stretched to at
    least ``min_region_s`` (then re-merged where that made them overlap).
    Whisper decodes a clip in 30 s windows that end at the clip's end and
    restarts its context at every clip: fed the raw utterance-level chunks
    (dozens of 1–3 s clips) it lost the sentence context and filled the short
    windows with "Thank you." — 600 words, many invented, against 697
    coherent ones from decoding straight through. Long regions keep the
    windows full and the context flowing while still skipping stretches of
    the recording with nothing said in them (minutes of engine noise)."""
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    opts = VadOptions(threshold=threshold, min_silence_duration_ms=min_silence_ms, speech_pad_ms=speech_pad_ms)
    chunks = get_speech_timestamps(wav, opts)
    duration = len(wav) / SAMPLE_RATE
    regions: list[list[float]] = []
    for c in chunks:
        start, end = c["start"] / SAMPLE_RATE, c["end"] / SAMPLE_RATE
        if regions and start - regions[-1][1] <= max_gap_s:
            regions[-1][1] = max(regions[-1][1], end)
        else:
            regions.append([start, end])
    for r in regions:
        if r[1] - r[0] < min_region_s:
            r[1] = min(duration, r[0] + min_region_s)
    merged: list[list[float]] = []
    for r in regions:
        if merged and r[0] <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], r[1])
        else:
            merged.append(r)
    return [(round(s, 3), round(e, 3)) for s, e in merged]


def cut_regions(wav: np.ndarray, regions: list[tuple[float, float]]) -> np.ndarray:
    """Concatenate the ``regions`` (seconds) of ``wav`` — the recognizer input
    when a model has no clip-timestamp API of its own."""
    if not regions:
        return wav[:0]
    import numpy as np

    parts = [wav[int(s * SAMPLE_RATE): int(e * SAMPLE_RATE)] for s, e in regions]
    return np.concatenate(parts) if parts else wav[:0]


class Enhancer:
    """Policy + plumbing shared by the engines.

    ``mode``: "auto" runs enhancement when the recording measures noisy
    (spread under ``spread_db``), "always" runs it on every recording, "off"
    never. A missing binary degrades to off with one logged warning."""

    def __init__(self, mode: str = "auto", spread_db: float = 15.0, binary: str | None = None,
                 timeout_s: float | None = None):
        mode = (mode or "auto").strip().lower()
        if mode not in ("auto", "always", "off"):
            raise ValueError(f"unknown enhance mode {mode!r} (auto | always | off)")
        self.mode = mode
        self.spread_db = spread_db
        self.configured_binary = binary
        self.timeout_s = timeout_s
        self._binary: str | None = None
        self._binary_checked = False

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    def binary(self) -> str | None:
        if not self._binary_checked:
            self._binary_checked = True
            self._binary = find_binary(self.configured_binary)
            if self._binary is None and self.enabled:
                log.warning(
                    "PB_STT_ENHANCE=%s but the deep-filter binary was not found (%s); "
                    "noisy recordings will be transcribed without enhancement",
                    self.mode, self.configured_binary or DEFAULT_BIN,
                )
        return self._binary

    def wants(self, spread: float) -> bool:
        if self.mode == "off":
            return False
        if self.mode == "always":
            return True
        return spread < self.spread_db

    def plan(self, audio_path: Path, work_dir: Path, max_duration_s: float | None = None) -> "EnhancePlan | None":
        """Measure the recording; when it is noisy (per ``mode``) enhance it and
        locate the speech. Returns None when the recognizer should run its
        usual path. A failure is logged and treated as None; the one exception
        is a recording over ``max_duration_s`` (the engine's PB_STT_MAX_DURATION_S
        backstop for headers that lied), which raises EngineError so the engine
        rejects it before hours of enhancement."""
        if not self.enabled:
            return None
        # Resolve the binary first: without it there is nothing to do, and
        # decoding a multi-hour recording just to measure it would be waste.
        binary = self.binary()
        if binary is None:
            return None
        t0 = time.monotonic()
        try:
            wav = decode_waveform(audio_path)
        except Exception as exc:
            log.warning("enhancement skipped for %s: %s", audio_path.name, exc)
            return None
        duration = len(wav) / SAMPLE_RATE
        if max_duration_s is not None and duration > max_duration_s:
            raise EngineError(
                f"audio is {duration / 3600:.1f} h, over the "
                f"{max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )
        try:
            spread = noise_spread_db(wav)
            if not self.wants(spread):
                log.info("noise spread %.1f dB (threshold %.1f): no enhancement", spread, self.spread_db)
                return None
            log.info("noise spread %.1f dB under %.1f: enhancing with deep-filter", spread, self.spread_db)
            enhanced = enhance(wav, work_dir, binary, self.timeout_s)
            regions = speech_regions(enhanced)
            enhanced_path = work_dir / "enhanced.wav"
            write_wav(enhanced_path, enhanced)
            speech_s = sum(e - s for s, e in regions)
            log.info("speech regions on enhanced audio: %d regions, %.0fs of %.0fs",
                     len(regions), speech_s, len(wav) / SAMPLE_RATE)
            return EnhancePlan(
                original=wav, enhanced=enhanced, enhanced_path=enhanced_path, regions=regions,
                noise_spread_db=round(spread, 1), seconds=round(time.monotonic() - t0, 2),
            )
        except Exception as exc:
            log.warning("enhancement skipped for %s: %s", audio_path.name, exc)
            return None


class EnhancePlan:
    def __init__(self, original: np.ndarray, enhanced: np.ndarray, enhanced_path: Path,
                 regions: list[tuple[float, float]], noise_spread_db: float, seconds: float):
        self.original = original
        self.enhanced = enhanced
        self.enhanced_path = enhanced_path
        self.regions = regions
        self.noise_spread_db = noise_spread_db
        self.seconds = seconds

    @property
    def clip_timestamps(self) -> list[float]:
        """faster-whisper ``clip_timestamps``: flat start,end,start,end… seconds."""
        flat: list[float] = []
        for s, e in self.regions:
            flat += [s, e]
        return flat

    @property
    def speech_seconds(self) -> float:
        return round(sum(e - s for s, e in self.regions), 1)

    def stats(self) -> dict:
        return {
            "enhanced": True,
            "noise_spread_db": self.noise_spread_db,
            "enhance_seconds": self.seconds,
            "speech_regions": len(self.regions),
            "speech_seconds": self.speech_seconds,
        }
