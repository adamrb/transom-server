from app.engines.base import Segment
from app.vocabulary import (VocabEntry, apply_corrections, correct_segments, hotwords_string, merge,
                            normalize, parse_editor_text, to_editor_text)


def test_normalize_dedupes_and_cleans():
    v = normalize([{"term": "  Plaud  ", "aliases": ["plot", "Plaud", "plot"]},
                   {"term": "plaud", "aliases": ["Plod"]}, {"term": "", "aliases": ["x"]}])
    assert len(v) == 1 and v[0].term == "Plaud" and v[0].aliases == ["plot", "Plod"]


def test_hotwords_by_weight_manual_default_between_family_and_imports():
    v = [VocabEntry("Zed", source="obsidian", weight=5), VocabEntry("Alpha"), VocabEntry("Beta"),
         VocabEntry("Aardvark", source="obsidian", weight=1), VocabEntry("Morgan Ashford", source="obsidian", weight=10000),
         VocabEntry("VM2", weight=100)]
    assert hotwords_string(v) == "Morgan Ashford, Alpha, Beta, VM2, Zed, Aardvark"
    assert hotwords_string(v, max_chars=32) == "Morgan Ashford, Alpha, Beta"
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


def test_acronym_normalization_collapses_spelled_out_forms():
    from app.vocabulary import acronym_pattern
    v = [VocabEntry("VM2"), VocabEntry("T3"), VocabEntry("GKS"), VocabEntry("H100"), VocabEntry("RFC"), VocabEntry("Turbo")]
    text = ("We run on VM two and V.M.2 and v m 2, store in T three buckets, deploy to G.K.S. and g k s, "
            "on H one hundred and H 100 GPUs; the R F C is due. Turbo stays. VM2 unchanged. The bus three stops. Use G.K.S. Then rest.")
    out = apply_corrections(text, v)
    assert out == ("We run on VM2 and VM2 and VM2, store in T3 buckets, deploy to GKS and GKS, "
                   "on H100 and H100 GPUs; the RFC is due. Turbo stays. VM2 unchanged. The bus three stops. Use GKS. Then rest.")
    assert acronym_pattern("Turbo") is None and acronym_pattern("ModelForge") is None
    # a pure-letter acronym must not rewrite an unrelated word that merely contains the letters
    assert apply_corrections("the cactus", [VocabEntry("CAC")]) == "the cactus"


def test_acronym_plural_and_brand_casing():
    v = [VocabEntry("GPU"), VocabEntry("ModelForge"), VocabEntry("Plaud Bridge"), VocabEntry("Delta"), VocabEntry("MegaNode")]
    out = apply_corrections("eight G P Us and two GPU's on modelforge mega-node; plaud bridge; a delta moment", v)
    assert out == "eight GPUs and two GPU's on ModelForge mega-node; Plaud Bridge; a delta moment"
