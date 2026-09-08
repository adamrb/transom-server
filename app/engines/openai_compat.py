"""External engine: any OpenAI-compatible /v1/audio/transcriptions endpoint
(speaches, faster-whisper-server, whisper.cpp server, hosted APIs)."""

import logging
import mimetypes
import time
from pathlib import Path

import httpx

from .base import EngineError, EngineResult, Segment, render_text

log = logging.getLogger("plaud-bridge.engine.openai")


class OpenAICompatEngine:
    name = "openai"

    def __init__(
        self,
        base_url: str,
        model: str = "whisper-1",
        api_key: str | None = None,
        language: str | None = None,
        timeout_s: int = 1800,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.language = language
        self.timeout_s = timeout_s

    async def transcribe(self, audio_path: Path, hotwords: str | None = None, progress=None) -> EngineResult:
        # `progress` is accepted for interface parity; a remote endpoint gives
        # no partial results to report.
        url = f"{self.base_url}/audio/transcriptions"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        t0 = time.monotonic()
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            for response_format in ("verbose_json", "json"):
                data = {"model": self.model, "response_format": response_format}
                if self.language:
                    data["language"] = self.language
                if hotwords:
                    data["prompt"] = hotwords  # the API's vocabulary hint
                mime = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
                with audio_path.open("rb") as fh:
                    resp = await client.post(
                        url, headers=headers, data=data,
                        files={"file": (audio_path.name, fh, mime)},
                    )
                if resp.status_code == 200:
                    return self._parse(resp.json(), time.monotonic() - t0)
                # Some servers reject verbose_json; retry once with plain json.
                if response_format == "verbose_json" and resp.status_code in (400, 422):
                    continue
                raise EngineError(f"endpoint returned {resp.status_code}: {resp.text[:300]}")
        raise EngineError("unreachable")

    def _parse(self, body: dict, elapsed: float) -> EngineResult:
        segments = [
            Segment(start=s.get("start"), end=s.get("end"), text=(s.get("text") or "").strip())
            for s in body.get("segments") or []
        ]
        duration = body.get("duration")
        stats = {
            "engine": self.name,
            "model": self.model,
            "transcribe_seconds": round(elapsed, 2),
        }
        if duration:
            stats["rtf"] = round(elapsed / duration, 3)
        return EngineResult(
            text=render_text(segments, fallback=body.get("text", "")),
            segments=segments,
            language=body.get("language"),
            duration=duration,
            model=self.model,
            stats=stats,
        )
