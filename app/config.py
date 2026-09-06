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

    # OpenAI-compatible transcription endpoint (e.g. speaches, faster-whisper-server,
    # or api.openai.com). Base URL should include the /v1 suffix.
    transcribe_enabled: bool = field(default_factory=lambda: _env_bool("PB_TRANSCRIBE_ENABLED", True))
    transcribe_base_url: str | None = field(default_factory=lambda: _env("PB_TRANSCRIBE_BASE_URL"))
    transcribe_api_key: str | None = field(default_factory=lambda: _env("PB_TRANSCRIBE_API_KEY"))
    transcribe_model: str = field(default_factory=lambda: _env("PB_TRANSCRIBE_MODEL", "whisper-1"))
    transcribe_language: str | None = field(default_factory=lambda: _env("PB_TRANSCRIBE_LANGUAGE"))
    transcribe_timeout_s: int = field(default_factory=lambda: int(_env("PB_TRANSCRIBE_TIMEOUT_S", "1800")))
    transcribe_max_attempts: int = field(default_factory=lambda: int(_env("PB_TRANSCRIBE_MAX_ATTEMPTS", "3")))

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
        if self.transcribe_enabled and not self.transcribe_base_url:
            warnings.append("PB_TRANSCRIBE_BASE_URL not set — uploads will be stored but not transcribed.")
        return warnings


settings = Settings()
