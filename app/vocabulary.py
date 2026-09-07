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

MAX_ENTRIES = 600
MAX_TERM = 64
# Whisper keeps the first 223 prompt tokens and drops the rest; the engine
# trims the list to that budget with the real tokenizer (see
# LocalWhisperEngine._fit_hotwords). This char cap is only a generous upper
# bound so the API response and the app stay small.
HOTWORDS_MAX_CHARS = 1200
HOTWORDS_MAX_TOKENS = 220


@dataclass
class VocabEntry:
    term: str
    aliases: list[str] = field(default_factory=list)
    source: str = "manual"
    # How prominent the term is (imports use mention counts). Decides which
    # imported terms make it into the limited hotwords prompt.
    weight: int = 0

    def as_dict(self) -> dict:
        return {"term": self.term, "aliases": list(self.aliases), "source": self.source, "weight": self.weight}


def _clean(s: str) -> str:
    return " ".join((s or "").split())[:MAX_TERM]


def normalize(entries: list[dict | VocabEntry]) -> list[VocabEntry]:
    """Trim, drop empties, dedupe terms case-insensitively (first wins, merging
    aliases), never let a term be its own alias."""
    out: dict[str, VocabEntry] = {}
    for e in entries:
        if isinstance(e, VocabEntry):
            term, aliases, source, weight = e.term, e.aliases, e.source, e.weight
        else:
            term, aliases, source = e.get("term", ""), e.get("aliases") or [], e.get("source") or "manual"
            try:
                weight = int(e.get("weight") or 0)
            except (TypeError, ValueError):
                weight = 0
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
            out[key].weight = max(out[key].weight, weight)
        else:
            out[key] = VocabEntry(term, clean_aliases, source if source in ("manual", "obsidian") else "manual",
                                  max(0, min(weight, 10**6)))
        if len(out) >= MAX_ENTRIES:
            break
    return list(out.values())


def merge(existing: list[VocabEntry], incoming: list[VocabEntry]) -> list[VocabEntry]:
    """Import semantics: keep everything the user has, add new terms, merge
    aliases into matching terms. Nothing is ever removed by an import."""
    by_key = {e.term.lower(): VocabEntry(e.term, list(e.aliases), e.source, e.weight) for e in existing}
    for e in incoming:
        cur = by_key.get(e.term.lower())
        if cur is None:
            by_key[e.term.lower()] = VocabEntry(e.term, list(e.aliases), e.source, e.weight)
        else:
            have = {a.lower() for a in cur.aliases} | {cur.term.lower()}
            cur.aliases += [a for a in e.aliases if a.lower() not in have]
            cur.weight = max(cur.weight, e.weight)
    return list(by_key.values())[:MAX_ENTRIES]


def hotwords_string(entries: list[VocabEntry], max_chars: int = HOTWORDS_MAX_CHARS) -> str | None:
    """Comma-separated terms for faster-whisper's `hotwords`, heaviest first
    (a manual entry with no weight counts as MANUAL_DEFAULT_WEIGHT, below the
    Life gazetteer's 10000 but above imported coworkers), truncated to the
    prompt budget. None when the list is empty."""
    def w(e): return e.weight if (e.weight or e.source != "manual") else MANUAL_DEFAULT_WEIGHT
    ordered = sorted(entries, key=lambda e: (-w(e), e.term.lower()))
    parts: list[str] = []
    used = 0
    for e in ordered:
        add = len(e.term) + 2
        if used + add > max_chars:
            break
        parts.append(e.term)
        used += add
    return ", ".join(parts) if parts else None


MANUAL_DEFAULT_WEIGHT = 5000  # user-typed terms outrank imports unless the import says otherwise

_DIGIT_WORDS = {"0": "zero|oh", "1": "one", "2": "two|to|too", "3": "three", "4": "four|for", "5": "five",
                "6": "six", "7": "seven", "8": "eight", "9": "nine"}
_NUMBER_WORDS = {"100": "one hundred|a hundred|hundred", "200": "two hundred", "300": "three hundred",
                 "400": "four hundred", "500": "five hundred"}
ACRONYM_RE = re.compile(r"^(?=.*[A-Z].*[A-Z0-9])[A-Z][A-Z0-9]{1,6}$")  # VM2, T3, GKS, H100, RFC; not Turbo


def acronym_pattern(term: str) -> re.Pattern | None:
    """Spelled-out / dotted / spaced renderings of an acronym, e.g. for VM2:
    'V.M.2', 'v m 2', 'VM two', 'vm-2'; for T3: 'T three'; for H100: 'H one
    hundred'. Letters may be separated by dots, spaces or hyphens; a digit
    group may appear as digits or as number words. Whole-word bounded."""
    if not ACRONYM_RE.match(term):
        return None
    parts = re.findall(r"[A-Z]|\d+", term)
    sep = r"[\s.\-]*"
    pieces = []
    for part in parts:
        if part.isdigit():
            words = _NUMBER_WORDS.get(part)
            if words is None:
                words = r"\s*".join(_DIGIT_WORDS[d] for d in part) if len(part) <= 2 else None
            alts = [re.escape(part)] + ([words] if words else [])
            pieces.append("(?:" + "|".join(alts) + ")")
        else:
            pieces.append(part.lower())
    body = sep.join(pieces)
    # Trailing plural ("G P Us", "GPU's") is kept via the `pl` group. A dotted
    # rendering ("G.K.S. and") leaves its last dot behind; swallow it only when
    # a lowercase word follows, so a sentence-final period survives.
    return re.compile(r"(?<![\w.])" + body + r"(?P<pl>'?s)?(?:\.(?=\s+(?-i:[a-z])))?(?![\w])", re.IGNORECASE)


def casing_pattern(term: str) -> re.Pattern | None:
    """Canonical casing for brand-like terms Whisper lowercases or splits:
    CamelCase ('ModelForge' from 'modelforge'/'Modelforge') and multi-word names
    ('Plaud Bridge' from 'plaud bridge'). Plain single words are left alone:
    'drive', 'edge' or 'delta' are ordinary words as often as products."""
    if ACRONYM_RE.match(term):
        return None
    words = term.split()
    camel = len(words) == 1 and re.search(r"[a-z][A-Z]", term) is not None
    multi = len(words) >= 2 and any(w[:1].isupper() for w in words)
    if not (camel or multi):
        return None
    body = r"\s+".join(re.escape(w) for w in words)
    return re.compile(r"(?<!\w)" + body + r"(?!\w)", re.IGNORECASE)


def _compile(entries: list[VocabEntry]) -> list[tuple[re.Pattern, str]]:
    rules = []
    for e in entries:
        for a in sorted(e.aliases, key=len, reverse=True):  # longest alias first
            rules.append((re.compile(r"(?<!\w)" + re.escape(a) + r"(?!\w)", re.IGNORECASE), e.term))
        pat = acronym_pattern(e.term)
        if pat is not None:
            rules.append((pat, e.term + r"\g<pl>"))
        cpat = casing_pattern(e.term)
        if cpat is not None:
            rules.append((cpat, e.term))
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
