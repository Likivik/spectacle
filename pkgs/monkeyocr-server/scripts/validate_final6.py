#!/usr/bin/env python3
"""Reading-order validation for MonkeyOCR canonical artifacts vs bakeoff baseline.

Usage:
  python3 validate_final6.py [--model monkeyocrv2-official] [--file final6-pristine]

Reports:
  - per-page SequenceMatcher ratio vs baseline text
  - bbox validity (4-tuple, ordered, non-degenerate, in image bounds)
  - mixed-script (cyrillic+latin in one word) garbage count
  - layout.json / layout.pdf existence per page
  - JSON block count
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    import fitz  # noqa: F401 - imported lazily inside baseline_pages
except Exception:
    fitz = None  # type: ignore[assignment]

BAKEOFF = Path("/var/lib/hermes/.hermes/cache/documents/bakeoff-gemini")
SRC = Path("/var/lib/hermes/.hermes/cache/documents/ocrmatrix5")
BASELINE = BAKEOFF / "baseline"
OUT = BAKEOFF / "out"

FILES = {
    "final6-pristine": "final6-pristine-m3.pdf",
    "egrn": "egrn-m3.pdf",
    "mo4521": "mo4521-m3.pdf",
}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t).lower()
    t = re.sub(r"[^а-яёa-z0-9]+", "", t)
    return t


def baseline_pages(file_key: str) -> list[str]:
    src = SRC / FILES[file_key]
    base_txt = BASELINE / f"{file_key}.txt"
    if base_txt.exists():
        txt = base_txt.read_text()
        # baseline txt is pre-split by page separator (FF \x0c). Fall back to
        # rasterizing the source PDF for per-page text if no separator found.
        if "\x0c" in txt:
            return [norm(p) for p in txt.split("\x0c")]
    try:
        import fitz
        doc = fitz.open(str(src))
        return [norm(doc[i].get_text()) for i in range(len(doc))]
    except Exception:
        return []


def json_blocks(model: str, file_key: str, n: int) -> list[dict]:
    p = OUT / model / file_key / f"p{n}.json"
    if not p.exists():
        return []
    return json.loads(p.read_text()).get("blocks", []) or []


def md_text(model: str, file_key: str, n: int) -> str:
    p = OUT / model / file_key / f"p{n}.md"
    return p.read_text() if p.exists() else ""


def bbox_stats(blocks: list[dict], pw: int, ph: int) -> tuple[int, int, list[str]]:
    valid = 0
    issues = []
    for b in blocks:
        bb = b.get("bbox") or []
        if len(bb) != 4:
            issues.append("not 4-tuple")
            continue
        try:
            x0, y0, x1, y1 = (float(v) for v in bb)
        except (TypeError, ValueError):
            issues.append("non-numeric")
            continue
        if not (0 <= x0 < x1 <= pw and 0 <= y0 < y1 <= ph):
            issues.append("out-of-bounds")
            continue
        valid += 1
    return valid, len(blocks), issues


def mixed_script_words(text: str) -> int:
    return len([w for w in text.split()
                if re.search(r"[а-яё]", w, re.I) and re.search(r"[a-z]", w, re.I)])


def reading_order_score(blocks: list[dict]) -> float:
    """Fraction of consecutive block pairs whose top-left corner descends.

    Strict reading order: y0 strictly increases, ties broken by x0. Returns
    1.0 for empty/single block.
    """
    if len(blocks) < 2:
        return 1.0
    sorted_pairs = 0
    for a, b in zip(blocks, blocks[1:]):
        ax0, ay0, *_ = a["bbox"]
        bx0, by0, *_ = b["bbox"]
        if by0 > ay0 or (by0 == ay0 and bx0 >= ax0):
            sorted_pairs += 1
    return sorted_pairs / (len(blocks) - 1)


def validate(model: str, file_key: str, page_limit: int | None = None) -> dict:
    base = baseline_pages(file_key)
    n_pages = len(base) if page_limit is None else min(len(base), page_limit)
    rows = []
    artifacts_present = {"json": 0, "md": 0, "layout_pdf": 0}
    total_ro_score = 0.0
    total_valid = 0
    total_blocks = 0
    total_garbage = 0
    total_sim = 0.0
    sim_n = 0

    for n in range(1, n_pages + 1):
        blocks = json_blocks(model, file_key, n)
        json_p = OUT / model / file_key / f"p{n}.json"
        md_p = OUT / model / file_key / f"p{n}.md"
        lpdf_p = OUT / model / file_key / f"p{n}_layout.pdf"
        if json_p.exists():
            artifacts_present["json"] += 1
        if md_p.exists():
            artifacts_present["md"] += 1
        if lpdf_p.exists():
            artifacts_present["layout_pdf"] += 1

        # Read image dims from p{N}.json (server reported them) or PNG
        pw, ph = 0, 0
        if json_p.exists():
            data = json.loads(json_p.read_text())
            pw = data.get("page_w") or 0
            ph = data.get("page_h") or 0
        valid, tot, _ = bbox_stats(blocks, pw, ph)
        total_valid += valid
        total_blocks += tot
        ro = reading_order_score(blocks)
        total_ro_score += ro
        md = md_text(model, file_key, n)
        garbage = mixed_script_words(md)
        total_garbage += garbage
        sim = 0.0
        if md and n - 1 < len(base):
            import difflib
            sim = difflib.SequenceMatcher(None, norm(md), base[n - 1]).ratio()
            total_sim += sim
            sim_n += 1
        rows.append({"page": n, "blocks": tot, "valid_bbox": valid,
                     "ro": round(ro, 3), "sim": round(sim, 3),
                     "garbage": garbage})

    summary = {
        "model": model,
        "file": file_key,
        "pages": n_pages,
        "artifacts_present": artifacts_present,
        "avg_similarity_vs_M3": round(total_sim / sim_n, 3) if sim_n else None,
        "bbox_valid_total": f"{total_valid}/{total_blocks}",
        "bbox_valid_fraction": round(total_valid / total_blocks, 3) if total_blocks else 0,
        "avg_reading_order_score": round(total_ro_score / n_pages, 3) if n_pages else 0,
        "total_mixed_script_words": total_garbage,
    }
    return {"summary": summary, "per_page": rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="monkeyocrv2-official")
    ap.add_argument("--file", default="final6-pristine")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    res = validate(args.model, args.file, args.limit)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
