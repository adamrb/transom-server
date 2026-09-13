"""Engine factory: build the configured transcription engine from Settings."""

import logging
from dataclasses import replace
from pathlib import Path

from .base import EngineError, EngineResult, Segment, TranscriptionEngine, render_text

log = logging.getLogger("plaud-bridge.engine")


class FallbackEngine:
    """Primary engine with a stand-in: when the primary raises (a remote
    worker unreachable, out of memory, timed out), the recording goes to the
    fallback instead of failing, and the result says so in ``stats``."""

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    async def transcribe(self, audio_path: Path, hotwords: str | None = None, progress=None) -> EngineResult:
        try:
            return await self.primary.transcribe(audio_path, hotwords=hotwords, progress=progress)
        except Exception as exc:
            log.warning("%s engine failed (%s); falling back to %s", self.primary.name, exc, self.fallback.name)
            result = await self.fallback.transcribe(audio_path, hotwords=hotwords, progress=progress)
            result.stats["fallback_from"] = self.primary.name
            result.stats["fallback_reason"] = f"{type(exc).__name__}: {exc}"[:300]
            return result

    def close(self):
        for engine in (self.primary, self.fallback):
            close = getattr(engine, "close", None)
            if close:
                try:
                    close()
                except Exception:
                    log.exception("engine close failed")


def build_engine(settings) -> "TranscriptionEngine | None":
    """Return the configured engine, or None when transcription is disabled
    or misconfigured (the worker then stores uploads without transcribing).
    With PB_STT_FALLBACK_ENGINE set to a different engine, both are built
    and wrapped so a failing primary hands the recording to the fallback."""
    primary = _build_one(settings)
    fb = settings.stt_fallback_engine
    if primary is None or not fb or fb == settings.stt_engine or fb not in ("local", "parakeet", "openai"):
        return primary
    fallback = _build_one(replace(settings, stt_engine=fb))
    if fallback is None:
        return primary
    return FallbackEngine(primary, fallback)


def _build_one(settings) -> "TranscriptionEngine | None":
    if not settings.transcribe_enabled:
        return None
    enhancer = None
    if settings.stt_engine in ("local", "parakeet") and settings.stt_enhance in ("auto", "always"):
        from .enhance import Enhancer

        enhancer = Enhancer(
            mode=settings.stt_enhance,
            spread_db=settings.stt_enhance_spread_db,
            binary=settings.stt_enhance_bin,
        )
    if settings.stt_engine == "local":
        from .local_whisper import LocalWhisperEngine

        return LocalWhisperEngine(
            model=settings.stt_model,
            device=settings.stt_device,
            compute_type=settings.stt_compute,
            language=settings.transcribe_language,
            vad_filter=settings.stt_vad,
            max_duration_s=settings.stt_max_duration_s,
            diarization=settings.stt_diarize,
            diarization_model=settings.stt_diarize_model,
            hf_token=settings.stt_hf_token,
            num_speakers=settings.stt_num_speakers,
            min_speakers=settings.stt_min_speakers,
            max_speakers=settings.stt_max_speakers,
            beam_size=settings.stt_beam_size,
            condition_on_previous_text=settings.stt_condition_on_previous,
            diarization_device=settings.stt_diarize_device,
            enhancer=enhancer,
            enhance_diarize=settings.stt_enhance_diarize,
            consensus=(enhancer is not None and settings.stt_consensus == "auto"
                       and bool(settings.cleanup_base_url and settings.cleanup_model)),
            consensus_parakeet_model=settings.stt_consensus_parakeet_model,
            consensus_atten_db=settings.stt_consensus_atten_db,
            consensus_parakeet_device=settings.stt_consensus_parakeet_device,
            idle_unload_s=settings.stt_idle_unload_s,
            min_free_vram_mb=settings.stt_min_free_vram_mb,
        )
    if settings.stt_engine == "parakeet":
        from .parakeet import ParakeetEngine

        return ParakeetEngine(
            model=settings.stt_parakeet_model,
            device=settings.stt_device,
            quantization=settings.stt_parakeet_quantization,
            language=settings.transcribe_language,
            max_duration_s=settings.stt_max_duration_s,
            diarization=settings.stt_diarize,
            diarization_model=settings.stt_diarize_model,
            hf_token=settings.stt_hf_token,
            num_speakers=settings.stt_num_speakers,
            min_speakers=settings.stt_min_speakers,
            max_speakers=settings.stt_max_speakers,
            max_segment_s=settings.stt_parakeet_segment_s,
            min_silence_ms=settings.stt_parakeet_silence_ms,
            diarization_device=settings.stt_diarize_device,
            enhancer=enhancer,
            enhance_diarize=settings.stt_enhance_diarize,
        )
    if settings.stt_engine == "openai":
        if not settings.transcribe_base_url:
            return None
        from .openai_compat import OpenAICompatEngine

        return OpenAICompatEngine(
            base_url=settings.transcribe_base_url,
            model=settings.transcribe_model,
            api_key=settings.transcribe_api_key,
            language=settings.transcribe_language,
            timeout_s=settings.transcribe_timeout_s,
        )
    raise ValueError(
        f"unknown PB_STT_ENGINE: {settings.stt_engine!r} (use 'local', 'parakeet' or 'openai')"
    )


__all__ = [
    "EngineError",
    "FallbackEngine",
    "EngineResult",
    "Segment",
    "TranscriptionEngine",
    "build_engine",
    "render_text",
]
