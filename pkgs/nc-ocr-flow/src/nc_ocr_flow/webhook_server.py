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
import secrets
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

#: Image-branch collision: a PDF already exists at the target path,
#: so an image-to-PDF conversion would silently overwrite the user's
#: existing PDF. The image branch refuses and records this reason so
#: an operator can resolve the conflict manually (rename, delete, or
#: reroute the source image).
SKIP_REASON_PDF_EXISTS         = "pdf_already_exists"

#: G2: fingerprint-verified skip guard. After
#: :data:`FOREIGN_REWRITE_LIMIT` consecutive foreign rewrites of the
#: same NC path (i.e. another OCR writer on the same Nextcloud keeps
#: replacing our output), the guard stops auto-re-OCRing and records
#: this reason instead of the usual stamp skip. The file is left for
#: the operator to triage (typically by removing the competing writer
#: from the Nextcloud app store, or by /rescan with ``force=true``).
REASON_FOREIGN_REWRITE = "foreign_rewrite"

#: G2: the bound on consecutive foreign rewrites before the guard
#: gives up auto-re-OCRing the same path. Three is enough that a
#: transient storage-layer race (e.g. Nextcloud's async writer
#: overwriting us twice in quick succession) does not trip the
#: guard, but small enough that a permanently-installed competing
#: writer (the production failure mode: the third-party
#: ``workflow_ocr`` Nextcloud app rewriting us ~2 minutes after each
#: upload) is caught before it bills Google three more times in a
#: row. The trade-off is operator cost (manual triage) vs API cost
#: (unbounded Vision re-billing); 3 wins for the production
#: observed rate of one rewrite per ~2 min × per-file.
FOREIGN_REWRITE_LIMIT = 3

#: Current durable stamp version. Bumped from ``0.3`` to ``0.4``
#: because the previous parser bug silently returned zero text on a
#: long stretch of runs — every stamp produced by that broken
#: pipeline is *untrustworthy* and must be re-OCR'd. The skip check
#: requires this version: older stamps mean "treat as un-stamped",
#: which is the user-decided migration policy.
STAMP_VERSION = "0.4"
#: XMP namespace URI under which the durable stamp lives. Custom
#: namespaces don't collide with anything Nextcloud / pikepdf
#: regenerates, so the stamp survives a WebDAV PUT even when the
#: producer line is rewritten.
STAMP_XMP_NS = "http://likivik.com/nc-ocr-flow/1.0/"

# Loop prevention: which node IDs we processed recently. The claim lives
# in SQLite (jobstore.claim_node) so it survives a restart.
#: Default TTL — overridable via env ``NC_OCR_PROCESSED_TTL`` (seconds)
#: or a stored setting named ``NC_OCR_PROCESSED_TTL``. Read at call
#: time so an operator can tune the window without a redeploy when a
#: slow Vision batch plus a Nextcloud retry would otherwise exceed the
#: default 300 s.
_PROCESSED_TTL = 300  # 5 minutes
_DEFAULT_PROCESSED_TTL = 300


def _processed_ttl_seconds() -> float:
    """Resolve the recently-processed guard TTL honouring settings + env.

    Precedence (highest first):
      1. ``NC_OCR_PROCESSED_TTL`` stored in ``settings`` (operator panel)
      2. ``NC_OCR_PROCESSED_TTL`` env var (nix service config)
      3. :data:`_DEFAULT_PROCESSED_TTL` (compile-time default)

    The value is read on every webhook call so a panel change takes
    effect without a restart. Seconds (whole-number) — a float would
    buy nothing because WebDAV round-trips already run on second-scale
    timeouts, and integer seconds keep the panel simple.
    """
    return float(_int_env_nonneg(
        "NC_OCR_PROCESSED_TTL", _DEFAULT_PROCESSED_TTL,
    ))


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
    return not jobstore.claim_node(node_id, _processed_ttl_seconds())


def _claim_node(node_id: int) -> bool:
    """Atomically claim ``node_id`` for processing.

    Delegates to SQLite: the claim survives a restart, so a deploy no
    longer makes us forget which files we just processed. On a DB error
    it fails open (process the file) rather than skipping it forever.
    """
    return jobstore.claim_node(node_id, _processed_ttl_seconds())


def _mark_processed(node_id: int) -> None:
    """Refresh the claim timestamp after a successful run."""
    jobstore.claim_node(node_id, 0.0) if node_id else None


# --- WebDAV client ---

#: Distinct reason recorded in ``files.reason`` when a webhook fires
#: for a path owned by a Nextcloud user other than the one this service
#: is configured to authenticate as (NC_OCR_NC_USER, default ``likivik``).
#: The service user has no access to other users' WebDAV roots, so the
#: old behaviour — authenticate as NC_USER, hit a 401, retry 3×, mark
#: ``error`` — produced a stream of opaque ``error`` rows for files
#: the service could never have processed. We refuse the work at the
#: boundary instead (C1).
REASON_FOREIGN_USER = "foreign_user"


def _path_user(nc_path: str) -> str:
    """Return the Nextcloud user segment of an NC-internal path, or ``""``.

    NC delivers paths as ``/<user>/files/<rel>``; the same form the
    webhook hands us. The user segment is the first path component.
    Returns the empty string when the path is unparseable so the
    caller can fall back to :data:`NC_USER` and the WebDAV URL builder
    does the right thing. Deliberately permissive: the strict path
    check lives in :func:`_is_foreign_user` and the URL builder, not
    here.
    """
    rel = (nc_path or "").lstrip("/")
    if not rel:
        return ""
    return rel.split("/", 1)[0]


def _is_foreign_user(nc_path: str) -> bool:
    """True when ``nc_path`` belongs to a Nextcloud user other than NC_USER.

    Used at the /webhook /scan-all /rescan boundaries to short-circuit
    a job that the service user (NC_OCR_NC_USER) can never satisfy —
    every WebDAV call would 401, be retried 3×, and end as a generic
    ``error`` row. We record the file with :data:`REASON_FOREIGN_USER`
    and respond 200 so Nextcloud does not retry.
    """
    u = _path_user(nc_path)
    if not u:
        # Unparseable path: the URL builder will fall back to NC_USER,
        # so this is not "foreign" — let downstream handle the error.
        return False
    return u != NC_USER


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
    """Delete file from NC via WebDAV DELETE (for image→PDF replacement).

    Raises ``raise_for_status`` inside the retried closure — the same
    shape as ``_webdav_download`` / ``_webdav_upload``. A 5xx on the
    final attempt otherwise escapes unretried, and in the image→PDF
    branch (lines around 910-918 in ``_process_file``) would leave both
    the source image and the new PDF in Nextcloud while the job row
    silently records ``error``.
    """
    url = _webdav_url(nc_path)
    log.info("WebDAV DELETE %s", url)
    def _do_delete() -> requests.Response:
        r = requests.delete(
            url, auth=(NC_USER, NC_PASSWORD), timeout=30,
        )
        r.raise_for_status()
        return r

    _retry(_do_delete, what=f"WebDAV DELETE {nc_path}")


def _webdav_replace_atomic(nc_path: str, src: Path) -> None:
    """Atomically overwrite ``nc_path`` with ``src`` via WebDAV MOVE.

    C3: the previous PDF-overwrite path did a plain PUT straight over
    the user's original. A partial upload (server-side crash,
    connection reset, upload timeout) left a truncated, corrupt PDF on
    disk with no way to recover — the original was already gone.
    Nextcloud/sabre's WebDAV server supports atomic MOVE, so we:

      1. PUT the new content to a sibling temp path
         (``<name>.ocr-tmp-<rand>`` in the same WebDAV directory);
      2. MOVE the temp path onto ``nc_path`` with
         ``Destination: <target>`` and ``Overwrite: T`` (sabre
         implements MOVE atomically);
      3. DELETE the temp path on any failure (best-effort).

    The image→PDF branch keeps using ``_webdav_upload`` because the
    target is a brand-new path; nothing to corrupt, and a plain PUT is
    strictly cheaper than a temp-and-MOVE round trip.
    """
    from urllib.parse import quote

    target_url = _webdav_url(nc_path)
    # Build a sibling temp URL by splitting nc_path's user-relative
    # component, appending ``.ocr-tmp-<rand>``, and URL-encoding each
    # segment the same way ``_webdav_url`` does. We keep the temp in
    # the same WebDAV directory so a MOVE between them is local and
    # can be atomic (sabre won't cross storage backends).
    rel = nc_path.lstrip("/")
    parts = rel.split("/", 2)
    if len(parts) >= 3 and parts[1] == "files":
        user = parts[0]
        rel_file = parts[2]
    else:
        user = NC_USER
        rel_file = rel
    suffix = "".join(
        c if c.isalnum() else "" for c in (Path(rel_file).suffix or "")
    ) or ".tmp"
    parent = str(Path(rel_file).parent)
    base = Path(rel_file).name
    # Eight hex chars from a fresh os.urandom — collision chance is
    # negligible at the volumes this service runs, and we DELETE on
    # failure so a stray temp does not accumulate.
    rand = secrets.token_hex(4)
    tmp_name = f"{base}.ocr-tmp-{rand}{suffix}"
    if parent and parent != ".":
        tmp_rel = f"{parent}/{tmp_name}"
    else:
        tmp_rel = tmp_name
    tmp_url = f"{NC_URL}/remote.php/dav/files/{user}/" + "/".join(
        quote(p, safe="") for p in tmp_rel.split("/")
    )
    log.info("atomic-replace: PUT tmp %s", tmp_url)

    def _do_put_tmp() -> None:
        with src.open("rb") as f:
            r = requests.put(
                tmp_url,
                data=f,
                auth=(NC_USER, NC_PASSWORD),
                headers={"Content-Type": "application/octet-stream"},
                timeout=300,
            )
        r.raise_for_status()

    def _do_move() -> requests.Response:
        r = requests.request(
            "MOVE", tmp_url,
            auth=(NC_USER, NC_PASSWORD),
            headers={
                "Destination": target_url,
                "Overwrite": "T",
            },
            timeout=120,
        )
        # 201/204 are success; 412 means destination existed and
        # Overwrite: T was rejected (shouldn't happen on a known
        # existing path, but we surface it as a real error rather
        # than retrying forever).
        r.raise_for_status()
        return r

    def _do_cleanup() -> None:
        # Best-effort. If cleanup fails the temp object leaks; the
        # startup orphan sweep (if it finds it) and the operator can
        # remove it by hand. We do NOT want a cleanup failure to
        # mask a successful MOVE.
        try:
            requests.delete(
                tmp_url, auth=(NC_USER, NC_PASSWORD), timeout=30,
            ).raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "atomic-replace: cleanup DELETE %s failed (%s);"
                " temp object may leak", tmp_url, exc,
            )

    try:
        _retry(_do_put_tmp, what=f"atomic-replace PUT {tmp_url}")
        _retry(_do_move, what=f"atomic-replace MOVE {tmp_url} -> {target_url}")
    except Exception:
        _do_cleanup()
        raise


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


