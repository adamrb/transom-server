"""Built-in transcription: NVIDIA Parakeet (FastConformer encoder + TDT
decoder) via onnx-asr, on the GPU (CUDA) or CPU, with the same optional
pyannote speaker diarization as the whisper engine.

Why a second built-in engine: Parakeet is not an autoregressive text decoder,
so it does not invent sentences in silence or loop on a phrase the way Whisper
can on long recordings, and the 0.6B model sits above Whisper large-v3 on the
Open ASR leaderboard while needing ~2.4 GB of VRAM in float32 — or no GPU at
all (about 6x realtime on an 8-thread desktop CPU). Trade-offs: it takes no
prompt, so the custom vocabulary's hotwords cannot bias it (the vocabulary's
corrections still apply afterwards), it takes no forced language (v3 detects
it, v2 is English-only) and reports none, it transcribes verbatim (fillers
kept) and sometimes spells numbers out ("VM two").

Design notes:
- onnx-asr models take at most ~30 s of audio per pass, so the recording is
  cut at silences with Silero VAD and decoded chunk by chunk, in order — that
  ordering is what drives progress reporting.
- The whole waveform is decoded into memory first (16 kHz mono float32: ~230 MB
  per hour, ~1.2 GB for a 5 h file), because VAD needs the full signal.
- Token timestamps (80 ms frames) are regrouped into words so diarization can
  split a chunk at the word where the speaker changes, like the whisper path.
- Models load lazily on first use and stay warm; a lock serializes access.
- The GPU is used when onnxruntime's CUDA provider is present AND actually
  runs the model: PyPI onnxruntime-gpu ships no kernels for Maxwell cards, so
  a warm-up pass decides, and on failure only this recognizer drops to the
  CPU (pyannote keeps the GPU in its own process). ``stats.device`` records
  the outcome.
"""

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from .base import EngineError, EngineResult, ProgressCallback, Segment, render_text
from .diarization import DiarizationMixin, mark_cuda_used, probe_duration
from .enhance import Enhancer

log = logging.getLogger("transom.engine.parakeet")

SAMPLE_RATE = 16_000
# Silence kept on both sides of a VAD chunk so word onsets aren't clipped.
SPEECH_PAD_MS = 100.0
# Minimum wall-clock gap between two progress reports while decoding.
PROGRESS_INTERVAL_S = 2.0


