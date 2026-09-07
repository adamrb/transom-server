"""Custom vocabulary: names and terms Whisper keeps mishearing.

Two mechanisms, both driven by the same list the user edits:

* hotwords: the terms are handed to faster-whisper (`hotwords=`) so decoding
  is biased toward them ("Plaud" instead of "plot"). Whisper's prompt window
  is small, so the list is capped; manual entries win over imported ones.
* corrections: an entry may carry aliases, the mis-hearings it is usually
  transcribed as ("Plogged Bridge" -> "Plaud Bridge"). Those are replaced in
  the finished transcript, whole words only, case-insensitively. Aliases are
  for proper nouns and product names, never ordinary words.

Imported entries (source "obsidian") come from the vault's names gazetteer
via contrib/vocab_from_obsidian.py, run on demand, not synced automatically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_ENTRIES = 500
MAX_TERM = 64
HOTWORDS_MAX_CHARS = 700


@dataclass
class VocabEntry:
    term: str
    aliases: list[str] = field(default_factory=list)
    source: str = "manual"

    def as_dict(self) -> dict:
        return {"term": self.term, "aliases": list(self.aliases), "source": self.source}


def _clean(s: str) -> str:
    return " ".join((s or "").split())[:MAX_TERM]


def normalize(entries: list[dict | VocabEntry]) -> list[VocabEntry]:
    """Trim, drop empties, dedupe terms case-insensitively (first wins, merging
    aliases), never let a term be its own alias."""
    out: dict[str, VocabEntry] = {}
    for e in entries:
        if isinstance(e, VocabEntry):
            term, aliases, source = e.term, e.aliases, e.source
        else:
            term, aliases, source = e.get("term", ""), e.get("aliases") or [], e.get("source") or "manual"
        term = _clean(str(term))
        if not term:
            continue
        key = term.lower()
        clean_aliases = []
        for a in aliases:
            a = _clean(str(a))
            if a and a.lower() != key and a.lower() not in {x.lower() for x in clean_aliases}:
                clean_aliases.append(a)
        if key in out:
            have = {x.lower() for x in out[key].aliases}
            out[key].aliases += [a for a in clean_aliases if a.lower() not in have]
        else:
            out[key] = VocabEntry(term, clean_aliases, source if source in ("manual", "obsidian") else "manual")
        if len(out) >= MAX_ENTRIES:
            break
    return list(out.values())


def merge(existing: list[VocabEntry], incoming: list[VocabEntry]) -> list[VocabEntry]:
    """Import semantics: keep everything the user has, add new terms, merge
    aliases into matching terms. Nothing is ever removed by an import."""
    by_key = {e.term.lower(): VocabEntry(e.term, list(e.aliases), e.source) for e in existing}
    for e in incoming:
        cur = by_key.get(e.term.lower())
        if cur is None:
            by_key[e.term.lower()] = VocabEntry(e.term, list(e.aliases), e.source)
        else:
            have = {a.lower() for a in cur.aliases} | {cur.term.lower()}
            cur.aliases += [a for a in e.aliases if a.lower() not in have]
    return list(by_key.values())[:MAX_ENTRIES]


def hotwords_string(entries: list[VocabEntry], max_chars: int = HOTWORDS_MAX_CHARS) -> str | None:
    """Comma-separated terms for faster-whisper's `hotwords`, manual first,
    truncated to the prompt budget. None when the list is empty."""
    ordered = sorted(entries, key=lambda e: (e.source != "manual", e.term.lower()))
    parts: list[str] = []
    used = 0
    for e in ordered:
        add = len(e.term) + 2
        if used + add > max_chars:
            break
        parts.append(e.term)
        used += add
    return ", ".join(parts) if parts else None


def _compile(entries: list[VocabEntry]) -> list[tuple[re.Pattern, str]]:
    rules = []
    for e in entries:
        for a in sorted(e.aliases, key=len, reverse=True):  # longest alias first
            rules.append((re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)", re.IGNORECASE), e.term))
    return rules


def apply_corrections(text: str, entries: list[VocabEntry]) -> str:
    if not text or not entries:
        return text
    for pat, term in _compile(entries):
        text = pat.sub(term, text)
    return text


def correct_segments(segments, entries: list[VocabEntry]) -> int:
    """Apply corrections in place to Segment objects; returns how many
    segments changed."""
    if not entries:
        return 0
    rules = _compile(entries)
    if not rules:
        return 0
    changed = 0
    for seg in segments:
        new = seg.text
        for pat, term in rules:
            new = pat.sub(term, new)
        if new != seg.text:
            seg.text = new
            changed += 1
    return changed


# --- plain-text editor format: one entry per line, "Term = alias, alias" ---

def to_editor_text(entries: list[VocabEntry]) -> str:
    lines = []
    for e in sorted(entries, key=lambda e: e.term.lower()):
        lines.append(f"{e.term} = {', '.join(e.aliases)}" if e.aliases else e.term)
    return "\n".join(lines)


def parse_editor_text(text: str, source: str = "manual") -> list[VocabEntry]:
    entries = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        term, _, rest = line.partition("=")
        aliases = [a.strip() for a in rest.split(",")] if rest else []
        entries.append({"term": term.strip(), "aliases": aliases, "source": source})
    return normalize(entries)
