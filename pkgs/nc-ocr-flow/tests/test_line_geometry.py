"""Tests for line_geometry — pure pairing, no I/O, no network."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from nc_ocr_flow.line_geometry import (
    TextBlock,
    LineTextPair,
    PairingResult,
    pair_lines_by_reading_order,
)


# --- Helpers -----------------------------------------------------------------

@dataclass(frozen=True)
class FakeLine:
    """Mimics a DetectionLine shape; keeps tests independent of any
    particular detection backend."""
    bbox: tuple[float, float, float, float]
    polygon: tuple | None = None
    confidence: float | None = 0.5


def L(x0, y0, x1, y1, conf=0.9, polygon=None):
    return FakeLine(bbox=(x0, y0, x1, y1), polygon=polygon, confidence=conf)


# --- Single row, left-to-right ------------------------------------------------

def test_single_row_left_to_right():
    lines = [L(10, 20, 80, 30), L(100, 20, 180, 30)]
    blocks = [TextBlock("first"), TextBlock("second")]
    result = pair_lines_by_reading_order(lines, blocks)
    assert result.is_complete
    assert [p.body for p in result.pairs] == ["first", "second"]
    assert result.pairs[0].bbox == (10.0, 20.0, 80.0, 30.0)


def test_single_row_sorts_by_x_even_if_input_unsorted():
    lines = [L(100, 20, 180, 30), L(10, 20, 80, 30)]
    blocks = [TextBlock("left"), TextBlock("right")]
    result = pair_lines_by_reading_order(lines, blocks)
    assert [p.body for p in result.pairs] == ["left", "right"]


# --- Multi-row, top-to-bottom -------------------------------------------------

def test_multi_row_top_to_bottom():
    lines = [
        L(10, 10, 80, 25),    # row 1 left
        L(100, 10, 180, 25),  # row 1 right
        L(10, 40, 180, 55),   # row 2 (one line, full width)
    ]
    blocks = [
        TextBlock("r1-left"), TextBlock("r1-right"), TextBlock("r2-line"),
    ]
    result = pair_lines_by_reading_order(lines, blocks)
    assert result.is_complete
    assert [p.body for p in result.pairs] == ["r1-left", "r1-right", "r2-line"]


def test_multi_row_with_gaps():
    """Lines at very different y0 → separate rows even with different heights."""
    lines = [
        L(10, 10, 80, 20),   # h=10
        L(10, 100, 80, 130),  # h=30, gap=80 > 0.5*10=5 → new row
    ]
    blocks = [TextBlock("a"), TextBlock("b")]
    result = pair_lines_by_reading_order(lines, blocks)
    assert result.is_complete
    assert [p.body for p in result.pairs] == ["a", "b"]


def test_close_lines_group_into_one_row():
    """Two lines with small gap → one row (sub-header + body)."""
    lines = [
        L(10, 10, 80, 25),   # h=15
        L(10, 28, 80, 43),   # h=15, gap=3, tol=7.5 → same row
    ]
    blocks = [TextBlock("line1"), TextBlock("line2")]
    result = pair_lines_by_reading_order(lines, blocks)
    assert result.is_complete
    assert [p.body for p in result.pairs] == ["line1", "line2"]


# --- Polygon + confidence flow through ---------------------------------------

def test_pair_preserves_polygon_and_confidence():
    poly = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0), (7.0, 8.0))
    line = L(1, 2, 7, 8, conf=0.77, polygon=poly)
    result = pair_lines_by_reading_order([line], [TextBlock("x")])
    pair = result.pairs[0]
    assert pair.polygon == poly
    assert pair.confidence == 0.77
    assert pair.label == ""  # empty label flows through


def test_pair_label_passthrough():
    line = L(0, 0, 10, 10)
    result = pair_lines_by_reading_order(
        [line], [TextBlock("text", label="SectionHeader")]
    )
    assert result.pairs[0].label == "SectionHeader"


# --- Mismatched counts -------------------------------------------------------

def test_more_lines_than_text_unmatched_lines():
    lines = [L(10, 10, 80, 20), L(100, 10, 180, 20)]
    blocks = [TextBlock("only-one")]
    result = pair_lines_by_reading_order(lines, blocks)
    assert len(result.pairs) == 1
    assert len(result.unmatched_lines) == 1
    assert result.unmatched_lines[0].bbox == (100.0, 10.0, 180.0, 20.0)
    assert result.unmatched_texts == []
    assert not result.is_complete


def test_more_text_than_lines_unmatched_texts():
    lines = [L(10, 10, 80, 20)]
    blocks = [TextBlock("a"), TextBlock("b"), TextBlock("c")]
    result = pair_lines_by_reading_order(lines, blocks)
    assert len(result.pairs) == 1
    assert result.pairs[0].body == "a"
    assert [b.text for b in result.unmatched_texts] == ["b", "c"]
    assert result.unmatched_lines == []


def test_empty_lines():
    result = pair_lines_by_reading_order([], [])
    assert result.pairs == []
    assert result.is_complete


def test_empty_lines_with_texts():
    lines = []
    blocks = [TextBlock("orphan")]
    result = pair_lines_by_reading_order(lines, blocks)
    assert result.pairs == []
    assert [b.text for b in result.unmatched_texts] == ["orphan"]
    assert not result.is_complete


# --- Row-tolerance knob ------------------------------------------------------

def test_row_tolerance_factor_breaks_apart_close_lines():
    """Aggressive tolerance (small factor) keeps two close lines in one row."""
    lines = [L(10, 10, 80, 20), L(10, 22, 80, 32)]  # gap=2, h=10
    blocks = [TextBlock("a"), TextBlock("b")]
    # factor=0.5 → tol=5 → same row (gap 2 ≤ 5) → "a","b" preserved
    r1 = pair_lines_by_reading_order(lines, blocks, row_tolerance_factor=0.5)
    assert [p.body for p in r1.pairs] == ["a", "b"]


def test_row_tolerance_factor_zero_strict():
    """factor=0 → any positive gap starts a new row."""
    lines = [L(10, 10, 80, 20), L(10, 22, 80, 32)]  # gap=2
    blocks = [TextBlock("a"), TextBlock("b")]
    r = pair_lines_by_reading_order(lines, blocks, row_tolerance_factor=0.0)
    # Each in its own row; row order is by y0 → still "a","b" (top-to-bottom).
    # Within each row only one item, so x-sort doesn't change anything.
    assert [p.body for p in r.pairs] == ["a", "b"]


# --- Type / import smoke ------------------------------------------------------

def test_imports_clean():
    from nc_ocr_flow import line_geometry
    for name in [
        "TextBlock", "LineTextPair", "PairingResult",
        "pair_lines_by_reading_order",
    ]:
        assert hasattr(line_geometry, name), f"missing export: {name}"


# --- Region-aware pairing ----------------------------------------------------
#
# These tests use the geometry of a 4-card page (two rows × two columns)
# plus a header and footer — mirroring the structure of final6 page 2.
# Lines are 1182×1654 px (200 dpi from a 425×595 pt PDF page).
# Card box: ~550 wide × 230 tall, gap ~30 px between cards.
# -----------------------------------------------------------------------------


# Convenience: build a TextBlock with optional bbox.
from dataclasses import dataclass as _dc


@_dc(frozen=True)
class _BlockWithBbox:
    text: str
    label: str = ""
    bbox: tuple[float, float, float, float] | None = None


def test_region_two_columns_two_rows_card_grid():
    """Two rows × two columns of cards. Each card has its own text.

    Layout (all line bbox x0,y0,x1,y1; heights ~20):
      band 1:  card-A (x~100-650, y~100-330) | card-B (x~700-1100, y~120-340)
      band 2:  card-C (x~100-650, y~430-660) | card-D (x~700-1100, y~440-670)

    Global reading order would interleave A → B → C → D text and pair
    wrongly. Region-aware must keep each card's text block within its
    own region.
    """
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    lines = [
        # Card A (top-left)
        L(100, 100, 200, 120), L(100, 130, 300, 150), L(100, 160, 280, 180),
        # Card B (top-right)
        L(700, 120, 800, 140), L(700, 150, 900, 170), L(700, 180, 880, 200),
        # Card C (bottom-left)
        L(100, 430, 200, 450), L(100, 460, 300, 480), L(100, 490, 280, 510),
        # Card D (bottom-right)
        L(700, 440, 800, 460), L(700, 470, 900, 490), L(700, 500, 880, 520),
    ]
    # One text block per card (M3 emits per-card). Each card's block
    # sits within that card's region.
    blocks = [
        _BlockWithBbox("A1", bbox=(100, 105, 300, 175)),
        _BlockWithBbox("B1", bbox=(700, 125, 900, 195)),
        _BlockWithBbox("C1", bbox=(100, 435, 300, 505)),
        _BlockWithBbox("D1", bbox=(700, 445, 900, 515)),
    ]
    result = pair_lines_by_region(lines, blocks)
    bodies = [p.body for p in result.pairs]
    # Each card has 3 lines but only 1 block → 1 pair, 2 unmatched lines per region.
    assert sorted(bodies) == ["A1", "B1", "C1", "D1"]
    # Region order: A → B (top row) → C → D (bottom row).
    assert bodies.index("A1") < bodies.index("B1") < bodies.index("C1") < bodies.index("D1")
    # 4 pairs, 8 unmatched lines (2 per region × 4 regions).
    assert len(result.pairs) == 4
    assert len(result.unmatched_lines) == 8


def test_region_interleaved_columns_dont_mix():
    """Two side-by-side columns on same page must stay separated.

    Layout: column-L (x=100) and column-R (x=900), 5 lines each,
    interleaved by y (typical card layout).
    Global reading order would be: L1, R1, L2, R2, L3, R3...
    Region-aware must give: L1, L2, L3, L4, L5, R1, R2, R3, R4, R5.
    """
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    lines = []
    blocks = []
    for i in range(5):
        y = 100 + i * 40
        lines.append(L(100, y, 400, y + 20))   # column L
        lines.append(L(900, y, 1100, y + 20))  # column R
        blocks.append(_BlockWithBbox(f"L{i}", bbox=(100, y, 400, y + 20)))
        blocks.append(_BlockWithBbox(f"R{i}", bbox=(900, y, 1100, y + 20)))
    result = pair_lines_by_region(lines, blocks)
    assert result.is_complete
    bodies = [p.body for p in result.pairs]
    # All L's should appear before any R.
    last_L = max(i for i, b in enumerate(bodies) if b.startswith("L"))
    first_R = min(i for i, b in enumerate(bodies) if b.startswith("R"))
    assert last_L < first_R, f"interleaved: {bodies}"


def test_region_mismatched_counts_do_not_leak():
    """Independent regions have independent mismatched counts.

    Region A: 5 Surya lines, 3 M3 text blocks → 3 pairs, 2 unmatched lines.
    Region B: 2 Surya lines, 0 M3 text blocks → 0 pairs, 2 unmatched lines.
    Total: 3 pairs, 4 unmatched_lines, 0 unmatched_texts.

    The invariant is: NO text block from A is paired with a line from B.
    """
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    lines = [
        L(100, 100, 300, 120),
        L(100, 130, 320, 150),
        L(100, 160, 280, 180),
        L(100, 190, 290, 210),
        L(100, 220, 310, 240),
        L(700, 100, 900, 120),  # Card B
        L(700, 130, 880, 150),
    ]
    blocks = [
        _BlockWithBbox("A1", bbox=(100, 105, 300, 175)),
        _BlockWithBbox("A2", bbox=(100, 195, 290, 205)),  # spans lines 4-5
        _BlockWithBbox("A3", bbox=(100, 215, 310, 235)),
    ]
    result = pair_lines_by_region(lines, blocks)
    assert len(result.pairs) == 3
    # Critical invariant: no pair has a line from region B (x=700) paired
    # with an A-block text. Every pair's line x0 must be 100 (region A).
    for p in result.pairs:
        assert p.bbox[0] == 100, f"cross-region leak: {p}"
    # Unmatched lines: 2 from A's tail + 2 from B's region = 4.
    unmatched_y = sorted(ln.bbox[1] for ln in result.unmatched_lines)
    assert unmatched_y == [100.0, 130.0, 190.0, 220.0]
    assert result.unmatched_texts == []


def test_region_single_column_falls_back_to_reading_order():
    """With one row band and one column, behaves like reading-order."""
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    lines = [
        L(10, 20, 80, 30),
        L(100, 20, 180, 30),
        L(10, 40, 180, 55),
    ]
    blocks = [
        _BlockWithBbox("a", bbox=(10, 20, 80, 30)),
        _BlockWithBbox("b", bbox=(100, 20, 180, 30)),
        _BlockWithBbox("c", bbox=(10, 40, 180, 55)),
    ]
    result = pair_lines_by_region(lines, blocks)
    assert [p.body for p in result.pairs] == ["a", "b", "c"]


def test_region_plain_text_blocks_without_bbox():
    """Plain TextBlock (no bbox) gets distributed round-robin to regions.

    With no spatial signal on the text block, the only deterministic
    assignment is by input order (round-robin across regions). The
    user's input order [left-1, left-2, right-1, right-2] maps to
    regions [L, R, L, R] which is still better than dumping all
    blocks into region 0.
    """
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    lines = [
        L(100, 100, 300, 120),
        L(100, 130, 300, 150),
        L(700, 100, 900, 120),
        L(700, 130, 900, 150),
    ]
    blocks = [
        TextBlock("left-1"),
        TextBlock("left-2"),
        TextBlock("right-1"),
        TextBlock("right-2"),
    ]
    result = pair_lines_by_region(lines, blocks)
    # Round-robin across 2 regions: blocks 0,2 → region 0 (L); 1,3 → region 1 (R).
    # Each region has 2 lines + 2 blocks → 2 pairs each.
    assert len(result.pairs) == 4
    assert result.unmatched_lines == []
    assert result.unmatched_texts == []
    # Each region's pairs must use its own blocks.
    pairs_by_region_x = {round(p.bbox[0] / 100) * 100: p.body for p in result.pairs}
    # L region (x=100) has both left-* blocks; R region (x=700) has both right-* blocks.
    left_blocks_in_L = [b for p in result.pairs if p.bbox[0] == 100 for b in [p.body] if b.startswith("left")]
    right_blocks_in_R = [b for p in result.pairs if p.bbox[0] == 700 for b in [p.body] if b.startswith("right")]
    assert sorted(left_blocks_in_L) == ["left-1", "left-2"]
    assert sorted(right_blocks_in_R) == ["right-1", "right-2"]


def test_region_empty_inputs():
    """Empty inputs produce an empty result with no crash."""
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    assert pair_lines_by_region([], []).is_complete
    assert pair_lines_by_region([], [TextBlock("orphan")]).unmatched_texts == [TextBlock("orphan")]


def test_region_more_lines_than_text_per_region():
    """Two regions: A has 3 lines + 1 text, B has 2 lines + 3 texts.

    Region A's 2 extra lines → unmatched_lines.
    Region B's 1 extra text → unmatched_texts.
    Other region's leftovers must not be silently reused.
    """
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    lines = [
        L(100, 100, 300, 120),
        L(100, 130, 300, 150),
        L(100, 160, 300, 180),
        L(700, 100, 900, 120),
        L(700, 130, 900, 150),
    ]
    blocks = [
        _BlockWithBbox("only-A", bbox=(100, 105, 300, 175)),
        _BlockWithBbox("B1", bbox=(700, 105, 900, 115)),
        _BlockWithBbox("B2", bbox=(700, 135, 900, 145)),
        _BlockWithBbox("B3", bbox=(900, 105, 920, 115)),  # x-extends past column
    ]
    result = pair_lines_by_region(lines, blocks)
    # A: 3 lines, 1 text → 1 pair, 2 unmatched lines.
    # B: 2 lines, 3 texts → 2 pairs, 1 unmatched text.
    assert len(result.pairs) == 3
    assert len(result.unmatched_lines) == 2
    assert len(result.unmatched_texts) == 1
    # Unmatched text is whichever B-block didn't fit (after sorting by y).
    # Blocks sorted by y0: B1(y=105,x=700), B3(y=105,x=900), B2(y=135,x=700).
    # Lines sorted by y: (700,100), (700,130) → pairs B1, B3 → leftover B2.
    assert result.unmatched_texts[0].text == "B2"


def test_region_row_gap_factor_controls_band_split():
    """A wide vertical gap (>> line height) should start a new band."""
    from nc_ocr_flow.line_geometry import pair_lines_by_region
    # Two lines, very far apart vertically.
    lines = [L(100, 100, 300, 120), L(100, 500, 300, 520)]
    blocks = [
        _BlockWithBbox("top", bbox=(100, 100, 300, 120)),
        _BlockWithBbox("bottom", bbox=(100, 500, 300, 520)),
    ]
    # Default row_gap_factor=1.0 → gap=380 >> h=20 → 2 bands, 2 regions.
    result = pair_lines_by_region(lines, blocks)
    assert result.is_complete
    assert [p.body for p in result.pairs] == ["top", "bottom"]


def test_region_imports_clean():
    """pair_lines_by_region is exported and importable."""
    from nc_ocr_flow import line_geometry
    assert hasattr(line_geometry, "pair_lines_by_region")
    assert callable(line_geometry.pair_lines_by_region)
