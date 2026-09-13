"""Built-in transcription: Qwen3-ASR (Alibaba's 1.7B speech LLM) via
transformers, with the Qwen3 forced aligner for word timestamps and the same
optional pyannote diarization as the other engines.

Why a third built-in engine: on a shootout over the author's own recordings on an
L40S (Sep 2026) Qwen3-ASR-1.7B was the only single model that got the hard
phrases of a noisy car conversation right — "Sleepless in Seattle", "you were
flying home", "Sam kind of lead into it" — which whisper large-v3 and parakeet
only recovered together through the consensus pass; on clean speech it matched
whisper. It takes a free-text context prompt (the custom vocabulary rides in
as ``Vocabulary: …``), detects the language (or takes one), and handles
speech, singing and music. It wants a real GPU: 2B parameters in bf16, about
5 GB with the aligner, so it lives in the CUDA image (requirements-qwen.txt).

Design notes:
- The model decodes one utterance at a time, so the recording is cut at
  silences (Silero VAD) into chunks of at most ``chunk_s`` seconds and decoded
  in batches; each chunk becomes one segment. On a noisy recording the cuts
  come from the DeepFilterNet copy (see enhance.py) and are applied to the
  original audio.
- Word timestamps come from Qwen3-ForcedAligner-0.6B (one forward pass per
  chunk) and feed the word-level speaker assignment in DiarizationMixin; with
  the aligner off, diarization falls back to per-segment assignment.
- Consensus second opinions on noisy recordings are whisper (raw audio, same
  regions) and parakeet, borrowed from a LocalWhisperEngine helper.
- Models load lazily and stay warm; a lock serializes access; the shared-GPU
  housekeeping (idle unload, free-VRAM guard) mirrors the whisper engine.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path

from .base import Alternate, EngineError, EngineResult, ProgressCallback, Segment, render_text
from .diarization import DiarizationMixin, probe_duration
from .enhance import Enhancer, decode_waveform, speech_chunks

log = logging.getLogger("plaud-bridge.engine.qwen3")

SAMPLE_RATE = 16_000
DEFAULT_MODEL = "Qwen/Qwen3-ASR-1.7B-hf"
DEFAULT_ALIGNER = "Qwen/Qwen3-ForcedAligner-0.6B-hf"
PROGRESS_INTERVAL_S = 2.0
# Language codes → the names the aligner wants.
LANGUAGE_NAMES = {
    "en": "English", "zh": "Chinese", "yue": "Cantonese", "fr": "French", "de": "German", "it": "Italian",
    "ja": "Japanese", "ko": "Korean", "pt": "Portuguese", "ru": "Russian", "es": "Spanish",
}


class Qwen3AsrEngine(DiarizationMixin):
    name = "qwen3"

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        aligner: str | None = DEFAULT_ALIGNER,
        device: str = "auto",
        language: str | None = None,
        max_duration_s: int = 5 * 3600,
        diarization: bool = False,
        diarization_model: str = "pyannote/speaker-diarization-community-1",
        hf_token: str | None = None,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        diarization_device: str | None = None,
        enhancer: Enhancer | None = None,
        enhance_diarize: bool = True,
        consensus: bool = False,
        alternates_engine=None,
        chunk_s: float = 30.0,
        batch_size: int = 4,
        max_new_tokens: int = 512,
        idle_unload_s: int = 0,
        min_free_vram_mb: int = 0,
    ):
        self.model_name = model
        self.aligner_name = aligner or None
        self.device = device
        self.language = language
        self.max_duration_s = max_duration_s
        self.diarization = diarization
        self.diarization_model = diarization_model
        self.diarization_device = diarization_device
        self.hf_token = hf_token
        self.num_speakers = num_speakers
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.enhancer = enhancer
        self.enhance_diarize = enhance_diarize
        # A LocalWhisperEngine (diarization and consensus off) that supplies the
        # whisper + parakeet second opinions when a recording measured noisy.
        self.consensus = consensus
        self.alternates_engine = alternates_engine
        self.chunk_s = chunk_s
        self.batch_size = max(1, batch_size)
        self.max_new_tokens = max_new_tokens
        self.idle_unload_s = idle_unload_s
        self.min_free_vram_mb = min_free_vram_mb
        self._idle_task: asyncio.Task | None = None
        self._last_used = 0.0
        self.device_used: str | None = None
        self._diar_device_forced = False  # pyannote sent to the CPU by the VRAM guard, not by config
        # Once any model has run on the GPU in this process, the pyannote worker
        # can no longer be respawned (see DiarizationMixin): keep whichever one
        # exists from then on, even after an idle unload / CPU round trip.
        self._cuda_used = False
        self._model = None
        self._processor = None
        self._aligner = None
        self._aligner_processor = None
        self._diar_proc = None
        self._lock = asyncio.Lock()
        self.load_seconds: float | None = None

    # -- model loading ------------------------------------------------------

    def _pick_device(self) -> str:
        from .local_whisper import gpu_free_mb

        try:
            import torch

            cuda = torch.cuda.is_available()
        except ImportError as exc:
            raise EngineError("torch is not installed — use the CUDA image for the qwen3 engine") from exc
        if self.device == "cpu" or not cuda:
            return "cpu"
        if self.min_free_vram_mb:
            free = gpu_free_mb()
            if free is not None and free < self.min_free_vram_mb:
                log.warning("GPU has %d MB free, under PB_STT_MIN_FREE_VRAM_MB=%d: loading Qwen3-ASR on the CPU",
                            free, self.min_free_vram_mb)
                return "cpu"
        return "cuda"

    def _load_model(self):
        if self._model is not None:
            if self.device_used == "cpu" and self._pick_device() == "cuda":
                # Loaded on the CPU while the card was full (a training run);
                # it has room now, so start over on the GPU. This process has
                # never held a CUDA context (everything ran on the CPU), so the
                # diarization worker can be respawned on the GPU as well.
                log.info("GPU has room again: reloading Qwen3-ASR on it")
                self.unload()
                if self._diar_device_forced and not self._cuda_used:
                    self.close()
                    self.diarization_device = None
                    self._diar_device_forced = False
            else:
                return self._model
        # Decide the device before the diarization worker spawns so pyannote
        # follows whisper-engine rules: a short card sends both to the CPU.
        device = self._pick_device()
        if device == "cpu" and not self.diarization_device and self._diar_proc is None and not self._cuda_used:
            self.diarization_device = "cpu"
            self._diar_device_forced = True
        self._ensure_diar_worker()
        try:
            import torch
            from transformers import AutoModelForMultimodalLM, AutoProcessor
        except ImportError as exc:
            raise EngineError("transformers>=5.13 is not installed — install requirements-qwen.txt") from exc
        t0 = time.monotonic()
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        log.info("loading Qwen3-ASR %r (device=%s, dtype=%s)", self.model_name, device, str(dtype).split(".")[-1])
        self._processor = AutoProcessor.from_pretrained(self.model_name)
        self._model = AutoModelForMultimodalLM.from_pretrained(self.model_name, dtype=dtype, device_map=device).eval()
        if self.aligner_name:
            from transformers import AutoModelForTokenClassification

            log.info("loading forced aligner %r", self.aligner_name)
            self._aligner_processor = AutoProcessor.from_pretrained(self.aligner_name)
            self._aligner = AutoModelForTokenClassification.from_pretrained(
                self.aligner_name, dtype=dtype, device_map=device).eval()
        self.device_used = device
        self._cuda_used = self._cuda_used or device == "cuda"
        self.load_seconds = time.monotonic() - t0
        log.info("Qwen3-ASR loaded in %.1fs", self.load_seconds)
        return self._model

    # -- shared-GPU housekeeping --------------------------------------------

    def unload(self) -> None:
        if self._model is None:
            return
        log.info("unloading Qwen3-ASR (%s)", f"after {self.idle_unload_s}s idle" if self.idle_unload_s else "reload")
        self._model = self._processor = self._aligner = self._aligner_processor = None
        alt = self.alternates_engine
        if alt is not None:
            alt.unload()
        import gc

        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def _touch(self) -> None:
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

    def _transcribe_sync(
        self, audio_path: Path, hotwords: str | None = None, progress: ProgressCallback | None = None
    ) -> EngineResult:
        probed = probe_duration(audio_path)
        if probed and probed > self.max_duration_s:
            raise EngineError(
                f"audio is {probed / 3600:.1f} h, over the {self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )
        self._load_model()
        with tempfile.TemporaryDirectory(prefix="pb-enhance-") as tmp:
            plan = self.enhancer.plan(audio_path, Path(tmp), max_duration_s=self.max_duration_s) if self.enhancer else None
            return self._decode(audio_path, hotwords, progress, plan)

    def _prompt(self, hotwords: str | None) -> str | None:
        return f"Vocabulary: {hotwords}." if hotwords else None

    def _conversations(self, clips: list, hotwords: str | None) -> list[list[dict]]:
        """Chat-template conversations for a batch: the vocabulary as a system
        message (the model card's context/hotwords form), the audio as the user
        turn, and — when a language is forced — the assistant turn prefilled
        with ``language <Name><asr_text>`` so decoding continues from there
        (an empty prefill otherwise, as every row of a batch needs one)."""
        prompt = self._prompt(hotwords)
        lang = LANGUAGE_NAMES.get((self.language or "").lower(), self.language) if self.language else None
        prefill = f"language {lang}<asr_text>" if lang else ""
        conversations = []
        for clip in clips:
            conv: list[dict] = []
            if prompt:
                conv.append({"role": "system", "content": [{"type": "text", "text": prompt}]})
            conv.append({"role": "user", "content": [{"type": "audio", "audio": clip}]})
            conv.append({"role": "assistant", "content": [{"type": "text", "text": prefill}]})
            conversations.append(conv)
        return conversations

    def _generate(self, clips: list, hotwords: str | None) -> list[tuple[str, str | None]]:
        """Decode a batch of waveform chunks → [(text, language name or None)]."""
        import torch

        proc, model = self._processor, self._model
        inputs = proc.apply_chat_template(
            self._conversations(clips, hotwords), tokenize=True, return_dict=True, return_tensors="pt",
            continue_final_message=True,
        ).to(model.device, model.dtype)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        gen = out[:, inputs["input_ids"].shape[1]:]
        parsed = proc.decode(gen, return_format="parsed")
        result = []
        for p in parsed:
            if isinstance(p, dict):
                result.append(((p.get("transcription") or "").strip(), p.get("language") or None))
            else:
                result.append((str(p).strip(), None))
        return result

    def _align(self, clip, text: str, language: str | None) -> list[tuple[float, float, str]]:
        """Word (start, end, text) relative to the chunk start, via the forced
        aligner; empty when the aligner is off or fails."""
        if self._aligner is None or not text:
            return []
        import torch

        lang = LANGUAGE_NAMES.get((language or "").lower(), language) or "English"
        try:
            inputs, word_lists = self._aligner_processor.prepare_forced_aligner_inputs(
                audio=clip, transcript=text, language=lang)
            inputs = inputs.to(self._aligner.device, self._aligner.dtype)
            with torch.inference_mode():
                logits = self._aligner(**inputs).logits
            items = self._aligner_processor.decode_forced_alignment(
                logits=logits, input_ids=inputs["input_ids"], word_lists=word_lists,
                timestamp_token_id=self._aligner.config.timestamp_token_id)[0]
        except Exception as exc:
            log.warning("forced alignment failed for a chunk: %s", exc)
            return []
        return [(float(i["start_time"]), float(i["end_time"]), str(i["text"])) for i in items]

    @staticmethod
    def _words_for(idx: int, start: float, end: float, text: str,
                   aligned: list[tuple[float, float, str]]) -> list[tuple[float, float, str, int]]:
        """Word tuples for DiarizationMixin, on the recognized text's own
        tokens: the aligner normalizes (drops punctuation, splits numbers), so
        its times are mapped back onto the original whitespace tokens when the
        counts agree. Otherwise — no alignment, a count mismatch, a script
        without spaces — the whole segment becomes one word, which keeps it
        in the transcript with a segment-level speaker instead of dropping it
        (the mixin rebuilds the transcript from the word list)."""
        tokens = text.split()
        if aligned and len(aligned) == len(tokens):
            return [(round(start + a, 3), round(start + b, 3), " " + tok, idx)
                    for (a, b, _), tok in zip(aligned, tokens)]
        return [(round(start, 3), round(end, 3), " " + text, idx)]

    def _decode(self, audio_path: Path, hotwords: str | None, progress: ProgressCallback | None, plan) -> EngineResult:
        t0 = time.monotonic()
        try:
            wav = plan.original if plan is not None else decode_waveform(audio_path)
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"could not decode audio: {exc}") from exc
        duration = len(wav) / SAMPLE_RATE
        if duration > self.max_duration_s:
            raise EngineError(
                f"audio is {duration / 3600:.1f} h, over the {self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )
        vad_source = plan.enhanced if plan is not None else wav
        chunks = speech_chunks(vad_source, self.chunk_s)
        segments: list[Segment] = []
        words: list[tuple[float, float, str, int]] = []
        languages: list[str] = []
        last_report = 0.0
        try:
            for i in range(0, len(chunks), self.batch_size):
                batch = chunks[i:i + self.batch_size]
                clips = [wav[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)] for s, e in batch]
                for (s, e), (text, lang) in zip(batch, self._generate(clips, hotwords)):
                    if not text:
                        continue
                    if lang:
                        languages.append(lang)
                    idx = len(segments)
                    segments.append(Segment(start=round(s, 2), end=round(e, 2), text=text))
                    if self.diarization:
                        clip = wav[int(s * SAMPLE_RATE):int(e * SAMPLE_RATE)]
                        words.extend(self._words_for(idx, s, e, text, self._align(clip, text, lang)))
                now = time.monotonic()
                if progress and duration and now - last_report >= PROGRESS_INTERVAL_S:
                    last_report = now
                    progress("transcribing", min(0.99, max(0.0, batch[-1][1] / duration)))
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"Qwen3-ASR transcription failed: {exc}") from exc
        transcribe_s = time.monotonic() - t0

        alternates: list[Alternate] = []
        alternates_s = 0.0
        if self.consensus and plan is not None and segments and self.alternates_engine is not None:
            if progress:
                progress("transcribing", 0.99)
            t1 = time.monotonic()
            alternates = self._alternates(audio_path, hotwords, plan)
            alternates_s = time.monotonic() - t1

        diarize_s = 0.0
        if self.diarization and segments:
            if progress:
                progress("diarizing", None)
            t1 = time.monotonic()
            diar_path = plan.enhanced_path if plan is not None and self.enhance_diarize else audio_path
            try:
                self._apply_diarization(diar_path, segments, words)
            except Exception as exc:
                log.warning("diarization failed, returning unlabeled transcript: %s", exc)
            diarize_s = time.monotonic() - t1

        plain = " ".join(s.text for s in segments if s.text)
        language = None
        if languages:
            top = max(set(languages), key=languages.count)
            language = next((code for code, name in LANGUAGE_NAMES.items() if name == top), top)
        stats = {
            "engine": self.name,
            "model": self.model_name,
            "aligner": self.aligner_name if words else None,
            "device": self.device_used or self.device,
            "chunks": len(chunks),
            "transcribe_seconds": round(transcribe_s, 2),
            "diarize_seconds": round(diarize_s, 2) or None,
            "rtf": round(transcribe_s / duration, 3) if duration else None,
        }
        if plan is not None:
            stats.update(plan.stats())
        if alternates:
            stats["alternates"] = [a.name for a in alternates]
            stats["alternates_seconds"] = round(alternates_s, 2)
        return EngineResult(
            text=render_text(segments, fallback=plain),
            segments=segments,
            language=language or self.language,
            duration=round(duration, 2) if duration else None,
            model=self.model_name,
            stats={k: v for k, v in stats.items() if v is not None},
            alternates=alternates,
        )

    # -- second opinions for the consensus pass ------------------------------

    def _alternates(self, audio_path: Path, hotwords: str | None, plan) -> list[Alternate]:
        """whisper on the raw audio over the same speech regions, and parakeet,
        both from the helper whisper engine; each failure is logged and skipped."""
        out: list[Alternate] = []
        helper = self.alternates_engine
        try:
            model = helper._load_model()
            clips = plan.clip_timestamps if plan.regions else None
            seg_iter, _info = model.transcribe(
                str(audio_path), language=helper.language, beam_size=helper.beam_size,
                vad_filter=clips is None, clip_timestamps=clips if clips is not None else "0",
                hotwords=helper._fit_hotwords(model, hotwords) or None, condition_on_previous_text=False,
            )
            segs = [Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip()) for s in seg_iter]
            out.append(Alternate(name=f"whisper {helper.model_name} on the raw audio", segments=segs))
        except Exception as exc:
            log.warning("consensus alternate (whisper) failed: %s", exc)
        if helper.consensus_parakeet_model:
            try:
                result = helper._parakeet()._decode(audio_path, None, plan)
                out.append(Alternate(name=f"parakeet {helper.consensus_parakeet_model} on the raw audio",
                                     segments=result.segments))
            except Exception as exc:
                log.warning("consensus alternate (parakeet) failed: %s", exc)
        return out
