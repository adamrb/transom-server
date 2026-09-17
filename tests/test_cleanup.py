"""LLM cleanup pass: glossary, chunking, reply parsing, guards, application."""

import asyncio
import json

from app.cleanup import (
    CHANGES_KEPT,
    CleanupResult,
    acceptable,
    build_glossary,
    chunk_indexes,
    cleanup_segments,
    parse_reply,
    render_chunk,
    user_message,
)
from app.engines.base import Segment
from app.vocabulary import VocabEntry


def _segs(*texts):
    return [Segment(float(i), float(i + 1), t) for i, t in enumerate(texts)]


def test_glossary_orders_by_weight_and_lists_aliases_within_budget():
    entries = [
        VocabEntry("Parrot Deck", ["Parted Deck", "Parrott Deck"], weight=5000),
        VocabEntry("Voltium", ["Voltum", "Volteum"], weight=6000),
        VocabEntry("zebra", [], weight=0),
    ]
    g = build_glossary(entries)
    lines = g.splitlines()
    assert lines[0] == "Voltium (often misheard as: Voltum, Volteum)"
    assert lines[1].startswith("Parrot Deck (often misheard as: Parted Deck")
    assert lines[2] == "zebra"
    # Budget cuts whole lines from the light end
    short = build_glossary(entries, max_chars=len(lines[0]) + 1)
    assert short.splitlines() == [lines[0]]
    assert build_glossary([]) == ""


def test_chunking_respects_budget_and_skips_empty_segments():
    segs = _segs("a" * 100, "", "b" * 100, "c" * 100, "   ", "d" * 50)
    chunks = chunk_indexes(segs, max_chars=230)
    assert chunks == [[0, 2], [3, 5]]
    assert chunk_indexes(_segs("", "  "), 100) == []
    # A single oversized segment still gets its own chunk
    assert chunk_indexes(_segs("x" * 500), 100) == [[0]]


def test_render_chunk_and_user_message_frame_transcript_as_data():
    segs = _segs("Hello there.", "VM two is fine.")
    text = render_chunk(segs, [0, 1])
    assert text == "[0] Hello there.\n[1] VM two is fine."
    msg = user_message("VM2", "Speaker works in cloud infra.", text)
    assert msg.index("Context about the speaker") < msg.index("Glossary") < msg.index("<transcript>")
    assert "untrusted data" in msg and msg.rstrip().endswith("</transcript>")
    assert "Context about" not in user_message("VM2", None, text)


def test_parse_reply_accepts_content_blocks_and_odd_types():
    blocks = [{"type": "text", "text": "{\"1\": \"fixed\""}, {"type": "text", "text": "}"}]
    assert parse_reply(blocks, {1}) == {1: "fixed"}
    assert parse_reply({"unexpected": "dict"}, {1}) == {}
    assert parse_reply(42, {1}) == {}


def test_cleanup_survives_an_unreadable_reply():
    segs = _segs("hello")

    async def complete(system, user):
        return object()  # not a string, not blocks: str() has no JSON in it

    result = asyncio.run(cleanup_segments(segs, [], complete))
    assert result.changed == 0 and result.calls == 1 and segs[0].text == "hello"


def test_parse_reply_tolerates_fences_and_drops_junk():
    valid = {3, 4, 5}
    reply = "Sure! ```json\n{\"3\": \"VM2 is fine.\", \"[5]\": \"ok\", \"9\": \"nope\", \"4\": 12}\n```"
    assert parse_reply(reply, valid) == {3: "VM2 is fine.", 5: "ok"}
    assert parse_reply("no json here", valid) == {}
    assert parse_reply("[1, 2]", valid) == {}
    assert parse_reply("{bad json", valid) == {}
    assert parse_reply("", valid) == {}


