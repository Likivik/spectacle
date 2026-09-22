"""Pure pairing: line geometry from Surya /detect ↔ text from any source.

This is the integration seam between two independent OCR paths:

  * Surya /detect   → line polygons (geometry + reading order)
  * M3 / Gemini     → block text (no geometry)

The caller runs both on the same page image and pairs them by reading
order. This module is **pure** — no network, no PDF, no file I/O. It
takes already-deserialized dataclasses and returns paired records.

Pairing algorithms (deterministic, documented, pure):

``pair_lines_by_reading_order`` — single-column / paragraph flow:
  1. Group lines into rows by y0 proximity (overlap heuristic).
  2. Sort each row by x0 (left-to-right within row).
  3. Flatten the rows top-to-bottom → ordered list of line indices.
  4. ``text_blocks[i]`` is paired with the i-th line in that order.

If counts mismatch, the shorter side wins; the rest is reported in
``unmatched_lines`` / ``unmatched_texts``.

``pair_lines_by_region`` — multi-column / multi-region documents
(e.g. card catalogs where independent text blocks are interleaved
vertically across columns on the same page):
  1. Cluster lines into **row bands** by y-gap (large gap → new band).
  2. Within each row band, cluster into **column clusters** by x-gap.
  3. Each ``(row_band, column)`` is one independent region.
  4. Sort regions top-to-bottom then left-to-right.
  5. Assign each text block to its region by spatial containment
     (bbox overlap → nearest centroid → first region as fallback).
  6. Within each region, pair in reading order. Mismatched counts
     are confined to the region — they do NOT leak across regions.

This is deliberately NOT routed into ``ocr.process_pdf`` yet — wiring
into the pipeline (deciding which pages get this hybrid treatment vs.
tesseract-only vs. /ocr fallback) is a separate change. Keeping this
module pure means it's testable in isolation and can be reused by the
webhook or CLI paths independently.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, TypeVar


class _HasBbox(Protocol):
    """Structural type for any detection-line-like record."""
    bbox: tuple[float, float, float, float]


L = TypeVar("L", bound=_HasBbox)


@dataclass(frozen=True)
class TextBlock:
    """Plain text from any source (M3, Gemini, tesseract, manual…)."""
    text: str
    label: str = ""  # optional: "Text", "SectionHeader", etc.


@dataclass(frozen=True)
class LineTextPair:
    """One paired line: Surya geometry + matched text."""
    line: _HasBbox
    block: TextBlock

    @property
    def bbox(self):
        return self.line.bbox

    @property
    def polygon(self):
        return getattr(self.line, "polygon", None)

    @property
    def confidence(self):
        return getattr(self.line, "confidence", None)

    @property
    def body(self) -> str:
        return self.block.text

    @property
    def label(self) -> str:
        return self.block.label


@dataclass
class PairingResult:
    pairs: list[LineTextPair] = field(default_factory=list)
    unmatched_lines: list = field(default_factory=list)
    unmatched_texts: list[TextBlock] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return not self.unmatched_lines and not self.unmatched_texts


def _bbox_height(line: _HasBbox) -> float:
    _, y0, _, y1 = line.bbox
    return max(1.0, y1 - y0)


def _line_y0(line: _HasBbox) -> float:
    return line.bbox[1]


def _line_x0(line: _HasBbox) -> float:
    return line.bbox[0]


def _group_rows(lines: Sequence[L], row_tolerance_factor: float = 0.5) -> list[list[L]]:
    """Group lines into rows by vertical proximity.

    ``row_tolerance_factor`` is the fraction of a line's height used as
    the maximum vertical gap within a row. A new row starts when the
    gap to the previous line exceeds that tolerance.
    """
    if not lines:
        return []
    ordered = list(sorted(lines, key=_line_y0))
    rows: list[list[L]] = []
    current: list[L] = [ordered[0]]
    for prev, cur in zip(ordered, ordered[1:]):
        gap = _line_y0(cur) - (_line_y0(prev) + _bbox_height(prev))
        tol = _bbox_height(prev) * row_tolerance_factor
        if gap > tol:
            rows.append(current)
            current = [cur]
        else:
            current.append(cur)
    rows.append(current)
    return rows


def _reading_order(lines: Sequence[L], row_tolerance_factor: float = 0.5) -> list[L]:
    """Top-to-bottom, left-to-right within each row."""
    rows = _group_rows(lines, row_tolerance_factor=row_tolerance_factor)
    ordered: list[L] = []
    for row in rows:
        ordered.extend(sorted(row, key=_line_x0))
    return ordered


def pair_lines_by_reading_order(
    lines: Sequence[L],
    text_blocks: Sequence[TextBlock],
    row_tolerance_factor: float = 0.5,
) -> PairingResult:
    """Pair each text block with one line in reading order.

    Pure function. ``lines`` may be any objects exposing ``.bbox`` —
    typically ``DetectionLine`` from surya_client. ``text_blocks`` is
    the text in the same reading order the source emitted them.

    Args:
        lines: line records with ``.bbox`` (axis-aligned x0,y0,x1,y1).
        text_blocks: text strings in reading order.
        row_tolerance_factor: how aggressively to merge nearby lines
            into the same row. 0.5 = two lines belong to the same row
            iff their y-gaps are ≤ half the previous line's height.

    Returns:
        PairingResult with ``pairs`` (parallel lists), plus
        ``unmatched_lines`` / ``unmatched_texts`` if lengths differ.
    """
    ordered = _reading_order(lines, row_tolerance_factor=row_tolerance_factor)
    n_pairs = min(len(ordered), len(text_blocks))
    pairs = [
        LineTextPair(line=ordered[i], block=text_blocks[i])
        for i in range(n_pairs)
    ]
    return PairingResult(
        pairs=pairs,
        unmatched_lines=list(ordered[n_pairs:]),
        unmatched_texts=list(text_blocks[n_pairs:]),
    )


# --- Region-aware pairing ----------------------------------------------------
#
# Multi-column / multi-region documents (e.g. card catalogs) interleave
# independent text blocks across columns on the same page. A global
# top-to-bottom sort will silently mix flavor text from card A with the
# mechanics of card B. Pairing must respect the document's spatial
# layout: cluster lines into independent regions first, then pair
# M3/Gemini text blocks within their respective region.
#
# This is intentionally separate from ``pair_lines_by_reading_order`` —
# the single-column path is correct and well-tested for paragraphs, so
# it is preserved unchanged. The new function is opt-in.
# ---------------------------------------------------------------------------


class _HasBboxAndText(Protocol):
    """Structural type for ``TextBlock``-like records with optional bbox.

    Used by the region-aware pairing: text blocks whose source emits
    geometry (e.g. M3 with bbox) can be clustered spatially; text blocks
    without geometry (e.g. flat Gemini output) fall back to nearest-
    centroid assignment. ``pair_lines_by_region`` accepts either kind.
    """
    text: str
    label: str
    bbox: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class _Region:
    """One independent text region on a page.

    A region is defined by its member lines. The region's spatial
    extent (bounding box of member lines) is used to assign text
    blocks that lack geometry (e.g. plain ``TextBlock``).
    """
    lines: tuple = ()
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0


def _median(values: Sequence[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(s[n // 2])
    return (s[n // 2 - 1] + s[n // 2]) / 2.0


def _cluster_row_bands(
    lines: Sequence[L],
    row_gap_factor: float = 1.0,
) -> list[list[L]]:
    """Group lines into **row bands** by vertical-gap clustering.

    A new band starts when the vertical gap between consecutive lines
    (sorted by y0) exceeds ``row_gap_factor × median_line_height``.
    A larger factor merges more aggressive gaps into the same band; a
    smaller factor splits finer. Default ``1.0`` means a gap > one
    line-height worth of whitespace starts a new band.

    Unlike ``_group_rows`` (which only merges by overlap, used for
    single-column flow), this is meant to split bands at the white
    space between distinct rows of cards.
    """
    if not lines:
        return []
    ordered = sorted(lines, key=_line_y0)
    heights = [_bbox_height(ln) for ln in ordered]
    median_h = _median(heights)
    threshold = max(1.0, median_h * row_gap_factor)

    bands: list[list[L]] = [[ordered[0]]]
    for prev, cur in zip(ordered, ordered[1:]):
        gap = _line_y0(cur) - (_line_y0(prev) + _bbox_height(prev))
        if gap > threshold:
            bands.append([cur])
        else:
            bands[-1].append(cur)
    return bands


def _cluster_columns(
    band: Sequence[L],
    col_gap_factor: float = 0.5,
) -> list[list[L]]:
    """Cluster a row band's lines into **columns** by x-gap.

    A new column starts when the horizontal gap between consecutive
    lines (sorted by x0) exceeds ``col_gap_factor × median_line_width``.
    Default ``0.5`` means a gap > half a typical line-width starts a
    new column.
    """
    if not band:
        return []
    if len(band) == 1:
        return [list(band)]
    ordered = sorted(band, key=_line_x0)
    widths = [max(1.0, ln.bbox[2] - ln.bbox[0]) for ln in ordered]
    median_w = _median(widths)
    threshold = max(1.0, median_w * col_gap_factor)

    cols: list[list[L]] = [[ordered[0]]]
    for prev, cur in zip(ordered, ordered[1:]):
        gap = _line_x0(cur) - prev.bbox[2]
        if gap > threshold:
            cols.append([cur])
        else:
            cols[-1].append(cur)
    return cols


def _bbox_overlap(a: tuple[float, float, float, float],
                  b: tuple[float, float, float, float]) -> float:
    """Intersection area of two axis-aligned bboxes (>=0)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ox0 = max(ax0, bx0)
    oy0 = max(ay0, by0)
    ox1 = min(ax1, bx1)
    oy1 = min(ay1, by1)
    if ox1 <= ox0 or oy1 <= oy0:
        return 0.0
    return (ox1 - ox0) * (oy1 - oy0)


