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
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from urllib.parse import quote

from .classifier import classify
from .ocr import process_pdf
from .pdf_classify import classify_pdf
from . import jobstore

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

#: Below this many extractable characters per page a PDF is treated
#: as a scan even when the text-based classifier says otherwise
#: (real uploads: 1 and 4 chars/page were silently skipped).
MIN_TEXT_CHARS_PER_PAGE = 25

#: Distinct skip reasons recorded in ``files.reason`` and surfaced
#: through ``/stats`` + the panel ``skip_reasons`` breakdown.  Three
#: concrete paths inside ``_needs_ocr_decision`` can yield a skip;
#: before this PR they were all collapsed into a single
#: ``born_digital_or_stamped_good`` string, which made it impossible
#: for an operator to tell "we already OCR'd this file" (trustworthy)
#: apart from "the classifier thinks this is born-digital" (which may
#: still be a broken pre-existing text layer that we DO want to
#: re-OCR).  The PR keeps the runtime skip behaviour identical — only
#: the *reason* string is split.
SKIP_REASON_STAMPED_BY_US      = "stamped_good_by_us"
SKIP_REASON_BORN_DIGITAL       = "born_digital_text_based"
#: Reserved for the text-density guard branch.  Today that branch
#: FORCES OCR (returns ``needs_ocr=True`` when per-page chars fall
#: below MIN_TEXT_CHARS_PER_PAGE) and so does not produce a skip —
#: but the constant is defined so a future "skip" path through that
#: guard can be reported distinctly instead of being conflated with
#: the other two.
SKIP_REASON_TEXT_DENSITY_GUARD = "text_density_guard_low"
#: The old, undifferentiated string.  External consumers and stored
#: rows may still reference it; we keep it exported so callers can
#: compare against either form.
SKIP_REASON_LEGACY             = "born_digital_or_stamped_good"

# Loop prevention: which node IDs we processed recently. The claim lives
# in SQLite (jobstore.claim_node) so it survives a restart.
_PROCESSED_TTL = 300  # 5 minutes


# --- Per-file OCR state (survives restarts) --------------------------------
# Maps NC path -> {status, engine, reason, node_id, finished, size, etag}.
# It lives in the ``files`` table (see jobstore), so the index costs no
# RAM no matter how many files the instance has seen.

def _state_dir() -> Path:
    d = os.environ.get("NC_OCR_STATE_DIR") or os.environ.get("STATE_DIRECTORY", "")
    d = d.split(":")[0] if d else ""
    return Path(d) if d else Path("/var/lib/nc-ocr")


_INDEX_FILE = _state_dir() / "ocr_index.json"


def _index_record(nc_path: str, status: str, engine: str | None,
                  reason: str | None, node_id: int = 0,
                  size: int | None = None, etag: str | None = None) -> None:
    """Record the outcome for a path.

    ``size``/``etag`` are the fingerprint of the file *as we left it* after
    processing. The NC app compares them with the live file to detect that
    the user replaced the file since we OCR'd it — otherwise a stale
    ``done`` would keep hiding the "Send to OCR" action forever.
    """
    jobstore.file_put({
        "path": nc_path,
        "status": status,
        "engine": engine if status == "done" else None,
        "reason": reason,
        "node_id": node_id,
        "finished": time.time(),
        "size": size,
        "etag": etag,
    })


def _is_recently_processed(node_id: int) -> bool:
    """Kept for callers that only want to look, without claiming."""
    return not jobstore.claim_node(node_id, _PROCESSED_TTL)


def _claim_node(node_id: int) -> bool:
    """Atomically claim ``node_id`` for processing.

    Delegates to SQLite: the claim survives a restart, so a deploy no
    longer makes us forget which files we just processed. On a DB error
    it fails open (process the file) rather than skipping it forever.
    """
    return jobstore.claim_node(node_id, _PROCESSED_TTL)