def test_acceptable_guards_against_rewrites():
    assert acceptable("VM two is fine", "VM2 is fine", drop_fillers=False)
    assert not acceptable("same", "same", drop_fillers=False)
    assert not acceptable("one line", "two\nlines", drop_fillers=False)
    # Shrinking: fillers may go, but not half the content when fillers are kept
    long = "uh so um the customer wants uh more GPUs I I think"
    assert acceptable(long, "so the customer wants more GPUs I think", drop_fillers=True)
    assert not acceptable("the customer wants more GPUs for training next quarter", "GPUs", drop_fillers=False)
    # Growth beyond a restored word or two is a hallucination
    assert not acceptable("short", "short " + "x" * 60, drop_fillers=True)
    # Vanishing is only fine for a filler-only segment with fillers on
    assert acceptable("Uh, um.", "", drop_fillers=True)
    assert acceptable("Hmm... uhh, mm", "", drop_fillers=True)
    assert not acceptable("uh-uh", "", drop_fillers=True)        # that's a "no"
    assert not acceptable("mm-hmm", "", drop_fillers=True)       # and a "yes"
    assert not acceptable("Uh, um.", "", drop_fillers=False)
    assert not acceptable("Yes.", "", drop_fillers=True)
    assert not acceptable("Um, ship it.", "", drop_fillers=True)
    assert not acceptable("um 42", "", drop_fillers=True)        # a number is content
    assert not acceptable("uh はい", "", drop_fillers=True)       # so is another script
    assert not acceptable("...", "", drop_fillers=True)
    assert not acceptable("a" * 60, "", drop_fillers=True)


def test_edit_allowed_accepts_the_edits_we_asked_for():
    from app.cleanup import edit_allowed, glossary_tokens

    g = glossary_tokens([VocabEntry("Voltium", ["Voltum"]), VocabEntry("Alex Rashid", []), VocabEntry("VM2", [])])
    assert "rashid" in g and "alex rashid" in g and "voltium" in g
    ok = lambda a, b, f=True: edit_allowed(a, b, g, f)
    assert ok("talk to Voltum about it", "talk to Voltium about it")          # glossary spelling
    assert ok("like Alex Rasheed is under", "like Alex Rashid is under")      # glossary name
    assert ok("map to VM two in terms", "map to VM2 in terms")                # digits for a numeric span
    assert ok("requested X seven Ks which", "requested X7Ks which")
    assert ok("the RTX Pro six sixty five hundred", "the RTX Pro 6 6500")
    assert ok("stuff from nvidia here", "stuff from NVIDIA here")             # case only
    assert ok("uh so um the the customer wants", "so the customer wants")     # fillers + stutter
    assert ok("we should not not ship today", "we should not ship today")     # one of the pair survives
    assert ok("the the the customer wants", "the customer wants")             # a run collapses to one
    # A known mis-hearing may be replaced however different the letters are
    from app.cleanup import alias_tokens
    g2 = glossary_tokens([VocabEntry("QBS", ["cubes"])])
    assert edit_allowed("some are cubes customers", "some are QBS customers", g2, True,
                        aliases=alias_tokens([VocabEntry("QBS", ["cubes"])]))
    # ...but an unrelated span (no alias, no digits, no resemblance) may not become one
    assert not edit_allowed("some are those customers", "some are QBS customers", g2, True)
    assert ok("I I think there fine", "I think they're fine")                 # uncapitalized homophone
    assert ok("hello there", "Hello, there.")                                # punctuation / case


def test_edit_allowed_rejects_guessed_names_and_invented_words():
    from app.cleanup import edit_allowed, glossary_tokens

    g = glossary_tokens([VocabEntry("Voltium", ["Voltum"])])
    no = lambda a, b, f=True: not edit_allowed(a, b, g, f)
    assert no("like Alex Rashid is under Terry", "like Alex Rasheed is under Thierry")  # name guess
    assert no("it's probably Ray Tomaszewski", "it's probably Ray Tomashefsky")
    assert no("outside the XKR family", "outside the XBR family")            # acronym swap, no numbers
    assert no("we need more capacity", "we need more Voltium")              # content word swapped for a glossary term
    assert no("we need more capacity", "we need more GPU capacity")          # inserted word
    assert no("we need capacity.", "we need capacity for tomorrow")          # insertion dressed as punctuation swap
    assert no("we should not not ship today", "we should ship today")        # whole repeated run = negation lost
    assert no("ship it today", "ship it")                                    # deleted content word
    assert no("uh so the customer wants", "so the customer wants", False)    # fillers kept when off
    assert no("fine", "fine and here is a whole new clause about pricing")


def test_cleanup_rejects_name_guesses_end_to_end():
    segs = _segs("like Alex Rashid is under Terry", "talk to Voltum")
    vocab = [VocabEntry("Voltium", ["Voltum"])]

    async def complete(system, user):
        return json.dumps({"0": "like Alex Rasheed is under Thierry", "1": "talk to Voltium"})

    result = asyncio.run(cleanup_segments(segs, vocab, complete))
    assert [s.text for s in segs] == ["like Alex Rashid is under Terry", "talk to Voltium"]
    assert result.changed == 1 and result.rejected == 1