def _webdav_exists(nc_path: str, timeout: int = 10) -> bool:
    """Cheap existence check: HEAD the WebDAV URL, return True on 2xx/3xx.

    Used by the C5 stale-row reconciler. We pick HEAD over PROPFIND
    because sabre answers HEAD without reading the body — important
    when one reconcile pass may scan a few hundred rows. A
    transport-level failure (timeout, 5xx, connection reset) is
    treated as "unknown, do not mark" so the reconciler is safe to
    re-run: the row is still in the index, just not flipped to
    ``gone`` this pass.

    B3 audit: Nextcloud returns ``410 Gone`` for a file that has
    been permanently removed out-of-band (vs ``404 Not Found`` for
    a missing path). Both signals mean "the path is gone for good
    from our perspective"; we treat them the same so the
    reconciler can mark the row ``gone``. ``HEAD`` on a folder in
    Nextcloud sometimes returns ``405 Method Not Allowed`` even
    when the folder exists, so any non-4xx-and-not-410 status
    keeps the row.

    Note: we call ``requests.request("HEAD", ...)`` rather than
    ``requests.head(...)`` so the standard test pattern of
    monkeypatching ``ws.requests.request`` actually intercepts the
    call (``requests.head`` captures ``request`` at import time and
    bypasses attribute lookup on the parent module).
    """
    url = _webdav_url(nc_path)
    try:
        r = requests.request(
            "HEAD", url, auth=(NC_USER, NC_PASSWORD), timeout=timeout,
        )
    except (requests.RequestException, TimeoutError, OSError) as exc:
        log.debug("HEAD %s failed: %s", url, exc)
        return True  # unknown — keep the row
    # 404 Not Found AND 410 Gone both mean "permanently removed".
    # 2xx/3xx = present. 5xx, 401/403, 405 = we cannot tell, keep
    # the row (transient, auth, or folder-edge quirk).
    return r.status_code not in (404, 410)


# --- Stale-row reconciler (C5) ---------------------------------------------
# Cap on how many rows one reconcile pass will examine. The query
# itself is bounded by ``jobstore.file_paths_by_status``; this is the
# *post-query* ceiling on PROPFINDs to keep the worst-case wall-clock
# bounded if the index is large. Empirically one PROPFIND takes
# ~50–200ms over a tailnet, so 500 rows ≈ 1.5 minutes.
_RECONCILE_MAX_PROPFINDS = int(os.environ.get(
    "NC_OCR_RECONCILE_MAX_PROPFINDS", "500"
))
# How many rows one reconcile pass queries from the index. The
# ordering is ``finished ASC`` (oldest first) so the first pass
# cleans the worst offenders.
_RECONCILE_QUERY_LIMIT = int(os.environ.get(
    "NC_OCR_RECONCILE_QUERY_LIMIT", "500"
))


