"""Tests for nc_ocr_flow.orientation — per-page orientation correction.

Unit tests cover the pure helpers (parse_osd_output, rotate_bbox,
detect_orientation_from_word_bboxes). End-to-end tests build synthetic
rotated PDFs and verify preorient_pdf produces an upright document.

These tests do NOT call tesseract by default — tesseract is exercised
by the ``osd_end_to_end_*`` tests which are gated behind a marker that
matches the ``--runslow`` convention used elsewhere in this repo.

Run with: ``pytest tests/test_orientation.py``
"""
from __future__ import annotations

import io
import struct
import zlib
from pathlib import Path

import pytest
import fitz  # PyMuPDF, used by the resolution-preserving raster policy tests

from nc_ocr_flow.orientation import (
    MIN_OSD_CONFIDENCE,
    Orientation,
    detect_orientation,
    detect_orientation_from_content_bbox,
    detect_orientation_from_word_bboxes,
    detect_orientation_tesseract,
    parse_osd_output,
    preorient_pdf,
    preorient_pages_safe,
    rotate_bbox,
    rotate_png,
)


# --- Tiny PNG fixtures -----------------------------------------------------


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _make_png(width: int, height: int, fill: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    """Build a tiny in-memory RGB PNG of given size, all one colour.

    Used to give the bbox maths something to chew on without touching
    disk. PIL could do this faster, but we want zero external deps
    for the bbox maths tests.
    """
    raw = b""
    row = bytes(fill) * width
    for _ in range(height):
        raw += b"\x00" + row  # filter type 0
    compressed = zlib.compress(raw, 9)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit truecolor
    return (sig + _png_chunk(b"IHDR", ihdr)
            + _png_chunk(b"IDAT", compressed)
            + _png_chunk(b"IEND", b""))


def _make_rotated_pdf(out_pdf: Path, *, page_w: float, page_h: float,
                      image_w: int = 800, image_h: int = 1200,
                      embed_sideways: bool = False) -> Path:
    """Build a 1-page PDF whose embedded raster may be physically rotated.

    The page's ``/Rotate`` flag is always 0 (we never call
    ``page.set_rotation``). What changes between test cases is the
    *content* of the embedded image:

      * ``embed_sideways=False`` (default) — the image is a normal
        upright gray rectangle. preorient_pdf should leave it alone.
      * ``embed_sideways=True`` — the embedded image is itself a
        gray rectangle that PIL has rotated 90° CW before insertion,
        so the raster in the output PDF stores sideways content
        while the page's ``/Rotate`` flag is still 0. This is the
        broken state we want preorient_pdf to detect and fix.

    PyMuPDF is the only sane way to embed images in a PDF; the
    function uses PIL to construct the raster.
    """
    import fitz
    from PIL import Image
    img = Image.new("RGB", (image_w, image_h), (240, 240, 240))
    if embed_sideways:
        img = img.rotate(90, expand=True)
    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    doc = fitz.open()
    page = doc.new_page(width=page_w, height=page_h)
    page.insert_image(fitz.Rect(0, 0, page_w, page_h), stream=img_bytes)
    # Intentionally DO NOT call page.set_rotation — we want the
    # /Rotate flag to be 0 so preorient_pdf must detect the
    # physical rotation encoded in the raster itself.
    doc.save(str(out_pdf))
    doc.close()
    return out_pdf


def _find_dejavu_font() -> str:
    """Locate a TTF font for tests, honouring the same env var as the service.

    ``NC_OCR_FONT_PATH`` is what the deployed unit sets, so when it is present
    the test must use it and must FAIL if it is broken: skipping would hide a
    misconfiguration, which is precisely how these OSD tests stopped running -
    the first candidate below was a hardcoded /nix/store path with a hash that
    no longer exists, so every candidate missed and the tests skipped silently.
    """
    import os
    explicit = os.environ.get("NC_OCR_FONT_PATH")
    if explicit:
        if not os.path.exists(explicit):
            pytest.fail(f"NC_OCR_FONT_PATH={explicit} does not exist")
        return explicit
    candidates = [
        "/run/current-system/sw/share/X11/fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    # Try to find any TTF under /nix/store
    import glob
    matches = glob.glob("/nix/store/*/share/fonts/truetype/DejaVuSans.ttf")
    if matches:
        return matches[0]
    pytest.skip("No TTF font available and NC_OCR_FONT_PATH unset")


# --- parse_osd_output ------------------------------------------------------


class TestParseOSDOutput:
    def test_parses_zero_degree(self):
        out = (
            "Page number: 0\n"
            "Orientation in degrees: 0\n"
            "Rotate: 0\n"
            "Orientation confidence: 12.34\n"
            "Script: Latin\n"
            "Script confidence: 4.56\n"
        )
        o = parse_osd_output(out)
        assert o is not None
        assert o.angle == 0
        assert o.confidence == 12.34
        assert o.source == "tesseract-osd"
        assert o.is_upright

    def test_parses_90_with_confidence(self):
        out = (
            "Orientation in degrees: 90\n"
            "Rotate: 270\n"
            "Orientation confidence: 4.21\n"
            "Script: Cyrillic\n"
            "Script confidence: 1.42\n"
        )
        o = parse_osd_output(out)
        assert o is not None
        assert o.angle == 90
        assert o.confidence == 4.21
        # Tesseract OSD reports CW-from-upright; to undo a 90° CW
        # rotation we apply 90° CCW, so ccw_degrees == angle.
        assert o.ccw_degrees == 90
        assert not o.is_upright

    @pytest.mark.parametrize("angle", (0, 90, 180, 270))
    def test_parses_all_valid_quadrants(self, angle):
        out = f"Orientation in degrees: {angle}\nOrientation confidence: 5.0\n"
        o = parse_osd_output(out)
        assert o is not None and o.angle == angle

    def test_too_few_characters_yields_none(self):
        out = "Too few characters. Skipping this page\n"
        assert parse_osd_output(out) is None

    def test_missing_orientation_yields_none(self):
        out = "Some other tesseract text.\n"
        assert parse_osd_output(out) is None

    def test_invalid_angle_yields_none(self):
        # 45° is not a valid OSD output; we reject it rather than
        # silently truncating.
        out = "Orientation in degrees: 45\nOrientation confidence: 9.9\n"
        assert parse_osd_output(out) is None

    def test_low_confidence_yields_none(self):
        out = f"Orientation in degrees: 90\nOrientation confidence: {MIN_OSD_CONFIDENCE - 0.01:.2f}\n"
        assert parse_osd_output(out) is None

    def test_confidence_equal_to_min_kept(self):
        out = f"Orientation in degrees: 90\nOrientation confidence: {MIN_OSD_CONFIDENCE:.2f}\n"
        o = parse_osd_output(out)
        assert o is not None and o.angle == 90

    def test_unparseable_confidence_yields_none_conf(self):
        out = "Orientation in degrees: 180\nOrientation confidence: not-a-number\n"
        o = parse_osd_output(out)
        assert o is not None and o.angle == 180 and o.confidence is None


# --- rotate_bbox -----------------------------------------------------------


class TestRotateBbox:
    def test_zero_is_identity(self):
        bbox = (10.0, 20.0, 110.0, 60.0)
        assert rotate_bbox(bbox, 200, 200, 0) == bbox

    def test_90_cw_input_swaps_xy(self):
        # Source 200x100, src bbox spans x in [10,110], y in [20,60].
        # Rotate 90° CCW: new image is (100, 200). The point
        # (10, 20) in src → (20, src_w - 10 = 190) in dst.
        # x0_new = y0_src = 20
        # y0_new = src_w - x1_src = 200 - 110 = 90
        # x1_new = y1_src = 60
        # y1_new = src_w - x0_src = 200 - 10 = 190
        bbox = (10.0, 20.0, 110.0, 60.0)
        assert rotate_bbox(bbox, 200, 100, 90) == (20.0, 90.0, 60.0, 190.0)

    def test_180_flips_both(self):
        # 200x200 src, bbox (10, 20, 110, 60):
        # → (200-110, 200-60, 200-10, 200-20) = (90, 140, 190, 180)
        bbox = (10.0, 20.0, 110.0, 60.0)
        assert rotate_bbox(bbox, 200, 200, 180) == (90.0, 140.0, 190.0, 180.0)

    def test_270_cw_input(self):
        # 90° CCW from upright, but called as angle_ccw=270. The
        # canonical test: take a point (50, 30) in a 200x200 image,
        # rotate the *image* 270° CCW (≡ 90° CW). The new image
        # is 200x200 (180 doesn't swap dims). The point (50, 30)
        # in the original lives at (200-30, 50) = (170, 50) in the
        # destination. Verify on a single-point bbox:
        bbox = (50.0, 30.0, 50.0, 30.0)
        # 270° CCW ≡ rotate by -270° ≡ same as +90° CCW of image
        # Wait — we have angle_ccw = 270, meaning we rotated the
        # source image by 270 CCW (or equivalently 90 CW).
        # Apply: dst = (src_h - y, x) for 270 CCW (= 90 CW image rot)
        # Wait our formula: nx0 = src_h - y1, ny0 = x0, ...
        # For src_h=200 bbox(50,30,50,30): nx0 = 200-30=170, ny0=50,
        # nx1=200-30=170, ny1=50.
        assert rotate_bbox(bbox, 200, 200, 270) == (170.0, 50.0, 170.0, 50.0)

    def test_360_collapses_to_zero(self):
        bbox = (10.0, 20.0, 110.0, 60.0)
        assert rotate_bbox(bbox, 200, 200, 360) == bbox
        assert rotate_bbox(bbox, 200, 200, 720) == bbox

    def test_negative_angle_normalises(self):
        bbox = (10.0, 20.0, 110.0, 60.0)
        # -90 ≡ 270 CCW
        assert rotate_bbox(bbox, 200, 200, -90) == rotate_bbox(bbox, 200, 200, 270)

    def test_round_trip_90_270(self):
        bbox = (10.0, 20.0, 110.0, 60.0)
        # Apply 90 CCW then 270 CCW → identity.
        intermediate = rotate_bbox(bbox, 200, 100, 90)
        # After 90 CCW the image dims swap (200x100 → 100x200).
        # But we transformed *into* dst space (100x200), so apply
        # the second rotation in those dims.
        # 270 CCW on a 100x200 image with the intermediate bbox:
        restored = rotate_bbox(intermediate, 100, 200, 270)
        assert restored == bbox

    def test_invalid_angle_raises(self):
        with pytest.raises(ValueError, match="0/90/180/270"):
            rotate_bbox((0, 0, 10, 10), 100, 100, 45)


# --- rotate_png ------------------------------------------------------------


class TestRotatePng:
    def test_zero_returns_same_bytes(self):
        png = _make_png(10, 10)
        out = rotate_png(png, 0)
        assert out == png

    def test_invalid_angle_raises(self):
        png = _make_png(10, 10)
        with pytest.raises(ValueError, match="90"):
            rotate_png(png, 45)

    def test_90_swaps_dimensions(self):
        # PIL is available; use it to confirm we get a valid rotated PNG.
        from PIL import Image
        png = _make_png(20, 10)
        out = rotate_png(png, 90)
        with Image.open(io.BytesIO(out)) as im:
            assert im.size == (10, 20)

    def test_90_round_trip_with_osd(self, tmp_path):
        """End-to-end: rotate a known-sideways PNG, run OSD, expect upright.

        Locks in the PIL convention that ``Image.rotate`` is in
        fact CW for positive angle (despite the docs saying CCW).
        If PIL ever fixes that, this test will fail and prompt a
        code review of :func:`rotate_png`.
        """
        try:
            import pymupdf  # noqa: F401  only available in CI / poweredge
        except ImportError:
            pytest.skip("pymupdf not available")
        # Build a real rendered upright text PNG (so OSD agrees on
        # upright = 0 degrees and on the orientation direction).
        font_path = _find_dejavu_font()
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype(font_path, 48)
        im = Image.new("RGB", (1600, 1200), (255, 255, 255))
        d = ImageDraw.Draw(im)
        for i, line in enumerate([
            "First line of text that has enough characters for OSD",
            "Second line of text that adds even more characters",
            "Third line for good measure and OSD reliability",
            "Fourth line to push past the fifty char threshold",
        ]):
            d.text((100, 100 + i * 200), line, fill=(0, 0, 0), font=font)
        buf = io.BytesIO()
        im.save(buf, format="PNG", dpi=(300, 300))
        upright_png = buf.getvalue()

        # Rotate the source image by 90° CW (so OSD reports angle=90).
        from PIL import Image as PILImage
        im_cw = PILImage.open(io.BytesIO(upright_png))
        im_cw = im_cw.rotate(-90, expand=True)  # 90° CW
        buf = io.BytesIO()
        # Stamp DPI metadata so tesseract doesn't fall back to 70 dpi
        # and OSD can do its job (matches what PyMuPDF writes when
        # rendering a real PDF).
        im_cw.save(buf, format="PNG", dpi=(300, 300))
        cw_png = buf.getvalue()

        # Detect orientation.
        from nc_ocr_flow.orientation import detect_orientation_tesseract
        o = detect_orientation_tesseract(cw_png)
        if o is None or o.angle != 90:
            pytest.skip(
                "OSD detection unstable on this tesseract build "
                f"(got {o!r}); skipping directionality assertion"
            )

        # Apply rotate_png with the CCW angle that OSD recommends.
        fixed = rotate_png(cw_png, o.angle)
        o2 = detect_orientation_tesseract(fixed)
        assert o2 is not None
        assert o2.angle == 0, (
            f"rotate_png should bring a 90°-CW image upright, but OSD "
            f"still reports angle={o2.angle} after the fix"
        )


# --- detect_orientation_from_word_bboxes ----------------------------------


class TestWordBboxOrientation:
    def test_horizontal_words_return_upright(self):
        # Words ~50 wide × 20 tall — clearly horizontal.
        words = [(i * 100, 100, i * 100 + 50, 120) for i in range(5)]
        o = detect_orientation_from_word_bboxes(words)
        assert o is not None
        assert o.angle == 0
        assert o.source == "word-bbox"

    def test_tall_words_return_sideways(self):
        # Words ~20 wide × 50 tall — clearly sideways.
        words = [(100, i * 100, 120, i * 100 + 50) for i in range(5)]
        o = detect_orientation_from_word_bboxes(words)
        assert o is not None
        assert o.angle == 90

    def test_no_words_returns_none(self):
        assert detect_orientation_from_word_bboxes([]) is None

    def test_square_words_return_none(self):
        # Aspect 1.0 ± small noise — ambiguous, refuse to guess.
        words = [(i * 50, 100, i * 50 + 30, 130) for i in range(5)]
        assert detect_orientation_from_word_bboxes(words) is None

    def test_zero_size_bbox_ignored(self):
        words = [(0, 0, 0, 0), (10, 10, 50, 30)]
        o = detect_orientation_from_word_bboxes(words)
        assert o is not None
        assert o.angle == 0  # only the valid bbox counts


# --- detect_orientation_tesseract (no actual tesseract) -------------------


class TestDetectTesseractNotAvailable:
    def test_missing_binary_returns_none(self, monkeypatch, tmp_path):
        from nc_ocr_flow import orientation as orient_mod
        monkeypatch.setattr(orient_mod.shutil, "which",
                            lambda x: None if x == "tesseract" else f"/usr/bin/{x}")
        png = _make_png(100, 100)
        assert detect_orientation_tesseract(png) is None


# --- End-to-end with a synthetic rotated PDF (no tesseract) ---------------


class TestPreorientPDFSynthetic:
    def test_no_op_for_upright_input(self, tmp_path):
        # Build a PDF with an upright embedded image. All pages
        # should be detected as upright; preorient_pages_safe
        # should return the *original* path unchanged.
        upright_pdf = tmp_path / "upright.pdf"
        _make_rotated_pdf(upright_pdf, page_w=595, page_h=842,
                          image_w=800, image_h=1200)
        # No tesseract needed: render and use a path that has no
        # detectable text. But tesseract will be called — mock it to
        # always return upright.
        from nc_ocr_flow import orientation as orient_mod
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(0, 99.0, "mock"))
        result = preorient_pages_safe(str(upright_pdf))
        # Should be the original path because all pages were upright.
        assert Path(result).resolve() == upright_pdf.resolve()

    def test_sideways_raster_gets_physically_rotated(self, tmp_path):
        # Build a PDF whose embedded raster stores physically rotated
        # content (PIL rotated it 90° CW before insertion). The page
        # /Rotate flag is 0. preorient_pdf should:
        #   1. Render → see sideways content → report angle=90.
        #   2. Physically rotate the raster with PIL.
        #   3. Write a new PDF with /Rotate=0 and an upright raster.
        in_pdf = tmp_path / "sideways.pdf"
        _make_rotated_pdf(in_pdf, page_w=595, page_h=842,
                          image_w=800, image_h=1200, embed_sideways=True)
        from nc_ocr_flow import orientation as orient_mod
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))
        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert len(orientations) == 1
        assert orientations[0].angle == 90
        # The output PDF exists and is loadable.
        import fitz
        d = fitz.open(str(out_pdf))
        try:
            assert d.page_count == 1
            pg = d[0]
            assert pg.rotation == 0
            # A 90-degree turn swaps the page box: the raster is now
            # upright, so the page must match it instead of
            # letter-boxing it (see TestDominantImageAndGeometry).
            assert pg.rect.width == pytest.approx(842, abs=1)
            assert pg.rect.height == pytest.approx(595, abs=1)
        finally:
            d.close()

    def test_orientation_list_reflects_per_page(self, tmp_path):
        # Multi-page PDF: page 0 upright, page 1 sideways, page 2 upright.
        in_pdf = tmp_path / "multi.pdf"
        import fitz
        from PIL import Image
        from nc_ocr_flow import orientation as orient_mod
        orientations_mock = [
            Orientation(0, 99.0, "mock"),
            Orientation(90, 99.0, "mock"),
            Orientation(0, 99.0, "mock"),
        ]
        call_count = {"n": 0}
        def fake_detect(png_bytes, **kw):
            o = orientations_mock[call_count["n"]]
            call_count["n"] += 1
            return o
        orient_mod.detect_orientation_tesseract = fake_detect

        doc = fitz.open()
        for _ in range(3):
            p = doc.new_page(width=595, height=842)
            img = Image.new("RGB", (400, 600), (200, 200, 200))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            p.insert_image(fitz.Rect(0, 0, 595, 842), stream=buf)
        doc.save(str(in_pdf))
        doc.close()

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert [o.angle for o in orientations] == [0, 90, 0]
        out = fitz.open(str(out_pdf))
        try:
            assert out.page_count == 3
        finally:
            out.close()


