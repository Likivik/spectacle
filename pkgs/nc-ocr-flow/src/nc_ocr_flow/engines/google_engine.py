"""Google Cloud Vision whole-document OCR engine.

This is the default engine in nc-ocr-flow. It submits the whole PDF
to Google Cloud Vision ``async_batch_annotate_files`` with
``DOCUMENT_TEXT_DETECTION``, waits for the long-running operation, and
walks the per-page responses to assemble per-word blocks in **Google
native reading order** (never re-sorted — Google's order is the
correct reading order; re-sorting by x/y scrambles multi-column text).

Authentication:

  - ``GOOGLE_APPLICATION_CREDENTIALS`` env var pointing to a service
    account JSON key (standard Google Cloud SDK convention), OR
  - The credentials helper chain that ``google-cloud-vision`` ships
    with on the host (GCE metadata server, gcloud auth, etc.).

Env (all optional):

  NC_OCR_GOOGLE_PROJECT         GCP project id (overrides the one in
                                the credentials file, if set).
  NC_OCR_GOOGLE_BUCKET          GCS bucket for input/output JSON
                                (default: a temp bucket is created when
                                absent; for production, set this so the
                                bucket is in the same region as the
                                service account).
  NC_OCR_GOOGLE_LOCATION        Vision API location ("us", "eu", etc.
                                default: "us").

Key API facts (per the loaded google-vision-word-ocr-pdf skill):

  * Whole-doc PDF OCR requires uploading the PDF to GCS first, then
    submitting an ``AsyncAnnotateFileRequest`` whose ``InputConfig``
    uses a ``GcsSource`` (there is no inline-content path for PDFs).
  * ``OutputConfig`` must include a ``gcs_destination`` for the JSON
    output; we use ``batch_size=1``. The operation writes one or more
    JSON files under ``out/`` in the bucket.
  * We aggregate those JSON files by ``context.pageNumber`` so results
    land in real page order regardless of how many files Vision writes.
  * ``features=[DOCUMENT_TEXT_DETECTION]`` is the only feature that
    gives per-word bboxes + reading order.
  * We emit ONE OcrBlock per visual LINE (grouping words by vertical
    overlap, keeping Google's native order — never re-sort, because
    re-sorting by x/y scrambles multi-column text).
  * Block-level confidence lives at the block; we default to 0.95.

The embedded text layer is built from the words in Google's order.
"""
from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from uuid import uuid4

from nc_ocr_flow.ocr_models import OcrBlock, OcrResult

log = logging.getLogger(__name__)

ENGINE_NAME = "google"

# Vision API limits per file for DOCUMENT_TEXT_DETECTION.
# https://cloud.google.com/vision/docs/detect-document-text
_MAX_INLINE_BYTES = 20 * 1024 * 1024  # 20 MB on inline content
_BATCH_TIMEOUT_S = int(os.environ.get("NC_OCR_GOOGLE_BATCH_TIMEOUT", "300"))
_POLL_INTERVAL_S = float(os.environ.get("NC_OCR_GOOGLE_POLL_INTERVAL", "2"))


# --- Lazily-built Vision client --------------------------------------------

_client = None


def _get_client():
    """Lazily construct an ImageAnnotatorClient.

    Imports the SDK only on first call so unit tests and tesseract/minimax
    paths don't pull google-cloud-* into the process.
    """
    global _client
    if _client is None:
        from google.cloud import vision  # type: ignore[import-not-found]
        _client = vision.ImageAnnotatorClient()
    return _client


# --- Public engine entry point ---------------------------------------------