def _mark_processed(node_id: int) -> None:
    """Refresh the claim timestamp after a successful run."""
    jobstore.claim_node(node_id, 0.0) if node_id else None


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
    # Refuse anything that could escape the user's own profile: a '..'
    # segment must never reach the server, even if a client sends one.
    if '..' in Path(rel).parts:
        raise ValueError(f"refusing unsafe Nextcloud path: {nc_path!r}")
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
    def _do_get():
        r = requests.get(
            url,
            auth=(NC_USER, NC_PASSWORD),
            stream=True,
            timeout=120,
        )
        r.raise_for_status()
        # Write inside the retried closure: a stream that dies midway
        # would otherwise leave a truncated file behind.
        with dest.open("wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return r

    _retry(_do_get, what=f"WebDAV GET {nc_path}")


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
    def _do_put():
        with src.open("rb") as f:
            r = requests.put(
                url,
                data=f,
                auth=(NC_USER, NC_PASSWORD),
                headers={"Content-Type": "application/octet-stream"},
                timeout=300,
            )
        r.raise_for_status()
        return r

    resp = _retry(_do_put, what=f"WebDAV PUT {nc_path}")
    log.info("WebDAV PUT %s → %d", nc_path, resp.status_code)


#: Transient failures (NC restarting, DAV lock contention, a blip on
#: the tailnet) used to kill a job permanently. Retry with backoff.
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 1.0


def _retry(fn, *, what: str, attempts: int = _RETRY_ATTEMPTS):
    """Call ``fn`` with exponential backoff on transient failures."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except (requests.RequestException, TimeoutError, OSError) as exc:
            last = exc
            if i + 1 < attempts:
                delay = _RETRY_BASE_DELAY * (2 ** i)
                log.warning("%s failed (%s) — retry %d/%d in %.1fs",
                            what, exc, i + 1, attempts - 1, delay)
                time.sleep(delay)
    log.error("%s failed after %d attempts: %s", what, attempts, last)
    raise last  # type: ignore[misc]


def _webdav_delete(nc_path: str) -> None:
    """Delete file from NC via WebDAV DELETE (for image→PDF replacement)."""
    url = _webdav_url(nc_path)
    log.info("WebDAV DELETE %s", url)
    resp = _retry(
        lambda: requests.delete(url, auth=(NC_USER, NC_PASSWORD), timeout=30),
        what=f"WebDAV DELETE {nc_path}",
    )
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

    TODO (user-requested policy revisit, NOT a behaviour change in this PR):
    ``stamped_good_by_us`` is recorded as a skip reason but the operator's
    position is that "stamped by us" is a *re-OCR candidate*, not a trusted
    terminal skip.  Concrete evidence on the 9 ПрофиМаркет files: even
    after Run-1 stamped them with ``engine=google``, two of them
    (СГР Бонсолар бессрочно, СГР Double Black) still have a broken
    *pre-existing* OCRmyPDF/Tesseract text layer underneath, and the
    extractable text remains mojibake (combining-mark noise, zero Cyrillic).
    Our Google layer was supposed to replace the broken layer via
    ``page.add_redact_annot(...) / apply_redactions(...)`` followed by
    ``_embed_ocr_text``, but the redact step appears not to remove the
    invisible-mode text in some cases, so the old broken layer is what
    ``get_text()`` returns.  The stamp branch therefore trusts a Google
    result that, for these files, isn't actually visible in extraction.

    The user's actual safety criterion for "safe to skip":
      (a) provenance — Creator/Producer contain no OCR-tool string
          (``OCRmyPDF``, ``pikepdf``, ``Tesseract``, …) AND no
          ``nc-ocr-flow`` stamp;
      (b) deep inspection is clean — pdf-inspector's
          ``pdf_type == "text_based"`` AND no encoding issues
          AND no invisible-text-layer flags on any page raster; AND
      (c) ``text_based`` ALONE is not sufficient (see (a)+(c) in
          the same files above).

    Until the policy is changed, this function and the caller at
    ``_needs_ocr_decision`` continue to treat ``engine=google`` as
    trustworthy so we do not blow the Vision-API budget re-OCR'ing
    the entire stamp-flagged set.  That is a deliberate, explicitly
    documented policy choice — not a confident assertion that those
    files are good.
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


def _needs_ocr_decision(
    path: Path, force: bool
) -> tuple[bool, str | None]:
    """Decide whether ``path`` actually needs OCR, and report WHY if not.

    Returns ``(needs_ocr, skip_reason)``:
      * ``(True,  None)``  — OCR must run; no skip was decided.
      * ``(False, reason)`` — skip; ``reason`` is one of
        :data:`SKIP_REASON_STAMPED_BY_US` /
        :data:`SKIP_REASON_BORN_DIGITAL` /
        :data:`SKIP_REASON_TEXT_DENSITY_GUARD`.

    A skip is taken when ``force`` is False AND one of:
      - The file already carries a Google-engine stamp from us
        → :data:`SKIP_REASON_STAMPED_BY_US`;
      - pdf-inspector (or the heuristic fallback) classifies it as
        text_based with no encoding issues
        → :data:`SKIP_REASON_BORN_DIGITAL`.

    The Google-stamp check is fast (PyMuPDF metadata read) and avoids
    loading pdf-inspector on files we already OCR'd with our best
    engine. The pdf-inspector call is the expensive path but only runs
    once per newly-seen file.

    See :func:`_already_stamped_by_us` for the user-flagged caveat that
    "stamped by us" is treated as trustworthy here as a deliberate,
    temporary policy — not as a confident assertion.
    """
    if force:
        return True, None

    if _already_stamped_by_us(path):
        return False, SKIP_REASON_STAMPED_BY_US

    try:
        cls = classify_pdf(path)
        needs = bool(cls.get("needs_ocr", True))
    except Exception as exc:
        # Classifier crashed — default to OCR (better safe than skip).
        log.warning("pdf_classify raised (%s); defaulting to OCR", exc)
        return True, None

    if needs:
        return True, None

    # Text-density guard. The inspector (pdf-inspector / heuristic)
    # calls a page "text_based" whenever it finds text objects, even
    # when the page is really an image scan carrying a stamp or a
    # watermark. Measured on real uploads: two phone-photo scans
    # classified as text_based with 1 and 4 characters of extractable
    # text, and were silently skipped — no OCR, no text layer. If
    # there is essentially no text per page, treat it as a scan.
    try:
        import fitz
        with fitz.open(str(path)) as doc:
            pages = max(1, doc.page_count)
            chars = sum(len(page.get_text().strip()) for page in doc)
        per_page = chars / pages
        if per_page < MIN_TEXT_CHARS_PER_PAGE:
            log.info(
                "pdf_classify said text_based but only %.1f chars/page "
                "on %s; OCR-ing anyway", per_page, path.name,
            )
            # Force OCR — this branch does NOT produce a skip today.
            # ``SKIP_REASON_TEXT_DENSITY_GUARD`` is reserved for a future
            # skip path through this guard (see its definition).
            return True, None
    except Exception as exc:  # noqa: BLE001 — guard is best-effort
        log.warning("text-density guard failed (%s); trusting classifier", exc)

    return False, SKIP_REASON_BORN_DIGITAL


def _assert_ocr_produced_blocks(result, nc_path: str) -> None:
    """Raise if a structured-OCR engine returned zero blocks.

    Two engines populate ``result.page_results`` (google, minimax); the
    third (``tesseract``) writes the text layer directly via ocrmypdf and
    deliberately leaves ``page_results=[]`` — that one is exempted.

    Background: the Google engine's bbox parser used to silently drop
    every Word (Vision populates ``normalized_vertices`` on the
    whole-doc batch path; pre-fix the code only read ``vertices``), so
    a "successful" run returned ``page_results`` with empty blocks for
    every page. The webhook then unconditionally stamped
    ``Producer = 'nc-ocr-flow 0.3 (engine=google)'`` and uploaded,
    marking the file ``done`` forever. Two follow-on costs:

      1. The stamp-skip branch (``_already_stamped_by_us``) kept
         hiding the file from re-OCR until manual intervention.
      2. The user's Nextcloud storage was rewriting ``Producer`` to
         ``pikepdf …`` (a separate, unfired TODO), so the stamp-based
         dedup didn't even survive — we just had no second-line
         defence.

    Raising here takes the existing error path (``_run_job``'s
    ``except Exception`` already records ``status=error`` and writes
    ``error`` to the SQLite job row). The file is left UN-stamped and
    UN-uploaded, so the next webhook or ``/rescan`` retries it. The
    error message names file, engine, and block count so an operator
    triaging the panel can act on it.
    """
    # Inline the canonical names instead of importing the registry, to
    # avoid loading engine modules just for a string compare and to
    # keep this function stable across engine renames.
    if result.engine_used not in ("google", "minimax"):
        return

    pages = result.page_results or []
    total_blocks = sum(len(p.blocks) for p in pages)
    if total_blocks > 0:
        return

    raise RuntimeError(
        f"OCR engine={result.engine_used} produced 0 blocks across "
        f"{len(pages)} page(s) for {nc_path!r}: empty result; file not "
        f"stamped or uploaded, eligible for retry"
    )


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

            # Gate the stamp + upload on a non-empty OCR result. An
            # engine that returned zero blocks (the documented Google
            # bbox-parser bug, or any future regression that drops text
            # silently) must NOT mark the file ``done`` — the worker
            # sees the raise as ``status=error`` and the next webhook
            # /rescan retries it. See :func:`_assert_ocr_produced_blocks`.
            _assert_ocr_produced_blocks(result, nc_path)

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
            # bypasses it (used by the "Re-OCR anyway" action). The
            # reason returned by ``_needs_ocr_decision`` is one of
            # ``SKIP_REASON_*`` — recording the actual branch lets the
            # operator tell "stamped by us" apart from "classifier
            # thinks born-digital" without re-running the classifier.
            needs_ocr, skip_reason = _needs_ocr_decision(local_file, force)
            if not needs_ocr:
                log.info(
                    "skip %s: %s (force=%s)",
                    nc_path, skip_reason, force,
                )
                return {
                    "path": nc_path,
                    "skipped": True,
                    "reason": skip_reason,
                }

            log.info("OCR-ing PDF (engine=%s force=%s): %s", engine, force, nc_path)
            result = process_pdf(local_file, engine=engine)

            # Gate the stamp + upload on a non-empty OCR result. See the
            # image branch above for the rationale and
            # :func:`_assert_ocr_produced_blocks` for the engine list.
            _assert_ocr_produced_blocks(result, nc_path)

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
#: Workers are woken by this signal; the work list itself is the
#: ``jobs`` table in SQLite, so a backlog of a million files costs
#: nothing in RAM.
_work_available = threading.Event()
#: Idle workers wake up this often even without a signal, so a lost
#: notification can never wedge the queue.
_IDLE_POLL_SECONDS = 5.0


#: Settings the panel may change: short key -> (env var, default).
#: Reading honours env (nix, authoritative) -> SQLite override -> default.
_SETTING_SPEC: dict[str, tuple[str, int]] = {
    "workers": ("NC_OCR_WORKERS", 2),
    "max_concurrent_google": ("NC_OCR_MAX_CONCURRENT_GOOGLE", 2),
    "max_concurrent_tesseract": ("NC_OCR_MAX_CONCURRENT_TESSERACT", 1),
    "max_concurrent_minimax": ("NC_OCR_MAX_CONCURRENT_MINIMAX", 1),
}
#: Settings that only take effect after a restart (the worker pool and
#: the semaphores are built at import time).
_RESTART_SETTINGS = {"workers"}

# Open the store before reading any setting out of it. Clearing the
# restart flag here is what makes "applied" mean applied: we only get
# this far by having restarted.
jobstore.init()
jobstore.setting_delete("_restart_pending")


def _int_env(name: str, default: int) -> int:
    """Positive int for a setting, honouring the precedence above.

    A value saved from the panel wins, so the operator can change the
    worker pool without a redeploy; the nix value stays the default and
    is what a fresh database falls back to.
    """
    raw = jobstore.settings_all().get(name)
    if raw in (None, ""):
        raw = os.environ.get(name)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return default


def _setting_values() -> tuple[dict[str, int], dict[str, int], dict[str, str]]:
    """(current, defaults, source) per short key, for the panel."""
    stored = jobstore.settings_all()
    current: dict[str, int] = {}
    defaults: dict[str, int] = {}
    sources: dict[str, str] = {}
    for key, (env_name, default) in _SETTING_SPEC.items():
        defaults[key] = default
        raw = stored.get(env_name)
        if raw not in (None, ""):
            sources[key] = "db"
        else:
            raw = os.environ.get(env_name)
            sources[key] = "env" if raw not in (None, "") else "default"
        try:
            current[key] = max(1, int(raw))
        except (TypeError, ValueError):
            current[key] = default
            sources[key] = "default"
    return current, defaults, sources


def _pending_restart() -> bool:
    return bool(jobstore.settings_all().get("_restart_pending"))


#: How many worker threads pull from the work list.
_WORKERS = _int_env("NC_OCR_WORKERS", 2)

#: Per-engine concurrency ceilings. Raising ``NC_OCR_WORKERS`` is safe:
#: a worker only starts a job after taking its engine's slot, so the
#: Google Vision / MiniMax quotas cannot be exceeded by adding workers.
_ENGINE_SLOTS = {
    "google": threading.Semaphore(
        _int_env("NC_OCR_MAX_CONCURRENT_GOOGLE", 2)),
    "tesseract": threading.Semaphore(
        _int_env("NC_OCR_MAX_CONCURRENT_TESSERACT", 1)),
    "minimax": threading.Semaphore(
        _int_env("NC_OCR_MAX_CONCURRENT_MINIMAX", 1)),
}
_DEFAULT_SLOT = threading.Semaphore(
    _int_env("NC_OCR_MAX_CONCURRENT_DEFAULT", 2))


def _path_in_flight(nc_path: str) -> bool:
    """True if this path is queued or running right now.

    Answered from the ``files`` table (one keyed lookup), not from an
    in-memory dict — the index has to work for a million files.
    """
    rec = jobstore.file_get(nc_path)
    return bool(rec) and rec.get("status") in ("queued", "running")


def _record_job(job: dict) -> None:
    """No-op shim, kept so the call sites stay readable.

    Job state lives in SQLite now (``jobstore.record_update``); the old
    in-memory mirror is gone, so a million-file backlog costs no RAM.
    """
    return None


def _engine_slot(engine: str | None):
    """Concurrency ceiling for this job's engine."""
    key = (engine or os.environ.get("NC_OCR_ENGINE") or "google").lower()
    return _ENGINE_SLOTS.get(key, _DEFAULT_SLOT)


def _run_job(job: dict) -> None:
    """Process one claimed job and persist its outcome."""
    item = job
    job["status"] = "running"
    job["started"] = job.get("started") or time.time()
    # Mirror to durable history (best-effort; never raises).
    jobstore.record_update(job)
    try:
        log.info("worker: job %d start: %s (engine=%s force=%s)",
                 job["id"], job["path"], job["engine"], item.get("force"))
        # Take the engine's slot: this is what keeps an API quota intact
        # when NC_OCR_WORKERS is raised.
        with _engine_slot(item.get("engine")):
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
        # Persist the final state to SQLite. ``record_update`` is
        # upsert-by-id and never raises into the caller — the OCR
        # pipeline must not break because the history DB is down.
        jobstore.record_update(job)
        node_id = item["node_id"]
        force = item.get("force", False)
        # ``force`` re-OCRs skip the recently_processed guard so the
        # user can deliberately re-OCR a file we just processed. The
        # index write below records the path either way.
        if node_id and not force:
            _mark_processed(node_id)
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
        # Billable usage. Vision charges one unit per page (each PDF page
        # counts as an individual image), so count pages, not requests —
        # and only for jobs that really went to an engine (skipped files
        # are born-digital and never leave the box).
        if job["status"] == "done":
            _pages = 0
            if isinstance(job_result, dict):
                for key in ("vlm_pages", "pages", "page_count"):
                    val = job_result.get(key)
                    if isinstance(val, (list, tuple)):
                        _pages = max(_pages, len(val))
                    elif isinstance(val, int):
                        _pages = max(_pages, val)
            jobstore.usage_add(engine_used or job.get("engine"), pages=_pages)


def _ocr_worker() -> None:
    """Worker loop: claim a job from the SQLite work list and run it.

    The backlog lives in the DB, not in this process, so any number of
    these can run (``NC_OCR_WORKERS``). Idle workers wait on
    ``_work_available`` with a timeout, which also covers a signal that
    was set while a job was being processed.
    """
    while True:
        try:
            job = jobstore.claim_next()
        except Exception as exc:  # noqa: BLE001 — never kill the loop
            log.error("worker: claim failed: %s", exc)
            job = None
        if job is None:
            _work_available.wait(timeout=_IDLE_POLL_SECONDS)
            _work_available.clear()
            continue
        _run_job(job)


# Jobs left 'running' by a crash or restart go back in the queue before
# any worker starts.
_requeued = jobstore.requeue_stale()
if _requeued:
    log.info("startup: re-queued %d job(s) abandoned by a restart", _requeued)
for _worker_idx in range(_WORKERS):
    threading.Thread(target=_ocr_worker, daemon=True,
                     name=f"ocr-worker-{_worker_idx}").start()
log.info("started %d OCR worker(s) (NC_OCR_WORKERS)", _WORKERS)


# --- Vision spend + rate quota ---------------------------------------------
#: Free units per month per feature, then USD per 1000 units.
#: Source: cloud.google.com/vision/pricing — "each page is treated as an
#: individual image" and "each feature applied to an image is a billable
#: unit", so for us one unit = one page.
VISION_FREE_UNITS = 1000
VISION_USD_PER_1000 = 1.50
#: How often to re-read the rate quota. The metric is sampled once a
#: minute and lags up to four, so polling faster than this adds nothing.
_VISION_QUOTA_INTERVAL = float(os.environ.get("NC_OCR_VISION_QUOTA_INTERVAL", "900"))


def _vision_credentials_path() -> str:
    """Locate the Vision service-account JSON, or "" when unavailable."""
    p = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if p and Path(p).exists():
        return p
    d = os.environ.get("CREDENTIALS_DIRECTORY", "")
    if d:
        cand = Path(d) / "google-ocr-key"
        if cand.exists():
            return str(cand)
    return ""


def _vision_quota_once() -> None:
    """Read the Vision rate quota and last-minute usage into settings.

    Strictly read-only, and silent on every failure: without google-auth,
    without the credential file, or without the viewer roles the panel
    simply shows no reading instead of the service breaking.
    """
    path = _vision_credentials_path()
    if not path:
        return
    try:
        import datetime as _dt
        import urllib.parse
        import urllib.request

        import google.auth.transport.requests as _gtr
        from google.oauth2 import service_account

        info = json.loads(Path(path).read_text())
        proj = info.get("project_id")
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(_gtr.Request())
        hdr = {"Authorization": "Bearer " + creds.token}

        def _get(url: str) -> dict:
            req = urllib.request.Request(url, headers=hdr)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())

        limit = None
        url = (f"https://cloudquotas.googleapis.com/v1/projects/{proj}"
               "/locations/global/services/vision.googleapis.com/quotaInfos")
        for qi in _get(url).get("quotaInfos", []):
            if qi.get("quotaId") == "DocumentTextDetectionRequestsPerMinutePerProject":
                dims = qi.get("dimensionsInfos") or [{}]
                val = dims[0].get("details", {}).get("value")
                if val is not None:
                    limit = int(val)

        now = _dt.datetime.now(_dt.timezone.utc)
        flt = ('metric.type="serviceruntime.googleapis.com/quota/rate/net_usage"'
               ' AND resource.type="consumer_quota"'
               ' AND resource.label.service="vision.googleapis.com"')
        murl = (f"https://monitoring.googleapis.com/v3/projects/{proj}/timeSeries?"
                + urllib.parse.urlencode({
                    "filter": flt,
                    "interval.startTime": (now - _dt.timedelta(minutes=10))
                    .isoformat().replace("+00:00", "Z"),
                    "interval.endTime": now.isoformat().replace("+00:00", "Z")}))
        peak = 0
        for series in _get(murl).get("timeSeries", []):
            for pt in series.get("points", []):
                val = pt.get("value", {})
                raw = val.get("int64Value", val.get("doubleValue", 0))
                try:
                    peak = max(peak, int(float(raw)))
                except (TypeError, ValueError):
                    continue

        if limit:
            jobstore.setting_put("_vision_limit_per_min", str(limit))
        jobstore.setting_put("_vision_used_per_min", str(peak))
        jobstore.setting_put("_vision_checked", str(int(time.time())))
        jobstore.setting_put("_vision_quota_ok", "1")
        log.info("vision quota: %s of %s requests/min used", peak, limit or "?")
    except Exception as exc:  # noqa: BLE001 — quota reading must never matter
        jobstore.setting_put("_vision_quota_ok", "")
        log.warning("vision quota read failed: %s", exc)


