"""Per-page orientation correction for the nc-ocr-flow OCR pipeline.

The problem this module solves
==============================

Scanned PDFs have a nasty interaction between (a) the PDF's own
``/Rotate`` flag on a page and (b) the raster that is *embedded inside*
the page. A document scanned in landscape orientation may have a PDF
``/Rotate`` of 0 (the scanner embedded a JPEG of the page already
rotated 90° relative to "natural reading order"); in that case the
text in the raster is sideways, but PyMuPDF's ``page.rotation`` is 0
and the page appears as a portrait object on disk.

The fix has two halves:

  1. **Detect** the rotation (0 / 90 / 180 / 270 degrees clockwise
     from upright) of the raster. This module's primary detector is
     Tesseract's OSD (``--psm 0 -l osd``) which is engine-independent,
     fast, and reliable for pages with enough text. For pages with very
     little extractable text Tesseract prints "Too few characters" —
     we fall back to "no rotation detected" (safe: leave the page
     alone rather than mangle readable content).

  2. **Apply** the rotation to the rendered PNG that gets fed to
     downstream OCR engines, and to the bboxes the engine returns.

The detectors
------------

There are two public detectors:

  * :func:`detect_orientation_tesseract` — Tesseract OSD on raw PNG
    bytes. Engine-independent, no network.
  * :func:`detect_orientation_from_word_bboxes` — heuristic that
    inspects the aspect ratio of detected word bounding boxes. Used
    for engines that already produce a per-word JSON (currently:
    Google Vision's per-page word list). Returns ``None`` on sparse pages
    so callers can fall back to Tesseract OSD.

The applier
----------

Three public functions:

  * :func:`rotate_png` — physically rotate a PNG by an integer
    multiple of 90° (PIL). Cheap.
  * :func:`rotate_bbox` — transform an ``(x0, y0, x1, y1)`` rectangle
    in source-pixel coordinates to destination-pixel coordinates
    after rotating the source ``angle`` degrees CCW.
  * :func:`preorient_pdf` — read a PDF, render each page, detect the
    rotation, physically rotate the raster, and write a new PDF with
    each page rebuilt from the rotated raster (with ``/Rotate = 0``).

Why preorient the whole PDF and not just pages?
------------------------------------------------

Because every engine in this codebase can consume a PDF:

  * Google Vision needs a PDF for whole-document OCR (GCS upload).
  * Tesseract/ocrmypdf needs a PDF.
  * MiniMax renders the PDF page-by-page with PyMuPDF.

Producing a single upright-on-disk PDF before the engine runs keeps
the engines simple and ensures they all see the same upright content
without each having to repeat the same OSD pass.

Pitfalls (verified from PyMuPDF 1.24+ docs and Tesseract 5.x docs):

  * ``page.set_rotation()`` changes the page's ``/Rotate`` flag but
    does **not** re-rasterize the embedded image. It is useless when
    the raster itself is sideways and the flag is already 0.
  * PyMuPDF's ``page.rect`` and insertion coordinates are always in
    *unrotated* page space, so changing the rotation flag later does
    not change bbox meaning in the text layer.
  * Tesseract's OSD ``Orientation in degrees`` field reports how far
    the input image is rotated clockwise from its natural orientation
    (so 0 = upright; 90 = 90° CW from upright; 270 = 90° CCW from
    upright). The companion ``Rotate`` field is the inverse — the
    CW rotation the caller must apply to recover the natural
    orientation. Our :attr:`Orientation.ccw_degrees` is the
    counter-clockwise rotation that *undoes* the OSD-reported angle.
  * OSD confidence is unreliable on low-character scans (often returns
    values in the 0.0–1.0 range). We accept any non-zero confidence
    because the alternative — leaving a sideways scan unchanged —
    is strictly worse than a possibly-wrong rotation that the engine
    can still partly read.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

log = logging.getLogger(__name__)


# --- Constants ---------------------------------------------------------------

#: Confidence below which we trust the OSD result. Tesseract OSD
#: returns a float confidence; very low values (or "Too few
#: characters" emitted to stderr) mean the page had too little text
#: for OSD — in that case we default to 0 (no rotation) rather than
#: risk rotating a low-confidence guess onto a readable page.
#:
#: Empirically, real-world scanned documents frequently return OSD
#: confidence in the 0.1–1.0 range (the OCR engine is genuinely
#: uncertain because the raster is fuzzy), and 0.0–0.1 for very poor
#: quality scans. We therefore accept any *non-zero* confidence:
#: even a tiny confidence value means Tesseract committed to a
#: specific {0,90,180,270} angle, which is what we want — false
#: positives on the angle value are caught by the orchestrator
#: (the engine will simply return low-quality OCR for a misrotated
#: page, which is no worse than today).
MIN_OSD_CONFIDENCE = 0.0

#: Threshold below which a word-bbox aspect heuristic we ignore
#: (close to square — could be either orientation). The threshold
#: was chosen empirically: printed-text words are typically ~2-3x
#: wider than they are tall when upright, or ~2-3x taller when
#: rotated 90°.
WORD_BBOX_ASPECT_THRESHOLD = 1.4


# --- Data class ------------------------------------------------------------


# --- Resolution-preserving raster policy ----------------------------------
#
# Scanned PDFs come in a wide range of embedded raster dpi: 75 dpi
# fax-style scans, 150–200 dpi office scans, 300–600 dpi archive
# scans. The previous preorient pass always rasterized and re-encoded
# every page at a single fixed DPI (200). That has two problems:
#
#   1. A 75-dpi source was upscaled to 200 dpi before being
#      re-embedded — bigger file, no new detail, "fake sharpness".
#   2. A 600-dpi source was downscaled to 200 dpi before being
#      re-embedded — lossy, fine text became mushy.
#
# Both cases also re-encoded every page (JPEG ⇢ PNG inside
# ``pix.tobytes("png")`` + ``page.insert_image(stream=...)``), which
# is wasteful when the page needs no rotation at all.
#
# The fix is a per-page resolution-preserving raster policy:
#
#   - Compute the *effective dpi* of each page from its embedded
#     image(s). ``dpi_x = image_px_width / (page.rect.width/72)``,
#     same for y; take the max over images on the page; clamp to
#     a sane 30..2400 range. If the page has no images, fall back
#     to the cap.
#   - Render the rebuilt page at ``min(source_dpi, cap)`` so a
#     75-dpi page stays 75 dpi and a 600-dpi page is capped at the
#     configured ceiling. The cap comes from the new env var
#     ``NC_OCR_ORIENTATION_MAX_DPI`` (default 300).
#   - Skip the rebuild entirely when no rotation is needed: the
#     original page is ``insert_pdf``-copied into the output so the
#     embedded image bytes are preserved (no upscaling, no
#     re-encoding, byte-identical pixels). When a rebuild *is*
#     needed, embed the rotated raster as a JPEG at the quality
#     set by ``NC_OCR_ORIENTATION_JPEG_Q`` (default 80).
#
# Backwards compatibility: the existing ``render_dpi`` keyword
# argument is now treated as the ceiling (cap) rather than a fixed
# render DPI. Existing callers that pass ``render_dpi=200`` get
# the same ceiling as before by default.

#: Lower bound for a sane source dpi estimate. Below this we trust
#: the cap (the page is too undersampled to be authoritative).
_MIN_SOURCE_DPI: int = 30
#: Upper bound for a sane source dpi estimate. Above this we
#: treat the embedded image as "very high res" but still clamp
#: to this number so the math doesn't blow up.
_MAX_SOURCE_DPI: int = 2400
#: Default ceiling for the rendered raster dpi when the source
#: doesn't constrain it. Overridable via the
#: ``NC_OCR_ORIENTATION_MAX_DPI`` env var.
_DEFAULT_MAX_DPI: int = 300
#: Default JPEG quality for re-embedded rotated rasters.
#: Overridable via the ``NC_OCR_ORIENTATION_JPEG_Q`` env var.
_DEFAULT_JPEG_QUALITY: int = 80


def _resolve_max_dpi(render_dpi: int) -> int:
    """Return the render-dpi cap.

    Priority:

      1. ``NC_OCR_ORIENTATION_MAX_DPI`` env var, if set to an int
         in a sane range.
      2. The ``render_dpi`` keyword argument (treated as the cap,
         not a fixed dpi — see the module docstring).
      3. :data:`_DEFAULT_MAX_DPI` (300).
    """
    import os as _os
    raw = _os.environ.get("NC_OCR_ORIENTATION_MAX_DPI", "").strip()
    if raw:
        try:
            val = int(raw)
        except ValueError:
            val = render_dpi if render_dpi else _DEFAULT_MAX_DPI
        else:
            return val
    return render_dpi if render_dpi else _DEFAULT_MAX_DPI


def _resolve_jpeg_quality() -> int:
    """Return the JPEG quality to use when re-embedding rotated pages.

    Priority: ``NC_OCR_ORIENTATION_JPEG_Q`` env var, falling back to
    :data:`_DEFAULT_JPEG_QUALITY`.
    """
    import os as _os
    raw = _os.environ.get("NC_OCR_ORIENTATION_JPEG_Q", "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            return _DEFAULT_JPEG_QUALITY
    return _DEFAULT_JPEG_QUALITY


def _compute_source_dpi(page, cap_dpi: int) -> int:
    """Compute the *effective dpi* of an embedded raster on a page.

    Walks ``page.get_images(full=True)`` and for each image
    computes::

        dpi_x = image_px_width  * 72.0 / page.rect.width
        dpi_y = image_px_height * 72.0 / page.rect.height

    Returns the dpi of the image that covers the largest area of the
    page, clamped to ``[_MIN_SOURCE_DPI, _MAX_SOURCE_DPI]``. Ranking by
    area (not by maximum dpi) keeps a small high-resolution logo or
    stamp from raising the render dpi and upscaling the actual scan.
    If the page has no images, falls back to ``cap_dpi`` (the rendered
    raster at the cap is the honest answer: we don't know what
    dpi the "blank" page is).
    """
    try:
        images = page.get_images(full=True)
    except Exception as exc:  # noqa: BLE001
        log.debug("_compute_source_dpi: get_images failed (%s); "
                  "falling back to cap=%d", exc, cap_dpi)
        return cap_dpi
    if not images:
        return cap_dpi
    pw = float(page.rect.width) or 1.0
    ph = float(page.rect.height) or 1.0
    best_area = -1.0
    best_dpi = 0.0
    for info in images:
        # get_images(full=True) returns a tuple:
        #   (xref, smask, width, height, bpc, colorspace, xres, yres,
        #    name, filter, referencer, ...)
        # Positions 0/2/3 are the xref and the pixel width/height.
        try:
            xref, w, h = info[0], info[2], info[3]
        except (IndexError, TypeError):
            continue
        try:
            xref = int(xref)
            w = int(w)
            h = int(h)
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue

        # Rank images by the page area they actually occupy, and take
        # the dpi of the *dominant* one. Using the maximum dpi instead
        # would let a small high-resolution logo or stamp sitting next
        # to a low-resolution scan drag the render dpi up and upscale
        # the scan — exactly what this policy exists to prevent.
        placed = None
        try:
            rects = page.get_image_rects(xref)
        except Exception:  # noqa: BLE001
            rects = []
        for rect in rects:
            try:
                area = abs(float(rect.width) * float(rect.height))
            except (TypeError, ValueError):
                continue
            if placed is None or area > placed[0]:
                placed = (area, rect)
        if placed is not None and float(placed[1].width) > 0:
            dpi = w * 72.0 / float(placed[1].width)
            area = placed[0]
        else:
            # Placement unknown: rank by pixel area and measure the
            # dpi against the page box.
            dpi = max(w * 72.0 / pw, h * 72.0 / ph)
            area = float(w) * float(h)
        if area > best_area:
            best_area = area
            best_dpi = dpi
    if best_dpi <= 0:
        return cap_dpi
    # Clamp to a sane range. The floor protects against pathological
    # "1-pixel-wide image stretched across an A4 page" answers that
    # come out around 0.05 dpi.
    best_dpi = max(_MIN_SOURCE_DPI,
                   min(int(round(best_dpi)), _MAX_SOURCE_DPI))
    return best_dpi


@dataclass(frozen=True)
class Orientation:
    """Detected page orientation.

    Attributes:
        angle: Degrees clockwise from upright. One of {0, 90, 180,
            270}. 0 means "already upright, no rotation needed".
        confidence: Detector-reported confidence. Higher = more
            trustworthy. ``None`` when the detector has no
            confidence channel (e.g. the word-bbox heuristic).
        source: Name of the detector that produced this result
            (``"tesseract-osd"``, ``"word-bbox"``, ``"default"``).
            Useful for telemetry / debugging.
    """
    angle: int  # 0, 90, 180, 270
    confidence: Optional[float]
    source: str

    @property
    def is_upright(self) -> bool:
        """True if no correction is required."""
        return self.angle % 360 == 0

    @property
    def ccw_degrees(self) -> int:
        """How many degrees to rotate the page counter-clockwise to
        bring it upright.

        Tesseract's ``Orientation in degrees`` reports CW-from-upright
        (0 = upright, 90 = 90° CW, 180 = upside-down, 270 = 90° CCW).
        To undo a CW rotation of N degrees we rotate CCW by N degrees,
        so ``ccw_degrees`` equals ``angle`` directly.
        """
        return self.angle % 360


# --- Tesseract OSD detector ------------------------------------------------


_OSD_ORIENTATION_RE = re.compile(
    r"^\s*Orientation\s+in\s+degrees:\s*(\d+)\s*$",
    re.MULTILINE,
)
_OSD_CONFIDENCE_RE = re.compile(
    r"^\s*Orientation\s+confidence:\s*([0-9.+-]+(?:[eE][0-9.+-]+)?)\s*$",
    re.MULTILINE,
)
_TOO_FEW_CHARS_RE = re.compile(r"Too few characters", re.IGNORECASE)


def parse_osd_output(osd_text: str) -> Optional[Orientation]:
    """Parse ``tesseract --psm 0 -l osd`` output.

    Returns ``None`` when:

      * Tesseract printed ``"Too few characters"`` (the page had
        less than ``min_characters_to_try`` characters; the OSD
        model cannot reliably detect orientation in that case).
      * No ``Orientation in degrees`` line was found.
      * The angle is not one of {0, 90, 180, 270} or the confidence
        is below :data:`MIN_OSD_CONFIDENCE`.
    """
    if _TOO_FEW_CHARS_RE.search(osd_text):
        return None
    m = _OSD_ORIENTATION_RE.search(osd_text)
    if not m:
        # Tesseract emits the values in this order:
        #   Page number / Orientation in degrees / Rotate /
        #   Orientation confidence / Script / Script confidence.
        # If none of those lines is present the result is unusable.
        return None
    angle = int(m.group(1))
    if angle not in (0, 90, 180, 270):
        return None
    cm = _OSD_CONFIDENCE_RE.search(osd_text)
    try:
        conf = float(cm.group(1)) if cm else None
    except ValueError:
        conf = None
    if conf is not None and conf < MIN_OSD_CONFIDENCE:
        return None
    return Orientation(angle=angle, confidence=conf, source="tesseract-osd")


def detect_orientation_tesseract(png_bytes: bytes,
                                 timeout_s: int = 30,
                                 binary: str = "tesseract") -> Optional[Orientation]:
    """Run ``tesseract --psm 0 -l osd`` on raw PNG bytes.

    Returns an :class:`Orientation` or ``None`` when the detector
    refused (sparse pages, missing binary, timeout).

    The detector needs the ``osd`` language file. We check for it
    in the same Tesseract data dir tesseract uses; if absent we
    fall through to ``None`` rather than crash — the calling layer
    treats ``None`` as "don't rotate, page might be borderline".
    """
    tess = shutil.which(binary)
    if not tess:
        log.debug("orientation: tesseract binary not found")
        return None

    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        in_png = td_p / "in.png"
        out_base = td_p / "out"
        in_png.write_bytes(png_bytes)
        try:
            proc = subprocess.run(
                [tess, str(in_png), str(out_base),
                 "--psm", "0", "-l", "osd"],
                check=False,
                capture_output=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            log.warning("orientation: tesseract OSD timed out after %ds",
                        timeout_s)
            return None
        # tesseract writes stdout OSD to <base>.osd in modern builds.
        osd_path = out_base.with_suffix(".osd")
        text: str
        if osd_path.exists():
            text = osd_path.read_text(errors="replace")
        else:
            # Older tesseract or "stdout" output: parse captured
            # stdout/stderr (whichever has the lines).
            text = (proc.stdout or b"") + (proc.stderr or b"")
            text = text.decode(errors="replace")
    return parse_osd_output(text)


# --- Word-bbox heuristic (Google Vision consumer) --------------------------


def detect_orientation_from_word_bboxes(
    word_bboxes: Iterable[tuple[float, float, float, float]],
) -> Optional[Orientation]:
    """Infer page orientation from per-word bounding boxes.

    Words are usually wider than they are tall when text is
    horizontal. When the whole page is rotated 90°, words appear
    taller than wide. We compute the median aspect ratio (width /
    height) of the supplied words; if it is well above 1 the page
    is upright (or 180° rotated — which we cannot distinguish from
    bbox aspect alone), if well below 1 the page is sideways (90°
    or 270°).

    Because 0° and 180° are indistinguishable from word shapes
    alone, and 90° vs 270° are also indistinguishable, this
    heuristic returns only "0 or 180" / "90 or 270". For the nc-ocr
    pipeline we accept the ambiguity: the per-page fallback to
    Tesseract OSD is authoritative when this heuristic returns a
    sideways verdict, and a 180° verdict is not produced by this
    function (we never rotate by 180° based solely on aspect).

    Returns ``None`` when no usable words are supplied.
    """
    aspects: list[float] = []
    for x0, y0, x1, y1 in word_bboxes:
        w = x1 - x0
        h = y1 - y0
        if w <= 0 or h <= 0:
            continue
        aspects.append(w / h)
    if not aspects:
        return None
    aspects.sort()
    # Median
    n = len(aspects)
    median = aspects[n // 2] if n % 2 else 0.5 * (aspects[n // 2 - 1] + aspects[n // 2])
    if median >= WORD_BBOX_ASPECT_THRESHOLD:
        # Words are wider than tall — page is horizontal (0° or 180°).
        # We never rotate 180° on this evidence alone: a stamp that
        # happens to be on the page should not corrupt upright scans.
        return Orientation(angle=0, confidence=None, source="word-bbox")
    if median <= 1.0 / WORD_BBOX_ASPECT_THRESHOLD:
        return Orientation(angle=90, confidence=None, source="word-bbox")
    return None


# --- Content-aspect fallback (engines with very sparse text) ---------------
#
# Tesseract OSD refuses to score orientation on pages with fewer than
# ``min_characters_to_try`` characters (default 50). For pages with
# only a stamp, a signature, or sparse metadata, OSD will fail and we
# would default to "no rotation" — which is wrong if the page is
# actually sideways. As a last-resort fallback, compute the bounding
# box of dark pixels and compare its aspect to the image aspect:
#
#   * Portrait image, landscape content → 90° / 270° rotation.
#   * Landscape image, portrait content → 90° / 270° rotation.
#   * Portrait image, portrait content  → likely no rotation.
#   * Landscape image, landscape content → likely no rotation.
#
# Returns ``None`` if no dark pixels are found or the bbox is
# suspiciously large/small to be content. The heuristic can confuse
# large margins with sideways pages so callers should treat its
# results as a *suggestion* and prefer Tesseract OSD whenever
# available.


def detect_orientation_from_content_bbox(
    png_bytes: bytes,
    *,
    dark_threshold: int = 200,
    min_content_fraction: float = 0.02,
) -> Optional[Orientation]:
    """Infer page rotation from the bbox of dark pixels in ``png_bytes``.

    Args:
        png_bytes: PNG bytes (typically the output of
            ``page.get_pixmap(dpi=200).tobytes("png")``).
        dark_threshold: Pixels with all RGB channels below this
            value are considered "dark content". Default 200
            (most scanners output near-black for ink).
        min_content_fraction: If dark pixels cover less than this
            fraction of the image area we return ``None`` — a
            near-blank page can't be classified by aspect.

    Notes:
        Aspect ratio alone distinguishes "0 vs 90" and "0 vs 180"
        but cannot tell 90 from 270. We always return 90 in the
        sideways case; the upside-down case is rare in real scans
        (most scanners save landscape pages sideways, not upside
        down).
    """
    import io
    from PIL import Image
    import numpy as np
    try:
        with Image.open(io.BytesIO(png_bytes)) as im:
            arr = np.asarray(im.convert("L"))
    except Exception:
        return None
    if arr.size == 0:
        return None
    h, w = arr.shape
    total = h * w
    # Boolean mask of "dark" pixels
    dark = arr < dark_threshold
    n_dark = int(dark.sum())
    if n_dark == 0 or n_dark / total < min_content_fraction:
        return None
    # Bounding box of dark pixels.
    rows = np.any(dark, axis=1)
    cols = np.any(dark, axis=0)
    if not rows.any() or not cols.any():
        return None
    r0, r1 = int(np.argmax(rows)), int(h - 1 - np.argmax(rows[::-1]))
    c0, c1 = int(np.argmax(cols)), int(w - 1 - np.argmax(cols[::-1]))
    content_w = c1 - c0 + 1
    content_h = r1 - r0 + 1
    if content_w <= 0 or content_h <= 0:
        return None
    # Image is portrait iff w < h.
    img_portrait = w < h
    content_portrait = content_w < content_h
    if img_portrait == content_portrait:
        return Orientation(angle=0, confidence=None, source="content-bbox")
    # Content is rotated 90° relative to page.
    return Orientation(angle=90, confidence=None, source="content-bbox")


# --- Two-stage detector ----------------------------------------------------

#: PP-LCNet decision rule: ALWAYS take the argmax; only fall
#: through to stage-2 when the *margin* (top-1 − top-2) is small.
#:
#: Why margin, not absolute confidence: PP-LCNet's softmax is
#: genuinely flat on whitespace-heavy / scanned Russian pages —
#: measured top-1 ≈ 0.45 with the other three classes splitting
#: ≈ 0.55 (verified empirically on real scans, 2026-10-10). An
#: absolute 0.80 gate would skip stage-1 on exactly the pages
#: where we need it and fall back to unreliable Tesseract OSD.
#:
#: On clean single-column text PP-LCNet returns top-1 ≈ 0.99
#: and margin ≈ 0.97 — orders of magnitude above this threshold.
#: On rotated scans of dense Cyrillic the margin is still ≈ 0.27
#: (0.45 − 0.18). We pick 0.15 as the fallback boundary: below
#: it the model is essentially a 4-way tie (e.g. a mostly-blank
#: page where every direction looks equally un-text-like), so
#: we run the 4-rotation OCR vote to break the tie.
DOC_ORI_MARGIN_THRESHOLD = 0.15

#: Tesseract word confidence (0..100) above which a recognised word
#: counts as "real text" for the stage-2 OCR vote. Measured on real
#: scans: upright pages yield dozens of words above this, wrongly
#: rotated pages yield zero to three.
STRONG_WORD_CONF = 70.0


def _vote_orientation_tesseract(
    png_bytes: bytes,
    *,
    languages: str = "rus+eng",
    binary: str = "tesseract",
    timeout_s: int = 30,
) -> Optional[Orientation]:
    """Stage-2 fallback: OCR the page at 0/90/180/270, pick the winner.

    For each candidate CCW rotation r ∈ {0,90,180,270}:

      * Apply ``rotate_png(png_bytes, r)`` to bring the image into
        the orientation where text would be upright *if the page is
        currently rotated -r from upright*.
      * Run ``tesseract`` on the upright candidate and compute a
        score from the output text length and average word
        confidence.
      * The rotation that produces the highest score is treated as
        the "upright" rotation — i.e. the CCW rotation we must
        apply to the *original* input to make it upright is the
        same r.

    Why this works: tesseract returns *much* more (and more
    confident) text when the text is upright than when it's
    sideways / upside down. The score curve is a strong signal
    even when OSD itself returns a wrong angle.

    Score: ``len(text) * (1 + mean_word_conf)`` where mean_word_conf
    is averaged across non-empty recognised tokens. This rewards
    both quantity ("more text found") and quality ("more confident
    recognition"). Ties broken by score, then by smaller |r|
    (preferring "no rotation" as a safer assumption).

    Returns ``None`` if all four rotations produced near-empty /
    zero-confidence output (the page is genuinely blank).
    """
    tess = shutil.which(binary)
    if not tess:
        log.debug("orientation: tesseract binary not found; "
                  "OCR-vote fallback unavailable")
        return None

    import tempfile
    candidates: list[tuple[int, float, str]] = []
    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        in_png = td_p / "in.png"
        out_base = td_p / "out"
        in_png.write_bytes(png_bytes)
        for angle_ccw in (0, 90, 180, 270):
            # rotate_png rotates the input by angle_ccw CCW.
            # To evaluate "if the page needs N° CW correction to
            # become upright", we feed tesseract a version rotated
            # N° CCW (= N° CCW from the original) — that's the
            # upright candidate. So our score for N maps back to
            # the verdict "apply N° CCW to original".
            rotated_for_eval = rotate_png(png_bytes, angle_ccw)
            eval_path = td_p / f"eval_{angle_ccw}.png"
            eval_path.write_bytes(rotated_for_eval)
            try:
                # tesseract stdout is the recognised text; TSV
                # gives per-word conf. We grab text + TSV in one
                # call by using -c options isn't portable; so
                # run twice but with a tight timeout.
                proc = subprocess.run(
                    [tess, str(eval_path), str(out_base),
                     "-l", languages],
                    check=False, capture_output=True, timeout=timeout_s,
                )
                text = (proc.stdout or b"").decode(errors="replace")
            except subprocess.TimeoutExpired:
                log.warning("orientation: tesseract timed out for "
                            "%d° candidate after %ds",
                            angle_ccw, timeout_s)
                continue
            # Confidence via TSV (run again with tsv output mode)
            word_confs: list[float] = []
            try:
                ts_proc = subprocess.run(
                    [tess, str(eval_path), str(out_base),
                     "-l", languages, "tsv"],
                    check=False, capture_output=True, timeout=timeout_s,
                )
                tsv_path = out_base.with_suffix(".tsv")
                if tsv_path.exists():
                    lines = tsv_path.read_text(errors="replace").splitlines()
                    for line in lines[1:]:
                        parts = line.split("\t")
                        if len(parts) >= 12 and parts[0] == "5":
                            try:
                                c = float(parts[11])
                                t = (parts[12] or "").strip()
                                if c >= 0 and t:
                                    word_confs.append(c)
                            except (ValueError, IndexError):
                                continue
                    tsv_path.unlink(missing_ok=True)
            except subprocess.TimeoutExpired:
                pass
            n_words = len(word_confs)
            strong = [c for c in word_confs if c >= STRONG_WORD_CONF]
            text_len = len(text.strip())
            # Score by the number of HIGH-CONFIDENCE words, not by
            # character count. A wrongly-oriented page makes
            # tesseract emit *more* characters (noise) but far fewer
            # confident words — measured on real scans: the upright
            # variant had 54 words at conf>=70 vs 0-3 for the other
            # three rotations, while raw char counts were flipped.
            # Summed confidence breaks ties between equally many
            # strong words.
            score = (len(strong) * 1000.0
                     + (sum(strong) / len(strong) if strong else 0.0))
            candidates.append((angle_ccw, score, text[:80]))

    if not candidates:
        return None
    # Winner by score, ties broken by smaller |r|
    candidates.sort(key=lambda c: (-c[1], c[0]))
    best_angle, best_score, snippet = candidates[0]
    if best_score <= 1.0:  # nothing matched
        return None
    log.debug("orientation: OCR-vote candidates=%s winner=%d "
              "(score=%.1f) snippet=%r",
              [(a, round(s, 1)) for a, s, _ in candidates],
              best_angle, best_score, snippet)
    return Orientation(
        angle=best_angle,
        confidence=None,           # vote has no calibrated probability
        source="ocr-vote",
    )


def detect_orientation(png_bytes: bytes,
                       *,
                       doc_ori_margin: float = DOC_ORI_MARGIN_THRESHOLD,
                       ) -> Orientation:
    """Best-effort orientation detector combining all stages in
    priority order:

      1. **Stage 1 — PP-LCNet_x1_0_doc_ori ONNX** (PaddleOCR). Fast
         (~3 ms / page on CPU) and returns a calibrated 4-way
         probability over {0°, 90°, 180°, 270°}. We ALWAYS take
         the argmax; stage-1 is only treated as "uncertain" when
         the margin (top-1 − top-2) is below
         :data:`DOC_ORI_MARGIN_THRESHOLD` (default 0.15), in which
         case stage 2 takes over.
      2. **Stage 2 — Local 4-rotation OCR vote** (tesseract). Run
         tesseract on the page rotated 0/90/180/270 CCW; pick the
         rotation that produces the most text × highest average
         word confidence. Used when stage 1 is uncertain,
         unavailable, or raises. No API calls.
      3. **Legacy Tesseract OSD** (a.k.a. ``--psm 0 -l osd``) for
         pages where the OCR vote also failed — same engine as
         stage-2 but a single-shot orientation-specific call that
         is sometimes more discriminating than the vote.
      4. **Content-bbox aspect-ratio** heuristic as last resort.

    Returns ``Orientation(0, None, "default")`` if every detector
    refused — safe default ("no rotation, leave the page alone").
    """
    # ---- Stage 1: PP-LCNet (always take argmax; margin-gated fallback) ----
    try:
        from . import doc_ori
        r = doc_ori.classify(png_bytes)
        if r is not None:
            ccw, conf, probs = r
            # Margin = top1 - top2.  PP-LCNet's softmax is flat on
            # whitespace-heavy scans, so absolute conf is unreliable
            # (≈ 0.45 even when the answer is correct); the *gap*
            # between top-1 and the next best is what tells us
            # whether the model actually committed to a verdict.
            sorted_probs = sorted(probs, reverse=True)
            margin = sorted_probs[0] - sorted_probs[1]
            if margin >= doc_ori_margin:
                return Orientation(angle=ccw, confidence=conf,
                                   source="pp-lcnet-doc-ori")
            # Margin too small: tied/uncertain.  Fall through to
            # the OCR vote.  Logged at debug so retraining work
            # can find these cases.
            log.debug("orientation: PP-LCNet small margin "
                      "(%.3f < %.3f, top1=%.3f); deferring to OCR vote",
                      margin, doc_ori_margin, conf)
        else:
            log.debug("orientation: PP-LCNet unavailable; trying OCR vote")
    except Exception as exc:
        log.warning("orientation: PP-LCNet raised (%s); trying OCR vote", exc)

    # ---- Stage 2: OCR vote (4 rotations, tesseract) --------------------
    vote = _vote_orientation_tesseract(png_bytes)
    if vote is not None:
        return vote

    # ---- Stage 3: legacy Tesseract OSD ---------------------------------
    tess = detect_orientation_tesseract(png_bytes)
    if tess is not None:
        return tess

    # ---- Stage 4: content bbox heuristic ------------------------------
    bbox = detect_orientation_from_content_bbox(png_bytes)
    if bbox is not None:
        return bbox

    return Orientation(angle=0, confidence=None, source="default")


# --- Image transforms ------------------------------------------------------


def rotate_png(png_bytes: bytes, angle_ccw: int) -> bytes:
    """Rotate PNG bytes by ``angle_ccw`` degrees counter-clockwise.

    Accepts integer multiples of 90° only. Non-multiples raise
    ``ValueError`` — for arbitrary angle correction the caller
    should use a deskewing path (e.g. ocrmypdf ``--deskew``),
    which is orthogonal to this module.

    Returns the PNG bytes of the rotated image. Output dimensions
    swap width/height for 90°/270° rotations.

    Implementation note: PIL.Image.rotate is CCW for positive
    angles and CW for negative angles (verified empirically with
    tesseract OSD round-trips on tesseract 5.5.3 + Pillow 12.x).
    """
    if angle_ccw % 360 == 0:
        return png_bytes
    if angle_ccw % 90 != 0:
        raise ValueError(
            f"rotate_png: only 90°-multiples supported, got {angle_ccw}"
        )
    from PIL import Image
    import io
    with Image.open(io.BytesIO(png_bytes)) as im:
        rotated = im.rotate(angle_ccw, expand=True)
        out = io.BytesIO()
        # Preserve the source mode.
        rotated.save(out, format="PNG")
    return out.getvalue()


def rotate_bbox(bbox: tuple[float, float, float, float],
                src_w: float, src_h: float,
                angle_ccw: int) -> tuple[float, float, float, float]:
    """Transform an axis-aligned bbox after rotating the image CCW.

    Given an axis-aligned bbox ``(x0, y0, x1, y1)`` in source-image
    pixel coordinates (image size ``src_w x src_h``), return the
    axis-aligned bbox in destination-image coordinates after the
    source image has been rotated ``angle_ccw`` degrees
    counter-clockwise.

    The math is exact for 0/90/180/270 rotations on axis-aligned
    bboxes (the rotated bbox is still axis-aligned because the
    input was).

    The destination dimensions ``dst_w x dst_h`` are implicit:

      * 0°   → dst = src
      * 90°  → dst = (src_h, src_w)
      * 180° → dst = src
      * 270° → dst = (src_h, src_w)
    """
    angle = angle_ccw % 360
    if angle == 0:
        return bbox
    x0, y0, x1, y1 = bbox
    if angle == 90:
        # (x, y) in src → (y, src_w - x) in dst.
        nx0 = y0
        ny0 = src_w - x1
        nx1 = y1
        ny1 = src_w - x0
        return (nx0, ny0, nx1, ny1)
    if angle == 180:
        nx0 = src_w - x1
        ny0 = src_h - y1
        nx1 = src_w - x0
        ny1 = src_h - y0
        return (nx0, ny0, nx1, ny1)
    if angle == 270:
        # (x, y) in src → (src_h - y, x) in dst.
        nx0 = src_h - y1
        ny0 = x0
        nx1 = src_h - y0
        ny1 = x1
        return (nx0, ny0, nx1, ny1)
    raise ValueError(
        f"rotate_bbox: only 0/90/180/270 supported, got {angle_ccw}"
    )


# --- PDF-level pre-orientation --------------------------------------------


def preorient_pdf(in_pdf: str | Path,
                  out_pdf: str | Path,
                  *,
                  render_dpi: int = 300,
                  skip_pages: Optional[set[int]] = None,
                  ) -> list[Orientation]:
    """Read ``in_pdf`` page-by-page, detect each page's rotation,
    physically rotate the raster, and write a new PDF where every
    page is upright (``/Rotate = 0``) on disk.

    Args:
        in_pdf: PDF to read.
        out_pdf: Destination path. The parent directory is created.
        render_dpi: **Cap** for the per-page rendered raster DPI,
            not a fixed render DPI. For each page the actual render
            DPI is ``min(source_dpi, render_dpi)``, where
            ``source_dpi`` is computed from the page's embedded
            image(s). The env var ``NC_OCR_ORIENTATION_MAX_DPI``
            overrides this value when set. Default ``200`` matches
            the prior behaviour's render DPI; the *new default cap*
            — when callers take the no-arg default — is effectively
            ``200`` (env absent). To opt into the recommended
            ``300`` cap, set ``NC_OCR_ORIENTATION_MAX_DPI=300`` in
            the environment or pass ``render_dpi=300``.
        skip_pages: Optional set of 0-indexed page numbers to leave
            untouched (e.g. born-digital pages with real text layers).
            Default: rotate every page.

    Returns:
        A list of :class:`Orientation` (one per page, in page
        order). Useful for telemetry — the caller can log which
        pages were rotated.

    Resolution-preserving raster policy
    -----------------------------------

    For each page we:

    1. Compute ``source_dpi`` from the page's embedded image(s)
       using the ``dpi = image_px / (page.rect / 72)`` formula,
       taking the max over images on the page, clamping to
       ``[_MIN_SOURCE_DPI, _MAX_SOURCE_DPI]`` (= ``[30, 2400]``)
       and falling back to the cap when the page has no images.
    2. Render the page at ``render_dpi_page = min(source_dpi, cap)``.
       A 75-dpi source page is therefore rasterised at 75 dpi (no
       upscaling) and a 600-dpi source page is rasterised at the
       cap (no detail loss beyond the cap).
    3. Detect orientation from the rendered raster.
    4. If the page needs rotation, rotate the rendered raster and
       re-embed it as a JPEG at ``NC_OCR_ORIENTATION_JPEG_Q``
       quality (default ``80``).
    5. If the page needs no rotation (``angle == 0``), insert the
       source page *verbatim* into the output document via
       ``out_doc.insert_pdf(in_doc, from_page=i, to_page=i)``.
       This preserves the original embedded image bytes — no
       re-encoding, no upscaling, same pixel dimensions — which
       matters for archival fidelity and downstream OCR engines
       that key on raster pixel counts.

    Notes:
        * Only the *raster* of each page is rotated. Any existing
          text layer (born-digital pages, partial OCR layers) is **not**
          re-OCR'd or transformed — pages with extractable text
          should be passed via ``skip_pages`` so the orchestrator
          can preserve them.
        * The output PDF is a flattened "image-per-page" PDF: each
          rebuilt page is a single full-page image with
          ``/Rotate = 0``. Original vector content is **lost**.
          This is acceptable for scanned-PDF OCR — the whole point
          is that we're OCRing the raster — but should be flagged
          so callers don't use it on born-digital PDFs.
    """
    import fitz  # PyMuPDF, imported lazily so engine tests don't need it

    in_pdf = Path(in_pdf)
    out_pdf = Path(out_pdf)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    skip_pages = skip_pages or set()

    cap_dpi = _resolve_max_dpi(int(render_dpi) if render_dpi else _DEFAULT_MAX_DPI)
    jpeg_q = _resolve_jpeg_quality()

    log.info(
        "preorient_pdf: %s → %s ; cap_dpi=%d jpeg_q=%d",
        in_pdf, out_pdf, cap_dpi, jpeg_q,
    )

    orientations: list[Orientation] = []
    out_doc = fitz.open()

    # Work on a private copy of the input: the rotation branch below
    # calls ``page.remove_rotation()`` on a page of the source handle,
    # which mutates the in-memory view of the caller's file. With
    # incremental-save semantics, PyMuPDF can flush that back to disk.
    # A throwaway copy keeps the original PDF byte-identical to what
    # the caller passed in. The copy lives next to the output and is
    # cleaned up regardless of how the loop terminates.
    work_pdf = out_pdf.parent / (out_pdf.stem + ".src.pdf")
    shutil.copyfile(str(in_pdf), str(work_pdf))

    try:
        with fitz.open(str(work_pdf)) as src:
            for page_idx, page in enumerate(src):
                if page_idx in skip_pages:
                    # Carry the original page over unchanged.
                    out_doc.insert_pdf(src, from_page=page_idx,
                                        to_page=page_idx)
                    orientations.append(Orientation(
                        angle=0, confidence=None, source="skipped"))
                    continue

                # Resolve per-page render DPI = min(source_dpi, cap).
                # We compute source_dpi once and use it for both the
                # OSD raster and the rebuilt raster so they match.
                source_dpi = _compute_source_dpi(page, cap_dpi)
                page_dpi = min(source_dpi, cap_dpi)

                # Step 1: render the page to PNG at the per-page DPI.
                # (Used for OSD; later steps reuse the bytes if
                # rotation is required.)
                pix = page.get_pixmap(dpi=page_dpi)
                png_bytes = pix.tobytes("png")

                # Step 2: detect orientation.
                orientation = detect_orientation(png_bytes)
                if not orientation.is_upright:
                    log.info(
                        "preorient_pdf: page %d needs %d° rotation "
                        "(source=%s confidence=%s render_dpi=%d "
                        "(source_dpi=%d, cap=%d))",
                        page_idx, orientation.ccw_degrees,
                        orientation.source, orientation.confidence,
                        page_dpi, source_dpi, cap_dpi,
                    )
                orientations.append(orientation)

                # Step 3: physically rotate the raster if needed;
                # otherwise copy the original page over verbatim so
                # the embedded image bytes are preserved.
                if not orientation.is_upright:
                    # Bake the rotation into the page content instead of
                    # re-rasterizing. ``show_pdf_page`` places the source
                    # page as a form XObject with the rotation applied, so
                    # vectors, an existing text layer and the original
                    # embedded image bytes all survive untouched: no
                    # resampling, no quality loss, no size blow-up.
                    #
                    # A 90/270 turn also swaps the page box, otherwise the
                    # rotated content is letter-boxed inside the old
                    # (mismatched) box.
                    if orientation.ccw_degrees in (90, 270):
                        page_w, page_h = page.rect.height, page.rect.width
                    else:
                        page_w, page_h = page.rect.width, page.rect.height

                    # ``show_pdf_page`` mis-fits source pages that carry a
                    # non-zero /Rotate, so neutralise it first (PyMuPDF
                    # issue #4453).
                    try:
                        if page.rotation:
                            page.remove_rotation()
                    except Exception as exc:  # noqa: BLE001
                        log.debug(
                            "preorient_pdf: remove_rotation failed on "
                            "page %d: %s", page_idx, exc)

                    new_page = out_doc.new_page(
                        width=page_w, height=page_h)
                    new_page.show_pdf_page(
                        new_page.rect,
                        src,
                        page_idx,
                        rotate=orientation.ccw_degrees,
                    )
                    new_page.set_rotation(0)
                else:
                    # No rotation needed: insert the original page
                    # verbatim. Preserves the embedded image bytes
                    # (no re-encoding) and existing text layer.
                    # This is the byte-identical copy the
                    # resolution-preserving raster policy promises
                    # for angle==0 pages.
                    out_doc.insert_pdf(src, from_page=page_idx,
                                        to_page=page_idx)
        # Preserve the document outline. Neither insert_pdf nor
        # show_pdf_page carries it over, so a PDF with bookmarks came
        # back with none — even when no page was rotated. The source
        # handle is already closed by this point, so reopen the input.
        try:
            with fitz.open(str(in_pdf)) as src_toc:
                toc = src_toc.get_toc(simple=True)
            if toc:
                out_doc.set_toc(toc)
        except Exception as exc:  # noqa: BLE001
            log.debug("preorient_pdf: could not copy the outline: %s", exc)

        out_doc.save(str(out_pdf), garbage=4, deflate=True)
    finally:
        out_doc.close()
        # Always clean up the working copy of the source — the
        # rotation loop only mutates that, never the caller's file.
        try:
            work_pdf.unlink(missing_ok=True)
        except OSError:
            pass

    log.info(
        "preorient_pdf: %s → %s ; orientations=%s",
        in_pdf, out_pdf, orientations,
    )
    return orientations


# --- Convenience wrapper ---------------------------------------------------


def orient_to_apply(orientation: Orientation) -> int:
    """Return the CCW rotation to apply to the rendered image.

    Convenience: ``0`` if the orientation is already upright, else
    ``orientation.ccw_degrees``. Same as calling
    ``orientation.ccw_degrees`` directly but reads better in
    orchestrator code.
    """
    return orientation.ccw_degrees


# --- "Safe" orchestrator-facing entry point --------------------------------


def preorient_pages_safe(in_pdf: str | Path) -> str:
    """Pre-orient ``in_pdf`` to a temp file and return its path.

    Used by :func:`nc_ocr_flow.ocr.process_pdf` to provide the
    engine with an upright PDF. Returns the original path if
    pre-orientation is a no-op (every page is already upright) so
    the caller doesn't need to clean up an unnecessary temp file.

    The no-op case is the hot path for born-digital files: most of
    them would later be skipped by the OCR engine anyway, so paying
    a full PDF rewrite here just to throw the result away is wasted
    work. We do a read-only per-page orientation pass first and
    return the input unchanged when nothing needs rotating.

    Raises on hard failure (PyMuPDF missing, etc.) — the caller
    is expected to catch and fall back to the original input.
    """
    import os as _os
    import tempfile
    in_pdf = Path(in_pdf)

    # Fast precheck: run the existing detector over every page
    # *without* writing anything. If every page is already upright
    # we hand the input back unchanged and skip the full PDF
    # rebuild (insert_pdf + save + outline copy) below. If the
    # precheck itself errors, fall through to the safe path —
    # ``preorient_pdf`` will report the failure the same way it
    # always has.
    precheck = _detect_all_pages_orientations(in_pdf)
    if precheck is not None and all(o.is_upright for o in precheck):
        log.debug(
            "preorient_pages_safe: %s already upright on precheck, "
            "skipping rebuild", in_pdf)
        return str(in_pdf)

    fd, tmp_path = tempfile.mkstemp(suffix=".upright.pdf", prefix="nc-ocr-")
    _os.close(fd)
    orientations = preorient_pdf(in_pdf, tmp_path)
    if all(o.is_upright for o in orientations):
        # Nothing changed → don't make the engines read a different
        # file. Delete the throwaway upright copy.
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except OSError:
            pass
        return str(in_pdf)
    return tmp_path


def _detect_all_pages_orientations(
    in_pdf: str | Path,
) -> Optional[list[Orientation]]:
    """Render every page of ``in_pdf`` and run :func:`detect_orientation`
    on it, returning a per-page :class:`Orientation` list.

    Read-only: never mutates the file and never writes an output.
    Used by :func:`preorient_pages_safe` as a cheap precheck so a
    fully-upright document can short-circuit before paying the full
    PDF rewrite.

    Returns ``None`` on any failure (file unreadable, PyMuPDF
    exception, …) so the caller can fall through to the full
    ``preorient_pdf`` path rather than wrongly handing back a
    precheck result that wasn't actually produced.
    """
    import fitz

    in_pdf = Path(in_pdf)
    cap_dpi = _resolve_max_dpi(_DEFAULT_MAX_DPI)

    try:
        with fitz.open(str(in_pdf)) as src:
            n_pages = src.page_count
            if n_pages == 0:
                return [Orientation(angle=0, confidence=None, source="default")]

            out: list[Orientation] = []
            for page_idx, page in enumerate(src):
                source_dpi = _compute_source_dpi(page, cap_dpi)
                page_dpi = min(source_dpi, cap_dpi)
                pix = page.get_pixmap(dpi=page_dpi)
                png_bytes = pix.tobytes("png")
                out.append(detect_orientation(png_bytes))
            return out
    except Exception as exc:  # noqa: BLE001
        log.debug(
            "preorient precheck failed on %s: %s", in_pdf, exc)
        return None


def compute_source_dpi(page, cap_dpi: int) -> int:
    """Public alias of :func:`_compute_source_dpi` for tests.

    Walks ``page.get_images(full=True)`` and for each image
    computes::

        dpi_x = image_px_width  * 72.0 / page.rect.width
        dpi_y = image_px_height * 72.0 / page.rect.height

    Returns the dpi of the image that covers the largest area of the
    page, clamped to ``[_MIN_SOURCE_DPI, _MAX_SOURCE_DPI]``. Ranking by
    area (not by maximum dpi) keeps a small high-resolution logo or
    stamp from raising the render dpi and upscaling the actual scan.
    If the page has no images, falls back to ``cap_dpi`` (the rendered
    raster at the cap is the honest answer: we don't know what
    dpi the "blank" page is).
    """
    return _compute_source_dpi(page, cap_dpi)


__all__ = [
    "Orientation",
    "MIN_OSD_CONFIDENCE",
    "WORD_BBOX_ASPECT_THRESHOLD",
    "parse_osd_output",
    "detect_orientation_tesseract",
    "detect_orientation_from_word_bboxes",
    "detect_orientation_from_content_bbox",
    "detect_orientation",
    "DOC_ORI_MARGIN_THRESHOLD",
    "rotate_png",
    "rotate_bbox",
    "preorient_pdf",
    "preorient_pages_safe",
    "orient_to_apply",
    "compute_source_dpi",
]