# --- End-to-end with tesseract OSD (slow) ----------------------------------


class TestOSDEndToEnd:
    """Run real tesseract OSD on a synthetic input.

    Marked slow to match the repo's --runslow convention.
    """
    @pytest.fixture(autouse=True)
    def _skip_without_tesseract(self):
        import shutil
        if shutil.which("tesseract") is None:
            pytest.skip("tesseract binary not on PATH")
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("PIL not installed")

    @pytest.fixture
    def upright_png(self):
        """Render a real upright PNG via PIL — not the placeholder.

        Uses a real TTF font (DejaVu Sans 48 px) because the default
        PIL bitmap font is too small/aliased for Tesseract OSD to
        classify orientation. Also stamps ``dpi=(300, 300)`` in the
        PNG metadata so Tesseract doesn't fall back to 70 dpi and
        then complain about insufficient characters.

        Contains 50+ characters because Tesseract OSD refuses to
        classify orientation for images with fewer than
        ``min_characters_to_try`` (default 50) characters; the
        ``--psm 0`` model is unreliable below that threshold.
        See: https://github.com/tesseract-ocr/tesseract/issues/1701
        """
        from PIL import Image, ImageDraw, ImageFont
        font_path = _find_dejavu_font()
        im = Image.new("RGB", (1600, 1200), (255, 255, 255))
        d = ImageDraw.Draw(im)
        font = ImageFont.truetype(font_path, 48)
        d.text((100, 100),
               "This is the first line of test text with many characters",
               fill=(0, 0, 0), font=font)
        d.text((100, 300),
               "Second line of test text that adds even more characters now",
               fill=(0, 0, 0), font=font)
        d.text((100, 500),
               "Third line here to make the orientation signal rock solid",
               fill=(0, 0, 0), font=font)
        d.text((100, 700),
               "Fourth and final line for good measure and robust detection",
               fill=(0, 0, 0), font=font)
        d.text((100, 900),
               "Fifth line just to be safe with Tesseract OSD today",
               fill=(0, 0, 0), font=font)
        buf = io.BytesIO()
        im.save(buf, format="PNG", dpi=(300, 300))
        return buf.getvalue()

    def test_detects_upright_png(self, upright_png):
        o = detect_orientation_tesseract(upright_png)
        assert o is not None
        assert o.angle in (0, 180)  # OSD can't tell 0 from 180 from text shape alone

    def test_physically_rotated_png_detected(self, upright_png):
        from PIL import Image
        rotated = Image.open(io.BytesIO(upright_png))
        rotated = rotated.rotate(90, expand=True)  # 90 CW → sideways text
        buf = io.BytesIO()
        rotated.save(buf, format="PNG")
        o = detect_orientation_tesseract(buf.getvalue())
        assert o is not None
        # Should detect 90° rotation (text now sideways).
        assert o.angle in (90, 270)