def _vision_quota_loop() -> None:
    while True:
        _vision_quota_once()
        time.sleep(_VISION_QUOTA_INTERVAL)


threading.Thread(target=_vision_quota_loop, name="vision-quota",
                 daemon=True).start()


def _vision_summary() -> dict:
    """Vision spend this month plus the last rate-quota reading."""
    month = jobstore.usage_month("google")
    pages = month["pages"]
    stored = jobstore.settings_all()
    try:
        limit = int(stored.get("_vision_limit_per_min") or 1800)
    except (TypeError, ValueError):
        limit = 1800
    try:
        used = int(stored.get("_vision_used_per_min") or 0)
    except (TypeError, ValueError):
        used = 0
    try:
        checked = float(stored.get("_vision_checked") or 0) or None
    except (TypeError, ValueError):
        checked = None
    return {
        "pages_month": pages,
        "jobs_month": month["jobs"],
        "cost_usd": round(pages * VISION_USD_PER_1000 / 1000, 4),
        "free_units": VISION_FREE_UNITS,
        "free_left": max(0, VISION_FREE_UNITS - pages),
        "limit_per_min": limit,
        "used_per_min": used,
        "used_percent": round(used / limit * 100, 1) if limit else 0.0,
        "quota_checked": checked,
        "quota_ok": bool(stored.get("_vision_quota_ok")),
    }

