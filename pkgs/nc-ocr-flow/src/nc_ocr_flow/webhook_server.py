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
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from urllib.parse import quote

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

# Persistent-ish record of files OCR'd by this service (survives queue but
# resets on restart; scan-all uses it to skip already-done files)
_ocrd_paths: set[str] = set()
_ocrd_lock = threading.Lock()


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
    """Build WebDAV URL from a NC-internal path.

    NC webhook delivers node.path as '/<user>/files/<relative_path>'
    e.g. /admin/files/Documents/foo.pdf
    WebDAV URL: /remote.php/dav/files/<user>/<relative_path>
    """
    from urllib.parse import quote
    # Strip leading slash, then remove '<user>/files/' prefix to get relative path
    rel = nc_path.lstrip('/')
    parts = rel.split('/', 2)
    if len(parts) >= 3 and parts[1] == 'files':
        user = parts[0]
        file_path = parts[2]
    else:
        # Fallback: assume nc_path is already relative
        user = NC_USER
        file_path = rel
    # URL-encode each path segment individually, preserving '/' separators.
    # Without this, Cyrillic/space chars in paths cause WebDAV 404s.
    encoded_path = '/'.join(quote(p, safe='') for p in file_path.split('/'))
    return f"{NC_URL}/remote.php/dav/files/{user}/{encoded_path}"


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


def _stamp_metadata(
    pdf_path: Path,
    engine: str,
    vlm_pages: list[int],
    tess_pages: list[int],
    vlm_failed: list[int] | None = None,
) -> None:
    """Write OCR provenance into PDF metadata (PyMuPDF).

    Sets Producer/Subject/Keywords so any PDF reader can show when and how
    the file was OCR'd:
      Producer: nc-ocr-flow 0.3 (engine=auto)
      Subject:  OCR 2026-09-04T10:00:00+03:00 tesseract_pages=1-4 vlm_pages=5
      Keywords: nc-ocr-flow, ocr[, vlm-failed]
    vlm_failed pages kept their tesseract layer (backend error) — stamped
    so they can be found and re-OCR'd later.
    """
    import fitz  # PyMuPDF
    import datetime

    doc = fitz.open(str(pdf_path))
    meta = doc.metadata or {}

    def _ranges(pages: list[int]) -> str:
        if not pages:
            return "-"
        # 1-indexed compact ranges: [0,1,4] -> "1-2,5"
        pages = sorted(p + 1 for p in pages)
        out, start, prev = [], pages[0], pages[0]
        for p in pages[1:]:
            if p == prev + 1:
                prev = p
                continue
            out.append(f"{start}-{prev}" if prev > start else f"{start}")
            start = prev = p
        out.append(f"{start}-{prev}" if prev > start else f"{start}")
        return ",".join(out)

    ts = datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    meta["producer"] = f"nc-ocr-flow 0.3 (engine={engine})"
    subj = (
        f"OCR {ts} tesseract_pages={_ranges(tess_pages)} "
        f"vlm_pages={_ranges(vlm_pages)}"
    )
    if vlm_failed:
        subj += f" vlm_failed={_ranges(vlm_failed)}"
    meta["subject"] = subj
    meta["keywords"] = "nc-ocr-flow, ocr" + (", vlm-failed" if vlm_failed else "")
    doc.set_metadata(meta)
    doc.saveIncr()
    doc.close()


def _process_file(nc_path: str, node_id: int, engine: str = "auto") -> dict:
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
            result = process_pdf(pdf_path, engine=engine)

            # Stamp PDF metadata: engine, timestamp, pages per engine
            _stamp_metadata(
                Path(result.output_pdf),
                engine=engine,
                vlm_pages=result.vlm_pages,
                tess_pages=result.tesseract_pages,
                vlm_failed=result.vlm_failed_pages,
            )

            # Upload OCR'd PDF (new .pdf path), delete original image
            pdf_nc_path = str(Path(nc_path).with_suffix(".pdf"))
            _webdav_upload(pdf_nc_path, Path(result.output_pdf))
            _webdav_delete(nc_path)

            return {
                "path": nc_path, "output": pdf_nc_path,
                "vlm_pages": result.vlm_pages,
            }

        if ext in PDF_EXTS:
            log.info("OCR-ing PDF (engine=%s): %s", engine, nc_path)
            result = process_pdf(local_file, engine=engine)

            # Stamp PDF metadata: engine, timestamp, pages per engine
            _stamp_metadata(
                Path(result.output_pdf),
                engine=engine,
                vlm_pages=result.vlm_pages,
                tess_pages=result.tesseract_pages,
                vlm_failed=result.vlm_failed_pages,
            )

            # Upload OCR'd PDF (replaces original → NC version)
            _webdav_upload(nc_path, Path(result.output_pdf))

            return {
                "path": nc_path, "output": nc_path,
                "vlm_pages": result.vlm_pages,
            }

    return {"path": nc_path, "skipped": True, "reason": "unknown"}


