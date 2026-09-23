"""Tests for monkey_server helpers (clamp/swap/expand, parse_layouts,
prompt routing, retry-repeat, overlap suppression, junk filter).
Excludes GPU code paths (torch/transformers not required at import).
"""
import sys
from pathlib import Path

# Insert repo-relative path so we can import helpers without booting the model
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import monkey_server as ms  # noqa: E402


# --- clamp/swap/expand (symmetric, original) --------------------------------

def test_clamp_swap_expand_normal():
    px = ms._swap_and_expand([0, 0, 1000, 1000], w=100, h=200, expand_px=0)
    assert px == (0, 0, 100, 200)
    px = ms._swap_and_expand([0, 0, 1000, 1000], w=100, h=200, expand_px=2)
    assert px == (0, 0, 100, 200)  # clamped at bounds


def test_clamp_swap_expand_swaps_reversed():
    px = ms._swap_and_expand([1000, 1000, 0, 0], w=100, h=200, expand_px=0)
    assert px == (0, 0, 100, 200)


def test_clamp_swap_expand_clips_to_bounds():
    px = ms._swap_and_expand([-50, -50, 1050, 1050], w=100, h=200, expand_px=0)
    assert px == (0, 0, 100, 200)


# --- asymmetric crop padding (P1) -------------------------------------------

def test_asym_pad_left_overhang():
    # inset box at x=200..800 (normalized) on a 1000px-wide image
    px = ms._swap_and_expand_asym([200, 200, 800, 800], w=1000, h=1000,
                                  left=60, right=30, top=30, bottom=30)
    assert px[0] == 140  # 200 - 60
    assert px[2] == 830  # 800 + 30


def test_asym_pad_clamps_to_bounds():
    px = ms._swap_and_expand_asym([0, 0, 100, 900], w=1000, h=1000,
                                  left=60, right=30, top=30, bottom=30)
    assert px[0] == 0  # can't go below 0
    assert px[2] == 130


def test_asym_pad_swaps():
    px = ms._swap_and_expand_asym([800, 700, 100, 300], w=1000, h=1000,
                                  left=60, right=30, top=30, bottom=30)
    assert px[0] < px[2] and px[1] < px[3]


# --- IoU / containment suppression (P1) -------------------------------------

def test_iou_disjoint():
    assert ms._iou([0, 0, 10, 10], [20, 20, 30, 30]) == 0.0


def test_iou_overlap():
    assert ms._iou([0, 0, 10, 10], [5, 5, 15, 15]) > 0.0


def test_containment_full():
    assert ms._containment([0, 0, 10, 10], [0, 0, 20, 20]) == 1.0
    assert ms._containment([0, 0, 20, 20], [0, 0, 10, 10]) < 1.0


def test_suppress_identical_nested_same_label():
    # same-label 100%-nested duplicate must be dropped
    blocks = [
        {"bbox": [0, 0, 100, 100], "label": "Text"},
        {"bbox": [10, 10, 90, 90], "label": "Text"},
    ]
    out = ms._suppress_overlaps(blocks)
    assert len(out) == 1
    assert out[0]["bbox"] == [0, 0, 100, 100]


def test_suppress_heavy_overlap():
    # Only drop on high IoU (>0.30) — two partly-overlapping distinct
    # regions remain legitimate.
    blocks = [
        {"bbox": [0, 0, 100, 100], "label": "Text"},
        {"bbox": [0, 0, 100, 100], "label": "Text"},
    ]
    assert len(ms._suppress_overlaps(blocks)) == 1


def test_suppress_keeps_distinct_blocks():
    blocks = [
        {"bbox": [0, 0, 100, 100], "label": "Text"},
        {"bbox": [200, 200, 300, 300], "label": "Text"},
    ]
    assert len(ms._suppress_overlaps(blocks)) == 2


def test_suppress_keeps_different_label_contained():
    # a formula inside a caption block is legitimate—keep both
    blocks = [
        {"bbox": [0, 0, 200, 200], "label": "Caption"},
        {"bbox": [50, 50, 100, 100], "label": "Formula"},
    ]
    out = ms._suppress_overlaps(blocks)
    assert len(out) == 2


def test_suppress_preserves_model_order():
    blocks = [
        {"bbox": [200, 200, 300, 300], "label": "Text"},
        {"bbox": [0, 0, 100, 100], "label": "Text"},
    ]
    out = ms._suppress_overlaps(blocks)
    assert [b["bbox"] for b in out] == [[200, 200, 300, 300], [0, 0, 100, 100]]