class ParakeetEngine(DiarizationMixin):
    name = "parakeet"

    def __init__(
        self,
        model: str = "nemo-parakeet-tdt-0.6b-v3",
        device: str = "auto",
        quantization: str | None = None,
        language: str | None = None,
        max_duration_s: int = 5 * 3600,
        diarization: bool = False,
        diarization_model: str = "pyannote/speaker-diarization-community-1",
        hf_token: str | None = None,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        max_segment_s: float = 30.0,
        min_silence_ms: float = 600.0,
        batch_size: int = 4,
        cpu_threads: int = 0,
        diarization_device: str | None = None,
        enhancer: Enhancer | None = None,
        enhance_diarize: bool = True,
    ):
        self.model_name = model
        self.device = device
        self.quantization = quantization or None
        self.language = language
        self.max_duration_s = max_duration_s
        self.diarization = diarization
        self.diarization_model = diarization_model
        self.diarization_device = diarization_device
        self.hf_token = hf_token
        self.num_speakers = num_speakers
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.max_segment_s = max_segment_s
        self.min_silence_ms = min_silence_ms
        self.batch_size = batch_size
        self.cpu_threads = cpu_threads
        # Noisy-recording path (see enhance.py): None or mode "off" = never.
        self.enhancer = enhancer
        self.enhance_diarize = enhance_diarize
        self._model = None
        self._vad = None
        self._diar_proc = None
        self._lock = asyncio.Lock()
        self.load_seconds: float | None = None
        # "cuda" or "cpu" once the sessions exist: what onnxruntime actually
        # gave us, which can differ from the request (missing CUDA provider).
        self.device_used: str | None = None
        self._hotwords_noted = False
        self._language_noted = False

    # -- model loading ------------------------------------------------------

    @staticmethod
    def _choose_providers(device: str, available: list[str]) -> list[str]:
        """onnxruntime execution providers for the requested device. CUDA is
        taken when asked for (or on auto) and present; the CPU provider always
        trails as the fallback for ops the GPU build lacks."""
        cuda = "CUDAExecutionProvider"
        if device in ("auto", "cuda") and cuda in available:
            return [cuda, "CPUExecutionProvider"]
        if device == "cuda":
            log.warning("PB_STT_DEVICE=cuda but onnxruntime offers no CUDA provider (%s); "
                        "parakeet will run on the CPU", ", ".join(available) or "none")
        return ["CPUExecutionProvider"]

    @staticmethod
    def _detect_device(model, providers: list[str]) -> str:
        """What the encoder session really runs on. onnxruntime falls back to the
        CPU silently when the CUDA provider fails to initialize, so ask the
        session rather than trusting the request."""
        try:
            first = model.asr._encoder.get_providers()[0]
        except Exception:
            first = providers[0]
        return "cuda" if first.startswith("CUDA") else "cpu"

    @staticmethod
    def _available_providers() -> list[str]:
        import onnxruntime as ort

        return list(ort.get_available_providers())

    def _create_sessions(self, providers: list[str]):
        """Build the recognizer and the VAD for the given providers."""
        import onnx_asr
        import onnxruntime as ort

        sess_options = None
        if self.cpu_threads:
            sess_options = ort.SessionOptions()
            sess_options.intra_op_num_threads = self.cpu_threads
        model = onnx_asr.load_model(
            self.model_name, quantization=self.quantization,
            providers=providers, sess_options=sess_options,
        )
        # The VAD is tiny and built around an RNN; keep it on the CPU so it
        # needs no cuDNN and costs no VRAM.
        vad = onnx_asr.load_vad("silero", providers=["CPUExecutionProvider"])
        return model, vad

    @staticmethod
    def _warm_up(model) -> None:
        """Push one second of silence through the model. Session creation does
        not run any kernel, so a GPU the onnxruntime build has no kernels for
        (PyPI wheels start at Pascal; a Maxwell card fails with
        cudaErrorNoKernelImageForDevice) only shows up here."""
        import numpy as np

        model.recognize(np.zeros(SAMPLE_RATE, dtype=np.float32), sample_rate=SAMPLE_RATE)

    def _load_model(self):
        if self._model is not None:
            return self._model
        # Spawn the diarization worker BEFORE onnxruntime initializes a CUDA
        # context in this process (see DiarizationMixin).
        self._ensure_diar_worker()
        try:
            import onnx_asr  # noqa: F401  (presence check; used in _create_sessions)
            import onnxruntime as ort
        except ImportError as exc:
            raise EngineError(
                "onnx-asr is not installed — install requirements-stt.txt "
                "or use the CUDA/CPU docker image"
            ) from exc
        providers = self._choose_providers(self.device, self._available_providers())
        if providers[0] == "CUDAExecutionProvider":
            # Load CUDA/cuDNN from the nvidia pip wheels torch pinned rather than
            # whatever the system has (cuDNN 9.2x is known to fail on old cards).
            try:
                ort.preload_dlls()
            except Exception as exc:  # older onnxruntime without the helper
                log.debug("onnxruntime preload_dlls skipped: %s", exc)
        t0 = time.monotonic()
        log.info("loading parakeet model %r (providers=%s, quantization=%s)",
                 self.model_name, providers, self.quantization)
        try:
            model, vad = self._create_sessions(providers)
            if providers[0] == "CUDAExecutionProvider":
                try:
                    self._warm_up(model)
                except Exception as exc:
                    # Keep the GPU for diarization (a separate process); only
                    # this recognizer moves to the CPU.
                    log.warning("parakeet cannot run on this GPU (%s); falling back to the CPU",
                                str(exc).strip().splitlines()[-1][:200])
                    del model
                    providers = ["CPUExecutionProvider"]
                    model, vad = self._create_sessions(providers)
        except Exception as exc:
            raise EngineError(f"could not load parakeet model {self.model_name!r}: {exc}") from exc
        self.device_used = self._detect_device(model, providers)
        if self.device_used == "cuda":
            mark_cuda_used()
        self._model, self._vad = model, vad
        self.load_seconds = time.monotonic() - t0
        log.info("parakeet model loaded in %.1fs on %s", self.load_seconds, self.device_used)
        return self._model

    # -- transcription ------------------------------------------------------

    async def transcribe(
        self, audio_path: Path, hotwords: str | None = None, progress: ProgressCallback | None = None
    ) -> EngineResult:
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, audio_path, hotwords, progress)

    @staticmethod
    def _decode_waveform(audio_path: Path):
        """Decode any container/codec PyAV can read into a mono 16 kHz float32
        array (onnx-asr itself only reads PCM WAV)."""
        import av
        import numpy as np

        resampler = av.AudioResampler(format="fltp", layout="mono", rate=SAMPLE_RATE)
        chunks: list = []
        with av.open(str(audio_path)) as container:
            for frame in container.decode(audio=0):
                for rframe in resampler.resample(frame):
                    chunks.append(rframe.to_ndarray()[0])
            for rframe in resampler.resample(None):  # flush buffered samples
                chunks.append(rframe.to_ndarray()[0])
        if not chunks:
            raise EngineError(f"no audio decoded from {audio_path.name}")
        return np.concatenate(chunks).astype(np.float32, copy=False)

    def _recognize(self, wav, enhanced=None):
        """Iterate onnx-asr timestamped chunk results over the whole waveform:
        VAD-cut at silences, decoded in batches, yielded in audio order. With
        ``enhanced`` (the DeepFilterNet copy of ``wav``, same length) the
        silences are found on that copy and the cuts applied to ``wav``."""
        vad = self._vad if enhanced is None else _ProxyVad(self._vad, enhanced)
        recognizer = self._model.with_vad(
            vad,
            batch_size=self.batch_size,
            max_speech_duration_s=self.max_segment_s,
            min_silence_duration_ms=self.min_silence_ms,
            speech_pad_ms=SPEECH_PAD_MS,
        ).with_timestamps()
        # No language option: onnx-asr's Parakeet decoders ignore it (only its
        # Whisper/Canary models take one), and v3 detects the language itself.
        return recognizer.recognize(wav, sample_rate=SAMPLE_RATE)

    @staticmethod
    def _words_from_tokens(
        seg_start: float, seg_end: float, tokens: list[str] | None, timestamps: list[float] | None
    ) -> list[tuple[float, float, str]]:
        """Regroup subword tokens into words with absolute times.

        onnx-asr's NeMo tokens carry a leading space on the first piece of a
        word (" The"; "ce", "X" continue it; "," and "." attach to the word
        before). A token's timestamp is its emission time relative to the chunk
        start. A word runs from its first token to the next word's first token,
        the chunk end for the last one. Word texts keep the leading space so
        DiarizationMixin can concatenate them back into segment text."""
        if not tokens or not timestamps:
            return []
        grouped: list[list] = []  # [relative start, text]
        for tok, ts in zip(tokens, timestamps):
            if not tok:
                continue
            if tok.startswith(" ") or not grouped:
                grouped.append([float(ts), tok])
            else:
                grouped[-1][1] += tok
        length = max(seg_end - seg_start, 0.0)
        words: list[tuple[float, float, str]] = []
        for i, (rel, text) in enumerate(grouped):
            rel = min(max(rel, 0.0), length)
            nxt = grouped[i + 1][0] if i + 1 < len(grouped) else length
            rel_end = min(max(nxt, rel), length)
            if rel_end <= rel:
                rel_end = rel + 0.05
            text = text if text.startswith(" ") else " " + text
            words.append((round(seg_start + rel, 3), round(seg_start + rel_end, 3), text))
        return words

    def _transcribe_sync(
        self, audio_path: Path, hotwords: str | None = None, progress: ProgressCallback | None = None
    ) -> EngineResult:
        probed = probe_duration(audio_path)
        if probed and probed > self.max_duration_s:
            raise EngineError(
                f"audio is {probed / 3600:.1f} h, over the "
                f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )
        if hotwords and not self._hotwords_noted:
            log.info("parakeet takes no hotwords prompt; the vocabulary's corrections still apply")
            self._hotwords_noted = True
        if self.language and not self._language_noted:
            log.warning("PB_TRANSCRIBE_LANGUAGE=%s is ignored by parakeet (it detects the language "
                        "itself); the transcript's language field stays empty", self.language)
            self._language_noted = True

        self._load_model()
        # Noisy recording? Speech is then located on a DeepFilterNet-cleaned
        # copy (kept in the temp dir for diarization) and parakeet decodes those
        # regions of the original; see enhance.py for why not the copy itself.
        with tempfile.TemporaryDirectory(prefix="pb-enhance-") as tmp:
            plan = (
                self.enhancer.plan(audio_path, Path(tmp), max_duration_s=self.max_duration_s)
                if self.enhancer else None
            )
            return self._decode(audio_path, progress, plan)

    def _decode(self, audio_path: Path, progress: ProgressCallback | None, plan) -> EngineResult:
        t0 = time.monotonic()
        try:
            wav = plan.original if plan is not None else self._decode_waveform(audio_path)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"could not decode audio: {exc}") from exc
        duration = len(wav) / SAMPLE_RATE
        # Backstop for streams whose header lied or lacked a duration.
        if duration > self.max_duration_s:
            raise EngineError(
                f"audio is {duration / 3600:.1f} h, over the "
                f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )

        segments: list[Segment] = []
        # (start, end, word, index of the chunk it came from)
        words: list[tuple[float, float, str, int]] = []
        last_report = 0.0
        try:
            enhanced = plan.enhanced if plan is not None else None
            for result in self._recognize(wav, enhanced):  # generator: inference happens during this loop
                text = (result.text or "").strip()
                if not text:
                    continue
                idx = len(segments)
                segments.append(Segment(start=round(result.start, 2), end=round(result.end, 2), text=text))
                if self.diarization:
                    for w_start, w_end, w_text in self._words_from_tokens(
                        result.start, result.end,
                        getattr(result, "tokens", None), getattr(result, "timestamps", None),
                    ):
                        words.append((w_start, w_end, w_text, idx))
                now = time.monotonic()
                if progress and duration and now - last_report >= PROGRESS_INTERVAL_S:
                    last_report = now
                    progress("transcribing", min(0.99, max(0.0, result.end / duration)))
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"parakeet transcription failed: {exc}") from exc
        transcribe_s = time.monotonic() - t0

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
            "quantization": self.quantization,
            "transcribe_seconds": round(transcribe_s, 2),
            "diarize_seconds": round(diarize_s, 2) or None,
            "rtf": round(transcribe_s / duration, 3) if duration else None,
        }
        if plan is not None:
            stats.update(plan.stats())
        return EngineResult(
            text=render_text(segments, fallback=plain),
            segments=segments,
            # Not the configured language: parakeet neither honours nor reports
            # one, and claiming it would mislabel speech in another language.
            language=None,
            duration=round(duration, 2) if duration else None,
            model=self.model_name,
            stats={k: v for k, v in stats.items() if v is not None},
        )


