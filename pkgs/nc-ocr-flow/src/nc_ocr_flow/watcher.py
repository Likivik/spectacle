"""Inotify watcher: picks up new files in NC data dir, queues for OCR."""
from __future__ import annotations

import argparse
import json
import logging
import multiprocessing as mp
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
IGNORED_DIRS = {"/Photos", "/.trash", "/files_external"}
FAILED_DIR = os.environ.get("NC_OCR_FAILED_DIR", "/var/lib/nc-ocr/failed")
SIDECAR_DIR = os.environ.get("NC_OCR_SIDECAR_DIR", "/var/lib/nc-ocr/sidecars")
QUEUE_MAX = int(os.environ.get("NC_OCR_QUEUE_MAX", "1000"))
WORKERS = int(os.environ.get("NC_OCR_WORKERS", "2"))
POLL_INTERVAL = float(os.environ.get("NC_OCR_POLL_INTERVAL", "2.0"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".heic"}
PDF_EXTS = {".pdf"}


def _should_process(path: Path) -> bool:
    if not path.is_file():
        return False
    ext = path.suffix.lower()
    if ext not in IMAGE_EXTS and ext not in PDF_EXTS:
        return False
    rel = str(path).lower()
    for skip in IGNORED_DIRS:
        if skip.lower() in rel:
            return False
    return True


def _image_to_pdf(image_path: Path) -> Path:
    import img2pdf
    target = image_path.with_suffix(".pdf")
    with target.open("wb") as f:
        f.write(img2pdf.convert(str(image_path)))
    return target


def _write_sidecar_txt(pdf_path: Path, sidecar_dir: Path) -> Path:
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    sidecar = sidecar_dir / f"{pdf_path.stem}.txt"
    sidecar.write_text("")
    return sidecar


def _process_one(path_str: str) -> dict:
    path = Path(path_str)
    try:
        ext = path.suffix.lower()
        if ext in IMAGE_EXTS:
            log.info("classifying image: %s", path)
            result = classify(str(path))
            if not result.is_document:
                log.info("skipping photo: %s (reason=%s)", path, result.reason)
                return {"path": str(path), "skipped": True, "reason": result.reason}
            log.info("converting to PDF: %s (reason=%s)", path, result.reason)
            pdf_path = _image_to_pdf(path)
            path = pdf_path
            ext = ".pdf"

        if ext in PDF_EXTS:
            log.info("OCR-ing PDF: %s", path)
            result = process_pdf(str(path))
            sidecar = _write_sidecar_txt(Path(result["output_pdf"]), Path(SIDECAR_DIR))
            return {
                "path": str(path),
                "output_pdf": result["output_pdf"],
                "sidecar": str(sidecar),
                "vlm_pages": result["vlm_pages"],
            }
    except Exception as exc:
        log.exception("processing failed for %s", path)
        FAILED = Path(FAILED_DIR)
        FAILED.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, FAILED / path.name)
        except OSError:
            pass
        return {"path": str(path), "error": str(exc)}

    return {"path": str(path), "skipped": True, "reason": "unknown_extension"}


def _watch_loop(queue: Queue) -> None:
    import pyinotify

    wm = pyinotify.WatchManager()
    mask = pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO

    class Handler(pyinotify.ProcessEvent):
        def process_IN_CLOSE_WRITE(self, event):
            if _should_process(Path(event.pathname)):
                queue.put(event.pathname)

        def process_IN_MOVED_TO(self, event):
            if _should_process(Path(event.pathname)):
                queue.put(event.pathname)

    notifier = pyinotify.Notifier(wm, Handler())
    for subdir in WATCH_DIRS:
        watch_path = Path(NC_DATA_DIR) / subdir.lstrip("/")
        if watch_path.exists():
            wm.add_watch(str(watch_path), mask, recursive=True)
            log.info("watching: %s", watch_path)

    log.info("inotify loop started")
    notifier.loop()


def _worker_loop(queue: Queue) -> None:
    while True:
        try:
            path = queue.get(timeout=POLL_INTERVAL)
        except Empty:
            continue
        try:
            result = _process_one(path)
            log.info("processed: %s", json.dumps(result))
        finally:
            queue.task_done()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nextcloud OCR pipeline watcher")
    parser.add_argument("--validate-only", action="store_true", help="exit after one pass")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    queue: Queue = Queue(maxsize=QUEUE_MAX)

    if args.validate_only:
        log.info("validate-only mode: would watch %s/%s", NC_DATA_DIR, WATCH_DIRS)
        return 0

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
