"""Transcription engine interface.

Engines take an audio file and return an EngineResult. Two implementations:

- ``local``  — built-in faster-whisper (CTranslate2), GPU or CPU, with
  optional pyannote speaker diarization. No external services.
- ``openai`` — any external OpenAI-compatible /v1/audio/transcriptions
  endpoint (speaches, whisper.cpp server, hosted APIs).
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

# Progress reports from an engine: (stage, fraction). Stage is "transcribing"
# or "diarizing"; the fraction is 0..1 of the audio handled so far, or None
# when the stage has no measurable progress. May be called from a worker
# thread, so implementations must be thread-safe or hop to the event loop.
ProgressCallback = Callable[[str, float | None], None]


@dataclass
class Segment:
    start: float | None
    end: float | None
    text: str
    speaker: str | None = None

    def as_dict(self) -> dict:
        d = {"start": self.start, "end": self.end, "text": self.text}
        if self.speaker is not None:
            d["speaker"] = self.speaker
        return d


@dataclass
class EngineResult:
    text: str
    segments: list[Segment] = field(default_factory=list)
    language: str | None = None
    duration: float | None = None
    model: str | None = None
    # Engine-reported performance stats (benchmarking + status UI)
    stats: dict = field(default_factory=dict)


class TranscriptionEngine(Protocol):
    name: str

    async def transcribe(
        self, audio_path: Path, hotwords: str | None = None, progress: ProgressCallback | None = None
    ) -> EngineResult: ...


class EngineError(Exception):
    """Transcription failed in a way that may succeed on retry."""


def render_text(segments: list[Segment], fallback: str = "") -> str:
    """Render final text; if speakers are labeled, prefix speaker turns."""
    if not segments:
        return fallback
    if not any(s.speaker for s in segments):
        return fallback or " ".join(s.text.strip() for s in segments if s.text.strip())
    lines: list[str] = []
    current: str | None = object()  # sentinel != any speaker value
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if seg.speaker != current:
            current = seg.speaker
            lines.append(f"\n{current or 'Unknown speaker'}: {text}")
        else:
            lines.append(text)
    return " ".join(lines).replace(" \n", "\n").strip()
