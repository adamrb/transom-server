from app.engines.base import Segment
from app.vocabulary import (VocabEntry, apply_corrections, correct_segments, hotwords_string, merge,
                            normalize, parse_editor_text, to_editor_text)


def test_normalize_dedupes_and_cleans():
    v = normalize([{"term": "  Plaud  ", "aliases": ["plot", "Plaud", "plot"]},
                   {"term": "plaud", "aliases": ["Plod"]}, {"term": "", "aliases": ["x"]}])
    assert len(v) == 1 and v[0].term == "Plaud" and v[0].aliases == ["plot", "Plod"]


def test_hotwords_manual_first_then_weight_then_capped():
    v = [VocabEntry("Zed", source="obsidian", weight=5), VocabEntry("Alpha"), VocabEntry("Beta"),
         VocabEntry("Aardvark", source="obsidian", weight=1)]
    assert hotwords_string(v) == "Alpha, Beta, Zed, Aardvark"
    assert hotwords_string(v, max_chars=13) == "Alpha, Beta"
    assert hotwords_string([]) is None


def test_corrections_are_whole_word_and_case_insensitive():
    v = [VocabEntry("Plaud", ["plod", "plaude"]), VocabEntry("Kilo Vox", ["Keelo Vox"])]
    assert apply_corrections("the PLOD device, plodding along, keelo vox", v) == "the Plaud device, plodding along, Kilo Vox"
    segs = [Segment(0, 1, "plaude test"), Segment(1, 2, "fine")]
    assert correct_segments(segs, v) == 1 and segs[0].text == "Plaud test"


def test_merge_keeps_existing_and_adds():
    existing = [VocabEntry("Plaud", ["plod"], "manual")]
    merged = merge(existing, normalize([{"term": "plaud", "aliases": ["plot"], "source": "obsidian"},
                                        {"term": "Morgan Ashford", "aliases": ["Morgen"], "source": "obsidian"}]))
    by = {e.term: e for e in merged}
    assert by["Plaud"].aliases == ["plod", "plot"] and by["Plaud"].source == "manual"
    assert by["Morgan Ashford"].source == "obsidian"


def test_editor_text_roundtrip():
    text = "Plaud Bridge = Plogged Bridge, plod bridge\n# comment\nObsidian\n"
    entries = parse_editor_text(text)
    assert [e.term for e in entries] == ["Plaud Bridge", "Obsidian"]
    assert to_editor_text(entries) == "Obsidian\nPlaud Bridge = Plogged Bridge, plod bridge"


def test_weight_survives_normalize_and_merge():
    v = normalize([{"term": "Sphere", "source": "obsidian", "weight": "94"}, {"term": "sphere", "weight": 3}])
    assert v[0].weight == 94
    merged = merge([VocabEntry("Sphere", source="obsidian", weight=10)], [VocabEntry("Sphere", weight=40)])
    assert merged[0].weight == 40