def reconcile_stale_files(
    limit: int | None = None,
    max_propfind: int | None = None,
    statuses: list[str] | None = None,
) -> dict:
    """Mark ``error``/``queued`` file rows ``gone`` when the file no longer exists.

    C5: production has 36 file rows stuck at ``status='error'`` for
    files that were deleted long ago (``__probe_*.pdf``, ``x.pdf``,
    and similar test artefacts). Nothing ever re-checks them, so
    ``/stats`` reports them as errors forever and the operator sees
    a panel that does not match reality. The reconciler:

      1. Selects up to ``limit`` file-index rows in ``statuses``
         (default ``['error', 'queued']``), ordered by ``finished``
         ASC so the oldest rows come first.
      2. HEAD-requests each path on WebDAV. 404 → mark ``gone`` with
         ``reason='file_removed'`` (same shape ``_run_job`` uses when
         it discovers a 404 mid-job, so the panel renders the state
         consistently).
      3. Bounded: ``max_propfind`` caps the PROPFINDs per call, so a
         large index never spawns an unbounded run.

    Rows that look transient (HEAD 5xx / connection error) are
    left alone — the next pass picks them up. Idempotent: rows
    already at ``status='gone'`` are filtered out at the query
    level, so calling this twice is a no-op the second time.
    """
    if limit is None:
        limit = _RECONCILE_QUERY_LIMIT
    if max_propfind is None:
        max_propfind = _RECONCILE_MAX_PROPFINDS
    if statuses is None:
        statuses = ["error", "queued"]
    effective = max(0, min(int(limit), int(max_propfind)))
    if effective == 0:
        return {
            "checked": 0, "marked_gone": 0, "kept": 0,
            "errors": [], "limit": int(limit),
            "max_propfind": int(max_propfind),
        }
    try:
        paths = jobstore.file_paths_by_status(statuses, limit=effective)
    except Exception as exc:  # noqa: BLE001
        log.error("reconcile_stale_files: query failed (%s)", exc)
        return {
            "checked": 0, "marked_gone": 0, "kept": 0,
            "errors": [{"path": None, "error": str(exc)}],
            "limit": int(limit), "max_propfind": int(max_propfind),
        }
    if not paths:
        return {
            "checked": 0, "marked_gone": 0, "kept": 0,
            "errors": [], "limit": int(limit),
            "max_propfind": int(max_propfind),
        }
    marked_gone = 0
    kept = 0
    errors: list[dict] = []
    for nc_path in paths:
        try:
            exists = _webdav_exists(nc_path)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": nc_path, "error": str(exc)})
            log.warning(
                "reconcile_stale_files: HEAD %s raised (%s); skipping",
                nc_path, exc,
            )
            continue
        if not exists:
            # Mirror the shape the worker produces when it discovers
            # a 404 mid-job — operators see one reason for "gone",
            # not one per reconciler invocation.
            _index_record(
                nc_path, "gone", engine=None,
                reason="file_removed", node_id=0,
            )
            marked_gone += 1
            log.info(
                "reconcile_stale_files: %s → gone (HEAD 404)", nc_path,
            )
        else:
            kept += 1
    if marked_gone or errors:
        log.warning(
            "reconcile_stale_files: checked=%d marked_gone=%d kept=%d errors=%d",
            len(paths), marked_gone, kept, len(errors),
        )
    return {
        "checked": len(paths),
        "marked_gone": marked_gone,
        "kept": kept,
        "errors": errors,
        "limit": int(limit),
        "max_propfind": int(max_propfind),
    }


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
    """Write OCR provenance into the PDF (PyMuPDF).

    Two storage locations are written on purpose:

      1. **Custom XMP property** under
         :data:`STAMP_XMP_NS` (``ncocr:stamp = STAMP_VERSION``). This
         is the *durable* marker — the user observed Nextcloud's
         storage layer rewriting ``Producer`` to ``pikepdf …`` on every
         WebDAV PUT, which made the previous Producer-only stamp a
         silent no-op in production. XMP under a custom namespace is
         not one of the standard fields any tool regenerates, so it
         survives the round-trip and remains a reliable "we stamped
         this" signal for :func:`_already_stamped_by_us`.

      2. **Document Info fields** — Subject / Keywords / Producer — for
         human-readable provenance when an operator opens the file in
         a PDF reader. ``Producer`` is best-effort (will likely be
         rewritten by Nextcloud on the next PUT); ``Subject`` and
         ``Keywords`` are durable enough on this host that we use
         ``Subject`` as a secondary fallback in the stamp check.

    Versioning
    ----------
    Every stamp carries ``stamp_version = STAMP_VERSION``. The skip
    check requires the *current* version, so any older stamp (the
    pre-fix ``0.3`` series produced by the silent-zero-text parser
    bug) means "treat as un-stamped". That is the user-decided
    migration policy — a one-time re-OCR of every previously-stamped
    file, which is exactly what we want after the parser fix.

    Subject / Keywords formats (carried over from 0.3):

      Subject:  OCR <ts> stamp_version=<VER> input_sha256=<hex64>
                source=current langs=rus+eng
                <engine>:api=<api> <engine>:ver=<ver>
                tesseract_pages=<ranges> vlm_pages=<ranges>
                [vlm_failed=<ranges>] [l2=<p:l:c[,esc];...>]

      Keywords: nc-ocr-flow, ocr, stamp_version=<VER>[, vlm-failed][, handwriting]
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

    meta["producer"] = f"nc-ocr-flow {STAMP_VERSION} (engine={engine})"

    # Build Subject as a single line — keys appear in a fixed order so
    # /status and triage scripts can grep reliably.
    parts = [
        f"OCR {ts}",
        f"stamp_version={STAMP_VERSION}",
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

    kw = f"nc-ocr-flow, ocr, stamp_version={STAMP_VERSION}"
    if vlm_failed:
        kw += ", vlm-failed"
    escalated = [p for p, v in (l2_pages or {}).items() if v.get("escalate")]
    if escalated:
        kw += ", handwriting"
    meta["keywords"] = kw
    doc.set_metadata(meta)

    # Durable stamp: a custom XMP property under our private namespace.
    # Pikepdf and Nextcloud's storage layer do not regenerate custom
    # XMP namespaces, so this marker is the only field we can trust to
    # survive an arbitrary number of WebDAV PUT cycles. See the module
    # docstring of :func:`_already_stamped_by_us` for the matching read
    # path.
    doc.set_xml_metadata(_build_stamp_xmp(engine, engine_api, engine_ver))

    doc.saveIncr()
    doc.close()


def _build_stamp_xmp(
    engine: str, engine_api: str = "unknown", engine_ver: str = "unknown"
) -> str:
    """Build the XMP packet carrying our durable stamp.

    Public so the test suite can construct the same packet without
    round-tripping through a real PDF (the read path in
    :func:`_already_stamped_by_us` accepts anything ElementTree can
    parse, so the test can hand-construct a minimal ``<rdf:Description>``
    and call the parser directly).
    """
    # xml.sax.saxutils.escape guards against engine strings that could
    # break the XML (e.g. an engine named "foo&bar"); STAMP_VERSION is
    # a literal so it's not strictly needed but we treat it uniformly.
    from xml.sax.saxutils import escape
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
        f'<rdf:Description xmlns:ncocr="{STAMP_XMP_NS}" rdf:about=""'
        f' ncocr:stamp="{escape(STAMP_VERSION)}"'
        f' ncocr:engine="{escape(engine)}"'
        f' ncocr:engine_api="{escape(engine_api)}"'
        f' ncocr:engine_ver="{escape(engine_ver)}"'
        '/>\n'
        '</rdf:RDF>\n'
        '</x:xmpmeta>\n'
    )


def _parse_xmp_stamp(stream_bytes: bytes | str) -> dict[str, str]:
    """Extract our stamp properties from an XMP packet.

    Returns a dict of ``{key: value}`` for every ``ncocr:*`` attribute
    found on the top-level ``rdf:Description``. Empty dict if the
    stream cannot be parsed or contains no stamp — never raises.

    Uses ``defusedxml`` when available to defang the well-known XXE /
    billion-laughs attacks in stdlib's XML parsers. The XMP packet is
    attacker-controlled in this service (it lives inside a PDF anyone
    can upload via Nextcloud's WebDAV), so hardening the parser is
    the right move; we only extract attribute values, never evaluate
    anything inside the XML. Falls back to stdlib's ElementTree with
    entity loading disabled if defusedxml is not installed — the
    fallback is still safer than the default because the parser is
    given an empty ``parser`` with no external entity resolver.
    """
    import logging as _logging
    import xml.etree.ElementTree as ET

    if isinstance(stream_bytes, bytes):
        try:
            text = stream_bytes.decode("utf-8", errors="replace")
        except Exception:
            return {}
    else:
        text = stream_bytes
    if not text:
        return {}
    try:
        try:
            import defusedxml.ElementTree as _defused
            root = _defused.fromstring(text)
        except ImportError:
            # stdlib fallback: parse without a default resolver so
            # external entities cannot be fetched. The PDF we are
            # reading is user-supplied, but we only use the parsed
            # attribute values — never any DTD, never any node text
            # outside ``rdf:Description`` attributes.
            parser = ET.XMLParser()
            try:
                parser.parser.SetParamEntityParsing(0)  # type: ignore[attr-defined]
            except Exception:
                pass
            root = ET.fromstring(text, parser=parser)
    except ET.ParseError as exc:
        _logging.getLogger(__name__).debug("XMP parse failed: %s", exc)
        return {}
    out: dict[str, str] = {}
    for desc in root.iter():
        tag = desc.tag
        # Tag is "{<namespace>}Description" — accept both with and
        # without an explicit namespace declaration.
        if not (tag == "Description" or tag.endswith("}Description")):
            continue
        for k, v in desc.attrib.items():
            if k.startswith(f"{{{STAMP_XMP_NS}}}"):
                out[k[len(f"{{{STAMP_XMP_NS}}}"):]] = v
        # A real PDF usually has exactly one rdf:Description at the
        # top level, but iterate-all is harmless and matches how some
        # tools emit the packet.
    return out


def _already_stamped_by_us(path: Path) -> bool:
    """True if ``path`` carries a current-version stamp from the fixed pipeline.

    Storage locations checked (in order of preference):

      1. **Custom XMP property** under :data:`STAMP_XMP_NS`. The
         user observed Nextcloud's storage layer rewriting ``Producer``
         to ``pikepdf …`` on every WebDAV PUT, which made the previous
         Producer-only stamp a silent no-op in production — the same
         two files were re-OCR'd 17+ times in a single day. XMP under a
         custom namespace is not one of the standard fields any tool
         regenerates, so it survives the round-trip and is the only
         field we can rely on for a programmatic check.

      2. **Subject fallback** — the long human-readable OCR summary
         also carries ``stamp_version=STAMP_VERSION``. If the XMP
         stream was somehow stripped (e.g. a stripping tool the user
         ran by hand) but Subject is intact, we still recognise the
         stamp.

    The check is strict about version: any stamp older than
    :data:`STAMP_VERSION` (or absent) returns ``False``. The previous
    ``0.3`` series was produced by a parser that silently returned
    zero text on a long stretch of runs, so those stamps are
    untrustworthy and the operator has decided a one-time re-OCR of
    every previously-stamped file is the right migration.

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
    ``_needs_ocr_decision`` continue to treat a current-version stamp
    as trustworthy so we do not blow the Vision-API budget re-OCR'ing
    the entire stamp-flagged set.  That is a deliberate, explicitly
    documented policy choice — not a confident assertion that those
    files are good.
    """
    try:
        import fitz
        with fitz.open(str(path)) as doc:
            # Primary: read the XMP packet and look for our custom stamp.
            try:
                xml_xref = doc.xref_xml_metadata()
            except Exception:
                xml_xref = 0
            if xml_xref:
                try:
                    stream = doc.xref_stream(xml_xref) or b""
                    props = _parse_xmp_stamp(stream)
                    if props.get("stamp") == STAMP_VERSION:
                        return True
                except Exception:
                    pass
            # Secondary: Subject carries stamp_version=STAMP_VERSION too.
            meta = doc.metadata or {}
            subject = meta.get("subject", "") or ""
            if f"stamp_version={STAMP_VERSION}" in subject:
                return True
            return False
    except Exception:
        return False


def _check_fingerprint_guard(
    nc_path: str,
) -> tuple[bool, str | None]:
    """G1+G2: fingerprint-verified skip guard.

    Returns ``(skip, reason)``:

      * ``(True,  None)`` — stored fingerprint unknown (NULL row) or
        PROPFIND failed. Fall back to the stamp-only skip; the caller
        records whatever reason the rest of :func:`_needs_ocr_decision`
        returns.
      * ``(True,  SKIP_REASON_STAMPED_BY_US)`` — live file matches
        what we left. Skip as today; reset the counter for good
        measure (it was probably already at 0; the explicit reset is
        the documented contract for the tests).
      * ``(True,  REASON_FOREIGN_REWRITE)`` — live file differs and the
        per-path ``foreign_rewrites`` counter is at or above
        :data:`FOREIGN_REWRITE_LIMIT`. Stop auto-re-OCR for this path
        until the operator clears the row.
      * ``(False, None)`` — live file differs but the counter is still
        below the limit. The caller should OCR the file (the bump will
        be visible in :func:`/stats` as ``foreign_rewrites``).

    PROPFIND cost is paid only on the stamp-skip branch, which is
    rare in steady state. The single round-trip is the documented
    cost of the guard.

    Counter discipline
    ------------------
    The counter is bounded: once it has crossed
    :data:`FOREIGN_REWRITE_LIMIT` the helper stops bumping and
    returns ``(True, :data:`REASON_FOREIGN_REWRITE`)`` silently (no
    WARNING, no ERROR). The ERROR that explains the loop is logged
    exactly once, on the call that crosses the limit — subsequent
    mismatches at the cap are silent so the operator's logs do not
    drown in repeated copies. The counter resets to 0 the next time
    a fingerprint check returns ``match`` (the file is back to our
    output), at which point :data:`/stats` ``foreign_rewrites`` is
    no longer inflated by the stuck path.
    """
    stored = jobstore.file_get(nc_path) or {}
    stored_size = stored.get("size")
    stored_etag = stored.get("etag")

    if stored_size is None and stored_etag is None:
        log.debug(
            "fingerprint guard: %s has no stored fingerprint;"
            " skipping the comparison (counter stays at whatever it was)",
            nc_path,
        )
        return True, None  # fall back to stamp-only skip

    try:
        live_size, live_etag = _propfind_size_etag(nc_path)
    except Exception as exc:  # noqa: BLE001 — PROPFIND never breaks the skip
        log.warning(
            "fingerprint guard: PROPFIND %s failed (%s);"
            " falling back to stamp-only skip",
            nc_path, exc,
        )
        return True, None  # fall back to stamp-only skip

    if (live_size == stored_size and live_etag == stored_etag
            and live_size is not None):
        # Match — file still matches what we left. Reset counter.
        jobstore.file_reset_foreign_rewrites(nc_path)
        return True, SKIP_REASON_STAMPED_BY_US

    # Mismatch — file was rewritten out from under us.
    # Read the current counter BEFORE bumping so we can (a) detect the
    # first crossing of FOREIGN_REWRITE_LIMIT for the one-time ERROR
    # log and (b) cap the counter at the limit so /stats stays
    # bounded (the bump helper is unconditional; the cap lives here
    # in the guard so the jobstore has no opinion on application
    # policy).
    existing = jobstore.file_get(nc_path) or {}
    prev_count = int(existing.get("foreign_rewrites") or 0)
    if prev_count >= FOREIGN_REWRITE_LIMIT:
        # Already at the cap from a prior crossing. Stay there;
        # don't grow, don't repeat the ERROR log.
        return True, REASON_FOREIGN_REWRITE
    new_count = jobstore.file_bump_foreign_rewrites(nc_path) or 0
    log.warning(
        "fingerprint guard: %s was rewritten by a foreign writer."
        " stored=(size=%r, etag=%r) live=(size=%r, etag=%r)."
        " foreign_rewrites counter is now %d.",
        nc_path, stored_size, stored_etag, live_size, live_etag,
        new_count,
    )
    if new_count >= FOREIGN_REWRITE_LIMIT:
        log.error(
            "fingerprint guard: %s reached %d consecutive foreign"
            " rewrites (limit=%d); stopping auto-re-OCR. The OCR"
            " output cannot survive because another writer keeps"
            " replacing it. Operator: remove the competing writer"
            " from the Nextcloud app store, or POST /rescan with"
            " force=true to clear the row.",
            nc_path, new_count, FOREIGN_REWRITE_LIMIT,
        )
        return True, REASON_FOREIGN_REWRITE
    return False, None


def _needs_ocr_decision(
    path: Path, force: bool, nc_path: str | None = None,
) -> tuple[bool, str | None]:
    """Decide whether ``path`` actually needs OCR, and report WHY if not.

    Returns ``(needs_ocr, skip_reason)``:
      * ``(True,  None)``  — OCR must run; no skip was decided.
      * ``(False, reason)`` — skip; ``reason`` is one of
        :data:`SKIP_REASON_STAMPED_BY_US` /
        :data:`SKIP_REASON_BORN_DIGITAL` /
        :data:`SKIP_REASON_TEXT_DENSITY_GUARD` /
        :data:`REASON_FOREIGN_REWRITE`.

    A skip is taken when ``force`` is False AND one of:
      - The file already carries a Google-engine stamp from us
        → :data:`SKIP_REASON_STAMPED_BY_US`;
      - pdf-inspector (or the heuristic fallback) classifies it as
        text_based with no encoding issues
        → :data:`SKIP_REASON_BORN_DIGITAL`.

    G1: fingerprint-verified stamp branch
    -------------------------------------
    When ``nc_path`` is provided (the production caller
    :func:`_process_file` always passes it) and the stamp matches,
    the guard looks up the stored ``(size, etag)`` for ``nc_path`` and
    compares it to a fresh WebDAV ``Depth: 0`` PROPFIND. Three outcomes:

      * **match** — skip as today; reset the per-path
        ``foreign_rewrites`` counter (it was 0 anyway, but the
        explicit reset is the documented contract for the test suite).
      * **mismatch** — another writer replaced our output. Log a
        WARNING naming the path and BOTH fingerprints, bump the
        counter, and return ``(True, None)`` so the worker re-OCRs.
        After :data:`FOREIGN_REWRITE_LIMIT` consecutive mismatches we
        instead return ``(False, REASON_FOREIGN_REWRITE)`` and log an
        ERROR once — no more auto-re-OCR for this path until the
        operator removes the competing writer or runs ``/rescan`` with
        ``force=true``.
      * **unknown** (stored size/etag is ``NULL`` — the row ended in
        ``error``/``gone``, or the path has never been recorded) —
        skip as today, log at debug so the guard's existence is
        visible without spamming WARNING on every freshly-error'd
        row.

    PROPFIND cost is paid only on the skip path; the rest of the
    pipeline (force=True, needs_ocr=True from the classifier,
    etc.) never touches WebDAV for this check. The PROPFIND is the
    single new round-trip per skip; it is not batched because the
    stamp branch is rare in steady state and a single PROPFIND takes
    ~50–200ms over a tailnet.

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
        if nc_path:
            skip, reason = _check_fingerprint_guard(nc_path)
            if skip:
                # Match / unknown / hit-the-limit — the helper already
                # decided what to record. ``reason`` is None for the
                # unknown branch (the caller falls back to
                # SKIP_REASON_STAMPED_BY_US), or one of
                # SKIP_REASON_STAMPED_BY_US / REASON_FOREIGN_REWRITE.
                if reason is None:
                    return False, SKIP_REASON_STAMPED_BY_US
                return False, reason
            # Mismatch, still under the limit — re-OCR.
            return True, None
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
    """Raise if a structured-OCR engine returned zero blocks (or tesseract
    produced an empty text layer).

    Two engines populate ``result.page_results`` (google, minimax); the
    third (``tesseract``) writes the text layer directly via ocrmypdf and
    deliberately leaves ``page_results=[]``. The tesseract branch is
    guarded by a text-density check on the produced PDF (a re-OCR of a
    blank page returns ``page_results=[]`` AND a PDF with no
    extractable text — without this second guard the user's original
    gets overwritten by a "successful" OCR that carried no text).

    Background: the Google engine's bbox parser used to silently drop
    every Word (Vision populates ``normalized_vertices`` on the
    whole-doc batch path; pre-fix the code only read ``vertices``), so
    a "successful" run returned ``page_results`` with empty blocks for
    every page. The webhook then unconditionally stamped
    ``Producer = 'nc-ocr-flow 0.3 (engine=google)'`` and uploaded,
    marking the file ``done`` forever. Two follow-on costs:

      1. The stamp-skip branch (``_already_stamped_by_us``) kept
         hiding the file from re-OCR until manual intervention —
         this PR bumps the stamp version to ``0.4`` so those
         pre-fix stamps are NOT recognised as a skip, and stores
         the durable marker in a custom XMP namespace that survives
         Nextcloud's WebDAV-storage ``Producer`` rewrite.
      2. The user's Nextcloud storage was rewriting ``Producer`` to
         ``pikepdf …`` (now fixed by moving the stamp to XMP, see
         :func:`_stamp_metadata` and :func:`_already_stamped_by_us`),
         so the stamp-based dedup didn't even survive — we just had
         no second-line defence.

    Raising here takes the existing error path (``_run_job``'s
    ``except Exception`` already records ``status=error`` and writes
    ``error`` to the SQLite job row). The file is left UN-stamped and
    UN-uploaded, so the next webhook or ``/rescan`` retries it. The
    error message names file, engine, and the failure shape so an
    operator triaging the panel can act on it.
    """
    engine = result.engine_used

    # Structured-output engines: google, minimax. The block count must
    # be > 0; an empty result here is the documented bbox-parser bug.
    if engine in ("google", "minimax"):
        pages = result.page_results or []
        total_blocks = sum(len(p.blocks) for p in pages)
        if total_blocks > 0:
            return
        raise RuntimeError(
            f"OCR engine={engine} produced 0 blocks across "
            f"{len(pages)} page(s) for {nc_path!r}: empty result; file not "
            f"stamped or uploaded, eligible for retry"
        )

    # Tesseract: the text layer is written by ocrmypdf directly into the
    # output PDF, so page_results is empty by design. Verify the layer
    # actually carries non-whitespace text using the same per-page floor
    # the text-density guard uses for the born-digital branch
    # (MIN_TEXT_CHARS_PER_PAGE). A blank ocrmypdf output — e.g. a blank
    # image, or ocrmypdf crashing silently — would otherwise be
    # stamped done and uploaded over the user's original.
    if engine == "tesseract":
        try:
            import fitz
            with fitz.open(str(result.output_pdf)) as doc:
                pages = max(1, doc.page_count)
                chars = sum(
                    len(p.get_text().strip()) for p in doc
                )
            per_page = chars / pages
        except Exception as exc:
            raise RuntimeError(
                f"OCR engine=tesseract output PDF unreadable for "
                f"{nc_path!r} ({exc}); file not stamped or uploaded, "
                f"eligible for retry"
            ) from exc
        if per_page >= MIN_TEXT_CHARS_PER_PAGE:
            return
        raise RuntimeError(
            f"OCR engine=tesseract produced an empty/garbled text layer "
            f"({chars} chars across {pages} page(s), "
            f"{per_page:.1f}/page < {MIN_TEXT_CHARS_PER_PAGE}) for "
            f"{nc_path!r}: file not stamped or uploaded, eligible for retry"
        )

    # Any other engine (auto/legacy): treat as structured — pass on
    # page_results without raising. New structured engines can be
    # added to the tuple above as they ship.


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

            # Collision check FIRST: if the target PDF path already has a
            # file on it, refuse to overwrite — converting the image
            # here would silently destroy the user's existing PDF (and
            # would also bill a Vision round-trip for nothing). The
            # skip reason, the file-row semantics, and the "source
            # image left in place" invariant are preserved exactly.
            pdf_nc_path = str(Path(nc_path).with_suffix(".pdf"))
            try:
                existing_size, _ = _propfind_size_etag(pdf_nc_path)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "image branch: PROPFIND %s failed (%s);"
                    " refusing upload to be safe",
                    pdf_nc_path, exc,
                )
                existing_size = None
            if existing_size is not None and existing_size > 0:
                log.warning(
                    "image branch collision: %s already exists (%d bytes);"
                    " refusing to overwrite. Source image %s is left in place.",
                    pdf_nc_path, existing_size, nc_path,
                )
                # Do NOT upload, do NOT delete the source image. The
                # file row is updated to "skipped" so /stats shows the
                # reason and /scan-all won't keep re-enqueueing it
                # (until the operator resolves the collision).
                return {
                    "path": nc_path,
                    "skipped": True,
                    "reason": SKIP_REASON_PDF_EXISTS,
                    "existing_pdf": pdf_nc_path,
                }

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

            # Upload OCR'd PDF (new .pdf path), delete original image.
            # C2: the upload can succeed while the delete of the
            # source image fails (intermittent WebDAV 5xx, brief
            # network blip, locked file). Old behaviour left the
            # source image in place and recorded the file row against
            # the image path with no signal — /stats showed
            # ``status=done`` and the operator had no way to know the
            # user sees both the image AND the new PDF. We retry the
            # delete (with the same _webdav_delete backoff loop that
            # already exists) and, if it still fails after all
            # retries, keep both files and record a distinct reason.
            # The status stays ``done`` because the OCR work itself
            # succeeded and the new PDF is live — but the reason makes
            # the leftover image visible to the panel and to
            # /stats. We deliberately do NOT mark the file
            # ``status=error``: the user now has a usable PDF, and
            # the leftover image is a cleanup problem, not a failed
            # job.
            _webdav_upload(pdf_nc_path, Path(result.output_pdf))
            try:
                _webdav_delete(nc_path)
                delete_failed = False
                delete_error = None
            except Exception as exc:  # noqa: BLE001
                delete_failed = True
                delete_error = exc
                log.warning(
                    "image branch: OCR + upload of %s succeeded, but"
                    " delete of source image %s failed after retries (%s);"
                    " keeping both files",
                    pdf_nc_path, nc_path, exc,
                )

            if delete_failed:
                return {
                    "path": nc_path, "output": pdf_nc_path,
                    "engine": result.engine_used,
                    "vlm_pages": result.vlm_pages,
                    # Distinct reason so the panel and /stats show
                    # the real cause. Operator's job: clean up the
                    # leftover image manually (it cannot be safely
                    # re-deleted by the worker because the user may
                    # already be looking at both files).
                    "reason": "image_delete_failed",
                    "delete_error": str(delete_error),
                }

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
            #
            # G1: pass ``nc_path`` so the stamp branch can run the
            # fingerprint-verified skip guard (PROPFIND vs stored
            # ``(size, etag)``). When the live file differs from what
            # we last left, the guard bumps ``foreign_rewrites`` and
            # forces a re-OCR (or, after ``FOREIGN_REWRITE_LIMIT``
            # consecutive foreign rewrites, records
            # ``reason='foreign_rewrite'`` and skips without OCR'ing).
            needs_ocr, skip_reason = _needs_ocr_decision(
                local_file, force, nc_path=nc_path,
            )
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

            # Upload OCR'd PDF (replaces original → NC version).
            # C3: the previous code did a plain PUT straight over
            # the user's original. A partial upload (server crash,
            # reset, timeout) left a truncated, corrupt PDF on disk
            # with no way to recover. We PUT to a sibling temp path
            # and then MOVE it atomically onto the target.
            _webdav_replace_atomic(nc_path, Path(result.output_pdf))

            return {
                "path": nc_path, "output": nc_path,
                "engine": result.engine_used,
                "vlm_pages": result.vlm_pages,
            }

    return {"path": nc_path, "skipped": True, "reason": "unknown"}


