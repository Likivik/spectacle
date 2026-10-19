"""Restore the original image out of a PDF this service produced.

Why this exists
---------------
The image branch converts an image to a PDF so the OCR text can live in a
text layer (a JPEG cannot carry selectable text). That conversion is
lossless: ``img2pdf`` stores the source JPEG bitstream untouched
(DCTDecode), and PyMuPDF re-saves without re-encoding it. Verified: the
extracted bytes are sha256-identical to the original upload, EXIF
included.

So this is a restore, not a re-render: the file you get back is the file
that was uploaded.

Usage
-----
    nc-ocr-extract path/to/file.pdf               # writes file.jpeg next to it
    nc-ocr-extract path/to/folder                 # every PDF we produced inside
    nc-ocr-extract a.pdf b.pdf --out-dir /tmp/x   # elsewhere, same names
    nc-ocr-extract a.pdf --overwrite              # replace an existing image
    nc-ocr-extract a.pdf --dry-run                # say what it would do

Refuses to touch a PDF it cannot prove it produced (``producer`` metadata
does not name nc-ocr-flow), unless ``--force`` is given: extracting "the
first image" of an arbitrary PDF would happily hand back a logo.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pymupdf

PRODUCER_MARK = "nc-ocr-flow"
#: An image has to cover this share of the page to count as the page
#: raster rather than a logo or stamp.
_MIN_COVERAGE = 0.30


def _looks_like_ours(doc: pymupdf.Document) -> bool:
    producer = ((doc.metadata or {}).get("producer") or "").lower()
    return PRODUCER_MARK in producer


def _page_raster(doc: pymupdf.Document) -> tuple[int, int] | None:
    """Return ``(pixels, xref)`` of the biggest image covering enough of page 1."""
    page = doc[0]
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    best = None
    for img in page.get_images(full=True):
        xref, width, height = img[0], img[2], img[3]
        if not width or not height:
            continue
        # image pixels -> page area, via the placement rect when we have one
        rects = [d["bbox"] for d in page.get_image_info(xrefs=True) if d.get("xref") == xref]
        coverage = 0.0
        for bbox in rects:
            r = pymupdf.Rect(bbox)
            coverage = max(coverage, abs(r.width * r.height) / page_area)
        if coverage < _MIN_COVERAGE:
            continue
        if best is None or width * height > best[0]:
            best = (width * height, xref)
    return best


def extract_image(pdf: Path, out_dir: Path | None = None, overwrite: bool = False,
                  force: bool = False, dry_run: bool = False) -> dict:
    """Extract the page raster to an image file beside ``pdf``.

    Returns a dict: ``status`` is one of ``extracted``, ``skipped``
    (not ours), ``no_image``, ``exists``, ``dry_run``; plus ``path``,
    ``bytes`` and ``sha256``/``source_sha256`` when it ran.
    """
    pdf = Path(pdf)
    doc = pymupdf.open(str(pdf))
    try:
        if not force and not _looks_like_ours(doc):
            return {"status": "skipped", "pdf": str(pdf),
                    "why": "producer is not nc-ocr-flow (use --force)"}
        found = _page_raster(doc)
        if not found:
            return {"status": "no_image", "pdf": str(pdf),
                    "why": "no image covers >=%d%% of page 1" % int(_MIN_COVERAGE * 100)}
        info = doc.extract_image(found[1])
    finally:
        doc.close()

    ext = info["ext"] if info["ext"] != "jpeg" else "jpg"
    target_dir = Path(out_dir) if out_dir else pdf.parent
    target = target_dir / (pdf.stem + "." + ext)
    sha = hashlib.sha256(info["image"]).hexdigest()
    if target.exists() and not overwrite:
        return {"status": "exists", "pdf": str(pdf), "path": str(target),
                "why": "target exists (use --overwrite)"}
    if dry_run:
        return {"status": "dry_run", "pdf": str(pdf), "path": str(target),
                "bytes": len(info["image"]), "sha256": sha}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(info["image"])
    return {"status": "extracted", "pdf": str(pdf), "path": str(target),
            "bytes": len(info["image"]), "sha256": sha}


def _iter_pdfs(targets: list[str]) -> list[Path]:
    out: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*.pdf") if q.is_file()))
        elif p.is_file():
            out.append(p)
        else:
            print(f"nc-ocr-extract: no such file or directory: {t}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="nc-ocr-extract",
        description="Restore the original image from a PDF produced by nc-ocr-flow.",
    )
    ap.add_argument("targets", nargs="+", help="PDF files and/or folders (recursive)",
                    metavar="PATH")
    ap.add_argument("--out-dir", help="write images here instead of next to each PDF")
    ap.add_argument("--overwrite", action="store_true", help="replace an existing image file")
    ap.add_argument("--force", action="store_true",
                    help="extract even if the PDF was not produced by nc-ocr-flow")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--quiet", action="store_true", help="only print errors")
    args = ap.parse_args(argv)

    pdfs = _iter_pdfs(args.targets)
    if not pdfs:
        print("nc-ocr-extract: nothing to do", file=sys.stderr)
        return 1

    counts: dict[str, int] = {}
    for pdf in pdfs:
        res = extract_image(pdf, out_dir=args.out_dir, overwrite=args.overwrite,
                            force=args.force, dry_run=args.dry_run)
        counts[res["status"]] = counts.get(res["status"], 0) + 1
        if args.quiet and res["status"] in ("extracted", "dry_run"):
            continue
        line = f"{res['status']:9} {res['pdf']}"
        if res.get("path") and res["status"] in ("extracted", "dry_run"):
            line += f" -> {res['path']} ({res['bytes']} B, sha256 {res['sha256'][:12]})"
        elif res.get("why"):
            line += f"  [{res['why']}]"
        print(line)

    print("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return 0 if counts.get("extracted") or counts.get("dry_run") else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
