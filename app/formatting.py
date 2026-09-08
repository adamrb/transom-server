"""Reader-friendly transcript layout.

Whisper gives us segments (a few seconds each, with timestamps). Nobody wants
to read those; they want prose: one paragraph per stretch of one speaker
talking, split again at long pauses or when a paragraph gets long, and no
timestamps in the flow. The only moments worth pointing at are the recorder
button presses (bookmarks), so each paragraph knows which bookmarks fall inside
it and clients can offer "jump to bookmark".

The structure is stored in the transcript document as ``paragraphs`` (and
recomputed on read for documents written before it existed):

    {"speaker": "Speaker 1" | None, "text": "...", "start": 12.3, "end": 40.1,
     "bookmarks": [0, 2]}     # indexes into the document's ``highlights``

``start``/``end`` are kept for seeking the player, not for display.
"""

from __future__ import annotations

import re

# A pause this long inside one speaker's turn starts a new paragraph, once the
# current one has some substance (a long breath after one sentence is not a
# paragraph break).
PAUSE_SPLIT_S = 2.5
MIN_CHARS_BEFORE_PAUSE_SPLIT = 200
# Soft cap: past this, the paragraph ends at the next sentence boundary.
MAX_PARAGRAPH_CHARS = 700

_SENTENCE_END = re.compile(r"[.!?…][\"'”’)]*$")
_SENTENCE_BOUNDARY = re.compile(r"[.!?…][\"'”’)]*\s+")


def _last_sentence_boundary(text: str, limit: int) -> int | None:
    """Index just after the last sentence end at or before `limit` (but not in
    the first fifth of the text, so a cut leaves a real paragraph behind)."""
    best = None
    floor = limit // 5
    for m in _SENTENCE_BOUNDARY.finditer(text):
        if m.end() > limit + 1:
            break
        if m.end() >= floor:
            best = m.end()
    return best


def _num(v) -> float | None:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def build_paragraphs(segments: list[dict], highlights: list[dict] | None = None) -> list[dict]:
    """Group whisper segments into paragraphs and attach bookmark indexes.

    Segments without text are skipped. Speaker labels are taken as they are
    (``None`` when the transcript is not diarized). Highlights are matched to
    the paragraph whose time span contains the press; a press in silence goes
    to the next paragraph that starts after it, or the last one.
    """
    paragraphs: list[dict] = []
    current: dict | None = None
    # Same contract as render_text: once any segment is labeled, unlabeled ones
    # are "Unknown speaker" rather than silently merged into a neighbour.
    diarized = any((s.get("speaker") or None) for s in segments or [])

    def flush() -> None:
        nonlocal current
        if current and current["text"]:
            current.pop("_pieces", None)
            paragraphs.append(current)
        current = None

    def piece_at(pieces: list[tuple[int, float | None, float | None]], offset: int):
        """The (offset, start, end) of the segment whose text covers `offset`."""
        hit = pieces[0]
        for piece in pieces:
            if piece[0] <= offset:
                hit = piece
            else:
                break
        return hit

    for seg in segments or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        speaker = (seg.get("speaker") or (UNKNOWN_SPEAKER if diarized else None))
        start, end = _num(seg.get("start")), _num(seg.get("end"))
        if current is not None:
            gap = (start - current["end"]) if (start is not None and current["end"] is not None) else 0.0
            long_pause = gap >= PAUSE_SPLIT_S and len(current["text"]) >= MIN_CHARS_BEFORE_PAUSE_SPLIT
            too_long = len(current["text"]) >= MAX_PARAGRAPH_CHARS and _SENTENCE_END.search(current["text"])
            if speaker != current["speaker"] or long_pause or too_long:
                flush()
        if current is None:
            current = {"speaker": speaker, "text": text, "start": start, "end": end, "bookmarks": [],
                       "_pieces": [(0, start, end)]}
        else:
            current["_pieces"].append((len(current["text"]) + 1, start, end))
            current["text"] = f"{current['text']} {text}"
            if end is not None and (current["end"] is None or end > current["end"]):
                current["end"] = end
            if current["start"] is None:
                current["start"] = start
        # Whisper segments rarely end exactly on a sentence, so a monologue can
        # run far past the cap with the end-of-text check alone: cut at the last
        # sentence boundary inside the text once it is over the cap. The halves
        # take their times from the segment the cut falls in, not the newest one.
        while len(current["text"]) > MAX_PARAGRAPH_CHARS:
            cut = _last_sentence_boundary(current["text"], MAX_PARAGRAPH_CHARS)
            if cut is None:
                break
            head, tail = current["text"][:cut].rstrip(), current["text"][cut:].lstrip()
            if not head or not tail:
                break
            pieces = current["_pieces"]
            cut_piece = piece_at(pieces, cut)
            tail_offset = len(current["text"]) - len(tail)
            tail_pieces = [(o - tail_offset, s, e) for (o, s, e) in pieces if o >= tail_offset]
            if not tail_pieces or tail_pieces[0][0] > 0:
                # The cut is inside a segment: the tail begins with that segment's remainder.
                tail_pieces.insert(0, (0, cut_piece[1], cut_piece[2]))
            rest = {"speaker": current["speaker"], "text": tail, "start": tail_pieces[0][1],
                    "end": current["end"], "bookmarks": [], "_pieces": tail_pieces}
            current["text"], current["end"] = head, cut_piece[2] if cut_piece[2] is not None else current["end"]
            flush()
            current = rest
    flush()

    for i, h in enumerate(highlights or []):
        at = _num(h.get("at"))
        if at is None or not paragraphs:
            continue
        target = next((p for p in paragraphs
                       if p["start"] is not None and p["end"] is not None and p["start"] <= at <= p["end"]), None)
        if target is None:
            target = next((p for p in paragraphs if p["start"] is not None and p["start"] >= at), paragraphs[-1])
        target["bookmarks"].append(i)
    return paragraphs


