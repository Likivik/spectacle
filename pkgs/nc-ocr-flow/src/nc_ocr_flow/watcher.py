"""Inotify watcher: picks up new files in NC data dir, routes to OCR.

  - PDF → process_pdf (tesseract + Surya fallback)
  - Image → classify → document? → img2pdf → process_pdf → replace
  - Image → photo? → skip (stays in NC untouched)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from queue import Empty, Queue

from .classifier import classify
from .ocr import process_pdf

log = logging.getLogger(__name__)

NC_DATA_DIR = os.environ.get("NC_DATA_DIR", "/tank/nextcloud/data")
WATCH_DIRS = os.environ.get("NC_WATCH_DIRS", "/Documents,/Inbox,/Scans").split(",")
FAILED_DIR = os.environ.get("NC_OCR_FAILED_DIR", "/var/lib/nc-ocr/failed")
WORKERS = int(os.environ.get("NC_OCR_WORKERS", "2"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".heic"}
PDF_EXTS = {".pdf"}


def _should_process(path: Path) -> bool:
    """Check if file should be processed (extension + not already OCR'd)."""
    if not path.is_file():
        return False
    ext = path.suffix.lower()
    if ext not in IMAGE_EXTS and ext not in PDF_EXTS:
        return False
    # Skip files already OCR'd (sidecar exists)
    if path.with_suffix(".ocr.pdf").exists():
        return False
    return True


def _replace_in_nc(original: Path, ocr_pdf: Path) -> None:
    """Replace original file with OCR'd PDF in NC (versioning preserves original).

    For images: rename .jpg → .pdf (NC versioning keeps .jpg as old version)
    For PDFs: overwrite in place (NC versioning preserves old version)
    """
    if original.suffix.lower() in IMAGE_EXTS:
        # Image → PDF: move original to .old, place PDF at .pdf name
        target = original.with_suffix(".pdf")
        original.rename(original.with_suffix(".original"))
        shutil.move(str(ocr_pdf), str(target))
        log.info("replaced image with PDF: %s → %s", original, target)
    else:
        # PDF → PDF: overwrite in place
        shutil.copy2(str(ocr_pdf), str(original))
        ocr_pdf.unlink()
        log.info("replaced PDF: %s", original)


def _image_to_pdf(image_path: Path) -> Path:
    """Convert image to PDF using img2pdf."""
    import img2pdf
    target = image_path.with_suffix(".pdf")
    with target.open("wb") as f:
        f.write(img2pdf.convert(str(image_path)))
    return target


def _process_one(path_str: str) -> dict:
    """Process a single file. Returns result dict for logging."""
    path = Path(path_str)
    try:
        ext = path.suffix.lower()

        if ext in IMAGE_EXTS:
            log.info("classifying image: %s", path)
            cls = classify(path)
            log.info("classify: is_document=%s reason=%s", cls.is_document, cls.reason)

            if not cls.is_document:
                log.info("skipping photo: %s", path)
                return {"path": str(path), "skipped": True, "reason": cls.reason}

            # Document image: convert to PDF, OCR
            pdf_path = _image_to_pdf(path)
            result = process_pdf(pdf_path)
            _replace_in_nc(path, Path(result.output_pdf))
            return {
                "path": str(path), "output": result.output_pdf,
                "vlm_pages": result.vlm_pages,
            }

        if ext in PDF_EXTS:
            log.info("OCR-ing PDF: %s", path)
            result = process_pdf(path)
            _replace_in_nc(path, Path(result.output_pdf))
            return {
                "path": str(path), "output": result.output_pdf,
                "vlm_pages": result.vlm_pages,
            }

    except Exception as exc:
        # Quarantine failed file
        failed = Path(FAILED_DIR)
        failed.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, failed / path.name)
        except OSError:
            pass
        log.error("processing failed for %s: %s", path, exc)
        return {"path": str(path), "error": str(exc)}

    return {"path": str(path), "skipped": True, "reason": "unknown_ext"}


# --- Watcher (inotify) -------------------------------------------------------

def _watch_loop(queue: Queue) -> None:
    """Watch WATCH_DIRS for new files via inotify_simple."""
    from inotify_simple import INotify, flags

    inotify = INotify()
    mask = flags.CLOSE_WRITE | flags.MOVED_TO | flags.CREATE | flags.ISDIR
    wd_to_path: dict[int, str] = {}

    def _add_watch(path: str) -> None:
        try:
            wd = inotify.add_watch(path, mask)
            wd_to_path[wd] = path
        except OSError:
            return
        for entry in Path(path).iterdir():
            if entry.is_dir():
                _add_watch(str(entry))

    for subdir in WATCH_DIRS:
        watch_path = Path(NC_DATA_DIR) / subdir.lstrip("/")
        if watch_path.exists():
            _add_watch(str(watch_path))
            log.info("watching %s", watch_path)
        else:
            log.warning("watch dir missing: %s", watch_path)

    while True:
        for event in inotify.read(timeout=1000):
            if event.mask & flags.ISDIR:
                parent = wd_to_path.get(event.wd, "")
                if parent and event.name:
                    new_dir = str(Path(parent) / event.name)
                    if Path(new_dir).is_dir():
                        _add_watch(new_dir)
                continue
            if event.mask & (flags.CLOSE_WRITE | flags.MOVED_TO):
                parent = wd_to_path.get(event.wd, "")
                if parent and event.name:
                    full = str(Path(parent) / event.name)
                    if _should_process(Path(full)):
                        queue.put(full)


def _worker_loop(queue: Queue) -> None:
    while True:
        try:
            path = queue.get(timeout=5.0)
        except Empty:
            continue
        try:
            result = _process_one(path)
            log.info("done: %s", json.dumps(result))
        finally:
            queue.task_done()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nextcloud OCR pipeline watcher")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--once", action="store_true",
                        help="process existing files, then exit")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    log.info("nc-ocr-flow: data=%s watch=%s workers=%d",
             NC_DATA_DIR, WATCH_DIRS, WORKERS)

    if args.validate_only:
        log.info("validate-only OK")
        return 0

    queue: Queue = Queue(maxsize=1000)

    if args.once:
        for subdir in WATCH_DIRS:
            watch_path = Path(NC_DATA_DIR) / subdir.lstrip("/")
            if watch_path.exists():
                for p in watch_path.rglob("*"):
                    if _should_process(p):
                        result = _process_one(str(p))
                        log.info("done: %s", json.dumps(result))
        return 0

    import multiprocessing as mp
    workers = [
        mp.Process(target=_worker_loop, args=(queue,), daemon=True)
        for _ in range(WORKERS)
    ]
    for w in workers:
        w.start()

    try:
        _watch_loop(queue)
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        for w in workers:
            w.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