def _assign_text_to_region(
    text_bbox: tuple[float, float, float, float] | None,
    regions: Sequence[_Region],
) -> int:
    """Pick the best region for a text block.

    Strategy: prefer the region whose bbox overlaps the text bbox
    most (intersection area). Fall back to nearest centroid by
    Euclidean distance. Final fallback: region 0.
    """
    if not regions:
        return 0
    if text_bbox is None:
        return 0

    # Pick region with maximum bbox overlap; tie-break by centroid distance.
    best_idx = 0
    best_overlap = -1.0
    for i, r in enumerate(regions):
        ov = _bbox_overlap(text_bbox, (r.x0, r.y0, r.x1, r.y1))
        if ov > best_overlap:
            best_overlap = ov
            best_idx = i
    if best_overlap > 0:
        return best_idx

    # No overlap: nearest centroid.
    cx = (text_bbox[0] + text_bbox[2]) / 2.0
    cy = (text_bbox[1] + text_bbox[3]) / 2.0
    best_idx = 0
    best_d2 = float("inf")
    for i, r in enumerate(regions):
        d2 = (r.cx - cx) ** 2 + (r.cy - cy) ** 2
        if d2 < best_d2:
            best_d2 = d2
            best_idx = i
    return best_idx


def _region_from_lines(rs: Sequence[L]) -> _Region:
    """Build a region from its member lines (bounding box of bboxes)."""
    if not rs:
        return _Region()
    x0 = min(ln.bbox[0] for ln in rs)
    y0 = min(ln.bbox[1] for ln in rs)
    x1 = max(ln.bbox[2] for ln in rs)
    y1 = max(ln.bbox[3] for ln in rs)
    return _Region(lines=tuple(rs), x0=x0, y0=y0, x1=x1, y1=y1)


