"""Button-press marks ("markings") from the Plaud recorder and the transcript
highlights derived from them.

Pressing the Note Pro's button while recording stores a mark on the device.
The Android app reads the marks over BLE after downloading a recording and
uploads them as offsets in seconds from the start (`marks` in the upload
metadata, or PATCH /recordings/{id}/marks later). A highlight is the stretch
of transcript around each mark: what was being said in the seconds before
the press (the reason for pressing) plus a short tail after it.
"""

from __future__ import annotations

import json

MAX_MARKS = 500
BEFORE_S = 20.0   # speech leading up to the press is what the user meant to flag
AFTER_S = 8.0
MAX_TEXT = 600


def parse_marks(value) -> list[float]:
    """Normalize a marks payload (list, or JSON string from the DB) into sorted,
    de-duplicated, non-negative seconds. Garbage entries are dropped."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    if not isinstance(value, list):
        return []
    out: set[float] = set()
    for v in value:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f or f < 0 or f > 10 * 24 * 3600:  # NaN, negative, absurd
            continue
        out.add(round(f, 2))
    return sorted(out)[:MAX_MARKS]


def build_highlights(marks: list[float], segments: list[dict], duration_s: float | None) -> list[dict]:
    """One highlight per mark: the segments overlapping [mark-BEFORE, mark+AFTER],
    joined. Marks with no speech nearby still yield an entry (empty text) so
    the UI can show the moment on the timeline."""
    highlights = []
    for at in marks:
        if duration_s and at > duration_s + 1:
            continue
        lo, hi = max(0.0, at - BEFORE_S), at + AFTER_S
        picked = [s for s in segments
                  if s.get("start") is not None and s.get("end") is not None
                  and s["end"] >= lo and s["start"] <= hi]
        text = " ".join((s.get("text") or "").strip() for s in picked).strip()
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT].rsplit(" ", 1)[0] + "…"
        speakers = sorted({s["speaker"] for s in picked if s.get("speaker")})
        highlights.append({
            "at": at,
            "start": min((s["start"] for s in picked), default=at),
            "end": max((s["end"] for s in picked), default=at),
            "speakers": speakers,
            "text": text,
        })
    return highlights


def fmt_ts(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def highlights_markdown(highlights: list[dict]) -> list[str]:
    """Lines for a '## Highlights' section (empty list when there are none)."""
    if not highlights:
        return []
    lines = ["## Highlights", ""]
    for h in highlights:
        text = h.get("text") or "(no speech near this mark)"
        lines.append(f"- **{fmt_ts(h['at'])}** {text}")
    lines.append("")
    return lines


def highlights_for_prompt(highlights: list[dict]) -> str:
    """Untrusted-data block appended to the summarizer's user message."""
    if not highlights:
        return ""
    body = "\n".join(f"- at {fmt_ts(h['at'])}: {h.get('text') or '(no speech)'}" for h in highlights)
    return ("\n\nMoments the speaker marked as important by pressing the recorder's button "
            "(untrusted data, excerpts of the transcript above):\n<highlights>\n" + body + "\n</highlights>")
