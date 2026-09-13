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
import subprocess
import tempfile
import time
from pathlib import Path

from .base import Alternate, EngineError, EngineResult, ProgressCallback, Segment, render_text
from .diarization import DiarizationMixin, cuda_used, mark_cuda_used, probe_duration
from .enhance import Enhancer

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
        enhancer: Enhancer | None = None,
        enhance_diarize: bool = True,
        consensus: bool = False,
        consensus_parakeet_model: str | None = "nemo-parakeet-tdt-0.6b-v2",
        consensus_atten_db: float | None = 12.0,
        consensus_parakeet_device: str = "cpu",
        idle_unload_s: int = 0,
        min_free_vram_mb: int = 0,
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
        # Noisy-recording path (see enhance.py): None or mode "off" = never.
        self.enhancer = enhancer
        self.enhance_diarize = enhance_diarize
        # Second opinions for the consensus pass on noisy recordings (see
        # consensus.py): parakeet on the raw audio, and this model again on a
        # partially denoised copy. Either may be turned off with None.
        self.consensus = consensus
        self.consensus_parakeet_model = consensus_parakeet_model
        self.consensus_atten_db = consensus_atten_db
        self.consensus_parakeet_device = consensus_parakeet_device
        self._alt_parakeet = None
        # Shared-GPU worker mode: unload the recognizers after idle_unload_s
        # seconds without work (the diarization worker stays: it cannot be
        # respawned once this process holds a CUDA context, see _load_model),
        # and load on the CPU instead of a GPU with under min_free_vram_mb free.
        self.idle_unload_s = idle_unload_s
        self.min_free_vram_mb = min_free_vram_mb
        self._idle_task: asyncio.Task | None = None
        self._last_used = 0.0
        self.device_used: str | None = None
        self._diar_device_forced = False  # pyannote sent to the CPU by the VRAM guard, not by config
        self._model = None
        self._diar_proc = None
        self._lock = asyncio.Lock()
        self.load_seconds: float | None = None

    # -- model loading ------------------------------------------------------

    def _load_model(self):
        if self._model is not None:
            if self.device_used == "cpu" and self.device in ("auto", "cuda") and self.min_free_vram_mb:
                free = gpu_free_mb()
                if free is not None and free >= self.min_free_vram_mb:
                    # Loaded on the CPU while the card was full; it has room
                    # now. No CUDA context was taken (everything ran on the
                    # CPU), so the pyannote worker may be respawned too.
                    log.info("GPU has %d MB free again: reloading whisper on it", free)
                    self.unload()
                    if self._diar_device_forced and not cuda_used():
                        self.close()
                        self.diarization_device = None
                        self._diar_device_forced = False
                else:
                    return self._model
            else:
                return self._model
        # Spawn the diarization worker BEFORE whisper initializes a CUDA context
        # in this process. Once whisper has a live context, this process can no
        # longer spawn a child cleanly (fork segfaults, posix_spawn/vfork
        # deadlocks against the driver's threads), so the child must be forked
        # off while we are still CUDA-free, then kept alive.
        # Shared-GPU guard, decided BEFORE anything allocates: a card with less
        # than min_free_vram_mb free gets neither whisper nor (when it would
        # have followed whisper's device) the pyannote worker.
        device, compute = self.device, self.compute_type
        if device in ("auto", "cuda") and self.min_free_vram_mb:
            free = gpu_free_mb()
            if free is not None and free < self.min_free_vram_mb:
                log.warning("GPU has %d MB free, under PB_STT_MIN_FREE_VRAM_MB=%d: loading whisper on the CPU",
                            free, self.min_free_vram_mb)
                device, compute = "cpu", "auto" if self.compute_type in ("float16", "int8_float16") else self.compute_type
                if not self.diarization_device and self._diar_proc is None and not cuda_used():
                    self.diarization_device = "cpu"
                    self._diar_device_forced = True
        self._ensure_diar_worker()
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise EngineError(
                "faster-whisper is not installed — install requirements-stt.txt "
                "or use the CUDA/CPU docker image"
            ) from exc
        t0 = time.monotonic()
        log.info("loading whisper model %r (device=%s, compute=%s)", self.model_name, device, compute)
        self._model = WhisperModel(
            self.model_name,
            device=device,
            compute_type=compute,
            cpu_threads=self.cpu_threads,
        )
        self.device_used = device
        if device in ("cuda", "auto"):
            mark_cuda_used()
        self.load_seconds = time.monotonic() - t0
        log.info("model loaded in %.1fs", self.load_seconds)
        return self._model

    # -- shared-GPU housekeeping --------------------------------------------

    def unload(self) -> None:
        """Drop the recognizers (whisper, the consensus parakeet) so their GPU
        memory goes back to the card. Models reload on the next request. The
        diarization worker is kept (see _load_model)."""
        if self._model is None and self._alt_parakeet is None:
            return
        log.info("unloading whisper%s after %ds idle",
                 " and parakeet" if self._alt_parakeet is not None else "", self.idle_unload_s)
        self._model = None
        self._alt_parakeet = None
        import gc

        gc.collect()

    def _touch(self) -> None:
        """Note activity and (re)arm the idle unload timer."""
        self._last_used = time.monotonic()
        if not self.idle_unload_s:
            return
        if self._idle_task is None or self._idle_task.done():
            self._idle_task = asyncio.get_running_loop().create_task(self._idle_watch())

    async def _idle_watch(self) -> None:
        while True:
            await asyncio.sleep(max(1.0, self.idle_unload_s - (time.monotonic() - self._last_used)))
            if time.monotonic() - self._last_used >= self.idle_unload_s:
                async with self._lock:
                    if time.monotonic() - self._last_used >= self.idle_unload_s:
                        self.unload()
                        return

    # Diarization worker management and speaker assignment live in
    # DiarizationMixin (shared with the parakeet engine).

    # -- transcription ------------------------------------------------------

    async def transcribe(
        self, audio_path: Path, hotwords: str | None = None, progress: ProgressCallback | None = None
    ) -> EngineResult:
        async with self._lock:
            self._touch()
            try:
                return await asyncio.to_thread(self._transcribe_sync, audio_path, hotwords, progress)
            finally:
                self._touch()

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
        # Noisy recording? Then speech is located on a DeepFilterNet-cleaned
        # copy and whisper decodes those regions of the original (its own VAD
        # would drop most of the speech). The temp dir holds the cleaned copy
        # for diarization and goes away with the transcription.
        with tempfile.TemporaryDirectory(prefix="pb-enhance-") as tmp:
            plan = (
                self.enhancer.plan(audio_path, Path(tmp), max_duration_s=self.max_duration_s)
                if self.enhancer else None
            )
            if plan is not None and progress:
                progress("transcribing", 0.0)
            return self._decode(model, audio_path, hotwords, progress, plan)

    def _decode(self, model, audio_path: Path, hotwords: str | None, progress: ProgressCallback | None, plan):
        # PB_STT_VAD=false means "decode everything": then the cleaned copy only
        # serves diarization and whisper still sees the whole recording.
        clips = plan.clip_timestamps if plan is not None and plan.regions and self.vad_filter else None
        t0 = time.monotonic()
        try:
            seg_iter, info = model.transcribe(
                str(audio_path),
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter and clips is None,
                clip_timestamps=clips if clips is not None else "0",
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

        alternates: list[Alternate] = []
        alternates_s = 0.0
        if self.consensus and plan is not None and segments:
            if progress:
                progress("transcribing", 0.99)
            t1 = time.monotonic()
            alternates = self._alternates(model, audio_path, clips, hotwords, plan)
            alternates_s = time.monotonic() - t1

        diarize_s = 0.0
        if self.diarization and segments:
            if progress:
                progress("diarizing", None)  # pyannote gives no partial results
            t1 = time.monotonic()
            # pyannote separates speakers better on the cleaned copy.
            diar_path = plan.enhanced_path if plan is not None and self.enhance_diarize else audio_path
            try:
                self._apply_diarization(diar_path, segments, words)
            except Exception as exc:
                # A transcript without speaker labels beats losing it entirely.
                log.warning("diarization failed, returning unlabeled transcript: %s", exc)
            diarize_s = time.monotonic() - t1

        plain = " ".join(s.text for s in segments if s.text)
        stats = {
            "engine": self.name,
            "model": self.model_name,
            "device": self.device_used or self.device,
            "compute_type": self.compute_type,
            "transcribe_seconds": round(transcribe_s, 2),
            "diarize_seconds": round(diarize_s, 2) or None,
            "rtf": round(transcribe_s / info.duration, 3) if info.duration else None,
        }
        if plan is not None:
            stats.update(plan.stats())
        if alternates:
            stats["alternates"] = [a.name for a in alternates]
            stats["alternates_seconds"] = round(alternates_s, 2)
        return EngineResult(
            text=render_text(segments, fallback=plain),
            segments=segments,
            language=info.language,
            duration=round(info.duration, 2) if info.duration else None,
            model=self.model_name,
            stats={k: v for k, v in stats.items() if v is not None},
            alternates=alternates,
        )

    # -- second opinions for the consensus pass ------------------------------

    def _alternates(self, model, audio_path: Path, clips, hotwords: str | None, plan) -> list[Alternate]:
        """Independent transcriptions of the same speech for consensus.py to
        weigh against the primary: each failure is logged and skipped."""
        out: list[Alternate] = []
        if self.consensus_atten_db is not None:
            try:
                partial = plan.partial_copy(self.consensus_atten_db)
                seg_iter, _info = model.transcribe(
                    str(partial), language=self.language, beam_size=self.beam_size,
                    vad_filter=False, clip_timestamps=clips if clips is not None else "0",
                    hotwords=hotwords or None, condition_on_previous_text=False,
                )
                segs = [Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip()) for s in seg_iter]
                out.append(Alternate(name=f"whisper {self.model_name} on a partially denoised copy "
                                          f"(noise -{self.consensus_atten_db:g} dB)", segments=segs))
            except Exception as exc:
                log.warning("consensus alternate (partial denoise) failed: %s", exc)
        if self.consensus_parakeet_model:
            try:
                engine = self._parakeet()
                result = engine._decode(audio_path, None, plan)
                out.append(Alternate(name=f"parakeet {self.consensus_parakeet_model} on the raw audio",
                                     segments=result.segments))
            except Exception as exc:
                log.warning("consensus alternate (parakeet) failed: %s", exc)
        return out

    def _parakeet(self):
        """The consensus parakeet recognizer, loaded once and kept warm. On
        the CPU by default: the GPU holds whisper (and pyannote), and on a
        6 GB card another 2.4 GB model does not fit beside them. A big card
        (PB_STT_CONSENSUS_PARAKEET_DEVICE=cuda) runs it in seconds instead."""
        if self._alt_parakeet is None:
            from .parakeet import ParakeetEngine

            device = self.consensus_parakeet_device
            if device in ("auto", "cuda"):
                # Same guard as whisper's: a card that was too full for whisper
                # (or is under the threshold now) does not get parakeet either.
                free = gpu_free_mb() if self.min_free_vram_mb else None
                if self.device_used == "cpu" or (free is not None and free < self.min_free_vram_mb):
                    log.warning("consensus parakeet requested on %s but the GPU is short (%s MB free): using the CPU",
                                device, free if free is not None else "?")
                    device = "cpu"
            engine = ParakeetEngine(
                model=self.consensus_parakeet_model, device=device, diarization=False,
                max_duration_s=self.max_duration_s, language=None,
            )
            engine._load_model()
            self._alt_parakeet = engine
        return self._alt_parakeet


def gpu_free_mb() -> int | None:
    """Free memory on the GPU whisper will use per nvidia-smi — the first
    entry of CUDA_VISIBLE_DEVICES (index or UUID) when set, else GPU 0 — or
    None when there is no usable nvidia-smi (no GPU, CPU image)."""
    import os

    visible = (os.environ.get("CUDA_VISIBLE_DEVICES") or "").split(",")[0].strip()
    target = visible if visible and visible.lower() not in ("all",) else "0"
    try:
        out = subprocess.run(
            ["nvidia-smi", f"--id={target}", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    first = out.stdout.strip().splitlines()[:1]
    try:
        return int(first[0].strip()) if first else None
    except ValueError:
        return None
