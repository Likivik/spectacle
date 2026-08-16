"""Webhook receiver: NC fires on file create/write, we OCR via WebDAV.

Flow:
  1. NC webhook POST → NodeCreatedEvent / NodeWrittenEvent
  2. Download file via WebDAV GET
  3. PDF → ocr.py (tesseract + Surya fallback)
     Image → classify → document? → img2pdf → ocr.py → upload as .pdf
  4. Upload result via WebDAV PUT (NC creates new version automatically)
  5. Loop prevention: skip files we just processed (in-memory ID set + TTL)
"""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .classifier import classify
from .ocr import process_pdf

log = logging.getLogger(__name__)

# --- Config from environment ---
NC_URL = os.environ.get("NC_OCR_NC_URL", "http://localhost").rstrip("/")
NC_USER = os.environ.get("NC_OCR_NC_USER", "likivik")

def _read_secret(env_var: str) -> str:
    """Read secret from env var directly or from file (env var + '_FILE')."""
    val = os.environ.get(env_var)
    if val:
        return val
    file_var = f"{env_var}_FILE"
    path = os.environ.get(file_var)
    if path:
        return Path(path).read_text().strip()
    return ""

NC_PASSWORD = _read_secret("NC_OCR_NC_PASSWORD")
WEBHOOK_SECRET = _read_secret("NC_OCR_WEBHOOK_SECRET")
LISTEN_HOST = os.environ.get("NC_OCR_LISTEN_HOST", "127.0.0.1")
LISTEN_PORT = int(os.environ.get("NC_OCR_LISTEN_PORT", "8095"))

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tiff", ".heic"}
PDF_EXTS = {".pdf"}
PROCESSABLE_EXTS = IMAGE_EXTS | PDF_EXTS

# Loop prevention: track recently processed node IDs
_processed_ids: dict[int, float] = {}
_processed_lock = threading.Lock()
_PROCESSED_TTL = 300  # 5 minutes


def _is_recently_processed(node_id: int) -> bool:
    with _processed_lock:
        ts = _processed_ids.get(node_id)
        if ts is None:
            return False
        if time.time() - ts > _PROCESSED_TTL:
            del _processed_ids[node_id]
            return False
        return True


def _mark_processed(node_id: int) -> None:
    with _processed_lock:
        _processed_ids[node_id] = time.time()
        # Prune old entries
        now = time.time()
        stale = [k for k, v in _processed_ids.items() if now - v > _PROCESSED_TTL]
        for k in stale:
            del _processed_ids[k]


# --- WebDAV client ---

def _webdav_url(nc_path: str) -> str:
    """Build WebDAV URL for a NC-internal path (e.g. /likivik/files/Documents/foo.pdf)."""
    return f"{NC_URL}/remote.php/dav/files/{nc_path.lstrip('/')}"


