# MonkeyOCRv2-B parsing server (spectacle)

Replaces the previous custom wrapper with semantics that match the official
[MonkeyOCR](https://github.com/Yuliang-Liu/MonkeyOCR) `core_runner` flow
(`parse.py` + `magic_pdf/model/batch_analyze_llm.py` +
`magic_pdf/utils/load_image.py` + `magic_pdf/model/custom_model.py`).

## Server

`monkey_server.py` exposes `POST /parse` (and `GET /health`) on port 8086.
The pipeline:

1. **layout** — page image is 1MP-capped (`load_image(max_pixels=1_000_000)`);
   layout prompt `Please output the categories and coordinates of the document
   elements in reading order.` produces ordered blocks.
2. **bbox normalization** — `clamp_swap_expand(bbox, w, h)` clamps to
   0–1000, swaps reversed edges, un-normalizes to pixels, expands by 2px,
   re-clamps to image bounds. Output bbox is returned as PNG pixel
   coordinates (preserves the existing `monkey_client.py` contract).
3. **recognition** — each surviving block is cropped, resized with the
   upstream recognition policy (`max_size=1600`), and routed through the
   label's official prompt:

   | label group                | prompt |
   |----------------------------|--------|
   | `text` / `title` / `section-header` / `caption` / `footnote` / `list-item` / `page-header` / `page-footer` | `Please output the text content from the image.` |
   | `formula` / `equation`     | `Please write out the expression of the formula in the image using LaTeX format.` |
   | `table`                    | `This is the image of a table. Please output the table in html format.` |

4. **retry-repeat** — `_generate_with_retry` re-prompts up to 2 additional
   times when recognition returns empty / JSON fragments / `undefined`.
5. **generation params** — `do_sample=False, temperature=0.0,
   repetition_penalty=1.05` (matches upstream `MonkeyChat_LMDeploy` /
   `MonkeyChat_vLLM.batch_inference`).
6. **tolerant parser** — `parse_layouts` handles fenced blocks, bare lists,
   single-quoted Python reprs, top-level dicts, and brace-depth
   fragment parsing for truncated outputs.

If the layout stage returns no valid blocks, the whole page is OCR'd with
the direct text prompt and wrapped as a single Text block (matches upstream
`split_pages` empty-layout fallback).

## Deployment

The NixOS module in `modules/aspects/server/monkey-server/default.nix` is
unchanged — it already mounts the local model cache, sets
`TRITON_LIBCUDA_PATH` / `TRITON_CACHE_DIR`, and applies the sm_75 SDPA +
fp16 monkey-patches. Restart the `nc-monkey-server` systemd unit on
Serenity to pick up the new code:

```
sudo systemctl restart nc-monkey-server
```

## Artifact scripts

`scripts/emit_final6.py` calls `POST /parse` for every page of the chosen
file and emits the canonical bakeoff triple into
`out/monkeyocrv2-official/<file_key>/`:

- `p<N>.json` — `{"blocks": [{"text": ..., "bbox": [x0,y0,x1,y1], "label": ...}], ...}`
  in PNG pixels, reading order preserved from upstream layout.
- `p<N>.md` — markdown rendering in reading order.
- `p<N>_layout.pdf` — page PDF with bbox overlays coloured by index, label
  annotated top-left of each box.
- `timings.tsv` — per-page elapsed seconds and block counts.

`scripts/validate_final6.py` walks the same output tree and reports:

- artifacts-present counts (`json` / `md` / `layout_pdf`)
- bbox validity (`valid/total`, in-image-bounds, 4-tuple, x0<x1 and y0<y1)
- reading-order score (fraction of consecutive block pairs whose top-left
  corner descends or stays level-and-shifts-right)
- mixed-script garble count (cyrillic+latin in the same token)
- average `difflib.SequenceMatcher` similarity vs the M3 baseline text
  layer for the same file.

Run after `emit_final6.py` once the server has been redeployed on Serenity.

## Tests

```
pytest pkgs/monkeyocr-server/tests/
```

24 tests cover: `clamp_swap_expand`, `parse_layouts` (fences, reprs,
top-level dict, fragmented, empty), `prompt_for`, `_is_bad_recognition`,
`_generate_with_retry`, `reading_order_score`, `bbox_stats`,
`mixed_script_words`, `norm`. No GPU required.