def test_split_text_cuts_at_sentences_near_target():
    from app.cleanup import split_text

    text = "One two three. Four five six! Seven eight? Nine ten."
    assert split_text(text, target_chars=30) == ["One two three. Four five six!", "Seven eight? Nine ten."]
    assert split_text("   ") == []
    assert split_text("no terminal punctuation here") == ["no terminal punctuation here"]
    # A single run-on sentence longer than the target stays whole (nothing to cut at)
    assert split_text("x" * 100, target_chars=10) == ["x" * 100]


def test_cleanup_applies_accepted_changes_and_records_them():
    segs = _segs("We use VM two a lot.", "Talk to Voltum about it.", "Fine.", "")
    vocab = [VocabEntry("Voltium", ["Voltum"], weight=1)]
    calls = []

    async def complete(system, user):
        calls.append((system, user))
        return json.dumps({"0": "We use VM2 a lot.", "1": "Talk to Voltium about it.",
                           "2": "Fine, and here is a whole new paragraph nobody said at all."})

    result = asyncio.run(cleanup_segments(segs, vocab, complete, context="ctx", model="m"))
    assert [s.text for s in segs] == ["We use VM2 a lot.", "Talk to Voltium about it.", "Fine.", ""]
    assert result.changed == 2 and result.rejected == 1 and result.calls == 1 and result.error is None
    assert result.changes == [{"i": 0, "from": "We use VM two a lot."}, {"i": 1, "from": "Talk to Voltum about it."}]
    d = result.as_dict()
    assert d["segments_changed"] == 2 and d["model"] == "m" and "error" not in d
    system, user = calls[0]
    assert "Remove filler sounds" in system and "Voltium (often misheard as: Voltum)" in user and "ctx" in user
    assert "[3]" not in user  # empty segment not sent


def test_cleanup_logs_when_reply_is_unusable(caplog):
    import logging

    segs = _segs("hello VM two")

    async def complete(system, user):
        return "I could not process this."

    with caplog.at_level(logging.INFO, logger="transom.cleanup"):
        result = asyncio.run(cleanup_segments(segs, [], complete))
    assert result.changed == 0 and result.calls == 1
    assert any("no usable changes" in r.message and "I could not" in r.message for r in caplog.records)


def test_cleanup_without_fillers_uses_the_keep_instruction():
    segs = _segs("uh hello")

    async def complete(system, user):
        assert "Keep fillers" in system
        return "{}"

    result = asyncio.run(cleanup_segments(segs, [], complete, drop_fillers=False))
    assert result.changed == 0 and segs[0].text == "uh hello"


def test_cleanup_chunks_and_stops_at_first_failure():
    segs = _segs("a" * 50, "b" * 50, "c" * 50)
    seen = []

    async def complete(system, user):
        seen.append(user)
        if len(seen) == 2:
            raise RuntimeError("endpoint returned 502")
        return "{}"

    result = asyncio.run(cleanup_segments(segs, [], complete, max_chars=70))
    assert len(seen) == 2  # third chunk never attempted after the failure
    assert result.calls == 1 and result.error and "502" in result.error
    assert result.as_dict()["error"].startswith("RuntimeError")
    assert [s.text for s in segs] == ["a" * 50, "b" * 50, "c" * 50]


def test_cleanup_bounds_the_recorded_changes():
    n = CHANGES_KEPT + 20
    segs = _segs(*(f"seg {i} VM two" for i in range(n)))

    async def complete(system, user):
        idx = [int(line.split("]")[0][1:]) for line in user.split("<transcript>\n", 1)[1].split("\n</transcript>")[0].splitlines()]
        return json.dumps({str(i): f"seg {i} VM2" for i in idx})

    result = asyncio.run(cleanup_segments(segs, [], complete, max_chars=100_000))
    assert result.changed == n and len(result.changes) == CHANGES_KEPT


def test_result_as_dict_shape_when_nothing_happened():
    assert CleanupResult(model="m").as_dict() == {
        "model": "m", "calls": 0, "segments_changed": 0, "rejected": 0, "seconds": 0.0,
    }