class _ProxyVad:
    """onnx-asr ``Vad`` that segments one waveform (the enhanced copy) and
    applies the cuts to another (the original) — the noisy-recording path.
    Both are the same length; region ends are clamped in case the enhancer's
    resampling left them a few samples apart."""

    def __init__(self, inner, enhanced):
        self._inner = inner
        self._enhanced = enhanced

    def recognize_batch(self, asr, waveforms, waveforms_len, sample_rate, asr_kwargs, batch_size=8, **kwargs):
        from itertools import islice

        import numpy as np
        from onnx_asr.utils import pad_list
        from onnx_asr.vad import TimestampedSegmentResult

        enh = self._enhanced.astype(np.float32, copy=False)[None, :]
        enh_len = np.array([enh.shape[1]], dtype=np.int64)

        def recognize(waveform, length, segment):
            length = int(length)
            while batch := list(islice(segment, int(batch_size))):
                batch = [(max(0, s), min(e, length)) for s, e in batch]
                batch = [(s, e) for s, e in batch if e > s]
                if not batch:
                    continue
                results = asr.recognize_batch(*pad_list([waveform[s:e] for s, e in batch]), **asr_kwargs)
                for res, (s, e) in zip(results, batch, strict=True):
                    yield TimestampedSegmentResult(
                        s / sample_rate, e / sample_rate, res.text, res.timestamps, res.tokens, res.logprobs
                    )

        # One enhanced copy => the proxy serves a batch of one waveform.
        segments = self._inner.segment_batch(enh, enh_len, sample_rate, **kwargs)
        return (recognize(w, n, seg) for w, n, seg in zip(waveforms, waveforms_len, segments))
