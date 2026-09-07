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


def test_transcript_body_markdown_bolds_speakers():
    from app.export import transcript_body_markdown
    assert transcript_body_markdown("Speaker 1: hi there\nSpeaker 2: hello\n") == "**Speaker 1:** hi there\n\n**Speaker 2:** hello"
    assert transcript_body_markdown("just prose, no labels") == "just prose, no labels"


def test_trusted_proxy_matching():
    from app.config import Settings
    import os
    os.environ["PB_AUTH_TOKENS"] = "t"
    os.environ.pop("PB_TRUSTED_PROXIES", None)
    s = Settings()
    assert s.trusted_proxies == [] and not s.is_trusted_proxy("127.0.0.1")   # trust nobody by default
    os.environ["PB_TRUSTED_PROXIES"] = "192.0.2.1, 172.18.0.0/16"
    s = Settings()
    assert s.is_trusted_proxy("192.0.2.1") and s.is_trusted_proxy("172.18.0.5")
    assert not s.is_trusted_proxy("203.0.113.9") and not s.is_trusted_proxy("testclient") and not s.is_trusted_proxy(None)
    os.environ.pop("PB_TRUSTED_PROXIES", None)