# One-time migration: the OCR index used to be a JSON file loaded into
# memory. It now lives in the ``files`` table, so a million-entry index
# costs no RAM and no JSON parse at startup.
try:
    if _INDEX_FILE.exists() and jobstore.file_count() == 0:
        _migrated = jobstore.file_import(json.loads(_INDEX_FILE.read_text()))
        if _migrated:
            log.info("migrated %d index entries from %s into SQLite",
                     _migrated, _INDEX_FILE)
            _INDEX_FILE.rename(_INDEX_FILE.with_suffix(".json.migrated"))
except Exception as exc:  # noqa: BLE001
    log.warning("index migration failed: %s", exc)
# Open the SQLite job history. ``init()`` is a no-op if the DB is
# unreachable; every later ``record_*`` call stays silent in that case.
jobstore.init()


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
        "nc_path": nc_path,
        "node_id": node_id,
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
    # Mirror to durable SQLite history (best-effort, never raises).
    jobstore.record_enqueue(job)
    # The row is already in SQLite (``record_enqueue`` above) — that IS
    # the queue. Mark the file in-flight so a repeat scan skips it,
    # then wake a worker.
    _prev = jobstore.file_get(nc_path) or {}
    jobstore.file_put({**_prev, "path": nc_path, "status": "queued",
                       "node_id": node_id})
    _work_available.set()
    return job