# --- Job tracking (for /status panel + NC app) ---
import queue
import itertools

_job_seq = itertools.count(1)
_jobs: dict[int, dict] = {}          # job_id -> job record
_jobs_lock = threading.Lock()
_MAX_JOBS_HISTORY = 500              # keep last N finished jobs

# Single-worker OCR queue: webhook endpoint enqueues, worker thread processes.
_ocr_queue: "queue.Queue[dict]" = queue.Queue()


def _record_job(job: dict) -> None:
    with _jobs_lock:
        _jobs[job["id"]] = job
        # Prune history
        finished = [j for j in _jobs.values() if j["status"] in ("done", "error", "skipped")]
        if len(finished) > _MAX_JOBS_HISTORY:
            for j in sorted(finished, key=lambda x: x["id"])[: len(finished) - _MAX_JOBS_HISTORY]:
                del _jobs[j["id"]]


def _ocr_worker() -> None:
    """Sequential OCR worker: processes queue items one at a time."""
    while True:
        item = _ocr_queue.get()
        job = item["job"]
        try:
            job["status"] = "running"
            job["started"] = time.time()
            log.info("worker: job %d start: %s (engine=%s)", job["id"], job["path"], job["engine"])
            result = _process_file(item["nc_path"], item["node_id"], item["engine"])
            job["status"] = "done" if not result.get("skipped") else "skipped"
            job["result"] = result
            if result.get("skipped"):
                job["reason"] = result.get("reason", "")
            log.info("worker: job %d %s: %s", job["id"], job["status"], job["path"])
        except Exception as exc:
            job["status"] = "error"
            job["error"] = str(exc)
            log.error("worker: job %d failed: %s — %s", job["id"], job["path"], exc)
        finally:
            job["finished"] = time.time()
            _record_job(job)
            node_id = item["node_id"]
            if node_id:
                _mark_processed(node_id)
            if job["status"] == "done":
                with _ocrd_lock:
                    _ocrd_paths.add(item["nc_path"])
            _ocr_queue.task_done()


threading.Thread(target=_ocr_worker, daemon=True, name="ocr-worker").start()


def _enqueue(nc_path: str, node_id: int, engine: str = "auto") -> dict:
    """Create a job record and enqueue for processing."""
    job = {
        "id": next(_job_seq),
        "path": nc_path,
        "engine": engine,
        "status": "queued",
        "created": time.time(),
        "finished": None,
        "result": None,
        "error": None,
        "reason": None,
    }
    _record_job(job)
    _ocr_queue.put({"job": job, "nc_path": nc_path, "node_id": node_id, "engine": engine})
    return job


def _check_secret(x_webhook_secret: str | None) -> None:
    if WEBHOOK_SECRET and x_webhook_secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid secret")


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
    """Handle NC webhook for file events. Enqueues job, returns immediately."""
    _check_secret(x_webhook_secret)

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

    job = _enqueue(nc_path, node_id or 0)
    # Return 200 immediately — NC won't retry, worker processes async
    return {"status": "queued", "job_id": job["id"], "path": nc_path}


