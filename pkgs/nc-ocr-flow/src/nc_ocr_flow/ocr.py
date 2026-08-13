"""ocrmypdf wrapper: embed text layer, olmOCR-v2 fallback for low-conf pages."""
from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

PER_PAGE_CONF_FLOOR = 70
PER_PAGE_MIN_CHARS = 40

OLMOCR_ENDPOINT = os.environ.get("NC_OCR_OLMOCR_ENDPOINT", "http://serenity:8083")


def _run_ocrmypdf(input_pdf: Path, output_pdf: Path) -> dict:
    sidecar = output_pdf.with_suffix(".tsv.json")
    cmd = [
        "ocrmypdf",
        "--skip-text",
        "--rotate-pages",
        "--deskew",
        "--clean",
        "--language", "rus+eng",
        "--sidecar", str(sidecar),
        "--output-type", "pdf",
        str(input_pdf),
        str(output_pdf),
    ]
    log.info("running: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, capture_output=True, timeout=600)
    if sidecar.exists():
        return json.loads(sidecar.read_text())
    return {}


def _needs_vlm_fallback(per_page_meta: dict) -> list[int]:
    flagged = []
    for page_idx, page_meta in per_page_meta.get("pages", {}).items():
        conf = page_meta.get("conf_p10", 100)
        chars = page_meta.get("char_count", 0)
        if conf < PER_PAGE_CONF_FLOOR or chars < PER_PAGE_MIN_CHARS:
            flagged.append(int(page_idx))
    return flagged


def _olmocr_ocr_page(pdf_bytes: bytes, page_idx: int) -> str:
    import requests
    resp = requests.post(
        f"{OLMOCR_ENDPOINT}/v1/chat",
        json={
            "model": "olmocr-v2",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "data": pdf_bytes.hex(), "page": page_idx},
                        {"type": "text", "text": "Extract all text preserving layout."},
                    ],
                }
            ],
        },
        timeout=300,
    )
    resp.raise_for_status()
    return resp.json().get("text", "")


def _write_vlm_sidecar(input_pdf: Path, page_text: dict[int, str]) -> Path:
    output_md = input_pdf.with_suffix(".vlm.md")
    with output_md.open("w") as f:
        for page_idx in sorted(page_text):
            f.write(f"\n## Page {page_idx + 1}\n\n")
            f.write(page_text[page_idx])
            f.write("\n")
    return output_md


def process_pdf(input_path: str, output_dir: str | None = None) -> dict:
    input_pdf = Path(input_path)
    if output_dir:
        output_pdf = Path(output_dir) / input_pdf.name
    else:
        output_pdf = input_pdf.with_suffix(".ocr.pdf")

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    per_page_meta = _run_ocrmypdf(input_pdf, output_pdf)
    flagged = _needs_vlm_fallback(per_page_meta)

    sidecar_md = None
    if flagged:
        log.info("pages needing VLM fallback: %s", flagged)
        with open(input_pdf, "rb") as f:
            pdf_bytes = f.read()
        page_text = {idx: _olmocr_ocr_page(pdf_bytes, idx) for idx in flagged}
        sidecar_md = _write_vlm_sidecar(output_pdf, page_text)

    return {
        "output_pdf": str(output_pdf),
        "sidecar_md": str(sidecar_md) if sidecar_md else None,
        "vlm_pages": flagged,
        "tesseract_pages": [int(k) for k in per_page_meta.get("pages", {}).keys()],
    }