# --- Job tracking (for /status panel + NC app) ---
import queue

#: Workers are woken by this signal; the work list itself is the
#: ``jobs`` table in SQLite, so a backlog of a million files costs
#: nothing in RAM.
#:
#: NB: the row id is assigned by SQLite (``record_enqueue`` reads
#: back ``lastrowid``) — not by an in-process counter. An earlier
#: ``itertools.count`` counter restarted at 1 on every service boot;
#: persisted rows kept their old ids, so the first batch of new
#: enqueues collided with old rows and ``INSERT OR IGNORE`` discarded
#: them silently. Letting SQLite auto-assign makes the sequence
#: collision-free across restarts.
_work_available = threading.Event()
#: Idle workers wake up this often even without a signal, so a lost
#: notification can never wedge the queue.
_IDLE_POLL_SECONDS = 5.0


# --- C6: Bounded automatic retry ------------------------------------------
#: How many retries a transient failure gets before we mark the
#: job ``error`` and stop. ``2`` is the spec-recommended cap; raising
#: it without thinking about it would re-amplify an outage (the
#: backoff would still be running, the queue would still be
#: blocked). 0 disables the feature.
_MAX_RETRY_ATTEMPTS = int(os.environ.get("NC_OCR_MAX_RETRY_ATTEMPTS", "2"))
#: Backoff schedule, indexed by ``attempts`` (the count BEFORE the
#: new attempt). The first retry waits 60s, the second 300s. Keep
#: this conservative: the worker is blocked on a queued retry, not
#: on a sleep, so a tight schedule just means we are doing the
#: same failed work over and over.
_RETRY_BACKOFF_SECONDS = (60.0, 300.0)
#: Mark a job as a transient retry when this classifier says so.
#: Anything else (404, "unsupported mime", "too large", "zero
#: blocks", foreign user, ValueError) is permanent and never
#: retried.
_PERMANENT_RETRY_REASONS = frozenset({
    "unsupported_mime", "too_large", "zero_blocks", "image_decode_failed",
    "stamped", "born_digital", "no_text_layer", "force_skip",
    REASON_FOREIGN_USER, "file_removed",
})


