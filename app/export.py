"""Markdown rendering of a finished recording for the copy/export buttons.

The Android app builds the identical layout on-device (TranscriptMarkdown), so
a note exported from the phone and one exported from the dashboard look the
same. Keep changes to this format in sync with the app.
"""

from __future__ import annotations

import json
import re


def transcript_markdown(title: str, recorded: str | None, duration_s: float | int | None,
                        summary: str | None, text: str, highlights: list[dict] | None = None) -> str:
    from .highlights import highlights_markdown

    def yq(value) -> str:  # YAML-safe scalar via JSON quoting
        return json.dumps("" if value is None else str(value), ensure_ascii=False)

    if isinstance(duration_s, float) and duration_s.is_integer():
        duration_s = int(duration_s)
    lines = [
        "---",
        f"title: {yq(title)}",
        f"recorded: {yq(recorded)}",
        f"duration_s: {yq(duration_s)}",
        "source: plaud-bridge",
        "---",
        f"# {title}",
        "",
    ]
    if summary and summary.strip():
        lines += ["## Summary", "", summary.strip(), ""]
    lines += highlights_markdown(highlights or [])
    lines += ["## Transcript", "", transcript_body_markdown(text), ""]
    return "\n".join(lines)


def transcript_body_markdown(text: str) -> str:
    """Speaker turns as markdown paragraphs with a bold label: 'Speaker 1: hi'
    becomes '**Speaker 1:** hi', one blank line between turns. Text without
    speaker labels is returned as-is (already prose)."""
    out = []
    for line in (text or "").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([A-Z][\w .'-]{0,40}?):\s+(.*)$", line)
        out.append(f"**{m.group(1)}:** {m.group(2)}" if m else line)
    return "\n\n".join(out)


def safe_filename(title: str, fallback: str = "transcript") -> str:
    """A filesystem- and header-safe base name (no extension) for a title."""
    name = re.sub(r'[\\/:*?"<>|#^\[\]\x00-\x1f]+', " ", title or "")
    name = re.sub(r"\s+", " ", name).strip(" .")[:80]
    return name or fallback
