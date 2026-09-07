from app.highlights import build_highlights, fmt_ts, highlights_markdown, parse_marks


def test_parse_marks_normalizes_and_drops_garbage():
    assert parse_marks(None) == []
    assert parse_marks("not json") == []
    assert parse_marks([12.345, "7", -1, None, "x", 12.35, float("nan"), 1e9]) == [7.0, 12.35]
    assert parse_marks("[3, 1, 2]") == [1.0, 2.0, 3.0]


def test_build_highlights_windows_around_each_mark():
    segs = [
        {"start": 0.0, "end": 10.0, "text": "intro", "speaker": "Speaker 1"},
        {"start": 40.0, "end": 55.0, "text": "the key decision", "speaker": "Speaker 2"},
        {"start": 56.0, "end": 70.0, "text": "follow-up", "speaker": "Speaker 1"},
        {"start": 200.0, "end": 210.0, "text": "far away", "speaker": "Speaker 1"},
    ]
    hl = build_highlights([60.0, 300.0], segs, duration_s=250.0)
    # 60 s: window [40, 68] catches the decision and the follow-up, not intro/far
    assert len(hl) == 1
    assert hl[0]["at"] == 60.0 and hl[0]["text"] == "the key decision follow-up"
    assert hl[0]["speakers"] == ["Speaker 1", "Speaker 2"]
    assert (hl[0]["start"], hl[0]["end"]) == (40.0, 70.0)
    # a mark with no speech nearby still shows up with empty text
    lonely = build_highlights([120.0], segs, duration_s=250.0)
    assert lonely[0]["text"] == "" and lonely[0]["start"] == 120.0


def test_markdown_and_timestamps():
    assert fmt_ts(65) == "1:05" and fmt_ts(3725) == "1:02:05"
    lines = highlights_markdown([{"at": 65, "text": "said this"}, {"at": 90, "text": ""}])
    assert lines[0] == "## Highlights"
    assert "- **1:05** said this" in lines and "- **1:30** (no speech near this mark)" in lines
    assert highlights_markdown([]) == []
