"""Environment-driven configuration. All settings use the PB_ prefix."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is not None and val.strip() != "":
        return val.strip()
    return default


def _env_bool(name: str, default: bool) -> bool:
    val = _env(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    # Plaud developer credentials (portal.plaud.ai -> Embedded SDK application)
    plaud_client_id: str | None = field(default_factory=lambda: _env("PB_PLAUD_CLIENT_ID"))
    plaud_secret_key: str | None = field(default_factory=lambda: _env("PB_PLAUD_SECRET_KEY"))
    plaud_api_base: str = field(
        default_factory=lambda: _env("PB_PLAUD_API_BASE", "https://platform-us.plaud.ai/developer/api")
    )

    # Bearer tokens accepted from clients (comma-separated to allow rotation)
    auth_tokens: list[str] = field(
        default_factory=lambda: [t.strip() for t in (_env("PB_AUTH_TOKENS") or "").split(",") if t.strip()]
    )

    data_dir: Path = field(default_factory=lambda: Path(_env("PB_DATA_DIR", "/data")))
    max_upload_mb: int = field(default_factory=lambda: int(_env("PB_MAX_UPLOAD_MB", "500")))

    # Android app distribution: hosted-APK upload size cap, and an optional
    # directory (baked into release docker images) holding a bundled APK +
    # manifest.json that gets auto-published at startup if newer than hosted.
    apk_max_upload_mb: int = field(default_factory=lambda: int(_env("PB_APK_MAX_UPLOAD_MB", "300")))
    bundled_apk_dir: Path = field(
        default_factory=lambda: Path(_env("PB_BUNDLED_APK_DIR", "/srv/plaud-bridge/bundled-apk"))
    )

    # Transcription. PB_STT_ENGINE selects the backend:
    #   local  — built-in faster-whisper (GPU/CPU), optional diarization (default)
    #   openai — external OpenAI-compatible /v1/audio/transcriptions endpoint
    transcribe_enabled: bool = field(default_factory=lambda: _env_bool("PB_TRANSCRIBE_ENABLED", True))
    # Default: local. Pre-engine deployments that configured an external
    # endpoint (PB_TRANSCRIBE_BASE_URL) but no PB_STT_ENGINE keep using it.
    stt_engine: str = field(
        default_factory=lambda: _env(
            "PB_STT_ENGINE", "openai" if _env("PB_TRANSCRIBE_BASE_URL") else "local"
        )
    )

    # -- built-in (local) engine --
    stt_model: str = field(default_factory=lambda: _env("PB_STT_MODEL", "base"))
    stt_device: str = field(default_factory=lambda: _env("PB_STT_DEVICE", "auto"))
    stt_compute: str = field(default_factory=lambda: _env("PB_STT_COMPUTE", "auto"))
    stt_vad: bool = field(default_factory=lambda: _env_bool("PB_STT_VAD", True))
    stt_beam_size: int = field(default_factory=lambda: int(_env("PB_STT_BEAM_SIZE", "5")))
    # Plaud hardware records up to ~5 h per file; reject anything longer.
    stt_max_duration_s: int = field(default_factory=lambda: int(_env("PB_STT_MAX_DURATION_S", "18000")))
    # Speaker diarization (multi-speaker labeling); needs requirements-diarization.txt
    # and a Hugging Face token that accepted pyannote/speaker-diarization-3.1 terms.
    stt_diarize: bool = field(default_factory=lambda: _env_bool("PB_STT_DIARIZE", False))
    stt_hf_token: str | None = field(default_factory=lambda: _env("PB_STT_HF_TOKEN"))

    # -- external (openai) engine --
    transcribe_base_url: str | None = field(default_factory=lambda: _env("PB_TRANSCRIBE_BASE_URL"))
    transcribe_api_key: str | None = field(default_factory=lambda: _env("PB_TRANSCRIBE_API_KEY"))
    transcribe_model: str = field(default_factory=lambda: _env("PB_TRANSCRIBE_MODEL", "whisper-1"))
    transcribe_language: str | None = field(default_factory=lambda: _env("PB_TRANSCRIBE_LANGUAGE"))
    transcribe_timeout_s: int = field(default_factory=lambda: int(_env("PB_TRANSCRIBE_TIMEOUT_S", "1800")))
    transcribe_max_attempts: int = field(default_factory=lambda: int(_env("PB_TRANSCRIBE_MAX_ATTEMPTS", "3")))

    # Optional LLM summarization of each transcript (any OpenAI-compatible chat
    # endpoint). Defaults to off; base URL should include the /v1 suffix.
    summary_enabled: bool = field(default_factory=lambda: _env_bool("PB_SUMMARY_ENABLED", False))
    summary_base_url: str | None = field(default_factory=lambda: _env("PB_SUMMARY_BASE_URL"))
    summary_api_key: str | None = field(default_factory=lambda: _env("PB_SUMMARY_API_KEY"))
    summary_model: str | None = field(default_factory=lambda: _env("PB_SUMMARY_MODEL"))
    summary_prompt: str = field(
        default_factory=lambda: _env(
            "PB_SUMMARY_PROMPT",
            "Summarize this voice recording transcript. Start with a one-line title, "
            "then a concise summary, then any action items as a bullet list. "
            "If the transcript is trivial (a few words), just restate it.",
        )
    )
    summary_max_chars: int = field(default_factory=lambda: int(_env("PB_SUMMARY_MAX_CHARS", "60000")))

    # Optional AI routing: after transcription (and summarization) an LLM
    # decides which configured routes apply and their actions run. The chat
    # endpoint settings fall back to the PB_SUMMARY_* equivalents so a single
    # configured LLM can serve both features.
    router_enabled: bool = field(default_factory=lambda: _env_bool("PB_ROUTER_ENABLED", False))
    router_base_url: str | None = field(
        default_factory=lambda: _env("PB_ROUTER_BASE_URL") or _env("PB_SUMMARY_BASE_URL")
    )
    router_api_key: str | None = field(
        default_factory=lambda: _env("PB_ROUTER_API_KEY") or _env("PB_SUMMARY_API_KEY")
    )
    router_model: str | None = field(
        default_factory=lambda: _env("PB_ROUTER_MODEL") or _env("PB_SUMMARY_MODEL")
    )
    # How much of the transcript the router sees (≈ first 500-800 words)
    router_max_chars: int = field(default_factory=lambda: int(_env("PB_ROUTER_MAX_CHARS", "4000")))

    # Optional: POSTed after each successful transcription (see README for payload)
    webhook_url: str | None = field(default_factory=lambda: _env("PB_WEBHOOK_URL"))
    webhook_auth_header: str | None = field(default_factory=lambda: _env("PB_WEBHOOK_AUTH_HEADER"))

    # Optional: also write a human-readable markdown note per transcript here
    # (point it at an Obsidian vault folder, a syncthing dir, etc.)
    markdown_export_dir: Path | None = field(
        default_factory=lambda: Path(p) if (p := _env("PB_MARKDOWN_EXPORT_DIR")) else None
    )

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def apk_dir(self) -> Path:
        return self.data_dir / "apk"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "plaud-bridge.sqlite3"

    def validate(self) -> list[str]:
        """Return a list of human-readable configuration warnings."""
        warnings = []
        if not self.auth_tokens:
            warnings.append("PB_AUTH_TOKENS is empty — all authenticated endpoints will reject requests.")
        if not (self.plaud_client_id and self.plaud_secret_key):
            warnings.append(
                "PB_PLAUD_CLIENT_ID / PB_PLAUD_SECRET_KEY not set — /plaud/user-token will be unavailable."
            )
        if self.transcribe_enabled and self.stt_engine == "openai" and not self.transcribe_base_url:
            warnings.append("PB_STT_ENGINE=openai but PB_TRANSCRIBE_BASE_URL is not set — uploads stored, not transcribed.")
        if self.stt_diarize and not self.stt_hf_token:
            warnings.append("PB_STT_DIARIZE is on but PB_STT_HF_TOKEN is not set — diarization will likely fail to load.")
        if self.summary_enabled and not (self.summary_base_url and self.summary_model):
            warnings.append(
                "PB_SUMMARY_ENABLED is on but PB_SUMMARY_BASE_URL/PB_SUMMARY_MODEL are missing — summaries disabled."
            )
        if self.router_enabled and not (self.router_base_url and self.router_model):
            warnings.append(
                "PB_ROUTER_ENABLED is on but no chat endpoint is configured "
                "(PB_ROUTER_BASE_URL/PB_ROUTER_MODEL or the PB_SUMMARY_* equivalents) — routing disabled."
            )
        return warnings


settings = Settings()