def _webdav_download(nc_path: str, dest: Path) -> None:
    """Download file from NC via WebDAV GET."""
    url = _webdav_url(nc_path)
    log.info("WebDAV GET %s", url)
    resp = requests.get(
        url,
        auth=(NC_USER, NC_PASSWORD),
        stream=True,
        timeout=120,
    )
    resp.raise_for_status()
    with dest.open("wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)


def _webdav_upload(nc_path: str, src: Path) -> None:
    """Upload file to NC via WebDAV PUT (creates new version automatically)."""
    url = _webdav_url(nc_path)
    log.info("WebDAV PUT %s", url)
    with src.open("rb") as f:
        resp = requests.put(
            url,
            data=f,
            auth=(NC_USER, NC_PASSWORD),
            headers={"Content-Type": "application/octet-stream"},
            timeout=300,
        )
    resp.raise_for_status()
    log.info("WebDAV PUT %s → %d", nc_path, resp.status_code)


def _webdav_delete(nc_path: str) -> None:
    """Delete file from NC via WebDAV DELETE (for image→PDF replacement)."""
    url = _webdav_url(nc_path)
    log.info("WebDAV DELETE %s", url)
    resp = requests.delete(url, auth=(NC_USER, NC_PASSWORD), timeout=30)
    resp.raise_for_status()


# --- OCR processing ---

def _image_to_pdf(image_path: Path) -> Path:
    """Convert image to PDF using img2pdf."""
    import img2pdf
    target = image_path.with_suffix(".pdf")
    with target.open("wb") as f:
        f.write(img2pdf.convert(str(image_path)))
    return target


def _process_file(nc_path: str, node_id: int) -> dict:
    """Download, OCR, upload back. Returns result dict."""
    ext = Path(nc_path).suffix.lower()
    filename = Path(nc_path).name

    if ext not in PROCESSABLE_EXTS:
        return {"path": nc_path, "skipped": True, "reason": "unsupported_ext"}

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        local_file = tmp / filename
        _webdav_download(nc_path, local_file)

        if ext in IMAGE_EXTS:
            log.info("classifying image: %s", nc_path)
            cls = classify(local_file)
            log.info("classify: is_document=%s reason=%s", cls.is_document, cls.reason)

            if not cls.is_document:
                log.info("skipping photo: %s", nc_path)
                return {"path": nc_path, "skipped": True, "reason": cls.reason}

            # Document image: convert to PDF, OCR
            pdf_path = _image_to_pdf(local_file)
            result = process_pdf(pdf_path)

            # Upload OCR'd PDF (new .pdf path), delete original image
            pdf_nc_path = str(Path(nc_path).with_suffix(".pdf"))
            _webdav_upload(pdf_nc_path, Path(result.output_pdf))
            _webdav_delete(nc_path)

            return {
                "path": nc_path, "output": pdf_nc_path,
                "vlm_pages": result.vlm_pages,
            }

        if ext in PDF_EXTS:
            log.info("OCR-ing PDF: %s", nc_path)
            result = process_pdf(local_file)

            # Upload OCR'd PDF (replaces original → NC version)
            _webdav_upload(nc_path, Path(result.output_pdf))

            return {
                "path": nc_path, "output": nc_path,
                "vlm_pages": result.vlm_pages,
            }

    return {"path": nc_path, "skipped": True, "reason": "unknown"}


# --- FastAPI app ---

app = FastAPI(title="nc-ocr-flow webhook receiver")


class WebhookPayload(BaseModel):
    event: dict
    user: dict | None = None
    time: int = 0


@app.post("/webhook")
async def handle_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Handle NC webhook for file events."""
    # Auth check
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid secret")

    body = await request.json()
    event = body.get("event", {})
    event_class = event.get("class", "")
    node = event.get("node", {})

    # Only handle create/write events
    if event_class not in (
        "OCP\\Files\\Events\\Node\\NodeCreatedEvent",
        "OCP\\Files\\Events\\Node\\NodeWrittenEvent",
    ):
        return {"status": "ignored", "reason": "uninteresting_event"}

    node_id = node.get("id")
    nc_path = node.get("path", "")

    if not nc_path:
        return {"status": "ignored", "reason": "no_path"}

    # Only process files (not directories)
    ext = Path(nc_path).suffix.lower()
    if ext not in PROCESSABLE_EXTS:
        return {"status": "ignored", "reason": "unsupported_ext"}

    # Skip files in trashbin
    if "files_trashbin" in nc_path:
        return {"status": "ignored", "reason": "trashbin"}

    # Skip files in versions
    if "files_versions" in nc_path:
        return {"status": "ignored", "reason": "versions"}

    # Loop prevention: skip if we just processed this file
    if node_id and _is_recently_processed(node_id):
        log.info("skip recently processed: id=%s path=%s", node_id, nc_path)
        return {"status": "skipped", "reason": "recently_processed"}

    log.info("webhook: event=%s path=%s id=%s", event_class, nc_path, node_id)

    try:
        result = _process_file(nc_path, node_id or 0)
        if node_id:
            _mark_processed(node_id)
        log.info("done: %s", result)
        return {"status": "ok", "result": result}
    except Exception as exc:
        log.error("processing failed for %s: %s", nc_path, exc, exc_info=True)
        # Return 200 so NC doesn't retry — we'll handle failures via logging
        return {"status": "error", "error": str(exc)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "nc-ocr-flow"}


def main():
    import uvicorn
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("nc-ocr-flow webhook server: %s:%d NC=%s user=%s",
             LISTEN_HOST, LISTEN_PORT, NC_URL, NC_USER)
    uvicorn.run(app, host=LISTEN_HOST, port=LISTEN_PORT, log_level="info")


if __name__ == "__main__":
    main()