def _check_secret(x_webhook_secret: str | None) -> None:
    """Fail closed: an unset secret must never mean "no auth"."""
    import hmac

    if not WEBHOOK_SECRET:
        log.error("webhook secret is not configured — refusing request")
        raise HTTPException(status_code=503,
                            detail="webhook secret not configured")
    if not hmac.compare_digest(str(x_webhook_secret or ""), WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="invalid secret")


# --- FastAPI app ---

# Docs endpoints off: FastAPI serves /openapi.json, /docs and /redoc
# unauthenticated by default, which hands anyone on the loopback the
# full API schema — including the name and shape of the secret header.
app = FastAPI(
    title="nc-ocr-flow webhook receiver",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

#: Nothing this service accepts is large — the payloads are event
#: notifications. Reject oversized bodies instead of parsing them.
_MAX_BODY_BYTES = 2 * 1024 * 1024


@app.middleware("http")
async def _limit_body_size(request: Request, call_next):
    raw = request.headers.get("content-length")
    if raw and raw.isdigit() and int(raw) > _MAX_BODY_BYTES:
        return JSONResponse({"detail": "payload too large"}, status_code=413)
    return await call_next(request)


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
    if not force and not _claim_node(node_id):
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
    # Everything comes from SQLite now — the in-memory job mirror is
    # gone, so the panel and the workers read the same state.
    counts = jobstore.stats()
    return {
        "service": "nc-ocr-flow",
        "queue_depth": counts.get("queued", 0),
        "workers": _WORKERS,
        "running_count": counts.get("running", 0),
        "queued": jobstore.query(limit=limit, status="queued"),
        "running": jobstore.query(limit=limit, status="running"),
        "history": jobstore.query(limit=limit),
    }


def _parse_since(value: str | None) -> float | None:
    """Coerce the ``since`` query param to a unix epoch (seconds).

    Accepts a numeric string (epoch seconds, optionally with decimals)
    or an ISO-8601 date/time. Returns ``None`` on parse failure so the
    downstream SQLite query just returns everything.
    """
    if value is None or value == "":
        return None
    s = value.strip()
    if not s:
        return None
    # Numeric first — most clients send epoch seconds.
    try:
        return float(s)
    except ValueError:
        pass
    try:
        from datetime import datetime, timezone
        iso = s.replace("Z", "+00:00") if s.endswith("Z") else s
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


@app.get("/settings")
async def get_settings(
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Current settings, where each value came from, and the defaults."""
    _check_secret(x_webhook_secret)
    current, defaults, sources = _setting_values()
    return {
        "settings": current,
        "defaults": defaults,
        "sources": sources,
        "restart_required": _pending_restart(),
    }


@app.post("/settings")
async def put_settings(
    body: dict,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Save setting overrides (stored in SQLite, applied on restart).

    Unknown keys and non-positive values are rejected with 422. Changing
    the worker count needs a restart because the pool is built at import
    time — safe now, since in-flight jobs are requeued on startup.
    """
    _check_secret(x_webhook_secret)
    saved: list[str] = []
    for key, value in (body or {}).items():
        if key not in _SETTING_SPEC:
            raise HTTPException(status_code=422,
                                detail=f"unknown setting: {key}")
        try:
            ival = int(value)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be a positive integer") from None
        if ival < 1:
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be at least 1 (got {ival})")
        jobstore.setting_put(_SETTING_SPEC[key][0], str(ival))
        saved.append(key)
    restart = any(k in _RESTART_SETTINGS for k in saved)
    if restart:
        jobstore.setting_put("_restart_pending", "1")
    current, _defaults, sources = _setting_values()
    return {"saved": saved, "settings": current, "sources": sources,
            "restart_required": restart or _pending_restart()}


@app.get("/jobs")
async def list_jobs(
    limit: int = 50,
    status: str | None = None,
    since: str | None = None,
    path_contains: str | None = None,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Durable job history backed by SQLite.

    Query params:
      limit          — max rows to return (default 50, hard-capped at 500)
      status         — exact-match filter, e.g. "done", "error", "queued"
      since          — unix epoch (seconds) or ISO-8601 date; only jobs
                       with ``created >= since`` are returned
      path_contains  — substring filter on the file's NC path

    Returns ``{"count": N, "limit": L, "jobs": [...]}``. Secret-protected
    like every other endpoint here — see ``_check_secret``.
    """
    _check_secret(x_webhook_secret)
    lim = max(1, min(int(limit), 500))
    since_f = _parse_since(since)
    rows = jobstore.query(
        limit=lim,
        status=status,
        since=since_f,
        path_contains=path_contains,
    )
    return {"count": len(rows), "limit": lim, "jobs": rows}


@app.get("/jobs/stats")
async def jobs_stats(
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Aggregate counts by status (plus ``total``)."""
    _check_secret(x_webhook_secret)
    return jobstore.stats()


@app.get("/jobs/{job_id}")
async def get_job(
    job_id: int,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Fetch one historical job by id, or 404 if not in the SQLite history."""
    _check_secret(x_webhook_secret)
    job = jobstore.get(int(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return job


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
    if all_files:
        out = jobstore.file_all()
    else:
        for p in want:
            m = jobstore.file_get(p)
            if m:
                out[p] = m

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
    idx = list(jobstore.file_all().values())

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
        # Spend and rate-limit visibility for the panel (see _vision_summary).
        "vision": _vision_summary(),
        "usage": jobstore.usage_summary(7),
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
        jobstore.node_forget(body.node_id)

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
        if body.skip_ocrd:
            _rec = jobstore.file_get(nc_path)
            if _rec and _rec.get("status") == "done":
                skipped_ocrd += 1
                continue
        # node_id is unknown from a listing, so dedup by path: skip
        # files whose job is already queued or running.
        if _path_in_flight(nc_path):
            log.info("scan-all: skip in-flight %s", nc_path)
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
async def panel(request: Request):
    """Serve the OCR status panel.

    Local-only (the service already binds to 127.0.0.1, this is
    defence in depth) and never framed: the page asks the user for the
    webhook secret, so embedding it in a foreign frame is a phishing
    surface.
    """
    client_host = ""
    try:
        client_host = (request.client.host if request.client else "") or ""
    except Exception:  # noqa: BLE001
        client_host = ""
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="panel is local-only")

    static = Path(__file__).parent / "static" / "panel.html"
    return HTMLResponse(
        content=static.read_text(encoding="utf-8"),
        headers={
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'none'; "
                "form-action 'none'"
            ),
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
