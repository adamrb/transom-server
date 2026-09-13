"""Consensus pass over several recognizers' readings of a noisy recording."""

import asyncio
import json

import pytest

from app.consensus import (
    ConsensusResult, consensus_segments, heard, overlapping, render_primary, windows,
)
from app.engines.base import Alternate, Segment


def _seg(start, end, text, speaker=None):
    return Segment(start=start, end=end, text=text, speaker=speaker)


def test_windows_group_segments_by_audio_span():
    segs = [_seg(0, 10, "a"), _seg(10, 25, "b"), _seg(25, 45, "c"), _seg(45, 50, ""), _seg(50, 70, "d"),
            _seg(None, None, "untimed"), _seg(70, 71, "e")]
    assert windows(segs, 40.0) == [[0, 1], [2], [4, 6]]
    assert windows([], 40.0) == []
    # A single segment longer than the window still forms one window.
    assert windows([_seg(0, 100, "long")], 40.0) == [[0]]


def test_overlapping_takes_slack_at_the_edges():
    alt = Alternate("x", [_seg(0, 5, "before"), _seg(8, 12, "edge"), _seg(20, 30, "in"), _seg(60, 65, "after")])
    got = [s.text for s in overlapping(alt, 10.0, 40.0, slack=2.0)]
    assert got == ["edge", "in"]


def test_heard_requires_every_word_from_some_system():
    vocab = {"we", "can", "have", "sam", "lead", "into", "it"}
    assert heard("We can have Sam lead into it.", vocab)
    assert not heard("We can have Samuel lead into it.", vocab)
    assert not heard("", vocab) and not heard("...", vocab)


def test_render_primary_numbers_and_times():
    out = render_primary([_seg(1.234, 5.6, "hello"), _seg(5.6, 9.0, "there")], [0, 1])
    assert out == "[0] (1.2-5.6) hello\n[1] (5.6-9.0) there"


def _run(segments, alternates, replies, **kw):
    calls = []

    async def complete(system, user):
        calls.append((system, user))
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    result = asyncio.run(consensus_segments(segments, alternates, complete, **kw))
    return result, calls


def test_consensus_applies_agreed_readings_and_keeps_timeline():
    segs = [
        _seg(0, 10, "So when you go to play this, oh, you were fine, call the card.", speaker="Speaker 1"),
        _seg(10, 20, "Alex listens to this song and immediately comes into the lore.", speaker="Speaker 2"),
    ]
    alts = [
        Alternate("parakeet", [_seg(0, 20, "so when she goes to play they're like oh you were flying home "
                                          "Alex listened to this song and immediately sent it to Morgan")]),
        Alternate("whisper partial", [_seg(1, 9, "oh, you were flying home."), _seg(11, 19, "sent it to Morgan")]),
    ]
    reply = json.dumps({
        "0": "So when you go to play this, oh, you were flying home.",
        "1": "Alex listened to this song and immediately sent it to Morgan.",
    })
    result, calls = _run(segs, alts, [reply], context="Alex and Morgan, two speakers", model="m")
    assert result.changed == 2 and result.rejected == 0 and result.calls == 1
    assert result.systems == ["parakeet", "whisper partial"]
    assert segs[0].text == "So when you go to play this, oh, you were flying home."
    assert segs[1].text == "Alex listened to this song and immediately sent it to Morgan."
    # Speakers and timestamps are untouched; the change log keeps the old text.
    assert (segs[0].speaker, segs[1].speaker) == ("Speaker 1", "Speaker 2")
    assert (segs[0].start, segs[1].end) == (0, 20)
    assert result.changes[0] == {"i": 0, "from": "So when you go to play this, oh, you were fine, call the card."}
    system, user = calls[0]
    assert "Alex and Morgan, two speakers" in system
    assert "ALTERNATE — parakeet" in user and "[0] (0.0-10.0)" in user
    d = result.as_dict()
    assert d["segments_changed"] == 2 and d["systems"] == ["parakeet", "whisper partial"] and d["model"] == "m"


def test_consensus_rejects_invented_words_and_rewrites():
    segs = [_seg(0, 10, "we can have to kind of lead into it")]
    alts = [Alternate("b", [_seg(0, 10, "we can have Sam kind of lead into it")])]
    reply = json.dumps({
        "0": "we can have Samuel kind of lead into it",  # nobody heard "Samuel"
    })
    result, _ = _run(segs, alts, [reply])
    assert result.changed == 0 and result.rejected == 1
    assert segs[0].text == "we can have to kind of lead into it"
    # A drastic rewrite from heard words is not a correction either.
    reply = json.dumps({"0": "we"})
    result, _ = _run(segs, alts, [reply])
    assert result.rejected == 1 and segs[0].text == "we can have to kind of lead into it"
    # Emptying a real segment is refused.
    reply = json.dumps({"0": ""})
    result, _ = _run(segs, alts, [reply])
    assert result.rejected == 1


def test_consensus_skips_windows_without_alternate_speech_and_tolerates_bad_json():
    segs = [_seg(0, 10, "first"), _seg(100, 110, "second window")]
    alts = [Alternate("b", [_seg(0, 10, "first!")])]
    result, calls = _run(segs, alts, ["not json at all"])
    assert result.calls == 1 and result.changed == 0
    assert "second window" not in calls[0][1]


def test_consensus_without_alternates_is_a_noop():
    segs = [_seg(0, 10, "x")]
    result, calls = _run(segs, [Alternate("empty", [])], [])
    assert result == ConsensusResult(systems=[]) and calls == []


def test_consensus_call_failure_is_recorded_not_raised():
    segs = [_seg(0, 10, "x"), _seg(50, 60, "y")]
    alts = [Alternate("b", [_seg(0, 60, "x y")])]
    result, calls = _run(segs, alts, [RuntimeError("endpoint returned 504")])
    assert result.error and "504" in result.error and result.calls == 0 and len(calls) == 1
    assert [s.text for s in segs] == ["x", "y"]


def test_consensus_unreadable_reply_costs_only_its_window(monkeypatch):
    import app.consensus as c

    segs = [_seg(0, 10, "first bit"), _seg(100, 110, "second bit")]
    alts = [Alternate("b", [_seg(0, 10, "first bit!"), _seg(100, 110, "second bit!")])]

    def parse(content, valid):
        if content == "boom":
            raise TypeError("content blocks")
        return {min(valid): "first bit!"} if 0 in valid else {}

    monkeypatch.setattr(c, "parse_reply", parse)
    result, calls = _run(segs, alts, [json.dumps({"0": "first bit!"}), "boom"])
    assert result.calls == 2 and result.changed == 1 and result.rejected == 1
    assert segs[0].text == "first bit!" and segs[1].text == "second bit"
    assert result.changes == [{"i": 0, "from": "first bit"}]