def _block_bbox(block) -> tuple[float, float, float, float] | None:
    """Return a text block's bbox if it has one, else None.

    M3 output provides bbox; plain ``TextBlock`` does not.
    """
    bb = getattr(block, "bbox", None)
    if bb is None:
        return None
    try:
        x0, y0, x1, y1 = bb
        return (float(x0), float(y0), float(x1), float(y1))
    except (TypeError, ValueError):
        return None


def pair_lines_by_region(
    lines: Sequence[L],
    text_blocks,
    row_gap_factor: float = 1.0,
    col_gap_factor: float = 0.5,
) -> PairingResult:
    """Pair line geometry with text blocks across independent regions.

    Use this for documents where independent text blocks are spatially
    interleaved on the page (multi-column layouts, card catalogs,
    side-by-side summary boxes). The global y/x reading-order sort in
    :func:`pair_lines_by_reading_order` will silently merge these.

    Algorithm (deterministic, see module docstring):

      1. Cluster ``lines`` into row bands (large y-gaps split).
      2. Within each row band, cluster into columns (large x-gaps split).
      3. Each ``(row_band, column)`` is one region. Sort regions
         top-to-bottom then left-to-right.
      4. Assign each text block to **exactly one** region (overlap →
         centroid fallback). Text blocks without bbox go to the region
         whose centroid is closest.
      5. Within each region, sort lines top-to-bottom, sort text blocks
         top-to-bottom, pair index-by-index. Mismatched counts are
         confined to the region — they do NOT leak across regions.

    Pure function. ``lines`` may be any objects with ``.bbox``.
    ``text_blocks`` may be plain ``TextBlock`` (no bbox, will be
    assigned by centroid) or objects exposing ``.bbox`` (preferred,
    assigned by overlap).

    Args:
        lines: line records with ``.bbox`` (axis-aligned x0,y0,x1,y1).
        text_blocks: any iterable of ``TextBlock``-compatible records.
        row_gap_factor: gap > this × median line-height starts new band.
        col_gap_factor: gap > this × median line-width starts new column.

    Returns:
        ``PairingResult`` aggregating pairs across all regions.
        ``unmatched_lines`` / ``unmatched_texts`` contain leftovers
        per-region.
    """
    if not lines:
        return PairingResult(
            pairs=[],
            unmatched_lines=[],
            unmatched_texts=list(text_blocks),
        )

    bands = _cluster_row_bands(lines, row_gap_factor=row_gap_factor)
    regions: list[_Region] = []
    for band in bands:
        for col in _cluster_columns(band, col_gap_factor=col_gap_factor):
            regions.append(_region_from_lines(col))
    # Sort regions top-to-bottom, then left-to-right.
    regions.sort(key=lambda r: (r.y0, r.x0))

    # Step 1: assign every text block to exactly one region. Done
    # up-front so a text block never gets paired twice (once per region).
    blocks_by_region: list[list] = [[] for _ in regions]
    orphans: list = []  # text blocks that matched no region (defensive)

    # For bbox-less blocks we have no spatial signal — distribute
    # them deterministically across regions in input order so the
    # user's reading-order sequence is preserved (left col, then
    # right col, etc.). Round-robin within a single pass.
    bboxless_buf: list = []
    for b in list(text_blocks):
        bb = _block_bbox(b)
        if regions and bb is not None:
            best_idx, best_overlap = 0, -1.0
            for i, r in enumerate(regions):
                ov = _bbox_overlap(bb, (r.x0, r.y0, r.x1, r.y1))
                if ov > best_overlap:
                    best_overlap = ov
                    best_idx = i
            if best_overlap > 0:
                blocks_by_region[best_idx].append(b)
                continue
            # No overlap: fall back to nearest centroid.
            cx = (bb[0] + bb[2]) / 2.0
            cy = (bb[1] + bb[3]) / 2.0
            best_idx, best_d2 = 0, float("inf")
            for i, r in enumerate(regions):
                d2 = (r.cx - cx) ** 2 + (r.cy - cy) ** 2
                if d2 < best_d2:
                    best_d2 = d2
                    best_idx = i
            blocks_by_region[best_idx].append(b)
        elif regions:
            # Defer distribution until we know how many bbox-less blocks
            # there are in total — round-robin across regions below.
            bboxless_buf.append(b)
        else:
            orphans.append(b)

    if bboxless_buf and regions:
        # No spatial signal on bbox-less blocks. Distribute by input
        # order, with each region's quota proportional to its line
        # count. This preserves the user's intended reading order
        # (left col, then right col, etc.) when blocks arrive sorted.
        total_lines = sum(len(r.lines) for r in regions)
        if total_lines == 0:
            # degenerate; just round-robin
            for i, b in enumerate(bboxless_buf):
                blocks_by_region[i % len(regions)].append(b)
        else:
            # Compute per-region quotas (proportional to line count),
            # then walk bbox-less blocks in order, filling each region
            # up to its quota before moving to the next.
            quotas = [max(1, round(len(r.lines) * len(bboxless_buf) / total_lines))
                      for r in regions]
            # Adjust last quota so the sum equals len(bboxless_buf).
            diff = len(bboxless_buf) - sum(quotas)
            quotas[-1] = max(1, quotas[-1] + diff)
            qi = 0
            filled = 0
            for b in bboxless_buf:
                while qi < len(regions) and filled >= quotas[qi]:
                    qi += 1
                    filled = 0
                if qi >= len(regions):
                    qi = len(regions) - 1  # overflow → last region
                blocks_by_region[qi].append(b)
                filled += 1

    # Step 2: pair within each region, in reading order.
    pairs: list[LineTextPair] = []
    unmatched_lines: list = []
    unmatched_texts = list(orphans)

    for region_idx, region in enumerate(regions):
        region_lines = sorted(region.lines, key=lambda ln: (ln.bbox[1], ln.bbox[0]))
        region_blocks = sorted(
            blocks_by_region[region_idx],
            key=lambda b: (
                (_block_bbox(b)[1], _block_bbox(b)[0])
                if _block_bbox(b) is not None
                else (region.y0, region.x0)
            ),
        )
        n = min(len(region_lines), len(region_blocks))
        for i in range(n):
            pairs.append(LineTextPair(line=region_lines[i], block=region_blocks[i]))
        if len(region_lines) > n:
            unmatched_lines.extend(region_lines[n:])
        if len(region_blocks) > n:
            unmatched_texts.extend(region_blocks[n:])

    return PairingResult(
        pairs=pairs,
        unmatched_lines=unmatched_lines,
        unmatched_texts=unmatched_texts,
    )


__all__ = [
    "TextBlock",
    "LineTextPair",
    "PairingResult",
    "pair_lines_by_reading_order",
    "pair_lines_by_region",
]