def process_pdf(pdf_path: str | os.PathLike,
                output_pdf: str | os.PathLike | None = None,
                **_unused) -> "object":
    """OCR a whole PDF via Google Cloud Vision.

    Returns ``ocr.ProcessResult`` (imported lazily to avoid a circular
    import with ``nc_ocr_flow.ocr``). The engine does not embed text
    into the PDF — the orchestrator does that using the returned page
    results.
    """
    from nc_ocr_flow import ocr as _ocr

    pdf_path = str(pdf_path)
    out_path = Path(output_pdf) if output_pdf else Path(tempfile.mkdtemp()) / "out.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # The orchestrator's _finalize embeds the text layer by opening
    # ``out_pdf`` and calling _embed_ocr_text over its pages. So we must
    # first seed out_pdf with a real base document (the source PDF keeps
    # the original page images, which the invisible text sits on top of).
    if out_path.exists():
        out_path.unlink()
    import shutil as _shutil
    _shutil.copy2(pdf_path, out_path)

    page_results = _ocr_pdf(pdf_path)

    # The orchestrator will embed the text layer, save, and stamp
    # metadata. This engine just returns the per-page OCR results.
    result = _ocr.ProcessResult(
        output_pdf=str(out_path),
        page_results=page_results,
        engine_used=ENGINE_NAME,
        tess_pages=[],
        vlm_pages=[],
        vlm_failed_pages=[],
        l2_pages={},
    )
    return result


# --- Core: async batch annotate --------------------------------------------


