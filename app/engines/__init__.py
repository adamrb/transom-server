"""Engine factory: build the configured transcription engine from Settings."""

from .base import EngineError, EngineResult, Segment, TranscriptionEngine, render_text


def build_engine(settings) -> "TranscriptionEngine | None":
    """Return the configured engine, or None when transcription is disabled
    or misconfigured (the worker then stores uploads without transcribing)."""
    if not settings.transcribe_enabled:
        return None
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
    "EngineResult",
    "Segment",
    "TranscriptionEngine",
    "build_engine",
    "render_text",
]
