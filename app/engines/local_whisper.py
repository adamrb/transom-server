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

from .base import EngineError, EngineResult, ProgressCallback, Segment, render_text
from .diarization import DiarizationMixin, probe_duration

log = logging.getLogger("plaud-bridge.engine.local")

# Minimum wall-clock gap between two progress reports while decoding.
PROGRESS_INTERVAL_S = 2.0


class LocalWhisperEngine(DiarizationMixin):
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
        diarization_model: str = "pyannote/speaker-diarization-community-1",
        hf_token: str | None = None,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        beam_size: int = 5,
        cpu_threads: int = 0,
        condition_on_previous_text: bool | None = None,
        diarization_device: str | None = None,
    ):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self.max_duration_s = max_duration_s
        self.diarization = diarization
        self.diarization_model = diarization_model
        self.diarization_device = diarization_device
        self.hf_token = hf_token
        self.num_speakers = num_speakers
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads
        self.condition_on_previous_text = condition_on_previous_text
        self._model = None
        self._diar_proc = None
        self._lock = asyncio.Lock()
        self.load_seconds: float | None = None

    # -- model loading ------------------------------------------------------

    def _load_model(self):
        if self._model is not None:
            return self._model
        # Spawn the diarization worker BEFORE whisper initializes a CUDA context
        # in this process. Once whisper has a live context, this process can no
        # longer spawn a child cleanly (fork segfaults, posix_spawn/vfork
        # deadlocks against the driver's threads), so the child must be forked
        # off while we are still CUDA-free, then kept alive.
        self._ensure_diar_worker()
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

    # Diarization worker management and speaker assignment live in
    # DiarizationMixin (shared with the parakeet engine).

    # -- transcription ------------------------------------------------------

    async def transcribe(
        self, audio_path: Path, hotwords: str | None = None, progress: ProgressCallback | None = None
    ) -> EngineResult:
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, audio_path, hotwords, progress)

    def _probe_duration(self, audio_path: Path) -> float | None:
        """Container-header duration probe (cheap; no decode). Used to reject
        over-limit files BEFORE whisper decodes the whole stream."""
        return probe_duration(audio_path)

    def _fit_hotwords(self, model, hotwords: str | None, max_tokens: int = 220) -> str | None:
        """Trim the comma-separated hotwords to what Whisper will actually keep.
        faster-whisper cuts the prompt at 223 tokens, mid-term and silently;
        cutting here at a term boundary keeps the list meaningful and lets us
        log how many terms made it. The list arrives highest-priority first."""
        if not hotwords:
            return None
        tok = getattr(model, "hf_tokenizer", None)
        if tok is None:
            return hotwords
        terms = [t.strip() for t in hotwords.split(",") if t.strip()]
        kept: list[str] = []
        for term in terms:
            candidate = ", ".join(kept + [term])
            if len(tok.encode(" " + candidate).ids) > max_tokens:
                break
            kept.append(term)
        if len(kept) != len(terms):
            log.info("hotwords trimmed to %d of %d terms (%d-token budget)", len(kept), len(terms), max_tokens)
        return ", ".join(kept) or None

    def _transcribe_sync(
        self, audio_path: Path, hotwords: str | None = None, progress: ProgressCallback | None = None
    ) -> EngineResult:
        probed = self._probe_duration(audio_path)
        if probed and probed > self.max_duration_s:
            raise EngineError(
                f"audio is {probed / 3600:.1f} h, over the "
                f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )

        model = self._load_model()
        hotwords = self._fit_hotwords(model, hotwords)
        t0 = time.monotonic()
        try:
            seg_iter, info = model.transcribe(
                str(audio_path),
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                # Word timestamps let diarization split a whisper segment that
                # spans a speaker change at the actual word boundary, instead of
                # collapsing the whole segment to the dominant speaker.
                word_timestamps=self.diarization,
                # Custom vocabulary (names, products) biases decoding toward
                # these spellings; None leaves the model unprompted.
                hotwords=hotwords or None,
                # Auto (None): keep Whisper's default context carry-over unless
                # a hotwords prompt is present. With one, feeding the previous
                # window's text back in makes Whisper drop most of the speech
                # and fall into repetition loops ("by the way, by the way…").
                # Measured on a 2 h 20 min podcast: 2.4k chars kept of 11.6k
                # per 10 min with it on, all 11.6k with it off, same hotwords;
                # without hotwords both settings transcribed everything.
                condition_on_previous_text=(
                    self.condition_on_previous_text
                    if self.condition_on_previous_text is not None
                    else not hotwords
                ),
            )
            # Backstop for streams whose header lied or lacked a duration.
            if info.duration and info.duration > self.max_duration_s:
                raise EngineError(
                    f"audio is {info.duration / 3600:.1f} h, over the "
                    f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
                )
            segments = []
            # (start, end, word, index of the whisper segment it came from)
            words: list[tuple[float, float, str, int]] = []
            last_report = 0.0
            for idx, s in enumerate(seg_iter):  # generator: inference happens during this loop
                segments.append(
                    Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip())
                )
                for w in (getattr(s, "words", None) or []):
                    if w.start is not None and w.end is not None:
                        words.append((w.start, w.end, w.word, idx))
                # Whisper yields segments in audio order, so the last end time
                # over the total duration is how far through the audio we are.
                # Throttled: a long recording yields thousands of segments.
                now = time.monotonic()
                if progress and info.duration and now - last_report >= PROGRESS_INTERVAL_S:
                    last_report = now
                    progress("transcribing", min(0.99, max(0.0, s.end / info.duration)))
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"whisper transcription failed: {exc}") from exc
        transcribe_s = time.monotonic() - t0

        diarize_s = 0.0
        if self.diarization and segments:
            if progress:
                progress("diarizing", None)  # pyannote gives no partial results
            t1 = time.monotonic()
            try:
                self._apply_diarization(audio_path, segments, words)
            except Exception as exc:
                # A transcript without speaker labels beats losing it entirely.
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
