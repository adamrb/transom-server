#!/usr/bin/env python3
"""Build a custom-vocabulary list from an Obsidian vault and (optionally) push
it to a transom server. Run on demand (by hand or by an agent); nothing
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
        out.append({"term": canonical, "aliases": aliases, "source": "obsidian", "weight": 10000})
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
        out.append({"term": title, "aliases": aliases, "source": "obsidian", "weight": 10000})
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
            title = re.sub(r"\s+\d{4}(-\d{2}){1,2}$", "", p.stem).strip()   # "Reunion 2026-05-02" -> "Reunion"
            title = re.sub(r"\s*\([^)]*\)", "", title).strip()                 # "Openpilot (Truck)" -> "Openpilot"
            if SKIP_TITLE_RE.match(title) or not looks_like_name(title) or len(title.split()) > MAX_TITLE_WORDS:
                continue
            out.append({"term": title, "aliases": [], "source": "obsidian", "weight": 200})
    return out


def _split_single_token_aliases(entries: list[dict]) -> list[dict]:
    """'Morgen' is a misspelling of 'Morgan', not of 'Morgan Ashford': correcting
    it to the full name would expand every first-name mention. Single-word
    aliases therefore attach to the matching canonical token as its own entry
    (term 'Morgan', alias 'Morgen'); multi-word aliases keep the full name."""
    out: list[dict] = []
    extra: dict[str, dict] = {}
    for e in entries:
        ctoks = e["term"].split()
        keep = []
        for a in e["aliases"]:
            if len(a.split()) == 1 and len(ctoks) > 1:
                target = min(ctoks, key=lambda t: _edit_distance(a, t))
                # corrections only: the full name already carries the hotword budget
                x = extra.setdefault(target.lower(), {"term": target, "aliases": [], "source": e["source"], "weight": 0})
                if a.lower() not in {z.lower() for z in x["aliases"]} and a.lower() != target.lower():
                    x["aliases"].append(a)
            else:
                keep.append(a)
        out.append({**e, "aliases": keep})
    return out + list(extra.values())


def collect(vault: Path) -> list[dict]:
    seen: dict[str, dict] = {}
    raw = parse_gazetteer(vault / "Life/_names.md") + parse_people(vault) + parse_titles(vault)
    for e in _split_single_token_aliases(raw):
        key = e["term"].lower()
        if key in seen:
            have = {a.lower() for a in seen[key]["aliases"]}
            seen[key]["aliases"] += [a for a in e["aliases"] if a.lower() not in have]
        else:
            seen[key] = e
    return list(seen.values())


# --- deep mining (--deep): people pages under any */People, wikilink targets,
# products/acronyms/surnames by frequency, weighted by mention count so the
# hotwords budget goes to what actually comes up. -------------------------

DEEP_INCLUDE = ("Life", "Work", "Career", "Personal", "0_Quick Add")
DEEP_SKIP = {"Attachments", "Clippings", "Excalidraw", ".trash", "Archive", "Staging", "Plaud", "Library", "Extras", "Spaces"}
STOP = set("""january february march april may june july august september october november december jan feb mar apr jun jul aug sep sept oct nov dec
monday tuesday wednesday thursday friday saturday sunday fridays mondays today yesterday tomorrow i im ive id ill am pm ok okay yes no the a an and or but if
claude chatgpt gpt ai todo done note notes meeting meetings summary action items next week month year day time team standup sync resources untitled
vendors open ideas mgr sr acc svcs prin dir mr mrs ms dr""".split())
GENERIC_ACRONYMS = {"AI", "ML", "GPU", "CPU", "UI", "UX", "VP", "FAQ", "TBD", "OS", "IT", "PDT", "PST", "GB", "MB", "TB", "II", "III", "IV", "TO", "WA",
                    "SA", "DM", "WW", "BD", "CR", "GA", "CD", "LP", "SUP", "VS", "PTO", "YTD", "ET", "DE", "OK", "PR", "QA", "US", "UK", "TV", "PC", "USB",
                    "API", "URL", "ID", "CEO", "CTO", "HR", "IP", "TL", "LT", "SLA", "KPI", "ROI", "POC", "MVP", "ASAP", "FYI", "EOD", "OOO", "WIP"}
MIN_LINK, MIN_TOKEN, MIN_ACRONYM = 8, 25, 20


def _fm_title(fm: dict, path: Path) -> str:
    t = fm.get("title")
    return t if isinstance(t, str) and t else path.stem


def deep_collect(vault: Path) -> list[dict]:
    import collections
    files = [p for d in DEEP_INCLUDE for p in (vault / d).rglob("*.md") if not (set(p.parts) & DEEP_SKIP)]
    people: dict[str, dict] = {}
    links = collections.Counter(); caps = collections.Counter(); acro = collections.Counter(); phrases = collections.Counter()
    lower_seen: set[str] = set()
    for p in files:
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        fm = frontmatter(p)
        if "People" in p.parts:
            title = _fm_title(fm, p)
            if looks_like_name(title):
                aliases = [a for a in (fm.get("aliases") or []) if isinstance(a, str) and looks_like_name(a) and is_misspelling(a, title)]
                people[title.lower()] = {"term": title, "aliases": aliases, "source": "obsidian", "weight": 1}
        body = text[text.find("\n---", 3) + 4:] if text.startswith("---") else text
        body = re.sub(r"```.*?```", " ", body, flags=re.S)
        body = re.sub(r"https?://\S+", " ", body)
        for m in re.finditer(r"\[\[([^\]|#]+)", body):
            tgt = m.group(1).strip().split("/")[-1].strip()
            if tgt and not tgt.startswith(("_", "+")) and not re.match(r"^\d", tgt):
                links[tgt] += 1
        plain = re.sub(r"\[\[[^\]]+\]\]", " ", body)
        for w in re.findall(r"[a-z][a-z'-]{2,}", plain):
            lower_seen.add(w.lower())
        for sent in re.split(r"(?<=[.!?])\s+|\n+", plain):
            toks = re.findall(r"[A-Za-z][A-Za-z0-9'&.-]*", sent)
            for i, tok in enumerate(toks):
                if re.fullmatch(r"[A-Z][A-Z0-9]{2,7}", tok):
                    acro[tok] += 1
                elif re.fullmatch(r"[A-Z][a-z]+[A-Z][A-Za-z0-9]+", tok):
                    caps[tok] += 1
                elif i > 0 and re.fullmatch(r"[A-Z][a-z]{2,}", tok):
                    caps[tok] += 1
            for m in re.finditer(r"(?<!^)\b([A-Z][a-z]+(?:\s+(?:[A-Z][a-z0-9]+|[A-Z]{2,})){1,2})\b", sent):
                phrases[m.group(1)] += 1

    out: dict[str, dict] = {}

    def add(term: str, weight: int, aliases=None):
        key = term.lower()
        if key in out:
            out[key]["weight"] = max(out[key]["weight"], weight)
        else:
            out[key] = {"term": term, "aliases": list(aliases or []), "source": "obsidian", "weight": weight}

    # People pages, weighted by how often they are linked or written out.
    for key, e in people.items():
        w = links.get(e["term"], 0) + phrases.get(e["term"], 0)
        add(e["term"], max(w, 1) * 10, e["aliases"])
    name_tokens = {t.lower() for e in people.values() for t in e["term"].split()}

    def generic(title: str) -> bool:
        words = title.split()
        return (not looks_like_name(title) or len(words) > 5 or any(w.lower() in STOP for w in words)
                or re.search(r"\d{4}-\d{2}|\bQ[1-4]\b|1on1|1-1|\bweekly\b", title, re.I) is not None)

    # Linked pages (projects, mechanisms, products) by link count.
    for tgt, c in links.items():
        if c >= MIN_LINK and tgt.lower() not in out and not generic(tgt):
            add(tgt, c * 5)
    # Domain acronyms.
    for tok, c in acro.items():
        if c >= MIN_ACRONYM and tok not in GENERIC_ACRONYMS and tok.lower() not in lower_seen and len(tok) >= 3:
            add(tok, c)
    # Products, places, surnames that only ever appear capitalized.
    for tok, c in caps.items():
        if (c >= MIN_TOKEN and tok.lower() not in lower_seen and tok.lower() not in STOP
                and tok.lower() not in name_tokens and not re.fullmatch(r"[A-Z][a-z]{2}", tok)):
            add(tok, c)
    # Multi-word proper phrases (places, venues, products) not already a person.
    for ph, c in phrases.items():
        words = ph.split()
        if (c >= 10 and ph.lower() not in out and all(w.lower() not in STOP for w in words)
                and not all(w.lower() in name_tokens for w in words)
                and all((w.lower() not in lower_seen) or w.isupper() for w in words)):
            add(ph, c * 2)
    return list(out.values())


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
    ap.add_argument("--url", help="transom base URL; omit for a dry run")
    ap.add_argument("--token-env", default="PB_AUTH_TOKENS", help="env var holding the bearer token")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--deep", action="store_true",
                    help="also mine people pages anywhere, linked pages, products, acronyms (weighted by mentions)")
    ap.add_argument("--top", type=int, default=0, help="print only the N heaviest terms (dry run)")
    args = ap.parse_args()
    entries = collect(args.vault)
    for e in entries:
        e.setdefault("weight", 0)
    if args.deep:
        have = {e["term"].lower(): e for e in entries}
        for e in deep_collect(args.vault):
            cur = have.get(e["term"].lower())
            if cur is None:
                entries.append(e); have[e["term"].lower()] = e
            else:
                cur["weight"] = max(cur.get("weight", 0), e["weight"])
                cur["aliases"] += [a for a in e["aliases"] if a.lower() not in {x.lower() for x in cur["aliases"]}]
    entries.sort(key=lambda e: -e.get("weight", 0))
    if args.top:
        entries_print = entries[: args.top]
    else:
        entries_print = entries
    print(f"{len(entries)} terms from {args.vault}", file=sys.stderr)
    for e in entries_print:
        print(f"  {e.get('weight', 0):>6}  {e['term']}" + (f" = {', '.join(e['aliases'])}" if e["aliases"] else ""), file=sys.stderr)
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
