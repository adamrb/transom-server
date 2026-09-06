"""Built-in transcription: faster-whisper (CTranslate2) with optional
pyannote speaker diarization. Runs fully locally on GPU (CUDA) or CPU.

Design notes:
- Models load lazily on first use and stay warm; a lock serializes access
  (one transcription at a time — these models saturate the device anyway).
- faster-whisper streams audio decode via PyAV and yields segments as it
  goes, so multi-hour recordings (Plaud hardware caps around 5 h) do not
  require the whole waveform in memory at once. VAD filtering skips
  silence, which matters a lot for long lecture/meeting recordings.
- Diarization (pyannote) is optional: it needs the heavier torch stack and
  a Hugging Face token for the gated pipeline. When enabled, whisper
  segments are assigned the speaker with the greatest temporal overlap.
"""

import asyncio
import logging
import time
from pathlib import Path

from .base import EngineError, EngineResult, Segment, render_text

log = logging.getLogger("plaud-bridge.engine.local")


class LocalWhisperEngine:
    name = "local"

    def __init__(
        self,
        model: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
        language: str | None = None,
        vad_filter: bool = True,
        max_duration_s: int = 5 * 3600,
        diarization: bool = False,
        hf_token: str | None = None,
        beam_size: int = 5,
        cpu_threads: int = 0,
    ):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self.max_duration_s = max_duration_s
        self.diarization = diarization
        self.hf_token = hf_token
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads
        self._model = None
        self._diar_pipeline = None
        self._lock = asyncio.Lock()
        self.load_seconds: float | None = None

    # -- model loading ------------------------------------------------------

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise EngineError(
                "faster-whisper is not installed — install requirements-stt.txt "
                "or use the CUDA/CPU docker image"
            ) from exc
        t0 = time.monotonic()
        log.info("loading whisper model %r (device=%s, compute=%s)",
                 self.model_name, self.device, self.compute_type)
        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        self.load_seconds = time.monotonic() - t0
        log.info("model loaded in %.1fs", self.load_seconds)
        return self._model

    def _load_diarizer(self):
        if not self.diarization:
            return None
        if self._diar_pipeline is not None:
            return self._diar_pipeline
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise EngineError(
                "diarization requested but pyannote.audio/torch are not installed — "
                "install requirements-diarization.txt or use the CUDA docker image"
            ) from exc
        log.info("loading diarization pipeline (pyannote)")
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1", use_auth_token=self.hf_token
        )
        if pipeline is None:
            raise EngineError(
                "could not load pyannote/speaker-diarization-3.1 — set PB_STT_HF_TOKEN "
                "to a Hugging Face token that has accepted the model's terms"
            )
        if torch.cuda.is_available() and self.device in ("auto", "cuda"):
            pipeline.to(torch.device("cuda"))
        self._diar_pipeline = pipeline
        return pipeline

    # -- transcription ------------------------------------------------------

    async def transcribe(self, audio_path: Path) -> EngineResult:
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, audio_path)

    def _probe_duration(self, audio_path: Path) -> float | None:
        """Container-header duration probe (cheap; no decode). Used to reject
        over-limit files BEFORE whisper decodes the whole stream."""
        try:
            import av

            with av.open(str(audio_path)) as container:
                if container.duration:
                    return container.duration / 1_000_000
        except Exception:
            pass
        return None

    def _transcribe_sync(self, audio_path: Path) -> EngineResult:
        probed = self._probe_duration(audio_path)
        if probed and probed > self.max_duration_s:
            raise EngineError(
                f"audio is {probed / 3600:.1f} h, over the "
                f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )

        model = self._load_model()
        t0 = time.monotonic()
        try:
            seg_iter, info = model.transcribe(
                str(audio_path),
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
            )
            # Backstop for streams whose header lied or lacked a duration.
            if info.duration and info.duration > self.max_duration_s:
                raise EngineError(
                    f"audio is {info.duration / 3600:.1f} h, over the "
                    f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
                )
            segments = [
                Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip())
                for s in seg_iter  # generator: inference happens during this loop
            ]
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"whisper transcription failed: {exc}") from exc
        transcribe_s = time.monotonic() - t0

        diarize_s = 0.0
        if self.diarization and segments:
            t1 = time.monotonic()
            try:
                self._apply_diarization(audio_path, segments)
            except EngineError:
                raise
            except Exception as exc:
                log.warning("diarization failed, returning unlabeled transcript: %s", exc)
            diarize_s = time.monotonic() - t1

        plain = " ".join(s.text for s in segments if s.text)
        stats = {
            "engine": self.name,
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "transcribe_seconds": round(transcribe_s, 2),
            "diarize_seconds": round(diarize_s, 2) or None,
            "rtf": round(transcribe_s / info.duration, 3) if info.duration else None,
        }
        return EngineResult(
            text=render_text(segments, fallback=plain),
            segments=segments,
            language=info.language,
            duration=round(info.duration, 2) if info.duration else None,
            model=self.model_name,
            stats={k: v for k, v in stats.items() if v is not None},
        )

    def _apply_diarization(self, audio_path: Path, segments: list[Segment]) -> None:
        pipeline = self._load_diarizer()
        annotation = pipeline(str(audio_path))
        turns = [
            (turn.start, turn.end, f"Speaker {label}")
            for turn, _, label in annotation.itertracks(yield_label=True)
        ]
        if not turns:
            return
        for seg in segments:
            if seg.start is None or seg.end is None:
                continue
            # Cumulative overlap per speaker: a speaker's turns may be split
            # around the segment; sum them rather than taking a single turn.
            totals: dict[str, float] = {}
            for t_start, t_end, speaker in turns:
                overlap = min(seg.end, t_end) - max(seg.start, t_start)
                if overlap > 0:
                    totals[speaker] = totals.get(speaker, 0.0) + overlap
            seg.speaker = max(totals, key=totals.get) if totals else None
        # Normalize labels to appearance order: Speaker 1, Speaker 2, ...
        mapping: dict[str, str] = {}
        for seg in segments:
            if seg.speaker and seg.speaker not in mapping:
                mapping[seg.speaker] = f"Speaker {len(mapping) + 1}"
        for seg in segments:
            if seg.speaker:
                seg.speaker = mapping[seg.speaker]
