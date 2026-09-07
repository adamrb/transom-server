from app.export import safe_filename, transcript_markdown


def test_markdown_without_summary_omits_block_and_ends_with_newline():
    md = transcript_markdown("T", "2026-09-07T05:27:31Z", 17, None, "hello\n")
    assert "## Summary" not in md
    assert md.endswith("## Transcript\n\nhello\n")
    assert md.startswith('---\ntitle: "T"\nrecorded: "2026-09-07T05:27:31Z"\nduration_s: "17"\nsource: plaud-bridge\n---\n# T\n')


def test_safe_filename_strips_unsafe_chars_and_caps_length():
    assert safe_filename('a/b:c*d?"e<f>g|h#i') == "a b c d e f g h i"
    assert safe_filename("   ") == "transcript"
    assert len(safe_filename("x" * 200)) == 80
