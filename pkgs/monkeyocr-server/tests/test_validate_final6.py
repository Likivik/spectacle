"""Offline test of validate_final6 reading-order + bbox validity math
using synthetic JSON/MD blocks. Does NOT touch the monkey server."""
import sys

sys.path.insert(0, "/Storage/Git/spectacle/pkgs/monkeyocr-server/scripts")
import importlib.util
spec = importlib.util.spec_from_file_location(
    "v", "/Storage/Git/spectacle/pkgs/monkeyocr-server/scripts/validate_final6.py")
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)


def test_reading_order_score_sorted():
    blocks = [
        {"bbox": [0, 0, 100, 10]},
        {"bbox": [0, 20, 100, 30]},
        {"bbox": [0, 40, 100, 50]},
    ]
    assert v.reading_order_score(blocks) == 1.0


def test_reading_order_score_unsorted():
    blocks = [
        {"bbox": [0, 50, 100, 60]},
        {"bbox": [0, 10, 100, 20]},
    ]
    assert v.reading_order_score(blocks) == 0.0


def test_reading_order_score_ties():
    blocks = [
        {"bbox": [50, 10, 100, 20]},
        {"bbox": [10, 10, 50, 20]},
    ]
    # same y, second x0 < first x0 -> violates order
    assert v.reading_order_score(blocks) == 0.0


def test_bbox_stats_valid():
    valid, total, issues = v.bbox_stats(
        [{"bbox": [10, 20, 100, 200]}], pw=1000, ph=2000)
    assert valid == 1 and total == 1 and issues == []


def test_bbox_stats_out_of_bounds():
    valid, total, _ = v.bbox_stats(
        [{"bbox": [10, 20, 1500, 200]}], pw=1000, ph=2000)
    assert valid == 0 and total == 1


def test_bbox_stats_malformed():
    valid, total, _ = v.bbox_stats(
        [{"bbox": "oops"}, {"bbox": [1, 2]}, {"bbox": None}], pw=100, ph=100)
    assert valid == 0 and total == 3


def test_mixed_script_words():
    # pure cyrillic / pure latin -> 0
    assert v.mixed_script_words("ДОГОВОР аренды") == 0
    # mixed cyrillic+latin inside one token
    assert v.mixed_script_words("Договорrent 2026") == 1
    assert v.mixed_script_words("Stranger123") == 0  # digits/letters, no scripts
    assert v.mixed_script_words("") == 0


def test_norm_drops_punct():
    assert v.norm("ДОГОВОР, аренды!") == "договораренды"
    assert v.norm("  Hello, World!  ") == "helloworld"