def paragraphs_markdown(paragraphs: list[dict], highlights: list[dict] | None = None) -> str:
    """Paragraphs as markdown: a bold speaker label when there is one, a
    bookmark star on paragraphs holding a button press, one blank line between
    paragraphs, no timestamps."""
    out = []
    for p in paragraphs:
        text = p["text"]
        if p.get("bookmarks"):
            text = "★ " + text
        out.append(f"**{p['speaker']}:** {text}" if p.get("speaker") else text)
    return "\n\n".join(out)


def paragraphs_plain(paragraphs: list[dict]) -> str:
    """Plain-text version for clipboards: 'Speaker: text' paragraphs."""
    return "\n\n".join(f"{p['speaker']}: {p['text']}" if p.get("speaker") else p["text"] for p in paragraphs)


# ── speaker labels ───────────────────────────────────────────────────────────

MAX_SPEAKER_NAME_CHARS = 64
# What an unlabeled segment is called in a diarized transcript (same string
# as build_paragraphs and engines.render_text use).
UNKNOWN_SPEAKER = "Unknown speaker"


def speaker_labels(doc: dict) -> list[str]:
    """Distinct speaker labels in first-appearance order, taken from the
    paragraphs (what clients render) and falling back to the segments."""
    out: list[str] = []
    for item in (doc.get("paragraphs") or doc.get("segments") or []):
        label = item.get("speaker")
        if label and label not in out:
            out.append(label)
    return out


def segments_text(segments: list[dict]) -> str:
    """Render the flat transcript text from segment dicts: the same layout as
    engines.render_text (speaker turns on their own 'Label: text' lines when
    any segment is labeled, plain prose otherwise)."""
    if not any(s.get("speaker") for s in segments):
        return " ".join((s.get("text") or "").strip() for s in segments if (s.get("text") or "").strip())
    lines: list[str] = []
    current: object = object()  # sentinel != any speaker value
    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        speaker = seg.get("speaker")
        if speaker != current:
            current = speaker
            lines.append(f"\n{speaker or UNKNOWN_SPEAKER}: {text}")
        else:
            lines.append(text)
    return " ".join(lines).replace(" \n", "\n").strip()


def apply_speaker_renames(doc: dict, renames: dict[str, str]) -> bool:
    """Rename speakers in a transcript document, in place.

    `renames` maps a label as it currently appears ("Speaker 1", or a name
    given earlier) to its new name. Segments, paragraphs and highlight speaker
    lists are rewritten in one pass (so swapping two labels works), the flat
    ``text`` is re-rendered from the segments when labels are embedded in it,
    and ``speaker_names`` (original engine label -> current name) is updated
    so the choice survives any later re-derivation. Unknown labels are
    ignored. Returns True when anything changed."""
    renames = {old: new for old, new in renames.items() if old and new and old != new}
    if not renames:
        return False
    segments = doc.get("segments") or []
    # In a diarized document, segments without a label are shown (by
    # build_paragraphs and render_text) as "Unknown speaker"; renaming that
    # label must reach those segments, or a refresh would bring it back.
    diarized = any(s.get("speaker") for s in segments)
    unlabeled = UNKNOWN_SPEAKER if diarized and any(not s.get("speaker") for s in segments) else None
    present = set(speaker_labels(doc)) | {s.get("speaker") for s in segments} | {unlabeled}
    renames = {old: new for old, new in renames.items() if old in present}
    if not renames:
        return False

    def relabel(item: dict, fallback: str | None = None) -> None:
        label = item.get("speaker") or fallback
        if label in renames:
            item["speaker"] = renames[label]

    for seg in segments:
        relabel(seg, unlabeled)
    for para in doc.get("paragraphs") or []:
        relabel(para)
    for h in doc.get("highlights") or []:
        if isinstance(h.get("speakers"), list):
            h["speakers"] = sorted({renames.get(s, s) for s in h["speakers"] if s})

    # Persistent map keyed on the label the engine produced. A label being
    # renamed is either an original label still shown as itself, or the
    # current name of one or more originals (two speakers merged under one
    # name): every original behind it moves. Resolved against the map as it
    # was before this batch, so swapping two labels in one call works.
    names: dict[str, str] = dict(doc.get("speaker_names") or {})
    before = dict(names)
    for old, new in renames.items():
        origs = [orig for orig, cur in before.items() if cur == old] or [old]
        for orig in origs:
            if new == orig:
                names.pop(orig, None)
            else:
                names[orig] = new
    doc["speaker_names"] = names

    if diarized:
        doc["text"] = segments_text(segments)
    return True