def _is_transient_failure(exc: BaseException, status_code: int | None) -> bool:
    """C6: decide whether a failed job deserves a retry.

    Transient (retry-eligible):
      * HTTP 5xx (NC restarting, DAV lock contention, gateway blip).
      * HTTP 408 / 429 (request timeout, rate-limited) — same root cause.
      * Transport-level failures: ``ConnectionError``,
        ``Timeout``, ``OSError`` (incl. ``ConnectionResetError``).

    Permanent (no retry): any other 4xx (404, 401, 403, 410, 422,
    ...). Those are NOT going to clear up by waiting.

    Implementation note: ``requests.HTTPError`` and
    ``requests.ConnectionError`` are themselves ``OSError``
    subclasses, so the order matters — we test the more specific
    requests types first, then fall back to the bare ``OSError``
    only for non-requests I/O errors.
    """
    if isinstance(exc, requests.ConnectionError):
        return True
    if isinstance(exc, (requests.Timeout, TimeoutError)):
        return True
    if isinstance(exc, requests.HTTPError):
        if status_code is None:
            return False
        if 500 <= status_code < 600:
            return True
        if status_code in (408, 429):
            return True
        # Any other status code (incl. 404, 401, 403, 410, 422)
        # is permanent: nothing about waiting will fix it.
        return False
    if isinstance(exc, OSError):
        return True
    return False


def _maybe_schedule_retry(job: dict, exc: BaseException,
                          status_code: int | None) -> bool:
    """C6: enqueue a scheduled retry if the failure is transient.

    Returns True iff a retry was scheduled (so the caller knows it
    must not also mark the job ``error``). The ``error`` field on
    ``job`` is preserved for the panel even after the retry is
    enqueued — operators want to see the failure that triggered
    the retry, not just the eventual success.
    """
    attempts = int(job.get("attempts", 0) or 0)
    if attempts >= _MAX_RETRY_ATTEMPTS:
        log.info(
            "worker: job %d exhausted %d retry attempts; giving up",
            job["id"], attempts,
        )
        return False
    if not _is_transient_failure(exc, status_code):
        return False
    # Compute backoff from the schedule. Cap to the schedule length
    # so an attacker who has somehow inflated ``attempts`` cannot
    # pick a backoff out of thin air.
    idx = min(attempts, len(_RETRY_BACKOFF_SECONDS) - 1)
    backoff = _RETRY_BACKOFF_SECONDS[idx]
    next_run_at = time.time() + backoff
    new_id = jobstore.enqueue_retry(
        job, attempts=attempts + 1, next_run_at=next_run_at,
    )
    if new_id is None:
        # DB down: treat as no-retry (the job will record ``error``
        # the normal way). A future webhook or /rescan re-enqueues
        # the file.
        return False
    log.warning(
        "worker: job %d: transient %s — scheduled retry as job %d in %.0fs"
        " (attempts %d → %d)",
        job["id"], exc, new_id, backoff, attempts, attempts + 1,
    )
    # Do NOT mirror ``attempts`` onto this (failing) row. The caller records it
    # as the failure that triggered the retry, and ``stats()['retries_total']``
    # counts rows with attempts > 0 — mirroring would count one attempt twice
    # (B2 audit). Only the retry row carries the bumped counter.
    return True


