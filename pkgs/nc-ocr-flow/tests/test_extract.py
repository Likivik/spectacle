"""Tests for nc-ocr-extract: restore the original image out of our own PDFs.

The guarantee under test is byte-exactness — the extracted image must be the
exact file that was uploaded, EXIF included — because ``img2pdf`` stores the
JPEG bitstream untouched and PyMuPDF re-saves without re-encoding it.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import img2pdf
import pymupdf
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nc_ocr_flow import extract as ex  # noqa: E402

EXIF_SENTINEL = b"SENTINEL-EXIF"


def _jpeg_with_exif(dest: Path) -> bytes:
    """A small JPEG carrying a synthetic APP1/Exif block we can look for."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "source page", fontsize=18)
    page.get_pixmap(dpi=100).save(str(dest))
    raw = dest.read_bytes()
    # A *valid* minimal Exif block, or PIL/img2pdf refuse to parse the JPEG:
    # "Exif\0\0" + little-endian TIFF header + IFD0 with one ImageDescription
    # entry pointing at our sentinel string.
    desc = EXIF_SENTINEL + b"\x00"          # ASCII, NUL-terminated
    tiff = b"II*\x00" + (8).to_bytes(4, "little")          # header, IFD0 at 8
    tiff += (1).to_bytes(2, "little")                       # one entry
    tiff += (0x010E).to_bytes(2, "little")                  # ImageDescription
    tiff += (2).to_bytes(2, "little")                       # ASCII
    tiff += len(desc).to_bytes(4, "little")                 # count
    tiff += (26).to_bytes(4, "little")                      # value offset
    tiff += (0).to_bytes(4, "little")                       # no IFD1
    assert len(tiff) == 26, len(tiff)
    tiff += desc
    payload = b"Exif\x00\x00" + tiff
    seg = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload
    out = raw[:2] + seg + raw[2:]
    dest.write_bytes(out)
    return out


def _ocr_style_pdf(jpg: Path, pdf: Path, producer: str = "nc-ocr-flow 0.4 (engine=google)") -> None:
    """Reproduce what the image branch does: img2pdf, then invisible text + save."""
    pdf.write_bytes(img2pdf.convert(str(jpg)))
    doc = pymupdf.open(str(pdf))
    page = doc[0]
    page.insert_text((20, 20), "invisible ocr text", fontsize=6, render_mode=3)
    doc.set_metadata({"producer": producer})
    doc.save(str(pdf) + ".tmp", garbage=4, deflate=True)
    doc.close()
    Path(str(pdf) + ".tmp").replace(pdf)


@pytest.fixture()
def ours(tmp_path):
    jpg = tmp_path / "photo.jpg"
    original = _jpeg_with_exif(jpg)
    pdf = tmp_path / "photo.pdf"
    _ocr_style_pdf(jpg, pdf)
    jpg.unlink()  # the service deletes the source image; the PDF is what remains
    return pdf, original


def test_extracted_bytes_are_the_original(ours, tmp_path):
    pdf, original = ours
    res = ex.extract_image(pdf)
    assert res["status"] == "extracted", res
    got = Path(res["path"]).read_bytes()
    assert hashlib.sha256(got).hexdigest() == hashlib.sha256(original).hexdigest()
    assert EXIF_SENTINEL in got, "EXIF block must survive the round trip"
    assert Path(res["path"]).name == "photo.jpg"


def test_original_pdf_is_kept(ours):
    pdf, _ = ours
    before = pdf.read_bytes()
    ex.extract_image(pdf)
    assert pdf.read_bytes() == before, "extraction must never modify the PDF"


def test_refuses_to_overwrite_without_flag(ours):
    pdf, _ = ours
    assert ex.extract_image(pdf)["status"] == "extracted"
    second = ex.extract_image(pdf)
    assert second["status"] == "exists"
    assert ex.extract_image(pdf, overwrite=True)["status"] == "extracted"


def test_skips_pdf_we_did_not_produce(tmp_path):
    jpg = tmp_path / "plain.jpg"
    _jpeg_with_exif(jpg)
    foreign = tmp_path / "foreign.pdf"
    foreign.write_bytes(img2pdf.convert(str(jpg)))
    res = ex.extract_image(foreign)
    assert res["status"] == "skipped"
    assert res["why"]


def test_force_overrides_the_producer_check(tmp_path):
    jpg = tmp_path / "plain.jpg"
    original = _jpeg_with_exif(jpg)
    foreign = tmp_path / "foreign.pdf"
    foreign.write_bytes(img2pdf.convert(str(jpg)))
    res = ex.extract_image(foreign, force=True)
    assert res["status"] == "extracted"
    assert Path(res["path"]).read_bytes() == original


def test_dry_run_writes_nothing(ours):
    pdf, _ = ours
    res = ex.extract_image(pdf, dry_run=True)
    assert res["status"] == "dry_run"
    assert res["bytes"] > 0
    assert not Path(res["path"]).exists()


def test_out_dir(tmp_path, ours):
    pdf, _ = ours
    out = tmp_path / "restored"
    res = ex.extract_image(pdf, out_dir=out)
    assert Path(res["path"]).parent == out
    assert Path(res["path"]).exists()


def test_cli_walks_a_folder(tmp_path, ours):
    pdf, _ = ours
    sub = pdf.parent / "nested"
    sub.mkdir()
    _jpeg_with_exif(tmp_path / "second.jpg")
    _ocr_style_pdf(tmp_path / "second.jpg", sub / "second.pdf")
    rc = ex.main([str(pdf.parent), "--quiet", "--overwrite"])
    assert rc == 0
    assert (pdf.parent / "photo.jpg").exists()


def test_pdf_without_a_page_raster_is_reported(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "born digital, no image", fontsize=12)
    doc.set_metadata({"producer": "nc-ocr-flow 0.4 (engine=google)"})
    pdf = tmp_path / "text-only.pdf"
    doc.save(str(pdf))
    res = ex.extract_image(pdf)
    assert res["status"] == "no_image", res