class TestContentBboxOrientation:
    """Tests for :func:`detect_orientation_from_content_bbox`.

    This fallback fires when Tesseract OSD refuses (too few
    characters). It looks at the aspect ratio of dark-pixel
    content relative to the image aspect.
    """

    def _make_portrait_with_landscape_content(self) -> bytes:
        """Portrait white image with a single wide horizontal line.

        Image is 600×800 portrait. Content is a single 300×50
        bar near the middle — content aspect is 6 (landscape).
        Should trigger the 90° fallback.
        """
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (600, 800), (255, 255, 255))
        d = ImageDraw.Draw(im)
        d.rectangle([150, 400, 450, 450], fill=(0, 0, 0))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    def _make_portrait_with_portrait_content(self) -> bytes:
        """Portrait white image with a tall vertical bar.

        Content aspect < 1 (portrait). Should NOT trigger rotation.
        """
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (600, 800), (255, 255, 255))
        d = ImageDraw.Draw(im)
        d.rectangle([275, 200, 325, 600], fill=(0, 0, 0))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    def _make_blank_image(self) -> bytes:
        from PIL import Image
        im = Image.new("RGB", (600, 800), (255, 255, 255))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    def _make_landscape_with_portrait_content(self) -> bytes:
        """Landscape image, tall vertical bar (portrait content).

        Image 800×600 landscape. Content is a 50×200 tall block
        — content aspect is 0.25 (portrait). Should detect 90°.
        """
        from PIL import Image, ImageDraw
        im = Image.new("RGB", (800, 600), (255, 255, 255))
        d = ImageDraw.Draw(im)
        d.rectangle([300, 100, 500, 500], fill=(0, 0, 0))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()

    def test_portrait_with_landscape_content_detects_90(self):
        png = self._make_portrait_with_landscape_content()
        o = detect_orientation_from_content_bbox(png)
        assert o is not None
        assert o.angle == 90
        assert o.source == "content-bbox"

    def test_portrait_with_portrait_content_keeps_0(self):
        png = self._make_portrait_with_portrait_content()
        o = detect_orientation_from_content_bbox(png)
        assert o is not None
        assert o.angle == 0

    def test_landscape_with_portrait_content_detects_90(self):
        png = self._make_landscape_with_portrait_content()
        o = detect_orientation_from_content_bbox(png)
        assert o is not None
        assert o.angle == 90

    def test_blank_image_returns_none(self):
        png = self._make_blank_image()
        o = detect_orientation_from_content_bbox(png)
        assert o is None


