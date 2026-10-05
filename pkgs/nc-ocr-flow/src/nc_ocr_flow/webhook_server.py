"""Webhook receiver: NC fires on file create/write, we OCR via WebDAV.

Flow:
  1. NC webhook POST → NodeCreatedEvent / NodeWrittenEvent
  2. Download file via WebDAV GET
  3. PDF → ocr.py (one of google|tesseract|minimax engines)
     Image → classify → document? → img2pdf → ocr.py → upload as .pdf
  4. Upload result via WebDAV PUT (NC creates new version automatically)
  5. Loop prevention: skip files we just processed (in-memory ID set + TTL)
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path

import requests
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from urllib.parse import quote

from .classifier import classify
from .ocr import process_pdf
from .pdf_classify import classify_pdf

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


# --- Durable OCR index (survives restarts) ---------------------------------
# Maps NC path -> {status, engine, reason, node_id, finished}. Written to the
# systemd StateDirectory (STATE_DIRECTORY=/var/lib/nc-ocr) so the "how many
# scanned / with which engine" metrics stay accurate across restarts. The
# in-memory _ocrd_paths set is rebuilt from it on startup.

def _state_dir() -> Path:
    d = os.environ.get("NC_OCR_STATE_DIR") or os.environ.get("STATE_DIRECTORY", "")
    d = d.split(":")[0] if d else ""
    return Path(d) if d else Path("/var/lib/nc-ocr")


_INDEX_FILE = _state_dir() / "ocr_index.json"
_ocr_index: dict[str, dict] = {}
_index_lock = threading.Lock()


def _load_index() -> None:
    global _ocr_index
    try:
        if _INDEX_FILE.exists():
            _ocr_index = json.loads(_INDEX_FILE.read_text())
            with _ocrd_lock:
                _ocrd_paths.update(
                    p for p, m in _ocr_index.items() if m.get("status") == "done"
                )
            log.info("loaded OCR index: %d entries from %s", len(_ocr_index), _INDEX_FILE)
    except Exception as exc:  # never block startup on a bad index
        log.warning("could not load OCR index %s: %s", _INDEX_FILE, exc)


def _save_index() -> None:
    try:
        _INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _INDEX_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_ocr_index))
        tmp.replace(_INDEX_FILE)
    except Exception as exc:
        log.warning("could not save OCR index: %s", exc)


def _index_record(nc_path: str, status: str, engine: str | None,
                  reason: str | None, node_id: int = 0,
                  size: int | None = None, etag: str | None = None) -> None:
    """Record the outcome for a path.

    ``size``/``etag`` are the fingerprint of the file *as we left it* after
    processing. The NC app compares them with the live file to detect that
    the user replaced the file since we OCR'd it — otherwise a stale
    ``done`` would keep hiding the "Send to OCR" action forever.
    """
    with _index_lock:
        _ocr_index[nc_path] = {
            "status": status,
            "engine": engine if status == "done" else None,
            "reason": reason,
            "node_id": node_id,
            "finished": time.time(),
            "size": size,
            "etag": etag,
        }
        _save_index()


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


# --- Per-engine version stamping (used by _stamp_metadata) -----------------


def _engine_api_version(engine: str) -> tuple[str, str]:
    """Return (api, version) for a given engine, both best-effort.

    Used by ``_stamp_metadata`` to record which OCR API/version
    actually processed this PDF. Failures degrade to "unknown" rather
    than raising — metadata stamping must never block an OCR result.
    """
    engine = (engine or "").lower()
    if engine == "google":
        api = "google.cloud.vision_v1"
        try:
            from importlib.metadata import version as _pkg_version
            ver = _pkg_version("google-cloud-vision")
        except Exception:
            ver = "unknown"
        return api, ver
    if engine == "tesseract":
        # tesseract binary version (first line of `tesseract --version`).
        ver = "unknown"
        try:
            import subprocess as _sp
            r = _sp.run(
                ["tesseract", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            out = (r.stdout or r.stderr or "").strip().splitlines()
            if out:
                ver = out[0].strip()
        except Exception:
            pass
        api = "ocrmypdf"
        try:
            from importlib.metadata import version as _pkg_version
            api = f"ocrmypdf {_pkg_version('ocrmypdf')}"
        except Exception:
            pass
        return api, ver
    if engine == "minimax":
        return "minimax-chat-completions", "MiniMax-M3"
    # 'auto' or unknown: stamp whatever engine actually ran via the
    # caller passing it in; this branch shouldn't normally fire.
    return "unknown", "unknown"


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


def _propfind_size_etag(nc_path: str) -> tuple[int | None, str | None]:
    """One raw PROPFIND → (size, etag)."""
    import re as _re

    url = _webdav_url(nc_path)
    body = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<d:propfind xmlns:d="DAV:"><d:prop>'
        '<d:getcontentlength/><d:getetag/>'
        '</d:prop></d:propfind>'
    )
    try:
        resp = requests.request(
            "PROPFIND", url, data=body,
            auth=(NC_USER, NC_PASSWORD),
            headers={"Depth": "0", "Content-Type": "application/xml"},
            timeout=60,
        )
        if resp.status_code >= 400:
            return None, None
        m_len = _re.search(r"<[^>]*getcontentlength>(\d+)<", resp.text)
        m_etag = _re.search(r"<[^>]*getetag>([^<]+)<", resp.text)
        size = int(m_len.group(1)) if m_len else None
        # Sabre returns the etag as an XML-escaped quoted string: &quot;abc&quot;
        etag = m_etag.group(1).strip().replace("&quot;", "").strip('"') if m_etag else None
        return size, etag
    except Exception as exc:
        log.debug("PROPFIND %s failed: %s", nc_path, exc)
        return None, None


def _webdav_stat(nc_path: str, attempts: int = 3) -> tuple[int | None, str | None]:
    """PROPFIND a file until two consecutive reads agree → (size, etag).

    Called right after we upload the OCR'd result, so the pair describes the
    file exactly as we left it. A single read is not enough: Nextcloud can
    still be settling the write and hand back the *previous* size/etag, which
    would make every processed file look modified afterwards. Returns
    (None, None) if the path is gone (e.g. an image we converted to PDF).
    """
    prev: tuple[int | None, str | None] = (None, None)
    for i in range(attempts):
        cur = _propfind_size_etag(nc_path)
        if cur[0] is not None and cur == prev:
            return cur
        prev = cur
        time.sleep(1.5)
    return prev


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
    l2_pages: dict[int, dict] | None = None,
) -> None:
    """Write OCR provenance into PDF metadata (PyMuPDF).

    Sets Producer/Subject/Keywords so any PDF reader can show when and
    how the file was OCR'd.

    New (0.3) per-engine stamped format:

      Producer: nc-ocr-flow 0.3 (engine=X)

      Subject:  OCR <ts> input_sha256=<hex64> source=current
                langs=rus+eng <engine>:api=<api> <engine>:ver=<ver>
                tesseract_pages=<ranges> vlm_pages=<ranges>
                [vlm_failed=<ranges>] [l2=<p:l:c[,esc];...>]

      Keywords: nc-ocr-flow, ocr[, vlm-failed][, handwriting]

    The ``source=current`` marker is reserved (the pristine source was
    removed in 0.3 — re-OCR always works on the current file via the
    ``force=True`` flag).
    """
    import fitz  # PyMuPDF
    import datetime
    import hashlib

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

    # Per-engine api/ver — degrade to "unknown" on failure (never raise)
    engine_api, engine_ver = _engine_api_version(engine)

    # sha256 of the PDF bytes actually OCR'd. Falls back to "-" if the
    # file is missing or unreadable (shouldn't happen — we just wrote
    # it — but defensive).
    try:
        h = hashlib.sha256()
        with open(pdf_path, "rb") as _f:
            for chunk in iter(lambda: _f.read(65536), b""):
                h.update(chunk)
        input_sha = h.hexdigest()
    except OSError:
        input_sha = "-"

    meta["producer"] = f"nc-ocr-flow 0.3 (engine={engine})"

    # Build Subject as a single line — keys appear in a fixed order so
    # /status and triage scripts can grep reliably.
    parts = [
        f"OCR {ts}",
        f"input_sha256={input_sha}",
        "source=current",
        "langs=rus+eng",
        f"{engine}:api={engine_api}",
        f"{engine}:ver={engine_ver}",
        f"tesseract_pages={_ranges(tess_pages)}",
        f"vlm_pages={_ranges(vlm_pages)}",
    ]
    if vlm_failed:
        parts.append(f"vlm_failed={_ranges(vlm_failed)}")
    if l2_pages:
        # compact L2 verdicts: p5:combination:0.85,escalated
        l2_parts = []
        for p in sorted(l2_pages):
            v = l2_pages[p]
            flag = ",esc" if v.get("escalate") else ""
            l2_parts.append(f"p{p + 1}:{v.get('label')}:{v.get('confidence')}{flag}")
        parts.append(f"l2={';'.join(l2_parts)}")
    meta["subject"] = " ".join(parts)

    kw = "nc-ocr-flow, ocr"
    if vlm_failed:
        kw += ", vlm-failed"
    escalated = [p for p, v in (l2_pages or {}).items() if v.get("escalate")]
    if escalated:
        kw += ", handwriting"
    meta["keywords"] = kw
    doc.set_metadata(meta)
    doc.saveIncr()
    doc.close()


def _already_stamped_by_us(path: Path) -> bool:
    """True if ``path`` carries our 0.3 stamp from a previous OCR run.

    Returns True only when the Producer line contains both ``nc-ocr-flow``
    and ``engine=google`` — Google's whole-doc OCR produces the highest-
    fidelity text layer, so any file with a Google-engine stamp from us
    can be skipped without risking a worse result.
    """
    try:
        import fitz
        with fitz.open(str(path)) as doc:
            producer = (doc.metadata or {}).get("producer", "") or ""
    except Exception:
        return False
    if "nc-ocr-flow" not in producer:
        return False
    if "engine=google" not in producer:
        return False
    return True


def _needs_ocr_decision(path: Path, force: bool) -> bool:
    """Decide whether ``path`` actually needs OCR.

    Returns False (skip) only when ``force`` is False AND one of:
      - The file already carries a Google-engine stamp from us, OR
      - pdf-inspector (or the heuristic fallback) classifies it as
        text_based with no encoding issues.

    The Google-stamp check is fast (PyMuPDF metadata read) and avoids
    loading pdf-inspector on files we already OCR'd with our best
    engine. The pdf-inspector call is the expensive path but only runs
    once per newly-seen file.
    """
    if force:
        return True

    if _already_stamped_by_us(path):
        return False

    try:
        cls = classify_pdf(path)
        return bool(cls.get("needs_ocr", True))
    except Exception as exc:
        # Classifier crashed — default to OCR (better safe than skip).
        log.warning("pdf_classify raised (%s); defaulting to OCR", exc)
        return True


def _process_file(nc_path: str, node_id: int, engine: str | None = None,
                  force: bool = False) -> dict:
    """Download, OCR, upload back. Returns result dict.

    ``engine`` defaults to ``None`` → orchestrator resolves via
    ``NC_OCR_ENGINE`` env var (default: "google").
    ``force`` (default False): bypass the born-digital skip decision
    AND the recently-processed guard. The user invokes this from the
    NC app's "Re-OCR anyway" action to force a re-OCR even on files
    we previously stamped or classified as born-digital.
    """
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
                engine=result.engine_used,
                vlm_pages=result.vlm_pages,
                tess_pages=result.tess_pages,
                vlm_failed=result.vlm_failed_pages,
                l2_pages=result.l2_pages,
            )

            # Upload OCR'd PDF (new .pdf path), delete original image
            pdf_nc_path = str(Path(nc_path).with_suffix(".pdf"))
            _webdav_upload(pdf_nc_path, Path(result.output_pdf))
            _webdav_delete(nc_path)

            return {
                "path": nc_path, "output": pdf_nc_path,
                "engine": result.engine_used,
                "vlm_pages": result.vlm_pages,
            }

        if ext in PDF_EXTS:
            # Born-digital / stamped-good skip decision. ``force=True``
            # bypasses it (used by the "Re-OCR anyway" action).
            if not _needs_ocr_decision(local_file, force):
                log.info(
                    "skip born-digital / stamped-good: %s (force=%s)",
                    nc_path, force,
                )
                return {
                    "path": nc_path,
                    "skipped": True,
                    "reason": "born_digital_or_stamped_good",
                }

            log.info("OCR-ing PDF (engine=%s force=%s): %s", engine, force, nc_path)
            result = process_pdf(local_file, engine=engine)

            # Stamp PDF metadata: engine, timestamp, pages per engine
            _stamp_metadata(
                Path(result.output_pdf),
                engine=result.engine_used,
                vlm_pages=result.vlm_pages,
                tess_pages=result.tess_pages,
                vlm_failed=result.vlm_failed_pages,
                l2_pages=result.l2_pages,
            )

            # Upload OCR'd PDF (replaces original → NC version)
            _webdav_upload(nc_path, Path(result.output_pdf))

            return {
                "path": nc_path, "output": nc_path,
                "engine": result.engine_used,
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
            log.info("worker: job %d start: %s (engine=%s force=%s)",
                     job["id"], job["path"], job["engine"], item.get("force"))
            result = _process_file(item["nc_path"], item["node_id"],
                                   item["engine"], item.get("force", False))
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
            force = item.get("force", False)
            # ``force`` re-OCRs skip the recently_processed guard so the
            # user can deliberately re-OCR a file we just processed. The
            # _ocrd_paths bookkeeping still records the path (it's the
            # same file the worker just touched).
            if node_id and not force:
                _mark_processed(node_id)
            if job["status"] == "done":
                with _ocrd_lock:
                    _ocrd_paths.add(item["nc_path"])
            # Persist outcome (incl. the engine that actually ran) so the
            # metrics survive a service restart.
            job_result = job.get("result")
            engine_used = None
            if isinstance(job_result, dict):
                engine_used = job_result.get("engine")
            # Fingerprint the file as we left it (size + etag), so the NC
            # app can tell a still-valid "done" from a replaced file.
            size_after, etag_after = (None, None)
            if job["status"] in ("done", "skipped"):
                size_after, etag_after = _webdav_stat(item["nc_path"])
            _index_record(
                item["nc_path"],
                job["status"],
                engine_used or job.get("engine"),
                job.get("reason") or job.get("error"),
                node_id or 0,
                size=size_after,
                etag=etag_after,
            )
            _ocr_queue.task_done()


threading.Thread(target=_ocr_worker, daemon=True, name="ocr-worker").start()

# Restore the durable index before serving traffic.
_load_index()


def _enqueue(nc_path: str, node_id: int, engine: str | None = None,
             force: bool = False) -> dict:
    """Create a job record and enqueue for processing.

    ``engine`` defaults to None → orchestrator resolves via env.
    ``force`` (default False): bypass the born-digital skip decision AND
    the recently-processed guard. The NC app's "Re-OCR anyway" action
    sends this so the user can deliberately re-OCR a file we previously
    classified or stamped.
    """
    job = {
        "id": next(_job_seq),
        "path": nc_path,
        "engine": engine,
        "force": force,
        "status": "queued",
        "created": time.time(),
        "started": None,
        "finished": None,
        "result": None,
        "error": None,
        "reason": None,
    }
    _record_job(job)
    _ocr_queue.put({"job": job, "nc_path": nc_path, "node_id": node_id,
                    "engine": engine, "force": force})
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

    # Loop prevention: skip if we just processed this file.
    # ``force`` (set by the NC app's "Re-OCR anyway" action) bypasses
    # this guard — the user is asking for a deliberate re-OCR.
    force = bool(body.get("force", False))
    if not force and node_id and _is_recently_processed(node_id):
        log.info("skip recently processed: id=%s path=%s", node_id, nc_path)
        return {"status": "skipped", "reason": "recently_processed"}

    log.info("webhook: event=%s path=%s id=%s force=%s",
             event_class, nc_path, node_id, force)

    job = _enqueue(nc_path, node_id or 0, force=force)
    # Return 200 immediately — NC won't retry, worker processes async
    return {"status": "queued", "job_id": job["id"], "path": nc_path,
            "force": force}


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


@app.get("/states")
async def states(
    paths: list[str] = Query(default=[]),
    all_files: int = Query(default=0, alias="all"),
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Per-file OCR state — drives which file action the NC app shows.

    One entry per requested NC path we know about; ``status`` is one of
    queued | running | done | skipped | error. The recorded ``size``/``etag``
    fingerprint lets the NC app decide whether a ``done`` is still valid
    (the user may have replaced the file since we OCR'd it).
    """
    _check_secret(x_webhook_secret)
    # Keys are NC-internal paths ("/<uid>/files/<rel>") exactly as the
    # webhook delivers them — do not normalise, or nothing will match.
    want = {p for p in paths if p}

    out: dict[str, dict] = {}
    with _index_lock:
        if all_files:
            out = {p: dict(m) for p, m in _ocr_index.items()}
        else:
            for p in want:
                m = _ocr_index.get(p)
                if m:
                    out[p] = dict(m)

    # A live queue entry is more accurate than the last recorded outcome.
    with _jobs_lock:
        live = [j for j in _jobs.values() if j["status"] in ("queued", "running")]
    for j in live:
        p = str(j.get("path") or "")
        if all_files or p in want:
            rec = out.setdefault(p, {})
            rec["status"] = j["status"]
            rec["job_id"] = j["id"]
            rec["finished"] = j.get("finished") or rec.get("finished")

    return {"states": out, "unknown": sorted(want - set(out))}