@app.get("/status")
async def status(
    limit: int = 50,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Job queue status for the panel / NC app."""
    _check_secret(x_webhook_secret)
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["id"])
    queued = [j for j in jobs if j["status"] == "queued"]
    running = [j for j in jobs if j["status"] == "running"]
    finished = [j for j in jobs if j["status"] in ("done", "error", "skipped")][-limit:]
    return {
        "service": "nc-ocr-flow",
        "queue_depth": _ocr_queue.qsize(),
        "queued": queued,
        "running": running,
        "history": finished[::-1],  # newest first
    }


class RescanRequest(BaseModel):
    path: str                    # NC-internal path: /<user>/files/<rel>
    node_id: int = 0
    engine: str = "auto"         # auto | tesseract | vlm


@app.post("/rescan")
async def rescan(
    body: RescanRequest,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Re-OCR a specific file with engine override (panel / NC-app action)."""
    _check_secret(x_webhook_secret)

    nc_path = body.path
    ext = Path(nc_path).suffix.lower()
    if ext not in PROCESSABLE_EXTS:
        raise HTTPException(status_code=422, detail=f"unsupported ext: {ext}")
    if body.engine not in ("auto", "tesseract", "vlm"):
        raise HTTPException(status_code=422, detail=f"invalid engine: {body.engine}")
    if "files_trashbin" in nc_path or "files_versions" in nc_path:
        raise HTTPException(status_code=422, detail="cannot rescan trashbin/versions")

    # Rescan must bypass recently_processed guard: clear the marker
    if body.node_id:
        with _processed_lock:
            _processed_ids.pop(body.node_id, None)

    job = _enqueue(nc_path, body.node_id, body.engine)
    return {"status": "queued", "job_id": job["id"], "engine": body.engine}


class ScanAllRequest(BaseModel):
    folder: str = ""             # NC-relative folder to scan ("Work/1-Аренда"); "" = all
    engine: str = "auto"         # auto | tesseract | vlm
    skip_ocrd: bool = True       # skip files already OCR'd by this service


@app.post("/scan-all")
async def scan_all(
    body: ScanAllRequest,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Batch scan: enqueue every processable file under a folder ("" = all).

    Skips files already OCR'd by this service (tracked in _ocrd_paths).
    Returns immediately with the number of jobs queued; processing is
    sequential in the single worker (queue Depth visible in /status).
    """
    _check_secret(x_webhook_secret)
    if body.engine not in ("auto", "tesseract", "vlm"):
        raise HTTPException(status_code=422, detail=f"invalid engine: {body.engine}")

    # PROPFIND the folder (depth infinity) for PDFs/images
    folder = body.folder.strip("/")
    dav_path = f"/remote.php/dav/files/{NC_USER}/" + "/".join(
        quote(p, safe="") for p in folder.split("/") if p
    )
    propfind_body = (
        '<?xml version="1.0"?>'
        '<d:propfind xmlns:d="DAV:"><d:prop>'
        "<d:resourcetype/><d:getcontenttype/>"
        "</d:prop></d:propfind>"
    )
    resp = requests.request(
        "PROPFIND", NC_URL + dav_path,
        auth=(NC_USER, NC_PASSWORD), headers={"Depth": "infinity",
                                              "Content-Type": "application/xml"},
        data=propfind_body, timeout=300,
    )
    resp.raise_for_status()

    import re as _re
    found = _re.findall(r"<d:href>([^<]+)</d:href>", resp.text)
    # Filter to processable extensions, decode %XX
    from urllib.parse import unquote
    enqueued = 0
    skipped_ocrd = 0
    for href in found:
        href = unquote(href)
        rel = href.split(f"/remote.php/dav/files/{NC_USER}/", 1)[-1]
        if not rel or rel in (folder, folder + "/"):
            continue
        if Path(rel).suffix.lower() not in PROCESSABLE_EXTS:
            continue
        nc_path = f"/{NC_USER}/files/{rel}"
        if body.skip_ocrd and nc_path in _ocrd_paths:
            skipped_ocrd += 1
            continue
        _enqueue(nc_path, 0, body.engine)
        enqueued += 1
    log.info("scan-all: folder=%r enqueued=%d skipped_ocrd=%d",
             body.folder, enqueued, skipped_ocrd)
    return {"status": "queued", "enqueued": enqueued, "skipped_ocrd": skipped_ocrd}



@app.get("/health")
async def health():
    return {"status": "ok", "service": "nc-ocr-flow"}


@app.get("/panel")
async def panel():
    """Serve the OCR status panel (secret is entered in the page itself)."""
    static = Path(__file__).parent / "static" / "panel.html"
    return HTMLResponse(content=static.read_text(encoding="utf-8"))


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