# --- parse_layouts ------------------------------------------------------------

def test_parse_layouts_json_fence():
    raw = "```json\n[{\"bbox\":[0,0,100,100],\"label\":\"Text\"}]\n```"
    assert ms._extract_layouts(raw) == [{"bbox": [0, 0, 100, 100], "label": "Text"}]


def test_parse_layouts_python_repr():
    raw = "[{'bbox': [0, 0, 100, 100], 'label': 'Section-header'}]"
    blocks = ms._extract_layouts(raw)
    assert len(blocks) == 1
    assert blocks[0]["label"] == "Section-header"


def test_parse_layouts_fragmented():
    raw = ("Some preamble text "
           "{\"bbox\":[0,0,100,100],\"label\":\"Text\"} and more "
           "{\"bbox\":[0,200,100,300],\"label\":\"Title\"}")
    blocks = ms._extract_layouts(raw)
    assert len(blocks) == 2


def test_parse_layouts_empty():
    assert ms._extract_layouts("") == []
    assert ms._extract_layouts("no json here") == []


# --- prompt routing -----------------------------------------------------------

def test_prompt_for_table_routes_to_html():
    assert ms._route_prompt("Table") == ms.TABLE_PROMPT


def test_prompt_for_formula_routes_to_latex():
    assert ms._route_prompt("Formula") == ms.FORMULA_PROMPT


def test_prompt_for_text_default():
    assert ms._route_prompt("Text") == ms.TEXT_PROMPT
    assert ms._route_prompt("") == ms.TEXT_PROMPT
    assert ms._route_prompt(None) == ms.TEXT_PROMPT


def test_prompt_for_picture_returns_empty():
    assert ms._route_prompt("Picture") == ""


# --- retry-repeat ---------------------------------------------------------------

def test_is_bad_recognition_filters_garbage():
    assert ms._is_bad_recognition("")
    assert ms._is_bad_recognition("   ")
    assert ms._is_bad_recognition("undefined")
    assert ms._is_bad_recognition("[1,2,3]")
    assert ms._is_bad_recognition('{"a":1}')
    assert ms._is_bad_recognition("The quick brown fox jumps over the lazy dog")
    assert not ms._is_bad_recognition("ДОГОВОР аренды")


def test_generate_with_retry_returns_good(monkeypatch):
    calls = {"n": 0}

    def fake_gen(img, prompt, max_new_tokens=4096):
        calls["n"] += 1
        return "real text"

    monkeypatch.setattr(ms, "_generate", fake_gen)
    out = ms._generate_with_retry(img=None, prompt="x", max_new_tokens=100, repeats=2)
    assert out == "real text"
    assert calls["n"] == 1  # good on first try


def test_generate_with_retry_gives_up(monkeypatch):
    monkeypatch.setattr(ms, "_generate", lambda *a, **k: "")
    monkeypatch.setattr(ms, "_generate_with_temp", lambda *a, **k: "")
    out = ms._generate_with_retry(img=None, prompt="x", max_new_tokens=100, repeats=2)
    assert out == ""
    # 1 deterministic + 2 temperature retries = 3


def test_generate_with_retry_recovers_on_temp(monkeypatch):
    calls = {"n": 0}

    def fake_gen(*a, **k):
        calls["n"] += 1
        return ""  # deterministic fails

    def fake_temp(*a, **k):
        if calls["n"] == 1:
            return "real"
        return ""

    monkeypatch.setattr(ms, "_generate", fake_gen)
    monkeypatch.setattr(ms, "_generate_with_temp", fake_temp)
    out = ms._generate_with_retry(img=None, prompt="x", max_new_tokens=100, repeats=2)
    assert out == "real"


# --- junk filter ---------------------------------------------------------------

def test_is_junk_content_matches_literals():
    assert ms._is_junk_content("The quick brown fox jumps over the lazy dog")
    assert ms._is_junk_content("lorem ipsum dolor sit amet")
    assert ms._is_junk_content("sample text here")
    assert not ms._is_junk_content("Добро пожаловать в Омерзительное средневековье")


def test_label_is_textlike():
    assert ms._label_is_textlike("Text")
    assert ms._label_is_textlike("Section-header")
    assert not ms._label_is_textlike("Picture")
    assert not ms._label_is_textlike("Formula")