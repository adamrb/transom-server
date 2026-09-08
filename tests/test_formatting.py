"""Reader layout: paragraphs by speaker turn, no timestamps, bookmarks attached."""

from app.formatting import (MAX_PARAGRAPH_CHARS, MIN_CHARS_BEFORE_PAUSE_SPLIT, PAUSE_SPLIT_S,
                            build_paragraphs, paragraphs_markdown, paragraphs_plain)


def seg(start, end, text, speaker=None):
    d = {"start": start, "end": end, "text": text}
    if speaker:
        d["speaker"] = speaker
    return d


def test_speaker_turns_become_paragraphs_without_timestamps():
    segs = [seg(0, 2, "Hello there.", "Speaker 1"), seg(2, 4, "How are you?", "Speaker 1"),
            seg(4, 5, "Fine.", "Speaker 2"), seg(5, 7, "And you?", "Speaker 2"),
            seg(7, 9, "Good.", "Speaker 1")]
    paras = build_paragraphs(segs)
    assert [(p["speaker"], p["text"]) for p in paras] == [
        ("Speaker 1", "Hello there. How are you?"), ("Speaker 2", "Fine. And you?"), ("Speaker 1", "Good.")]
    assert paras[0]["start"] == 0 and paras[0]["end"] == 4 and paras[0]["bookmarks"] == []
    md = paragraphs_markdown(paras)
    assert md.startswith("**Speaker 1:** Hello there. How are you?\n\n**Speaker 2:** Fine.")
    assert ":" not in md.replace("**Speaker 1:**", "").replace("**Speaker 2:**", "")  # no clock times
    assert paragraphs_plain(paras).splitlines()[0] == "Speaker 1: Hello there. How are you?"


def test_undiarized_text_is_one_flow_split_on_long_pauses_and_length():
    filler = "This is a sentence of some length that keeps going for a while. "
    long_text = filler * 4  # > MIN_CHARS_BEFORE_PAUSE_SPLIT
    segs = [seg(0, 10, long_text.strip()), seg(10 + PAUSE_SPLIT_S, 20, "After a pause."),
            seg(20, 21, "Short."), seg(21 + PAUSE_SPLIT_S, 25, "Still same paragraph, the last one was short.")]
    paras = build_paragraphs(segs)
    assert [p["speaker"] for p in paras] == [None, None]
    assert paras[0]["text"] == long_text.strip()
    assert paras[1]["text"] == "After a pause. Short. Still same paragraph, the last one was short."
    assert paragraphs_markdown(paras) == paras[0]["text"] + "\n\n" + paras[1]["text"]

    # Very long monologue: broken at a sentence end once past the soft cap.
    many = [seg(i, i + 1, "Sentence number %d ends here." % i, "Speaker 1") for i in range(60)]
    paras = build_paragraphs(many)
    assert len(paras) > 1
    assert all(len(p["text"]) < MAX_PARAGRAPH_CHARS + 60 for p in paras)
    assert all(p["text"].endswith(".") for p in paras)
    assert " ".join(p["text"] for p in paras) == " ".join(s["text"] for s in many)  # nothing lost

    # Segments that end mid-sentence (the usual whisper case): the cut happens at a
    # sentence boundary INSIDE the accumulated text, so paragraphs stay near the cap.
    clause = "the plan for the garage, which we discussed at length last weekend with everyone,"
    mid = [seg(i * 3, i * 3 + 3, f"{clause} was fine. Then we moved on to", "Speaker 1") for i in range(40)]
    paras = build_paragraphs(mid)
    assert len(paras) >= 6   # ~4.4k chars of text against a 700-char soft cap
    assert all(len(p["text"]) <= MAX_PARAGRAPH_CHARS + len(clause) + 40 for p in paras)
    assert all(p["text"].endswith("was fine.") for p in paras[:-1])
    assert " ".join(p["text"] for p in paras) == " ".join(s["text"] for s in mid)
    # Times follow the segment the cut fell in: each tail starts where its first
    # sentence was actually spoken, not at the newest segment.
    starts = {s["start"] for s in mid}
    for i in range(1, len(paras)):
        assert paras[i]["start"] in starts                      # a real segment start, not invented
        assert paras[i - 1]["start"] < paras[i]["start"]        # strictly moving forward through the audio
        assert paras[i - 1]["end"] <= paras[i]["start"] + 3     # head ends where the cut segment ends
        # The cut segment is where the tail's opening words were spoken (within a
        # segment either side, since a sentence may straddle two segments).
        opening = paras[i]["text"][:25]
        near = [s for s in mid if abs(s["start"] - paras[i]["start"]) <= 3]
        assert any(opening.split(" ")[0] in s["text"] for s in near)
    assert all("_pieces" not in p for p in paras)


def test_split_keeps_bookmarks_with_the_half_they_were_spoken_in():
    # Three long segments; a bookmark inside the first one must stay with the head half.
    body = ("Quite a long sentence about nothing in particular that fills the paragraph nicely. " * 5).strip()
    segs = [seg(0, 30, body, "Speaker 1"), seg(30, 60, body, "Speaker 1"), seg(60, 90, body, "Speaker 1")]
    paras = build_paragraphs(segs, [{"at": 10.0}, {"at": 70.0}])
    assert len(paras) >= 2
    assert 0 in paras[0]["bookmarks"]
    late = next(p for p in paras if 1 in p["bookmarks"])
    assert late["start"] <= 70.0 <= late["end"]


def test_unlabeled_segments_in_a_diarized_transcript_are_unknown_speaker():
    segs = [seg(0, 2, "Hi.", "Speaker 1"), seg(2, 3, "(cough)"), seg(3, 5, "Hello.", "Speaker 2")]
    assert [p["speaker"] for p in build_paragraphs(segs)] == ["Speaker 1", "Unknown speaker", "Speaker 2"]
    assert "**Unknown speaker:** (cough)" in paragraphs_markdown(build_paragraphs(segs))
    # Wholly undiarized text keeps no label at all.
    assert build_paragraphs([seg(0, 1, "a"), seg(1, 2, "b")])[0]["speaker"] is None


def test_bookmarks_attach_to_the_paragraph_they_fall_in_or_the_next_one():
    segs = [seg(0, 5, "Intro.", "Speaker 1"), seg(5, 10, "Reply.", "Speaker 2"), seg(30, 35, "Later.", "Speaker 1")]
    highlights = [{"at": 6.0}, {"at": 20.0}, {"at": 99.0}, {"at": None}]
    paras = build_paragraphs(segs, highlights)
    assert paras[0]["bookmarks"] == []
    assert paras[1]["bookmarks"] == [0]          # inside Speaker 2's span
    assert paras[2]["bookmarks"] == [1, 2]       # in silence -> next paragraph; past the end -> last
    md = paragraphs_markdown(paras, highlights)
    assert "**Speaker 2:** ★ Reply." in md and "**Speaker 1:** Intro." in md


def test_blank_segments_are_skipped_and_empty_input_is_empty():
    assert build_paragraphs([]) == []
    assert build_paragraphs([seg(0, 1, "   "), seg(1, 2, "")], [{"at": 1}]) == []
    assert build_paragraphs([seg(None, None, "no times")])[0]["text"] == "no times"
    assert paragraphs_markdown([]) == ""
