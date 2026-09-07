#!/usr/bin/env python3
"""Build a custom-vocabulary list from an Obsidian vault and (optionally) push
it to a plaud-bridge server. Run on demand (by hand or by an agent); nothing
syncs automatically.

Sources, in order of trust:
  1. Life/_names.md gazetteer lines: `Canonical | type | alias, alias | ...`
     (the aliases are exactly the likely mis-transcriptions we want corrected)
  2. Frontmatter `title:` + `aliases:` of notes under Life/People
  3. Note titles under Life/Projects, Life/Topics, Life/Threads, Life/Decisions
     (hotwords only, no correction aliases)

Aliases that are ordinary lowercase words or phrases ("the cleaner") are kept
as hotwords context only if they look like names (start with a capital), so a
common word is never rewritten in a transcript.

Usage:
  vocab_from_obsidian.py --vault ~/vault --dry-run
  vocab_from_obsidian.py --vault ~/vault --url http://localhost:8090 --token-env PB_AUTH_TOKENS
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

GENERIC = {"the", "a", "an", "my", "our", "her", "his", "dr", "mr", "mrs", "ms", "mom", "dad", "nurse"}
# Topics/Decisions are generic words (Finances, Cooking) or recipes; only
# Projects and Threads carry distinctive names worth biasing the decoder.
TITLE_DIRS = ("Life/Projects", "Life/Threads")
MAX_TITLE_WORDS = 4


def _edit_distance(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def is_misspelling(alias: str, canonical: str) -> bool:
    """A correction alias must be a plausible mis-hearing of the name itself,
    not a nickname or a bare first name: rewriting every 'Sam' or 'Mom' into
    a full name would corrupt transcripts. Rule: every token of the alias is
    within edit distance 2 of some token of the canonical name, and at least
    one token differs (otherwise it is just a prefix like 'Priya')."""
    ctoks = [t.lower() for t in canonical.split()]
    atoks = [t.lower() for t in alias.split()]
    if not atoks or atoks == ctoks:
        return False
    differs = False
    for at in atoks:
        best = min(_edit_distance(at, ct) for ct in ctoks)
        if best > 2:
            return False
        if best > 0:
            differs = True
    if not differs:
        # e.g. "Dana Whitlock" vs "Dana Whitlok" is handled above; "Priya" alone is a prefix
        return len(atoks) == len(ctoks)
    return True
SKIP_TITLE_RE = re.compile(r"^(_|\d{4}-\d{2}|index$|log$|readme$)", re.I)


def looks_like_name(s: str) -> bool:
    s = s.strip()
    if not s or len(s) > 64 or len(s) < 2:
        return False
    first = s.split()[0].strip("'\"")
    return first[:1].isupper() and first.lower() not in GENERIC


def parse_gazetteer(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        if "|" not in line or line.startswith("#") or line.startswith("One line"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 3 or not looks_like_name(parts[0]):
            continue
        canonical = parts[0]
        aliases = [a.strip() for a in parts[2].split(",")] if len(parts) > 2 else []
        aliases = [a for a in aliases if looks_like_name(a) and is_misspelling(a, canonical)]
        out.append({"term": canonical, "aliases": aliases, "source": "obsidian"})
    return out


def frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm: dict = {}
    for line in text[3:end].splitlines():
        m = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if val.startswith("[") and val.endswith("]"):
            fm[key] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
        else:
            fm[key] = val.strip("'\"")
    return fm


def parse_people(vault: Path) -> list[dict]:
    out = []
    for p in sorted((vault / "Life/People").glob("*.md")):
        fm = frontmatter(p)
        title = fm.get("title") or p.stem
        if not looks_like_name(title):
            continue
        aliases = [a for a in (fm.get("aliases") or []) if isinstance(a, str) and looks_like_name(a) and is_misspelling(a, title)]
        out.append({"term": title, "aliases": aliases, "source": "obsidian"})
    return out


def parse_titles(vault: Path) -> list[dict]:
    out = []
    for d in TITLE_DIRS:
        base = vault / d
        if not base.exists():
            continue
        for p in sorted(base.rglob("*.md")):
            if any(part.startswith(("Attachments", "Operational")) for part in p.relative_to(base).parts):
                continue
            title = re.sub(r"\s+\d{4}-\d{2}-\d{2}$", "", p.stem).strip()   # "Reunion 2026-05-02" -> "Reunion"
            title = re.sub(r"\s*\([^)]*\)", "", title).strip()                 # "Openpilot (Truck)" -> "Openpilot"
            if SKIP_TITLE_RE.match(title) or not looks_like_name(title) or len(title.split()) > MAX_TITLE_WORDS:
                continue
            out.append({"term": title, "aliases": [], "source": "obsidian"})
    return out


def collect(vault: Path) -> list[dict]:
    seen: dict[str, dict] = {}
    for e in parse_gazetteer(vault / "Life/_names.md") + parse_people(vault) + parse_titles(vault):
        key = e["term"].lower()
        if key in seen:
            have = {a.lower() for a in seen[key]["aliases"]}
            seen[key]["aliases"] += [a for a in e["aliases"] if a.lower() not in have]
        else:
            seen[key] = e
    return list(seen.values())


def push(url: str, token: str, entries: list[dict]) -> dict:
    req = urllib.request.Request(
        url.rstrip("/") + "/api/v1/vocabulary/import",
        data=json.dumps({"entries": entries}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", required=True, type=Path)
    ap.add_argument("--url", help="plaud-bridge base URL; omit for a dry run")
    ap.add_argument("--token-env", default="PB_AUTH_TOKENS", help="env var holding the bearer token")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    entries = collect(args.vault)
    print(f"{len(entries)} terms from {args.vault}", file=sys.stderr)
    for e in entries:
        print(f"  {e['term']}" + (f" = {', '.join(e['aliases'])}" if e["aliases"] else ""), file=sys.stderr)
    if args.dry_run or not args.url:
        json.dump({"entries": entries}, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    token = (os.environ.get(args.token_env) or "").split(",")[0].strip()
    if not token:
        print(f"no token in ${args.token_env}", file=sys.stderr)
        return 2
    result = push(args.url, token, entries)
    print(f"imported: {result.get('added')} new term(s); {len(result.get('entries', []))} total", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