#: Settings the panel may change: short key -> (env var, default).
#: Reading honours env (nix, authoritative) -> SQLite override -> default.
#: TTL is exposed as int seconds (whole-number); see ``processed_ttl``.
_SETTING_SPEC: dict[str, tuple[str, int]] = {
    "workers": ("NC_OCR_WORKERS", 2),
    "max_concurrent_google": ("NC_OCR_MAX_CONCURRENT_GOOGLE", 2),
    "max_concurrent_tesseract": ("NC_OCR_MAX_CONCURRENT_TESSERACT", 1),
    "max_concurrent_minimax": ("NC_OCR_MAX_CONCURRENT_MINIMAX", 1),
    "processed_ttl": ("NC_OCR_PROCESSED_TTL", _DEFAULT_PROCESSED_TTL),
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


def _int_env_nonneg(name: str, default: int) -> int:
    """Non-negative int for a setting (e.g. processed-TTL).

    Same precedence as :func:`_int_env` but allows 0 — a TTL of 0 means
    "never dedup" (every webhook event triggers a fresh OCR), which
    is a valid operator choice when debugging the loop-prevention
    behaviour.
    """
    raw = jobstore.settings_all().get(name)
    if raw in (None, ""):
        raw = os.environ.get(name)
    try:
        return max(0, int(raw))
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
        # The TTL setting is the only one in the spec where 0 is a
        # valid value (it means "always re-OCR"). Everything else has
        # a meaningful lower bound of 1, so the floor is per-key.
        floor = 0 if key == "processed_ttl" else 1
        try:
            current[key] = max(floor, int(raw))
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
        # C2: the image→PDF branch can succeed (PDF uploaded) but
        # leave the source image behind if the WebDAV DELETE failed.
        # The worker previously only stored ``reason`` on skipped
        # jobs, which silently dropped the image_delete_failed signal.
        # Propagate ``reason`` whenever the result carries one — the
        # index/panel/stats need to see it regardless of status.
        elif result.get("reason"):
            job["reason"] = result.get("reason", "")
        # Surface the WebDAV delete error in the job log even when
        # the rest of the OCR was a success.
        if result.get("delete_error") and not job.get("error"):
            job["error"] = f"image_delete_failed: {result['delete_error']}"
        log.info("worker: job %d %s: %s", job["id"], job["status"], job["path"])
    except requests.HTTPError as exc:
        # 404 means the file is gone from Nextcloud (deleted between
        # the webhook firing and our GET). Mark it ``gone`` rather
        # than ``error`` so /stats doesn't show it as a failure:
        # retrying will 404 again, and a permanent ``error`` row is
        # what produced the 36 phantom-errors on production. Any
        # other 4xx is still a permanent error.
        status_code = (
            exc.response.status_code if exc.response is not None else None
        )
        if status_code == 404:
            job["status"] = "gone"
            job["reason"] = "file_removed"
            job["error"] = str(exc)
            log.warning(
                "worker: job %d: file gone (404): %s",
                job["id"], job["path"],
            )
        else:
            # C6: 5xx / 408 / 429 may clear up; other 4xx will not.
            #
            # Record the terminal row BEFORE scheduling the retry. At this
            # point the row is still ``running`` (the ``finally`` below writes
            # it), and ``uq_jobs_inflight`` is UNIQUE on
            # ``jobs(path) WHERE status IN ('queued','running')`` — so a retry
            # inserted first is rejected, ``enqueue_retry`` returns None, and a
            # transient 429/5xx silently becomes a permanent error. Observed
            # live on poweredge, in this order:
            #   jobstore: insert skipped, path already in flight
            #     (UNIQUE constraint failed: jobs.path)
            #   worker: job 124 failed (429)
            job["status"] = "error"
            job["error"] = str(exc)
            jobstore.record_update(job)
            if _maybe_schedule_retry(job, exc, status_code):
                # Keep the failure visible — the panel reads this row — and
                # say a retry is queued. ``attempts`` deliberately stays 0:
                # only the retry row carries the counter (B2 audit).
                job["error"] = (
                    f"transient {status_code} (retry scheduled): {exc}"
                )
                jobstore.record_update(job)
                log.warning(
                    "worker: job %d: HTTP %s — transient, retry scheduled",
                    job["id"], status_code,
                )
            else:
                log.error(
                    "worker: job %d failed (%s): %s — %s",
                    job["id"], status_code, job["path"], exc,
                )
    except (requests.ConnectionError, requests.Timeout, TimeoutError,
            OSError) as exc:
        # C6: transport-level failures are the textbook transient
        # case — a packet drop or a daemon hiccup should not stick
        # the file in the error column forever. Schedule a retry
        # the same way HTTP 5xx does.
        # Same ordering rule as the HTTPError branch above: write the terminal
        # row first, or the retry insert collides with uq_jobs_inflight.
        job["status"] = "error"
        job["error"] = str(exc)
        jobstore.record_update(job)
        if _maybe_schedule_retry(job, exc, None):
            job["error"] = f"transient transport error: {exc}"
            jobstore.record_update(job)
            log.warning(
                "worker: job %d: %s — transient, retry scheduled",
                job["id"], exc,
            )
        else:
            log.error(
                "worker: job %d failed: %s — %s", job["id"], job["path"], exc,
            )
    except Exception as exc:
        # Permanent failure: anything that is not a known transient
        # signal. Includes our own ``_assert_ocr_produced_blocks``
        # RuntimeError, ``ValueError`` from engine internals, etc.
        # C6: do NOT retry these — the next attempt would fail
        # identically.
        job["status"] = "error"
        job["error"] = str(exc)
        log.error("worker: job %d failed: %s — %s", job["id"], job["path"], exc)
    finally:
        job["finished"] = time.time()
        # Persist the final state to SQLite. ``record_update`` is
        # upsert-by-id and never raises into the caller — the OCR
        # pipeline must not break because the history DB is down.
        jobstore.record_update(job)
        # C6 retry scheduling is handled in the ``except`` blocks above
        # (HTTPError / transport failures), which know whether the
        # failure is transient and how to encode it. A blanket
        # ``_maybe_schedule_retry(job)`` here would double-schedule
        # for the same failure path and re-trigger the B2 audit.
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


def reconcile_orphans() -> dict:
    """Recover files left ``status='queued'`` with no matching ``jobs`` row.

    Background — two real production shapes that left a file row at
    ``status='queued'`` with NO corresponding ``jobs`` row, so
    ``_path_in_flight`` reported it in-flight forever and ``/scan-all``
    silently skipped it:

      1. **Old in-process job-id collision** (now fixed). A previous
         version of the service kept an ``itertools.count(1)`` for
         job ids; on restart it would re-use ids that already existed
         in the persisted ``jobs`` table. The SQLite insert raised
         but was swallowed, leaving the file row at ``status='queued'``
         with nothing in ``jobs``. ``record_enqueue`` now reads
         ``lastrowid`` from SQLite so this is no longer produced —
         but rows orphaned by the older builds still exist.
      2. **Pruned history / lost row.** The ``jobs`` history is capped
         at 20 000 rows; very long-running services have shed old
         ``jobs`` rows whose file row was still at ``status='queued'``
         (e.g. the worker crashed between writing the file row and
         writing the job row, or the row was pruned before being
         picked up). The operator wants these recovered too.

    What the function does
    ----------------------
    For every path with ``files.status='queued'`` that does NOT have a
    matching ``jobs`` row at status ``queued`` or ``running``, the
    function calls ``_enqueue`` to insert a fresh ``jobs`` row and
    mark the worker pool ready to pick it up. The file row stays at
    ``status='queued'`` (correct — we just enqueued it again).

    Idempotency
    -----------
    Calling this twice is safe: the second call's query finds nothing
    (the re-enqueued jobs are now present, so the orphan predicate is
    false) and returns ``{"orphans_found": 0, "recovered": 0, ...}``.
    If a job row was lost between calls, the second call will pick
    it up again — that's the correct behaviour.

    Safety
    ------
    The query excludes rows whose matching ``jobs`` row is in
    ``('queued', 'running')``. A genuinely running worker holds a
    ``jobs.status='running'`` row while the corresponding file row
    is still ``status='queued'`` (we only write the terminal status
    once the worker finishes), so the join correctly leaves those
    rows alone.
    """
    try:
        orphans = jobstore.orphaned_queued_paths()
    except Exception as exc:  # noqa: BLE001
        log.error("reconcile_orphans: query failed (%s)", exc)
        return {"orphans_found": 0, "recovered": 0, "failed": 0, "error": str(exc)}
    if not orphans:
        log.info("reconcile_orphans: no orphans found")
        return {"orphans_found": 0, "recovered": 0, "failed": 0, "errors": []}

    log.warning(
        "reconcile_orphans: found %d orphaned queued file(s): %s",
        len(orphans), orphans,
    )
    recovered = 0
    failed: list[dict] = []
    for nc_path in orphans:
        try:
            _enqueue(nc_path, node_id=0, engine=None, force=True)
            recovered += 1
            log.info("reconcile_orphans: re-enqueued %s", nc_path)
        except Exception as exc:  # noqa: BLE001
            failed.append({"path": nc_path, "error": str(exc)})
            log.error("reconcile_orphans: re-enqueue %s failed (%s)", nc_path, exc)
    return {
        "orphans_found": len(orphans),
        "recovered": recovered,
        "failed": len(failed),
        "errors": failed,
        "paths": orphans,
    }


# Run the reconciler once at startup so an operator does not have to
# call the endpoint manually after every restart. The function is
# idempotent and never raises, so this is safe even when the queue is
# healthy.
_reconcile_startup = reconcile_orphans()
if _reconcile_startup.get("orphans_found"):
    log.warning(
        "startup: reconciler recovered %d / %d orphaned queued files",
        _reconcile_startup["recovered"],
        _reconcile_startup["orphans_found"],
    )
# C5: also run the stale-row reconciler once at startup so the 36
# phantom-errors on production are not stuck for another deploy
# cycle. The function is bounded, idempotent, and never raises —
# it will simply return 0/0/0 on a healthy index.
_reconcile_stale_startup = reconcile_stale_files()
if _reconcile_stale_startup.get("marked_gone"):
    log.warning(
        "startup: stale-row reconciler marked %d / %d rows gone",
        _reconcile_stale_startup["marked_gone"],
        _reconcile_stale_startup["checked"],
    )
for _worker_idx in range(_WORKERS):
    threading.Thread(target=_ocr_worker, daemon=True,
                     name=f"ocr-worker-{_worker_idx}").start()
log.info("started %d OCR worker(s) (NC_OCR_WORKERS)", _WORKERS)

# G3: one-line announcement so an operator can tell at a glance whether
# this build has the fingerprint-verified skip guard compiled in. The
# line is unconditional (every build has it today) but keeps the
# contract discoverable in logs without grepping for the constant.
log.info(
    "fingerprint-verified skip guard enabled (FOREIGN_REWRITE_LIMIT=%d);"
    " PROPFIND is paid only on the stamp-skip path",
    FOREIGN_REWRITE_LIMIT,
)


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


def _pick_quota_dimension(dims: list[dict], want_loc: str) -> dict | None:
    """Return the dimension entry whose ``location`` matches the
    engine's configured region.

    Extracted from :func:`_vision_quota_once` so the matching can be
    unit-tested without going through Google auth (the original code
    read ``dims[0]``, which is whichever region happens to come back
    first — usually not the engine's region).

    Rules:

      * Empty ``want_loc`` defaults to ``"US"`` (matches the engine
        env-var default).
      * Case-insensitive comparison; both sides are upper-cased.
      * The literal region ``"GLOBAL"`` is the wildcard bucket — when
        the engine is configured that way, the *first* non-empty
        dimension is accepted (its value is the aggregate bucket the
        wildcard consumes from).
      * Returns ``None`` if no dimension matches. The caller falls
        back to a conservative 1800 req/min and logs a WARNING.
    """
    want = (want_loc or "US").upper()
    for d in dims:
        loc = (d.get("dimensions") or {}).get("location", "").upper()
        if want == "GLOBAL" or loc == want:
            return d
    return None


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
                # The ``dimensionsInfos`` list carries one entry per
                # dimension the API knows about; the engine actually
                # consumes one specific region (NC_OCR_GOOGLE_LOCATION,
                # default "US"), and the first element of the list is
                # whatever region happens to come back first. Reading
                # dims[0] therefore reports a healthy limit for the
                # wrong bucket and /stats shows a quota we never
                # actually have. Match the dimension to the engine's
                # region; fall back to a conservative 1800 with a
                # logged WARNING when no dimension matches. The
                # matching rule itself lives in
                # :func:`_pick_quota_dimension` so the unit test can
                # exercise it without going through Google auth.
                match = _pick_quota_dimension(
                    qi.get("dimensionsInfos") or [],
                    os.environ.get("NC_OCR_GOOGLE_LOCATION", "US") or "US",
                )
                if match is None:
                    log.warning(
                        "vision quota: no dimension matched region=%r;"
                        " using conservative fallback 1800 req/min",
                        (os.environ.get("NC_OCR_GOOGLE_LOCATION", "US")
                         or "US").upper(),
                    )
                else:
                    val = match.get("details", {}).get("value")
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
        # Subtract the monthly free quota (1000 pages) before charging;
        # a 500-page run reports $0, not $0.75. The rounding step is
        # preserved so a non-free run still reports cents. See
        # :data:`VISION_FREE_UNITS`.
        "cost_usd": round(
            max(0, pages - VISION_FREE_UNITS) * VISION_USD_PER_1000 / 1000, 4
        ),
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


# B1 + B5 fix: per-path enqueue lock + bounded cache.
#
# Why a separate per-path lock instead of relying solely on the SQLite
# UNIQUE check: two concurrent enqueues (e.g. a /rescan racing a
# webhook, or the NC app's "Re-OCR anyway" double-clicked) can both
# pass the in-flight check before either has inserted its row, and
# SQLite has no UNIQUE on (path, status) — so without this lock they
# would each insert a queued job, producing two concurrent OCR runs
# and a double Vision billing. The lock serialises the gate-and-insert
# pair per path; everything else stays concurrent.
#
# B5 bound: a module-level dict keyed by nc_path would grow without
# bound across a long-running service (one entry per distinct path
# ever seen). The lock acquired below sweeps on every acquire,
# evicting entries unused for more than ``_ENQUEUE_LOCK_TTL_S``
# seconds, so memory usage stays proportional to the active working
# set.
_ENQUEUE_LOCKS: dict[str, threading.Lock] = {}
_ENQUEUE_LOCKS_LAST_USED: dict[str, float] = {}
_ENQUEUE_LOCK_TTL_S = 3600.0  # 1 hour idle ⇒ evicted on next acquire
_ENQUEUE_LOCKS_LOCK = threading.Lock()


def _enqueue_path_lock(nc_path: str) -> threading.Lock:
    """Return the per-path enqueue lock, evicting idle entries first.

    B5 leak fix: never returns a stale lock from ``_ENQUEUE_LOCKS``
    without sweeping the table first. ``_ENQUEUE_LOCKS`` is keyed by
    ``nc_path``; on a long-running service a tail of one-shot paths
    (PNGs uploaded, OCR'd, then deleted from the box) would otherwise
    accumulate forever. We bound memory by:
      - deleting any entry whose ``_ENQUEUE_LOCKS_LAST_USED`` is
        older than ``_ENQUEUE_LOCK_TTL_S`` (default 1h, generous
        slack for repeated enqueues on a hot folder);
      - keeping the lock for the path we are about to hand back.

    Thread-safe under simultaneous webhook / rescan / scan-all callers.
    Only protects threads within ONE process — see ``_enqueue`` for the
    multi-process caveat.
    """
    now = time.time()
    with _ENQUEUE_LOCKS_LOCK:
        # Sweep first (cheap; even at 100k entries this is one linear
        # walk). The lock here is the only mutator on the caches.
        cutoff = now - _ENQUEUE_LOCK_TTL_S
        stale = [k for k, t in _ENQUEUE_LOCKS_LAST_USED.items()
                 if t < cutoff]
        for k in stale:
            _ENQUEUE_LOCKS.pop(k, None)
            _ENQUEUE_LOCKS_LAST_USED.pop(k, None)
        lock = _ENQUEUE_LOCKS.get(nc_path)
        if lock is None:
            lock = threading.Lock()
            _ENQUEUE_LOCKS[nc_path] = lock
        _ENQUEUE_LOCKS_LAST_USED[nc_path] = now
        return lock


def _enqueue(nc_path: str, node_id: int, engine: str | None = None,
             force: bool = False) -> dict:
    """Create a job record and enqueue for processing.

    ``engine`` defaults to None → orchestrator resolves via env.
    ``force`` (default False): bypass the born-digital skip decision AND
    the recently-processed guard. The NC app's "Re-OCR anyway" action
    sends this so the user can deliberately re-OCR a file we previously
    classified or stamped.

    B1 fix: an in-flight job for this path is **never** bypassed by
    ``force``. Two concurrent callers (a /rescan racing the webhook,
    or "Re-OCR anyway" double-clicked) used to produce two jobs rows
    for the same path and bill Vision twice. We hold a single per-path
    critical section across the in-flight check AND the durable writes;
    the second caller either blocks on the lock and then sees the
    existing row (returning ``status='already_running'``) or, if it lost
    the race, returns the same handoff without ever calling
    ``record_enqueue`` twice. The caller's ``force`` bit is ignored at
    the in-flight gate — it still applies to the born-digital / stamp /
    TTL guards inside ``_process_file``.

    The ``id`` is **assigned by SQLite**, not by an in-process counter
    — that means the row's primary key survives a service restart and
    cannot collide with whatever the next process happens to call
    itself. ``record_enqueue`` writes the new id back into ``job`` so
    the API response reflects the canonical id.

    Atomicity — a single critical section
    --------------------------------------
    The whole gate-and-insert pair runs under ``_enqueue_path_lock`` so
    no other thread on this process can interleave between "I saw no
    in-flight job" and "I just inserted one". If step ``record_enqueue``
    fails (DB-level fault), the file row stays at ``queued`` with no
    matching jobs row — the orphan reconciler picks that up on next
    startup or on ``/admin/reconcile-orphans``. That's the same
    recovery shape as a process crash mid-enqueue, which we already
    accept.

    Multi-process deployments (one uvicorn per host × N workers across
    separate processes) are NOT fully covered by ``_enqueue_path_lock``
    — a threading.Lock only protects threads within ONE process. The
    cross-process backstop is the ``uq_jobs_inflight`` partial unique
    index on ``jobs(path) WHERE status IN ('queued','running')``
    installed by ``jobstore._migrate_inflight_unique_index``: if
    another worker slipped a row in for this path while we held the
    in-process lock, our ``record_enqueue`` hits ``IntegrityError`` and
    returns ``None``; we look up the winner and return it with
    ``status='already_running'`` so the call site sees the same shape
    as the in-process race. The single-process flow described above
    produces the cleanest response (no DB round-trip); the
    multi-process path is the rare-but-correct fallback.
    """
    job = {
        # id intentionally unset — let SQLite's rowid alias assign.
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
        "attempts": 0,
        "next_run_at": None,
    }
    # ONE critical section per path: the in-flight check and the
    # durable writes are atomic relative to other threads on this
    # process. A second caller arriving while we're inside this block
    # blocks on ``_enqueue_path_lock`` and, once admitted, sees the
    # row we just inserted — so it returns ``status='already_running'``
    # instead of creating a duplicate jobs row.
    with _enqueue_path_lock(nc_path):
        # In-flight is final here. ``force`` must NOT bypass this —
        # see B1 audit. ``force`` semantics still apply to the
        # born-digital / stamp / TTL guards downstream in
        # ``_process_file``.
        existing = jobstore.in_flight_job_for_path(nc_path)
        if existing is not None and existing.get("status") in (
                "queued", "running"):
            existing = dict(existing)
            existing["status"] = "already_running"
            # Don't claim a fresh engine — the existing job is the
            # source of truth on what is actually running.
            existing["engine"] = existing.get("engine") or engine
            existing["force"] = bool(existing.get("force") or force)
            return existing
        # Mark the file ``queued`` first. Any concurrent reader of
        # the files row (outside the per-path lock) sees
        # ``status='queued'`` and would short-circuit on its own
        # _path_in_flight check before reaching this code.
        _prev = jobstore.file_get(nc_path) or {}
        jobstore.file_put({**_prev, "path": nc_path, "status": "queued",
                           "node_id": node_id})
        # Durable queue insert. ``record_enqueue`` wraps its own
        # ``BEGIN IMMEDIATE`` transaction; on a path collision
        # (``uq_jobs_inflight`` — added by
        # ``_migrate_inflight_unique_index``) it returns ``None``
        # instead of raising, because the cross-process DB backstop
        # is the only thing that protects against two workers in
        # separate processes both inserting the same path. The
        # in-process ``_enqueue_path_lock`` above does NOT protect
        # against that case — it is process-local.
        assigned = jobstore.record_enqueue(job)
        if assigned is None:
            # Another process slipped in and inserted this path while
            # we held the in-process lock. The DB unique index
            # refused our row. Hand back the existing in-flight row
            # so the caller (webhook / scan-all / rescan) gets the
            # same ``status='already_running'`` shape the
            # in-process race would have produced.
            winner = jobstore.in_flight_job_for_path(nc_path)
            if winner is not None:
                winner = dict(winner)
                winner["status"] = "already_running"
                winner["engine"] = winner.get("engine") or engine
                winner["force"] = bool(
                    winner.get("force") or force
                )
                return winner
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

    # Catch malformed JSON: a 500 here used to retry-storm a healthy
    # backend (Nextcloud's dispatcher retries every 5xx indefinitely).
    # A bad body is a 400, not a server fault.
    try:
        body = await request.json()
    except Exception as exc:
        log.warning("webhook: invalid JSON body: %s", exc)
        return JSONResponse(
            {"detail": "invalid JSON body"},
            status_code=400,
        )
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

    # C1: refuse paths owned by a Nextcloud user other than the one
    # this service authenticates as. The service user has no access
    # to a foreign user's WebDAV root, so the job would 401, retry 3×,
    # and end as a generic ``error`` row. Logged at WARNING so the
    # operator can see why the panel shows the file as
    # ``foreign_user`` (a state Nextcloud won't try to redeliver).
    if _is_foreign_user(nc_path):
        log.warning(
            "webhook: foreign user %r (path=%s, NC_USER=%s); recording"
            " foreign_user reason and responding 200",
            _path_user(nc_path), nc_path, NC_USER,
        )
        _index_record(
            nc_path, "skipped", engine=None,
            reason=REASON_FOREIGN_USER, node_id=node_id or 0,
        )
        return {"status": "ignored", "reason": REASON_FOREIGN_USER,
                "path": nc_path}

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
        # The TTL is the only setting where 0 is meaningful ("never
        # dedup"), so the minimum is per-key.
        floor = 0 if key == "processed_ttl" else 1
        if ival < floor:
            raise HTTPException(
                status_code=422,
                detail=f"{key} must be at least {floor} (got {ival})")
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
    """Fetch one historical job by id, or 404 if not in the SQLite history.

    C4: ``jobstore.record_enqueue`` prunes the ``jobs`` table to
    :data:`jobstore._MAX_ROWS` rows by ``id``, so a job id older than
    the retention window returns 404 even though the corresponding
    ``files`` index row may still be present (and the NC app would
    then render the file as "never OCR'd"). The fallback here is the
    honest one: we cannot reliably map a job id back to a path (the
    jobs table is the only key we had, and it is gone), so the
    response explains the situation and points the caller at
    ``/stats`` and ``/states`` (both of which the NC app already
    uses) for the durable view. The least surprising 404 is one
    that tells the operator what the system actually did, not one
    that silently looks like a bug.
    """
    _check_secret(x_webhook_secret)
    job = jobstore.get(int(job_id))
    if job is None:
        # C4: distinguish "never existed" from "pruned by retention".
        # The current shape of the jobs table does not let us recover
        # the path for a pruned row — that is the only data we would
        # need to look the file up in the files index. Surface a
        # 404 with a detail that names the cause and points the
        # caller at the endpoints that DO still know about the
        # work, so the NC app can fall back gracefully.
        raise HTTPException(
            status_code=404,
            detail=(
                f"job {job_id} not found in history "
                f"(likely pruned beyond the {getattr(jobstore, '_MAX_ROWS', 5000)}-row"
                f" retention cap; see /stats and /states for the"
                f" per-file state index)"
            ),
        )
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

    Contract (this version)
    -----------------------
    The two historical endpoints have always been described as a single
    number-pair, but they actually counted different things:

      * ``/stats`` is built from the ``files`` table — one row per
        NC path we ever saw, so ``errors`` there is the *unique
        failed paths* count (a file may have been retried several
        times and still leave only one row, marked ``error``).
      * ``/jobs/stats`` is built from the ``jobs`` table — one row per
        *attempt*, so its ``error`` number is the total attempts that
        failed.

    Production saw ``errors=36`` from ``/stats`` while ``/jobs/stats``
    held 0 error rows, all of which was a deadlock of misread numbers
    (the 36 were leftover rows for test files that have since been
    deleted from Nextcloud — the WebDAV call still 404s, but the row
    is permanent until manually cleaned).

    The fix is to keep both numbers but make the contract explicit and
    add a third counter that ties them together:

      * ``errors``         — UNIQUE failed *paths* (``files.status = 'error'``)
      * ``gone``            — UNIQUE paths whose file vanished from NC
                              (404 on every WebDAV call); NOT counted
                              in ``errors`` (the file was never
                              successfully processed)
      * ``errors_attempts`` — total *attempts* that failed
                              (``jobs.status = 'error'``); the
                              ``/jobs/stats`` value mirrored here so
                              a panel can never read the two endpoints
                              as contradictory

    Operators can therefore answer both questions independently:

      * "is anything failing right now?" → ``errors_attempts`` (live)
      * "what files are stuck?"           → ``errors`` and ``gone``
                                            (durable index)
    """
    _check_secret(x_webhook_secret)
    idx = list(jobstore.file_all().values())

    scanned = [m for m in idx if m.get("status") == "done"]
    skipped = [m for m in idx if m.get("status") == "skipped"]
    errors = [m for m in idx if m.get("status") == "error"]
    # 'gone' is a separate state: the file is no longer in NC
    # (WebDAV GET → 404), so retrying it is futile. Excluded from
    # ``errors`` so the two endpoints are never read as
    # contradictory.
    gone = [m for m in idx if m.get("status") == "gone"]

    by_engine: dict[str, int] = {}
    for m in scanned:
        e = (m.get("engine") or "unknown") or "unknown"
        by_engine[e] = by_engine.get(e, 0) + 1

    skip_reasons: dict[str, int] = {}
    for m in skipped:
        r = m.get("reason") or "unknown"
        skip_reasons[r] = skip_reasons.get(r, 0) + 1

    # Mirror the jobs-table error count so /stats and /jobs/stats
    # agree on attempts. ``jobstore.stats()`` is keyed by status
    # already (see :func:`jobstore.stats`); B2 audit also pulls the
    # retry counters (``retries_total`` / ``retries_queued``) from
    # the same call so the panel sees them on the wire.
    js = jobstore.stats()
    errors_attempts = int(js.get("error", 0))
    retries_total = int(js.get("retries_total") or 0)
    retries_queued = int(js.get("retries_queued") or 0)
    # G3: cumulative count of foreign rewrites detected by the
    # fingerprint-verified skip guard (sum of ``files.foreign_rewrites``
    # across every row). The counter is bumped on every mismatch and
    # reset to 0 on the next match — so this number reflects how many
    # foreign rewrites have ever been observed, NOT the number of
    # currently-tainted paths. Unknown to the NC app's StatsService →
    # additive change, no schema coupling.
    foreign_rewrites = jobstore.file_foreign_rewrites_total()

    return {
        "service": "nc-ocr-flow",
        # Index-page counts (one per NC path).
        "indexed": len(idx),
        "scanned": len(scanned),
        "skipped": len(skipped),
        "errors": len(errors),
        "gone": len(gone),
        # Attempt-page counts (one per job), so /stats and /jobs/stats
        # never appear contradictory. See the docstring above.
        "errors_attempts": errors_attempts,
        "by_engine": by_engine,
        "skip_reasons": skip_reasons,
        # B2 fix: spread the retry counters so the NC app's
        # StatsService sees them. Before this they were computed
        # but only kept on the jobstore stats() side; the wire
        # returned ``{}`` for these keys and the panel row hid
        # itself behind ``if (!empty(...))``.
        "retries_total": retries_total,
        "retries_queued": retries_queued,
        # G3: fingerprint-verified skip guard total. See
        # ``_check_fingerprint_guard`` for the per-path counter and
        # ``FOREIGN_REWRITE_LIMIT`` for the bound.
        "foreign_rewrites": foreign_rewrites,
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
    # C1: refuse paths belonging to a different Nextcloud user. The
    # service user (NC_USER) cannot authenticate to a foreign user's
    # WebDAV root, so every rescan attempt would 401 and end as
    # ``error``. We 422 the request (it's an operator panel action, not
    # a Nextcloud retry, so 200 is the wrong code here).
    if _is_foreign_user(nc_path):
        log.warning(
            "rescan: refused foreign-user path user=%r nc_path=%s NC_USER=%s",
            _path_user(nc_path), nc_path, NC_USER,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"refusing rescan of foreign user"
                f" {_path_user(nc_path)!r}: this service only handles"
                f" user {NC_USER!r}"
            ),
        )
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
    #: Force re-OCR of every matched file, regardless of any previous
    #: stamp and regardless of an existing in-flight job for the same
    #: path. Default ``False`` preserves the original behaviour. When
    #: ``True``, ``skip_ocrd`` is treated as ``False`` and the
    #: ``_path_in_flight`` check is skipped too — useful when the
    #: operator wants to retry a folder that is partially stuck in the
    #: queue (the previously-shipped "force" flag on the per-file
    #: ``/rescan`` could not be expressed on a whole folder before).
    force: bool = False


@app.post("/scan-all")
async def scan_all(
    body: ScanAllRequest,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Batch scan: enqueue every processable file under a folder ("" = all).

    Skips files already OCR'd by this service (tracked in the file
    index, unless ``body.force=True``). Returns immediately with the
    number of jobs queued; processing is sequential in the single
    worker (queue depth visible in /status).

    ``body.force=True`` is the "force-re-OCR whole folder" operator
    lever the per-file ``/rescan`` already exposed. It bypasses:

      * ``skip_ocrd`` — even files with ``status='done'`` are queued;
      * ``_path_in_flight`` — even files with a queued or running job
        row get a fresh job appended (last writer wins on the file
        row when each job finishes);
      * the stamp check inside ``_process_file`` — the per-file
        ``force=True`` we pass through to ``_enqueue`` flips the
        ``_already_stamped_by_us`` gate off.

    Default behaviour is unchanged.
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
    # Some Nextcloud installs use a non-``d:`` namespace prefix in the
    # PROPFIND body (``D:``, ``DAV:``, no prefix at all, etc.). The
    # earlier hard-coded ``<d:href>`` dropped every entry whose prefix
    # happened to differ and silently broke /scan-all. Match any
    # prefix (or no prefix) the server happens to send.
    found = _re.findall(
        r"<[A-Za-z0-9_]*:?href>([^<]+)</[A-Za-z0-9_]*:?href>", resp.text
    )
    # Filter to processable extensions, decode %XX
    from urllib.parse import unquote
    enqueued = 0
    skipped_ocrd = 0
    forced_in_flight = 0
    for href in found:
        href = unquote(href)
        rel = href.split(f"/remote.php/dav/files/{NC_USER}/", 1)[-1]
        if not rel or rel in (folder, folder + "/"):
            continue
        if Path(rel).suffix.lower() not in PROCESSABLE_EXTS:
            continue
        nc_path = f"/{NC_USER}/files/{rel}"
        # C1: defence in depth. /scan-all PROPFINDs only NC_USER's
        # root, but a future change to that path (or a misconfigured
        # WebDAV proxy) could surface a foreign-user path. Refuse to
        # enqueue rather than producing a 401-storm that ends as a
        # generic ``error`` row.
        if _is_foreign_user(nc_path):
            log.warning(
                "scan-all: skipped foreign-user path user=%r nc_path=%s",
                _path_user(nc_path), nc_path,
            )
            continue
        if not body.force:
            if body.skip_ocrd:
                _rec = jobstore.file_get(nc_path)
                if _rec and _rec.get("status") == "done":
                    skipped_ocrd += 1
                    continue
            # node_id is unknown from a listing, so dedup by path:
            # skip files whose job is already queued or running.
            if _path_in_flight(nc_path):
                log.info("scan-all: skip in-flight %s", nc_path)
                continue
        else:
            # Track separately so an operator can see how many of the
            # "force" enqueues collided with already-in-flight paths.
            if _path_in_flight(nc_path):
                forced_in_flight += 1
                log.info("scan-all: force=true overwriting in-flight %s", nc_path)
        # Pass force through so the stamp check inside _process_file
        # is also bypassed for this job.
        _enqueue(nc_path, 0, body.engine, force=body.force)
        enqueued += 1
    log.info(
        "scan-all: folder=%r enqueued=%d skipped_ocrd=%d force=%s forced_in_flight=%d",
        body.folder, enqueued, skipped_ocrd, body.force, forced_in_flight,
    )
    return {
        "status": "queued",
        "enqueued": enqueued,
        "skipped_ocrd": skipped_ocrd,
        "force": body.force,
        "forced_in_flight": forced_in_flight,
    }



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


@app.post("/admin/reconcile-orphans")
async def admin_reconcile_orphans(
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """Operator-triggered orphan reconciler.

    Returns the same shape as :func:`reconcile_orphans`. The
    reconciler also runs once at startup; this endpoint exists so an
    operator can invoke it on demand without restarting the service
    (e.g. right after a manual SQLite intervention, or after noticing
    a folder in the panel stuck at ``queued``).

    Auth is the same ``X-Webhook-Secret`` header every other endpoint
    takes.
    """
    _check_secret(x_webhook_secret)
    return reconcile_orphans()


class ReconcileRequest(BaseModel):
    """C5: bounds for one on-demand reconcile pass.

    All fields optional — defaults to the configured global caps so
    a plain ``POST /reconcile`` is enough to run a normal pass.
    """
    limit: int | None = None
    max_propfind: int | None = None
    statuses: list[str] | None = None


@app.post("/reconcile")
async def reconcile_endpoint(
    body: ReconcileRequest | None = None,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """One-off C5 stale-row reconcile pass.

    Operator-triggered sweep that marks ``error``/``queued`` file
    rows as ``gone`` when the underlying Nextcloud file no longer
    exists. Bounded: each call is capped at
    :data:`_RECONCILE_MAX_PROPFINDS` (overridable per-request via
    ``body.max_propfind``). Idempotent: rows already at ``gone`` are
    excluded at the query level.

    The startup path also runs this once; this endpoint exists so an
    operator can invoke it on demand, e.g. right after noticing a
    list of ``__probe_*.pdf`` rows stuck at ``error``.
    """
    _check_secret(x_webhook_secret)
    body = body or ReconcileRequest()
    return reconcile_stale_files(
        limit=body.limit,
        max_propfind=body.max_propfind,
        statuses=body.statuses,
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