def _ocr_pdf(pdf_path: str) -> list[OcrResult]:
    """Submit the whole PDF to Vision async batch + return per-page results."""
    pdf_bytes = Path(pdf_path).read_bytes()
    if len(pdf_bytes) > _MAX_INLINE_BYTES:
        raise RuntimeError(
            f"PDF too large for inline batch ({len(pdf_bytes)} > "
            f"{_MAX_INLINE_BYTES} bytes); split first or use the GCS path"
        )

    from google.cloud import vision  # type: ignore[import-not-found]
    from google.cloud import storage  # type: ignore[import-not-found]

    client = _get_client()

    # Feature: full document text detection.
    feature = vision.Feature(
        type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION,
    )

    # The proven flow (see skill google-vision-word-ocr-pdf): upload the
    # PDF to GCS first, then submit an AsyncAnnotateFileRequest whose
    # InputConfig points at the GCS source. Vision's PDF support requires
    # GCS storage — there is no inline-content path for whole-doc PDFs.
    bucket = _ensure_batch_bucket(client)
    obj_name = f"ocr-{uuid4().hex}.pdf"
    storage.Client(project=_project_id(client)).bucket(bucket).\
        blob(obj_name).upload_from_string(pdf_bytes, content_type="application/pdf")
    gcs_uri = f"gs://{bucket}/{obj_name}"

    input_config = vision.InputConfig(
        gcs_source=vision.GcsSource(uri=gcs_uri),
        mime_type="application/pdf",
    )
    output_config = vision.OutputConfig(
        gcs_destination=vision.GcsDestination(uri=f"gs://{bucket}/out/"),
        batch_size=1,
    )

    request = vision.AsyncAnnotateFileRequest(
        features=[feature],
        input_config=input_config,
        output_config=output_config,
        image_context=vision.ImageContext(language_hints=["ru", "en"]),
    )

    log.info("vision: submitting batch (%d KB PDF, uri=%s)",
             len(pdf_bytes) // 1024, gcs_uri)

    op = client.async_batch_annotate_files(requests=[request])
    op_result = _wait_for_operation(op, timeout_s=_BATCH_TIMEOUT_S)
    del op_result  # async-GCS output is read from the bucket, not inline

    # Async batch writes one or more JSON files under gs://<bucket>/out/.
    # Read them all and aggregate per-page by context.pageNumber (the
    # proven skill flow: batch_size=1 may produce multiple JSON files).
    out = _aggregate_json_results(bucket, obj_name)

    # Best-effort cleanup of the GCS output dir.
    _cleanup_bucket(bucket)
    return out


def _aggregate_json_results(bucket: str, src_obj: str) -> list[OcrResult]:
    """Download Vision's per-file JSON outputs + aggregate by page.

    Vision writes one JSON per file/page under ``out/`` in the bucket.
    Each response carries ``context.pageNumber``; we key pages by that so
    results are ordered by real page index regardless of JSON-file count.
    """
    import json as _json
    from google.cloud import storage as _gs  # lazy, same as _ocr_pdf

    storage_client = _gs.Client(project=_project_id(_get_client()))
    prefix = "out/"
    blobs = [b for b in storage_client.list_blobs(bucket, prefix=prefix)
             if b.name.endswith(".json")]
    if not blobs:
        log.warning("vision: no JSON outputs under out/ (bucket=%s)", bucket)
        return []

    by_page: dict[int, object] = {}
    for blob in blobs:
        data = _json.loads(blob.download_as_text())
        for resp in data.get("responses", []):
            ctx = resp.get("context", {}) or {}
            page_num = ctx.get("pageNumber") or ctx.get("page_number")
            if page_num is None:
                continue
            by_page[int(page_num)] = resp
        blob.delete()

    out: list[OcrResult] = []
    for page_num in sorted(by_page):
        resp = by_page[page_num]
        # Deserialize the raw JSON response into a proto for _blocks_from_page.
        try:
            from google.cloud.vision_v1 import AnnotateImageResponse
            parsed = AnnotateImageResponse.from_json(_json.dumps(resp))
        except Exception as exc:  # noqa: BLE001 — best-effort parse
            log.warning("vision: could not parse page %d JSON: %s", page_num, exc)
            out.append(OcrResult(blocks=[], page_width=0.0, page_height=0.0))
            continue

        full = getattr(parsed, "full_text_annotation", None)
        if full is None:
            out.append(OcrResult(blocks=[], page_width=0.0, page_height=0.0))
            continue
        page_w, page_h = _page_dims(full, parsed)
        page_idx = page_num - 1
        blocks = _blocks_from_page(full, page_w, page_h, page_idx)
        out.append(OcrResult(blocks=blocks, page_width=page_w, page_height=page_h))

    return out


def _page_dims(full, page_resp) -> tuple[float, float]:
    """Get the page width/height in image pixels."""
    # The top-level Page (pages[0]) has page-level bbox & dims.
    pages = list(getattr(full, "pages", []))
    if pages:
        p = pages[0]
        # Property `width`/`height` are ints in the proto.
        return float(p.width), float(p.height)
    # Fallback: top-level bounding box vertices.
    bb = getattr(full, "bounding_boxes", None)
    if bb:
        v0 = bb[0].vertices[0]
        v2 = bb[0].vertices[2]
        return float(v2.x - v0.x), float(v2.y - v0.y)
    # Last resort — use the rendered page dimensions if we can.
    return 0.0, 0.0


def _blocks_from_page(full, page_w: float, page_h: float, page_idx: int) -> list[OcrBlock]:
    """Convert a Vision Page full_text_annotation into per-LINE OcrBlocks.

    **One OcrBlock per visual line** — this is the granularity the
    skill proved gives clean selection. We group each paragraph's words
    into lines by vertical overlap (keeping Google's native word order;
    never re-sort), and emit one OcrBlock per line with its own bbox.
    """
    blocks: list[OcrBlock] = []
    pages = list(getattr(full, "pages", []))
    for page in pages:
        for block in page.blocks:
            for line, bbox in _line_blocks(block, page_w, page_h):
                if not line.strip():
                    continue
                blocks.append(OcrBlock(
                    bbox=bbox,
                    text=line,
                    confidence=0.95,
                    label=_block_label(block),
                ))
    return blocks


def _line_blocks(block, page_w: float, page_h: float):
    """Yield (line_text, line_bbox) for each visual line in a Vision block.

    Groups words into lines by vertical overlap in native order.
    """
    # Collect words with their per-word bboxes.
    for para in block.paragraphs:
        words = []  # (x0, y0, x1, y1, text)
        for word in para.words:
            sym = "".join(s.text for s in word.symbols).strip()
            if not sym:
                continue
            vs = getattr(word.bounding_box, "vertices", None)
            if not vs or len(vs) < 4:
                continue
            xs = [float(v.x) for v in vs]
            ys = [float(v.y) for v in vs]
            words.append((min(xs), min(ys), max(xs), max(ys), sym))

        # Group into lines by vertical overlap, preserving native order.
        lines = []  # list of [word,...]
        for w in words:
            placed = False
            for L in lines:
                ly1 = min(x[1] for x in L)
                ly2 = max(x[3] for x in L)
                ov = min(w[3], ly2) - max(w[1], ly1)
                if ov > 0:
                    L.append(w)
                    placed = True
                    break
            if not placed:
                lines.append([w])

        for L in lines:
            text = " ".join(w[4] for w in L)
            x0 = max(0.0, min(w[0] for w in L))
            y0 = max(0.0, min(w[1] for w in L))
            x1 = min(page_w, max(w[2] for w in L))
            y1 = min(page_h, max(w[3] for w in L))
            yield text, (x0, y0, x1, y1)


def _block_label(block) -> str:
    """Block-level type tag from Vision, lowercased."""
    # BlockType is an enum: TEXT, TABLE, PICTURE, etc.
    bt = getattr(block, "block_type", None)
    name = getattr(bt, "name", "") if bt else ""
    return name.lower() or "google-block"


# --- GCS output bucket plumbing --------------------------------------------

# Cache so we don't churn buckets.
_batch_bucket: str | None = None


def _ensure_batch_bucket(client) -> str:
    """Return a GCS bucket name for batch output.

    Strategy: read NC_OCR_GOOGLE_BUCKET from env. If unset, create a
    short-lived bucket with a uuid name under our project (best-effort;
    we delete it in _cleanup_bucket).
    """
    global _batch_bucket
    if _batch_bucket:
        return _batch_bucket

    explicit = os.environ.get("NC_OCR_GOOGLE_BUCKET")
    if explicit:
        _batch_bucket = explicit
        return explicit

    import uuid
    from google.cloud import storage  # type: ignore[import-not-found]

    project = _project_id(client)
    name = f"nc-ocr-vision-tmp-{uuid.uuid4().hex[:10]}"
    gs = storage.Client(project=project)
    b = gs.bucket(name)
    b.location = os.environ.get("NC_OCR_GOOGLE_LOCATION", "US")
    b.create()
    _batch_bucket = name
    return name


def _cleanup_bucket(name: str | None) -> None:
    """Best-effort: delete the temp bucket + all its objects."""
    if not name or name == os.environ.get("NC_OCR_GOOGLE_BUCKET"):
        return
    try:
        from google.cloud import storage  # type: ignore[import-not-found]
        gs = storage.Client(project=_project_id(_get_client()))
        b = gs.bucket(name)
        # Force=True deletes non-empty buckets.
        b.delete(force=True)
        log.info("vision: cleaned up temp bucket %s", name)
    except Exception as exc:  # noqa: BLE001 — best-effort cleanup
        log.warning("vision: bucket cleanup failed: %s", exc)


def _project_id(client) -> str | None:
    """Resolve the active GCP project id."""
    if hasattr(client, "_channel") and hasattr(client, "_transport"):
        return None  # client doesn't expose project directly; SDK handles
    return os.environ.get("NC_OCR_GOOGLE_PROJECT") or os.environ.get(
        "GOOGLE_CLOUD_PROJECT"
    )


# --- Long-running operation poll -------------------------------------------


def _wait_for_operation(op, timeout_s: int):
    """Poll a Vision LRO until done.

    The Vision SDK exposes ``op.result(timeout=...)`` which blocks;
    we use the more transparent ``op.done()`` loop so logs show
    progress for large docs.
    """
    t0 = time.time()
    while not op.done():
        if time.time() - t0 > timeout_s:
            raise TimeoutError(f"vision batch timed out after {timeout_s}s")
        time.sleep(_POLL_INTERVAL_S)
    return op.result()


__all__ = ["process_pdf", "ENGINE_NAME"]