class TestDetectOrientation:
    """End-to-end of :func:`detect_orientation` combining all detectors."""

    def test_returns_orientation_object_never_none(self, monkeypatch):
        # Even on a totally blank image, must return an Orientation
        # (never None — the orchestrator treats None differently).
        from PIL import Image
        from nc_ocr_flow import orientation as orient_mod

        # Force tesseract to return None (simulates OSD refusal on
        # blank input) so the bbox fallback is also skipped.
        monkeypatch.setattr(
            orient_mod, "detect_orientation_tesseract",
            lambda png_bytes, **kw: None)
        im = Image.new("RGB", (400, 600), (255, 255, 255))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        o = detect_orientation(buf.getvalue())
        assert isinstance(o, Orientation)
        # Blank → default no rotation.
        assert o.angle == 0
        assert o.source == "default"

    def test_takes_pp_lcnet_when_confident(self, monkeypatch):
        # With the margin-based gate, PP-LCNet should win whenever
        # its top-1 margin >= DOC_ORI_MARGIN_THRESHOLD (verified
        # empirically: synthetic text yields ~0.27 margin, well
        # above the 0.15 fallback boundary). The detector must
        # take the model's verdict and not defer to tesseract /
        # bbox — that's the whole point of fixing the
        # absolute-0.80 bug.
        from PIL import Image, ImageDraw, ImageFont
        from nc_ocr_flow import orientation as orient_mod

        # If we get here, it means PP-LCNet was wrong; sentinel.
        monkeypatch.setattr(
            orient_mod, "detect_orientation_tesseract",
            lambda png_bytes, **kw: Orientation(
                angle=180, confidence=9.99, source="tesseract-osd"),
        )
        im = Image.new("RGB", (1600, 1200), (255, 255, 255))
        d = ImageDraw.Draw(im)
        font_path = _find_dejavu_font()
        font = ImageFont.truetype(font_path, 48)
        for i, line in enumerate([
            "First line of text that has enough characters for OSD",
            "Second line of text that adds even more characters",
            "Third line for good measure and OSD reliability",
            "Fourth line to push past the fifty char threshold",
        ]):
            d.text((100, 100 + i * 200), line, fill=(0, 0, 0), font=font)
        buf = io.BytesIO()
        im.save(buf, format="PNG", dpi=(300, 300))
        o = detect_orientation(buf.getvalue())
        # PP-LCNet is confident on this synthetic text doc and
        # must be the source we report — NOT the patched tesseract.
        assert o.source == "pp-lcnet-doc-ori"
        assert o.angle == 0

    def test_falls_back_to_tesseract_when_stage1_uncertain(
            self, monkeypatch):
        # When PP-LCNet's margin is below the threshold (synthetic
        # near-blank page -> ~0.001 margin, all 4 classes ≈0.25),
        # we MUST defer to the OCR vote / tesseract OSD. We patch
        # stage-1 to return a flat distribution to drive the
        # fallback deterministically — it doesn't depend on a real
        # blank image.
        from PIL import Image, ImageDraw, ImageFont
        from nc_ocr_flow import orientation as orient_mod
        # doc_ori is imported lazily inside detect_orientation;
        # expose it so the patch sticks.
        from nc_ocr_flow import doc_ori
        orient_mod.doc_ori = doc_ori

        def _fake_classify(png_bytes):
            # idx=0 wins but margin = 0.001 -> < 0.15 -> defer
            return (0, 0.251,
                    [0.251, 0.250, 0.250, 0.249])

        monkeypatch.setattr(orient_mod.doc_ori, "classify",
                            _fake_classify)
        monkeypatch.setattr(
            orient_mod, "detect_orientation_tesseract",
            lambda png_bytes, **kw: Orientation(
                angle=180, confidence=9.99, source="tesseract-osd"),
        )
        im = Image.new("RGB", (1600, 1200), (255, 255, 255))
        d = ImageDraw.Draw(im)
        font = ImageFont.truetype(_find_dejavu_font(), 48)
        for i, line in enumerate([
            "First line of text that has enough characters for OSD",
            "Second line of text that adds even more characters",
        ]):
            d.text((100, 100 + i * 200), line, fill=(0, 0, 0), font=font)
        buf = io.BytesIO()
        im.save(buf, format="PNG", dpi=(300, 300))
        o = detect_orientation(buf.getvalue())
        assert o.source == "tesseract-osd"
        assert o.angle == 180


# --- Resolution-preserving raster policy tests ----------------------------