@app.get("/stats")
async def stats(
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Aggregate OCR metrics from the durable index.

    ``scanned`` counts distinct files OCR'd by this service; ``by_engine``
    breaks that down by the engine that actually ran; ``skipped`` are files
    we deliberately did not OCR (born-digital PDFs, non-document photos).
    The caller (NC app) supplies the denominator — the total number of
    OCR-able files — because only Nextcloud knows the file tree.
    """
    _check_secret(x_webhook_secret)
    with _index_lock:
        idx = list(_ocr_index.values())

    scanned = [m for m in idx if m.get("status") == "done"]
    skipped = [m for m in idx if m.get("status") == "skipped"]
    errors = [m for m in idx if m.get("status") == "error"]

    by_engine: dict[str, int] = {}
    for m in scanned:
        e = (m.get("engine") or "unknown") or "unknown"
        by_engine[e] = by_engine.get(e, 0) + 1

    skip_reasons: dict[str, int] = {}
    for m in skipped:
        r = m.get("reason") or "unknown"
        skip_reasons[r] = skip_reasons.get(r, 0) + 1

    return {
        "service": "nc-ocr-flow",
        "indexed": len(idx),
        "scanned": len(scanned),
        "skipped": len(skipped),
        "errors": len(errors),
        "by_engine": by_engine,
        "skip_reasons": skip_reasons,
    }


class RescanRequest(BaseModel):
    path: str                    # NC-internal path: /<user>/files/<rel>
    node_id: int = 0
    engine: str | None = None    # google|tesseract|minimax; None → env
    force: bool = False          # bypass born-digital skip + recent guard


@app.post("/rescan")
async def rescan(
    body: RescanRequest,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Re-OCR a specific file with engine override (panel / NC-app action).

    ``body.force`` (default False): bypass the born-digital skip
    decision AND the recently-processed guard. The NC app's
    "Re-OCR anyway" action sends ``force=true`` so a user can
    deliberately re-OCR a file we previously stamped or classified
    as born-digital.
    """
    _check_secret(x_webhook_secret)

    nc_path = body.path
    ext = Path(nc_path).suffix.lower()
    if ext not in PROCESSABLE_EXTS:
        raise HTTPException(status_code=422, detail=f"unsupported ext: {ext}")
    if body.engine is not None and body.engine not in ("google", "tesseract", "minimax"):
        raise HTTPException(status_code=422, detail=f"invalid engine: {body.engine}")
    if "files_trashbin" in nc_path or "files_versions" in nc_path:
        raise HTTPException(status_code=422, detail="cannot rescan trashbin/versions")

    # Rescan must bypass recently_processed guard: clear the marker.
    # When force=True, the worker won't re-mark either — see _ocr_worker.
    if body.node_id and not body.force:
        with _processed_lock:
            _processed_ids.pop(body.node_id, None)

    job = _enqueue(nc_path, body.node_id, body.engine, force=body.force)
    return {"status": "queued", "job_id": job["id"],
            "engine": body.engine, "force": body.force}


class ScanAllRequest(BaseModel):
    folder: str = ""             # NC-relative folder to scan ("Work/1-Аренда"); "" = all
    engine: str | None = None    # google|tesseract|minimax; None → env
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
    if body.engine is not None and body.engine not in ("google", "tesseract", "minimax"):
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