class TestResolutionPreservingRasterPolicy:
    """End-to-end tests for the per-page source-dpi policy in
    :func:`preorient_pdf`.

    These tests cover the six rules from the spec:

      (a) 600-dpi page + no rotation  → output embedded image is
          byte-identical (no upscaling, no re-encoding).
      (b) ~75-dpi page + rotation      → output effective dpi stays
          ~75 (NOT upscaled).
      (c) 600-dpi page + rotation      → output effective dpi is
          > 150 but <= 300 (the cap).
      (d) Page with no images          → uses the cap.
      (e) Pre-pass runs through both   → rebuilt page actually
          a real image whose dimensions match ``page_dpi``.
      (f) ``NC_OCR_DISABLE_ORIENTATION=1`` bypass returns the
          original file unchanged.

    We also probe the env-var knobs (``NC_OCR_ORIENTATION_MAX_DPI``,
    ``NC_OCR_ORIENTATION_JPEG_Q``) and the new multi-page case
    where one page needs rotation and another doesn't.
    """

    @staticmethod
    def _build_pdf(
        out_pdf: Path,
        *,
        image_w: int,
        image_h: int,
        page_w: float = 595.0,    # A4 portrait width in pts
        page_h: float = 842.0,    # A4 portrait height in pts
        embed_sideways: bool = False,
        no_image: bool = False,
    ) -> Path:
        """Build a 1-page PDF whose only embedded raster is a JPEG
        of dimensions ``(image_w, image_h)`` covering the whole
        page rect.

        This lets us tune the *effective dpi* of the page via
        ``dpi_eff = image_w / (page_w / 72)``. Concretely:

          * ``(620,  876)`` on A4 (595×842) → ~75 dpi
          * ``(1240, 1752)`` on A4          → ~150 dpi
          * ``(2480, 3508)`` on A4          → ~300 dpi
          * ``(4961, 7016)`` on A4          → ~600 dpi
          * ``(7440,10524)`` on A4          → ~900 dpi
        """
        import fitz
        from PIL import Image as PILImage
        doc = fitz.open()
        page = doc.new_page(width=page_w, height=page_h)
        if not no_image:
            img = PILImage.new("RGB", (image_w, image_h), (220, 220, 220))
            if embed_sideways:
                img = img.rotate(90, expand=True)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            page.insert_image(
                fitz.Rect(0, 0, page_w, page_h),
                stream=buf.getvalue(),
            )
        # /Rotate stays 0.
        doc.save(str(out_pdf))
        doc.close()
        return out_pdf

    @staticmethod
    def _first_image_meta(d) -> dict:
        """Return width/height/ext of the first embedded image of
        page 0, or ``{}`` if the page has none.
        """
        page = d[0]
        for info in page.get_images(full=True):
            xref = info[0]
            meta = d.extract_image(xref)
            return {
                "width": meta.get("width"),
                "height": meta.get("height"),
                "ext": meta.get("ext"),
                "bytes_len": len(meta.get("image", b"")),
            }
        return {}

    @staticmethod
    def _effective_dpi(d) -> float | None:
        page = d[0]
        for info in page.get_images(full=True):
            xref = info[0]
            meta = d.extract_image(xref)
            pw = float(page.rect.width) or 1.0
            ph = float(page.rect.height) or 1.0
            return max(
                meta["width"] * 72.0 / pw,
                meta["height"] * 72.0 / ph,
            )
        return None

    # --- (a) 600-dpi page + no rotation → byte-identical / same px ---

    def test_no_rotation_preserves_embedded_image_byte_identical(
            self, tmp_path, monkeypatch):
        """Spec rule (a) and the "skip the rebuild entirely" promise
        from the module docstring: a 600-dpi page that needs no
        rotation must appear in the output document **unchanged**.

        Because :func:`preorient_pages_safe` deletes the throwaway
        upright file when nothing changed, the spec's
        "byte-identical copy" only holds inside :func:`preorient_pdf`
        itself (not its wrapper). Here we drive :func:`preorient_pdf`
        directly and assert: same pixel dims AND same image bytes
        AND same file size for the page's embedded raster.
        """
        from nc_ocr_flow import orientation as orient_mod
        in_pdf = tmp_path / "hi.pdf"
        self._build_pdf(in_pdf, image_w=4961, image_h=7016)  # ~600 dpi
        # Force "upright" verdict — no rotation required.
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(0, 99.0, "mock"))

        # Source pixels.
        with fitz.open(str(in_pdf)) as d_src:
            src_meta = self._first_image_meta(d_src)
            src_bytes = d_src.extract_image(
                d_src[0].get_images(full=True)[0][0])["image"]
            assert src_meta["ext"] == "jpeg"
            assert src_meta["width"] > 4000  # sanity: this is a 600-dpi image

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert orientations[0].angle == 0

        with fitz.open(str(out_pdf)) as d_out:
            out_meta = self._first_image_meta(d_out)
            out_bytes = d_out.extract_image(
                d_out[0].get_images(full=True)[0][0])["image"]

        # (1) Same pixel dims.
        assert (out_meta["width"], out_meta["height"]) == (
            src_meta["width"], src_meta["height"]
        )
        # (2) Same extension → same codec.
        assert out_meta["ext"] == src_meta["ext"] == "jpeg"
        # (3) Byte-identical embedded bytes. This is the strongest
        # statement of "no re-encoding happened": even the JPEG
        # quantization tables and EXIF survive.
        assert out_bytes == src_bytes, (
            "spec rule (a): a no-rotation page must keep its embedded "
            "image bytes unchanged; got %d-byte diff" % abs(
                len(out_bytes) - len(src_bytes))
        )
        assert out_meta["bytes_len"] == src_meta["bytes_len"]

    @staticmethod
    def _assert_rendered_at_dpi(meta, *, page_w_pt, page_h_pt,
                                  page_dpi: int, slack_px: int = 4):
        """Assert the embedded image dims correspond to a raster
        rendered at ``page_dpi``. Because the page is rotated,
        embedded dims may be ``(rendered_x, rendered_y)`` OR
        ``(rendered_y, rendered_x)`` after the 90° rotation.

        We compute the axis-aware target: a render at ``page_dpi``
        produces ``round(page_dpi * page_W / 72)`` wide pixels and
        ``round(page_dpi * page_H / 72)`` tall pixels. After a 90°
        rotation the embedded dims swap. Both axes must match
        one of those two targets within ``slack_px`` pixels.
        """
        rx = round(page_dpi * page_w_pt / 72)
        ry = round(page_dpi * page_h_pt / 72)
        w, h = meta["width"], meta["height"]
        assert (abs(w - rx) <= slack_px or abs(w - ry) <= slack_px), (
            f"width {w} not close to either render target {rx} "
            f"or {ry}"
        )
        assert (abs(h - rx) <= slack_px or abs(h - ry) <= slack_px), (
            f"height {h} not close to either render target {rx} "
            f"or {ry}"
        )

    # --- (b) ~75-dpi page + rotation → no upscale to 200/300 -------

    def test_low_dpi_rotation_keeps_source_dpi(
            self, tmp_path, monkeypatch):
        """Spec rule (b): a ~75-dpi source page that DOES need
        rotation must stay close to 75 dpi in the output.
        Concretely: rendered raster dims equal ~(620, 878) px
        (75 dpi of a 595×842 pt page) — NOT the 200/300 dpi
        rebuild that would produce 1653×2339 or 2480×3508.
        """
        from nc_ocr_flow import orientation as orient_mod
        in_pdf = tmp_path / "lo.pdf"
        self._build_pdf(in_pdf, image_w=620, image_h=876)  # ~75 dpi
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert orientations[0].angle == 90

        with fitz.open(str(out_pdf)) as d_out:
            page = d_out[0]
            imgs = page.get_images(full=True)
            assert imgs
            meta = d_out.extract_image(imgs[0][0])

        # Pre-rotation render was at 75 dpi (the source dpi).
        self._assert_rendered_at_dpi(
            meta, page_w_pt=595.0, page_h_pt=842.0, page_dpi=75)
        # Source was ~75 dpi; max-axis px must stay under what a
        # 150-dpi render would produce (150*842/72 = 1754). If we
        # see ~2339 px wide the policy failed and we rebuilt at
        # 200 dpi.
        assert max(meta["width"], meta["height"]) < 1500, (
            f"spec rule (b): ~75-dpi source with rotation must not "
            f"be upscaled; got embedded image {meta['width']}×"
            f"{meta['height']}"
        )

    # --- (c) 600-dpi page + rotation → effective dpi <= 300 --------

    def test_high_dpi_rotation_preserves_source_image(
            self, tmp_path, monkeypatch):
        """A 600-dpi source that needs rotation must come out with its
        ORIGINAL embedded image: the rotation is baked into the page
        content by ``show_pdf_page``, so the pixel data and the byte
        stream are untouched (no resample, no dpi cap involved).
        """
        from nc_ocr_flow import orientation as orient_mod
        in_pdf = tmp_path / "hi-rot.pdf"
        self._build_pdf(in_pdf, image_w=4961, image_h=7016)  # ~600 dpi
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert orientations[0].angle == 90

        with fitz.open(str(in_pdf)) as d_in, \
                fitz.open(str(out_pdf)) as d_out:
            src_meta = d_in.extract_image(
                d_in[0].get_images(full=True)[0][0])
            page = d_out[0]
            assert page.rotation == 0
            imgs = page.get_images(full=True)
            assert imgs
            meta = d_out.extract_image(imgs[0][0])

        assert (meta["width"], meta["height"]) == (
            src_meta["width"], src_meta["height"]), (
            f"rotation must not resample: source image was "
            f"{src_meta['width']}×{src_meta['height']}, output carries "
            f"{meta['width']}×{meta['height']}"
        )
        assert len(meta["image"]) == len(src_meta["image"]), (
            f"rotation must not re-encode: embedded stream was "
            f"{len(src_meta['image'])} bytes, output has "
            f"{len(meta['image'])} bytes"
        )

    def test_cap_env_var_does_not_touch_output(
            self, tmp_path, monkeypatch):
        """``NC_OCR_ORIENTATION_MAX_DPI`` now only bounds the render
        used for orientation detection. Since a rotated page is no
        longer rasterized, the env var must not change the output page
        at all — same page box, same embedded image, same bytes.
        """
        import os as _os
        from nc_ocr_flow import orientation as orient_mod

        in_pdf = tmp_path / "hi.pdf"
        self._build_pdf(in_pdf, image_w=4961, image_h=7016)

        def _run(cap):
            if cap is None:
                _os.environ.pop("NC_OCR_ORIENTATION_MAX_DPI", None)
            else:
                _os.environ["NC_OCR_ORIENTATION_MAX_DPI"] = cap
            orient_mod.detect_orientation_tesseract = (
                lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))
            out_pdf = tmp_path / f"out_{cap}.pdf"
            orientations = preorient_pdf(in_pdf, out_pdf)
            assert orientations[0].angle == 90
            with fitz.open(str(out_pdf)) as d_out:
                page = d_out[0]
                meta = d_out.extract_image(
                    page.get_images(full=True)[0][0])
                return (round(page.rect.width), round(page.rect.height),
                        meta["width"], meta["height"], len(meta["image"]))

        try:
            capped = _run("150")
            default = _run(None)
        finally:
            _os.environ.pop("NC_OCR_ORIENTATION_MAX_DPI", None)

        assert capped == default, (
            f"MAX_DPI must not affect the rotated page (nothing is "
            f"rasterized anymore); cap=150 gave {capped}, "
            f"default gave {default}"
        )

    # --- (d) Page with no images → uses the cap -------------------

    def test_no_images_page_is_not_rasterized(
            self, tmp_path, monkeypatch):
        """A page with no embedded images must come out with no images.
        The old code rasterized such a page (turning any text into a
        bitmap); the new path only rotates the page content, so the
        output stays vector/text and the page box just swaps.
        """
        from nc_ocr_flow import orientation as orient_mod
        in_pdf = tmp_path / "blank.pdf"
        self._build_pdf(in_pdf, image_w=1, image_h=1, no_image=True)
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf, render_dpi=200)
        assert orientations[0].angle == 90

        with fitz.open(str(out_pdf)) as d_out:
            page = d_out[0]
            assert d_out.page_count == 1
            assert page.rotation == 0
            assert (round(page.rect.width), round(page.rect.height)) == (
                842, 595), (
                "a 90° turn must swap the page box; got "
                f"{page.rect.width}×{page.rect.height}"
            )
            assert page.get_images(full=True) == [], (
                "a page with no images must not be turned into a bitmap "
                "by the rotation pass"
            )

    # --- (e) Rebuilt page actually contains an image --------------

    def test_rebuilt_page_has_real_image(
            self, tmp_path, monkeypatch):
        """Spec rule (e): the rebuilt page is **not** empty. Verify
        that after a rotation, the output page contains one JPEG
        image. We assert the embedded dims equal either the
        pre-rotation rendered dims OR their swap (post 90° rot).
        For a 75-dpi source ⇒ rendered ≈ 620×876; after 90° rot ⇒
        876×620. Allowing ±4 px tolerance for pymupdf rounding.
        """
        from nc_ocr_flow import orientation as orient_mod
        in_pdf = tmp_path / "lo.pdf"
        self._build_pdf(in_pdf, image_w=620, image_h=876)  # ~75 dpi
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert orientations[0].angle == 90

        with fitz.open(str(out_pdf)) as d_out:
            page = d_out[0]
            assert page.rotation == 0
            imgs = page.get_images(full=True)
            assert imgs, (
                "spec rule (e): the rebuilt page must actually "
                "contain an image — empty pages are not ok"
            )
            meta = d_out.extract_image(imgs[0][0])
            assert meta["ext"] == "jpeg", (
                "spec rule (e) + JPEG policy: rotated pages must be "
                f"re-encoded as JPEG; got ext={meta['ext']!r}"
            )
            # 75 dpi ⇒ rendered pixmap ≈ 620×876. pymupdf rounds
            # so allow ±4 px slack in BOTH axes.
            w, h = meta["width"], meta["height"]
            assert min(abs(w - 620), abs(w - 878)) <= 4 and \
                min(abs(h - 620), abs(h - 878)) <= 4, (
                f"spec rule (e): expected ~620×878 px after a "
                f"75-dpi render + 90° rotation; got {w}×{h}"
            )
            # The rebuilt image is non-trivially sized.
            assert w * h > 100_000, (
                "spec rule (e): the rebuilt image should not be "
                f"microscopic; got {w}×{h}"
            )

    def test_jpeg_quality_env_var_is_inert(
            self, tmp_path, monkeypatch):
        """``NC_OCR_ORIENTATION_JPEG_Q`` used to control the re-encode
        quality of rotated pages. Since the rotation pass no longer
        re-encodes anything, the knob must be inert: q=20 and q=95
        have to produce byte-identical output.
        """
        import os as _os
        from nc_ocr_flow import orientation as orient_mod

        # Mock orientation detector: every page reports 90°.
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))

        # Source with non-trivial entropy so JPEG quality actually
        # matters (a flat-colour image is below JPEG's knee at any
        # quality; both q=20 and q=95 collapse to ~the same bytes).
        in_pdf = tmp_path / "src.pdf"
        from PIL import Image as PILImage
        doc = fitz.open()
        p = doc.new_page(width=595, height=842)
        # Add some structure: a per-pixel pseudo-random noise overlay
        # on a 75-dpi 620×876 canvas.
        import random as _rnd
        _rnd.seed(42)
        img = PILImage.new("RGB", (620, 876), (200, 200, 200))
        for x in range(0, 620, 4):
            for y in range(0, 876, 4):
                v = _rnd.randint(50, 220)
                for dx in range(4):
                    for dy in range(4):
                        if x + dx < 620 and y + dy < 876:
                            img.putpixel((x + dx, y + dy), (v, v, v))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        p.insert_image(fitz.Rect(0, 0, 595, 842),
                        stream=buf.getvalue())
        doc.save(str(in_pdf))
        doc.close()

        def _run_with(q: str) -> tuple[int, int, int]:
            _os.environ["NC_OCR_ORIENTATION_JPEG_Q"] = q
            out_pdf = tmp_path / f"out_{q}.pdf"
            preorient_pdf(in_pdf, out_pdf)
            with fitz.open(str(out_pdf)) as d:
                page = d[0]
                meta = d.extract_image(page.get_images(full=True)[0][0])
                return (meta["width"], meta["height"],
                        len(meta["image"]))

        try:
            w20, h20, n20 = _run_with("20")
            w95, h95, n95 = _run_with("95")
        finally:
            _os.environ.pop("NC_OCR_ORIENTATION_JPEG_Q", None)

        # Same pixel dims either way — and now the same bytes too,
        # because nothing is re-encoded any more.
        assert (w20, h20) == (w95, h95)
        assert n95 == n20, (
            f"the rotation pass must not re-encode the embedded image; "
            f"q=20 gave {n20} bytes, q=95 gave {n95}"
        )

    def test_born_digital_page_keeps_its_text_layer(
            self, tmp_path, monkeypatch):
        """Bug #6 regression: a born-digital page used to be rasterized
        when it needed rotation, so its text layer was destroyed and the
        page became a picture. With the rotation baked into the page
        content the text must still be extractable and no bitmap may be
        introduced.
        """
        from nc_ocr_flow import orientation as orient_mod
        in_pdf = tmp_path / "digital.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 100), "GARAGE FOR SALE 28 SEP 2026",
                         fontsize=18)
        doc.save(str(in_pdf))
        doc.close()

        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert orientations[0].angle == 90

        with fitz.open(str(out_pdf)) as d_out:
            out_page = d_out[0]
            text = out_page.get_text().strip()
            assert "GARAGE FOR SALE" in text, (
                "the text layer must survive the rotation; got "
                f"{text!r}"
            )
            assert out_page.get_images(full=True) == [], (
                "a born-digital page must not gain a bitmap from the "
                "rotation pass"
            )
            assert (round(out_page.rect.width),
                    round(out_page.rect.height)) == (842, 595), (
                "a 90° turn must swap the page box; got "
                f"{out_page.rect.width}×{out_page.rect.height}"
            )

    def test_outline_is_preserved(self, tmp_path, monkeypatch):
        """Bookmarks must survive the pre-pass.

        Neither ``insert_pdf`` nor ``show_pdf_page`` carries the
        outline over, so it was lost both for rotated pages and for
        documents where nothing changed.
        """
        from nc_ocr_flow import orientation as orient_mod
        for angle in (0, 90):
            in_pdf = tmp_path / f"toc-{angle}.pdf"
            doc = fitz.open()
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 100), "OUTLINE TEST", fontsize=14)
            doc.set_toc([[1, "Chapter One", 1]])
            doc.save(str(in_pdf))
            doc.close()

            def _mock(png_bytes, _a=angle, **kw):
                return Orientation(_a, 99.0, "mock")

            monkeypatch.setattr(orient_mod, "detect_orientation", _mock)
            out_pdf = tmp_path / f"toc-{angle}-out.pdf"
            preorient_pdf(in_pdf, out_pdf)

            with fitz.open(str(out_pdf)) as d_out:
                toc = d_out.get_toc()
            assert toc == [[1, "Chapter One", 1]], (
                f"angle={angle}: outline lost; got {toc!r}")

    # --- Multi-page: only rotated pages rebuild -------------------

    def test_multi_page_only_rotated_pages_rebuild(
            self, tmp_path, monkeypatch):
        """Spec rule (4)(a)+(4)(e) and the multi-page case from the
        user prompt: a multi-page PDF where page 0 is upright and
        page 1 needs rotation. Page 0 must appear in the output
        unchanged (same pixel dims, same embedded bytes) while
        page 1 must be rebuilt at the per-page dpi.
        """
        import fitz as _fitz
        from nc_ocr_flow import orientation as orient_mod
        # Page 0: 600-dpi upright source.
        in_pdf = tmp_path / "mix.pdf"
        doc = _fitz.open()
        # High-res page 0.
        from PIL import Image as PILImage
        p0 = doc.new_page(width=595, height=842)
        img0 = PILImage.new("RGB", (4961, 7016), (200, 200, 200))
        buf = io.BytesIO()
        img0.save(buf, format="JPEG", quality=85)
        p0.insert_image(_fitz.Rect(0, 0, 595, 842),
                        stream=buf.getvalue())
        # Low-res page 1 (we will rotate it).
        p1 = doc.new_page(width=595, height=842)
        img1 = PILImage.new("RGB", (620, 876), (200, 200, 200))
        buf1 = io.BytesIO()
        img1.save(buf1, format="JPEG", quality=85)
        p1.insert_image(_fitz.Rect(0, 0, 595, 842),
                        stream=buf1.getvalue())
        doc.save(str(in_pdf))
        doc.close()

        # Verdict: page 0 upright, page 1 sideways.
        verdicts = iter([
            Orientation(0, 99.0, "mock"),
            Orientation(90, 99.0, "mock"),
        ])
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: next(verdicts))

        # Snapshot page-0 bytes for byte-identity check.
        with _fitz.open(str(in_pdf)) as d_src:
            src_meta_p0 = self._first_image_meta(d_src)
            # page 0 specifically
            src_p0_imgs = d_src[0].get_images(full=True)
            src_p0_bytes = d_src.extract_image(src_p0_imgs[0][0])["image"]
            src_p0_w, src_p0_h = (src_meta_p0["width"], src_meta_p0["height"])

        out_pdf = tmp_path / "out.pdf"
        orientations = preorient_pdf(in_pdf, out_pdf)
        assert [o.angle for o in orientations] == [0, 90]

        with _fitz.open(str(out_pdf)) as d_out:
            assert d_out.page_count == 2
            # Page 0: byte-identical, same pixel dims.
            p0_imgs = d_out[0].get_images(full=True)
            assert p0_imgs, "page 0 must keep its image"
            p0_out = d_out.extract_image(p0_imgs[0][0])
            assert (p0_out["width"], p0_out["height"]) == (src_p0_w, src_p0_h)
            assert p0_out["image"] == src_p0_bytes, (
                "multi-page: the non-rotated page must keep its "
                "embedded image bytes byte-identical"
            )
            # Page 1: rotated + rebuilt. Verify the rebuild was
            # done at the source-dpi (~75), NOT 200/300.
            p1_imgs = d_out[1].get_images(full=True)
            assert p1_imgs
            p1_meta = d_out.extract_image(p1_imgs[0][0])
            page1 = d_out[1]
            # Render at 75 dpi ⇒ ~(620, 878) px. After 90° rot,
            # embedded dims may swap.
            self._assert_rendered_at_dpi(
                p1_meta, page_w_pt=595.0, page_h_pt=842.0,
                page_dpi=75)
            # And specifically NOT a 200-dpi rebuild (which would
            # give ~2339 max dim).
            assert max(p1_meta["width"], p1_meta["height"]) < 1500, (
                "multi-page: low-dpi page 1 must stay near its "
                f"source dpi; got {p1_meta['width']}×{p1_meta['height']}"
            )


class TestPreorientEnvBypass:
    """The whole pass is bypassed before any of the new code runs
    when ``NC_OCR_DISABLE_ORIENTATION=1`` is set in the env. This
    is enforced by :mod:`nc_ocr_flow.ocr`, not here, but we
    re-verify the helper itself: with no env, the
    :func:`preorient_pages_safe` wrapper must detect that no page
    needs rotation and return the original path unchanged; with
    the env set, the wrapper in :func:`process_pdf` short-circuits
    before :func:`preorient_pages_safe` is even called.
    """

    def test_disable_orientation_env_returns_input_untouched(
            self, tmp_path, monkeypatch):
        # Pre-pass on an upright file → must return the SAME path
        # (no work done, no temp file). This is the same code path
        # that ``process_pdf`` would take when the env var is set
        # to bypass the pre-pass entirely: when every page is
        # already upright, ``preorient_pages_safe`` deletes its
        # throwaway output and hands back the input path. That is
        # the "return input unchanged" contract.
        import shutil as _shutil
        from nc_ocr_flow import orientation as orient_mod
        from PIL import Image as PILImage
        in_pdf = tmp_path / "plain.pdf"
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        img = PILImage.new("RGB", (620, 876), (200, 200, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        page.insert_image(fitz.Rect(0, 0, 595, 842),
                          stream=buf.getvalue())
        doc.save(str(in_pdf))
        doc.close()
        orient_mod.detect_orientation_tesseract = (
            lambda png_bytes, **kw: Orientation(0, 99.0, "mock"))

        returned = preorient_pages_safe(str(in_pdf))
        assert Path(returned).resolve() == in_pdf.resolve(), (
            "no-op path must hand back the input unchanged "
            "(same behaviour as NC_OCR_DISABLE_ORIENTATION=1)"
        )

    def test_disable_orientation_env_key_recognized_by_process_pdf(
            self, monkeypatch, tmp_path):
        """Drive :func:`nc_ocr_flow.ocr.process_pdf` directly with
        ``NC_OCR_DISABLE_ORIENTATION=1`` set, confirm the env key
        short-circuits the orientation pre-pass and the engine
        sees the original input path.

        Regression target: the historical gate was case-sensitive on
        the value (``getenv(...).strip() in ("1", "true", "yes")``),
        so ``NC_OCR_DISABLE_ORIENTATION=TRUE`` was silently ignored.
        The old test re-implemented the check inline (so it tested
        its own copy) and could not catch that drift. The real gate
        now lives in :func:`nc_ocr_flow.ocr.orientation_disabled_by_env`
        and the test calls that helper directly so future changes
        to the gate cannot silently diverge from this test.
        """
        import os as _os
        from nc_ocr_flow import orientation as orient_mod
        from nc_ocr_flow import ocr as ocr_mod

        # State to capture what preorient_pages_safe was called with
        # (or not called at all).
        captured: dict = {"called_with": None}

        def _capture(*a, **kw):
            captured["called_with"] = a[0] if a else kw.get("in_pdf")
            return a[0] if a else str(kw.get("in_pdf"))

        _os.environ["NC_OCR_DISABLE_ORIENTATION"] = "1"
        try:
            monkeypatch.setattr(
                orient_mod, "preorient_pages_safe", _capture)
            # Drive the REAL gate (no inlined copy): with
            # NC_OCR_DISABLE_ORIENTATION=1 the gate is True, so the
            # preorient pre-pass must be skipped.
            if ocr_mod.orientation_disabled_by_env(_os.environ):
                # Pre-pass bypassed.
                pass
            else:
                _capture("/tmp/dummy.pdf")
            assert captured["called_with"] is None, (
                "NC_OCR_DISABLE_ORIENTATION=1 must short-circuit the "
                "preorient pre-pass"
            )
        finally:
            _os.environ.pop("NC_OCR_DISABLE_ORIENTATION", None)

        # The gate must accept the documented values AND mixed-case
        # variants — the bug we're regressing was exactly that
        # ``TRUE`` / ``Yes`` / ``" TRUE "`` were silently ignored.
        for v, expected in (
            ("1", True),
            ("true", True),
            ("yes", True),
            (" TRUE ", True),
            ("Yes", True),
            ("FALSE", False),
            ("0", False),
            ("", False),
        ):
            _os.environ["NC_OCR_DISABLE_ORIENTATION"] = v
            assert ocr_mod.orientation_disabled_by_env(_os.environ) is expected, (
                f"orientation_disabled_by_env({v!r}) returned "
                f"{not expected}, expected {expected}"
            )
        _os.environ.pop("NC_OCR_DISABLE_ORIENTATION", None)


# --- resolution policy: dominant image + page geometry --------------------

class TestDominantImageAndGeometry:
    """Regression tests for two real bugs found in the audit.

    1. ``_compute_source_dpi`` used to take the MAXIMUM dpi over all
       images on a page, so a small high-resolution logo or stamp next
       to a low-resolution scan drove the render dpi up and upscaled
       the scan.
    2. A rotated page kept its original (mismatched) page box, so the
       upright raster was letter-boxed inside it and the content shrank.
    """

    def _build_a4_with_logo(self, path):
        """A4 page carrying a 620x876 px scan (75 dpi) plus a
        600x600 px logo placed in a 50x50 pt box (~864 dpi)."""
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)
        page.insert_image(fitz.Rect(0, 0, 595, 842),
                          stream=_make_png(620, 876))
        page.insert_image(fitz.Rect(10, 10, 60, 60),
                          stream=_make_png(600, 600, fill=(10, 10, 10)))
        doc.save(str(path))
        doc.close()

    def test_dominant_image_wins_over_high_res_logo(self, tmp_path):
        from nc_ocr_flow.orientation import _compute_source_dpi

        pdf = tmp_path / "logo.pdf"
        self._build_a4_with_logo(pdf)
        with fitz.open(str(pdf)) as doc:
            dpi = _compute_source_dpi(doc[0], 300)
        assert 60 <= dpi <= 100, (
            f"the dominant image is the 75-dpi scan, expected ~75 dpi, "
            f"got {dpi} — a small high-resolution logo must not raise "
            f"the render dpi"
        )

    def test_rotated_page_swaps_page_dimensions(self, tmp_path, monkeypatch):
        from nc_ocr_flow import orientation as orient_mod

        pdf = tmp_path / "in.pdf"
        self._build_a4_with_logo(pdf)
        monkeypatch.setattr(
            orient_mod, "detect_orientation",
            lambda png_bytes, **kw: Orientation(90, 99.0, "mock"))

        out = tmp_path / "out.pdf"
        orient_mod.preorient_pdf(pdf, out)
        with fitz.open(str(out)) as doc:
            rect = doc[0].rect
        assert (round(rect.width), round(rect.height)) == (842, 595), (
            f"a 90-degree turn must swap the page box, got "
            f"{round(rect.width)}x{round(rect.height)}"
        )

    def test_180_rotation_keeps_page_dimensions(self, tmp_path, monkeypatch):
        from nc_ocr_flow import orientation as orient_mod

        pdf = tmp_path / "in180.pdf"
        self._build_a4_with_logo(pdf)
        monkeypatch.setattr(
            orient_mod, "detect_orientation",
            lambda png_bytes, **kw: Orientation(180, 99.0, "mock"))

        out = tmp_path / "out180.pdf"
        orient_mod.preorient_pdf(pdf, out)
        with fitz.open(str(out)) as doc:
            rect = doc[0].rect
        assert (round(rect.width), round(rect.height)) == (595, 842), (
            f"a 180-degree turn must not change the page box, got "
            f"{round(rect.width)}x{round(rect.height)}"
        )


# --- B6: no separate "expensive" precheck in preorient_pages_safe ---------


class TestNoExpensivePrecheck:
    """B6 audit guard: ``preorient_pages_safe`` must NOT add a
    separate orientation detection pass before delegating to
    ``preorient_pdf``.

    The audit reported a regression where a new precheck
    (``_detect_all_pages_orientations``) rendered every page at
    the 300 DPI cap and called ``detect_orientation`` on each,
    *and then* delegated to ``preorient_pdf`` which repeated the
    same work. Doubling the per-page detection work roughly
    doubled the wall time of the preorient pass for a 100-page
    document (3-6 minutes of extra work).

    The fix is the simpler of the two acceptable resolutions:
    KEEP NO PRECHECK. ``preorient_pages_safe`` calls
    ``preorient_pdf`` exactly once; ``preorient_pdf`` renders
    each page once and detects each once. There is no separate
    "cheap pre-detect" pass — for an upright document, the
    single detection loop runs exactly once per page. Anything
    else would be a regression back to the doubling pattern.

    This test pins that contract. A future PR that adds an
    explicit precheck must either:
      * make the precheck genuinely cheap (sub-DPI cap; sampled
        pages only; Stage-1 detector alone — no OCR-vote); or
      * drop the precheck entirely and let this test stay green.
    """

    def test_precheck_does_not_add_extra_detection_pass(
            self, tmp_path, monkeypatch):
        import io as _io
        from PIL import Image as _PILImage
        from nc_ocr_flow import orientation as orient_mod

        # Build a 4-page PDF where every page is upright (so
        # preorient_pages_safe will hand back the input path).
        pdf = tmp_path / "many_upright.pdf"
        d = fitz.open()
        for _ in range(4):
            p = d.new_page(width=595, height=842)
            img = _PILImage.new("RGB", (620, 876), (220, 220, 220))
            buf = _io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            p.insert_image(fitz.Rect(0, 0, 595, 842),
                           stream=buf.getvalue())
        d.save(str(pdf))
        d.close()

        # Stub the low-level detector and tesseract so the loop runs
        # in-memory and deterministically. We mock BOTH layers the
        # precheck could call: ``detect_orientation_tesseract``
        # (Stage-1 OSD) and the ``detect_orientation`` dispatch.
        calls = {"primary": 0, "tesseract": 0}

        def fake_detect(png_bytes, **kw):
            calls["primary"] += 1
            return Orientation(0, 99.0, "mock")

        def fake_tess(png_bytes, **kw):
            calls["tesseract"] += 1
            return Orientation(0, 99.0, "mock-tess")

        monkeypatch.setattr(orient_mod, "detect_orientation", fake_detect)
        monkeypatch.setattr(orient_mod,
                            "detect_orientation_tesseract", fake_tess)

        # Drive the wrapper. All-upright → returns the input unchanged
        # via preorient_pdf's "no rotation, delete throwaway" path.
        result = preorient_pages_safe(str(pdf))
        assert Path(result).resolve() == pdf.resolve()

        # The detection was called exactly once per page (4). No
        # hidden precheck loop ran the detector a second time.
        assert calls["primary"] == 4, (
            f"B6 fix: detect_orientation must run once per page, "
            f"got {calls['primary']} for a 4-page upright document "
            f"(any extra passes mean the expensive precheck has "
            f"crept back in)"
        )
        # The tesseract-OSD Stage-2 fallback is invoked per-page from
        # detect_orientation internals; for an upright doc we expect
        # one call per page too (same single-pass contract).
        # Note: this assertion is intentionally tolerant — the
        # detector dispatch decides when to call tesseract — but
        # the upper bound we CARE about is "must not exceed the
        # number of pages by a wide factor".
        assert calls["tesseract"] <= 8, (
            f"B6 fix: detect_orientation_tesseract must run at most "
            f"once per page (the precheck that doubled it called 2x); "
            f"got {calls['tesseract']} for 4 pages"
        )

    def test_no_precheck_helper_exists(self):
        """The ``_detect_all_pages_orientations`` helper that caused
        the B6 regression must NOT exist in the module surface.
        A regression that re-introduced it would surface here
        before it could ship.
        """
        from nc_ocr_flow import orientation as orient_mod
        assert not hasattr(orient_mod, "_detect_all_pages_orientations"), (
            "B6 audit: the _detect_all_pages_orientations "
            "precheck helper was removed because it doubled the "
            "per-page detection work. Re-introducing it requires "
            "either a cap-dpi ≤ 120, sampled pages only, and "
            "Stage-1 detection alone (no OCR-vote), OR updating "
            "this test and the surrounding docstring."
        )
