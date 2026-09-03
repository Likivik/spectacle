# Self-Hosted OCR / Document-VLM Models for 6 GB VRAM (2025–2026)

Compiled September 2026. Scope: models that ship as open weights, can run on a single consumer GPU (RTX 3060/4060/3090/4090 / Apple Silicon), and produce structured output (Markdown / HTML / JSON). Each entry covers olmOCR-bench, OmniDocBench v1.5/v1.6, Russian/Cyrillic evidence, bbox/coordinate output (line-level text spotting), table recognition, throughput, quantization, and the inference backends it actually supports.

Bench numbers are taken from the **primary** citation for each model (model card, HF Space, paper). Where a model is not on olmOCR-Bench, the closest published score is used and flagged.

---

## TL;DR ranking (for a 6 GB VRAM box)

Ordered by "best deployed today inside the constraint". Faster ↑ = more pages/sec on consumer GPU.

| # | Model | Params | OmniDocBench v1.5/v1.6 | olmOCR-Bench | Russian | Backend(s) on 6 GB | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | **Surya OCR 2** | 0.65B | n/a (specialised) | **83.3** | **88.8** (top of class) | vLLM **or llama.cpp/Metal** | Best multilingual layout+table bundle that fits in <2 GB. |
| 2 | **GLM-OCR** | 0.9B | **94.62** v1.5 | n/a | limited evidence (no public RU score, but Z.ai GLM is bilingual-trained) | vLLM / SGLang / Ollama, transformers | Best single-page parse quality at 0.9B. |
| 3 | **PaddleOCR-VL 1.5 / 1.6** | 0.9B | **94.50** v1.5 / **96.34** v1.6 | **80.0** | strong (trained on RU/UK pages via PP-OCRv5; 109 languages) | vLLM / SGLang / FastDeploy / **llama.cpp** (merged b8110, Feb 2026) / mlx-vlm | First-class layout + bbox + text-spotting; full pipeline needs PaddlePaddle. |
| 4 | **Qwen3-VL 4B (Q4_K_M GGUF)** | 4B dense | 90.62 (v1.0 ODB) | 78.5 (Qwen3-VL-235B family) | **strong** (32 langs incl. RU, Cyrillic-aware tokenizer) | llama.cpp (MTMD), Ollama, vLLM | Best general-purpose VL choice if you need reasoning on top of OCR. |
| 5 | **Chandra OCR 2** | 4B (FP16) → 2.9 GB INT4 | n/a | **85.9** | **85.5** (88.8 with API/hosted) | vLLM (16-24 GB VRAM unquantized; INT4 fits 4-6 GB) | Best olmOCR-Bench raw score *with* bbox blocks; needs aggressive quant. |
| 6 | **dots.mocr** | 3B (vision tower stays BF16) | 90.77 v1.6 | **83.9 SOTA OSS** | strong (RU in MDPBench, photoreal Cyrillic issue noted) | vLLM + FP8 weight available | Pareto-best at 3B; needs ~5 GB FP8 to run. |
| 7 | **DeepSeek-OCR 2** | 3B (≈6.8 GB BF16) | **91.09** v1.5 | 76.3 | limited (deepseek tokenizer covers RU) | transformers / vLLM / **llama.cpp** (PR #20975) / Ollama :3b | Easiest to quantize to a single 6 GB card via llama.cpp GGUF. |
| 8 | **Inf-Parser2 Flash** | 2B (Qwen3.5-2B) | 91.98 v1.6 | **86.0** | not separately reported | vLLM only (no llama.cpp GGUFs yet) | Newest SOTA at 2B; bumps against 6 GB even at BF16. |
| 9 | **MinerU 2.5 / 2.5-Pro** | 1.2B (NaViT-675M + Qwen2-0.5B) | 92.98 / 95.75 v1.6 / 95.69 v1.6-Pro | 75.2 / 84.9 (Tables) | multilingual coverage; MinerU 2.5 updated Cyrillic OCR to PP-OCRv5 with +40 % accuracy | vLLM, sglang (legacy) | Two-stage (layout + recognition); strong on tables; smallest **end-to-end** SOTA-class model. |
| 10 | **Nemotron Parse 2.0** | 0.9B | n/a (MOSCAR 0.91) | n/a (specialised) | **excellent** for CJK/Indic/Cyrillic (MOSCAR +0.47) | vLLM (PR open); speculative-decode speed-up | Best **non-OCR VLM** for Cyrillic handheld/scanned workloads. |
| 11 | **olmOCR 2** | 7B (FP8 quantised) | 85.7 v1.6 | **82.4** | limited (English-focused) | vLLM + AllenAI toolchain; FP8 quant ships | Hard to fit under 6 GB at quality; only with INT4/FP8 + small batches. |
| 12 | **GOT-OCR 2.0** | 0.58B | n/a (Fox bench SOTA on text) | **48.3** (legacy basis) | partial (multilingual but EN/ZH focused) | transformers, HF pipeline | Falls behind on modern benchmarks; still useful for charts / sheet music / formulas. |
| 13 | **GLM-4.6V-Flash** | 9B | n/a (general VLM) | n/a | strong (GLM family) | vLLM / SGLang | Does **not** fit in 6 GB; included only because the prompt asks. |

(`Qwen3-VL 8B` and `GLM-4.6V` 106 B are above the 6 GB ceiling even when AGGRESSIVELY quantised and shared with KV; flagged below.)

---

## Score tables (verbatim, from primary sources)

### A. OmniDocBench v1.5/v1.6 leaderboard (OmniDocBench repo, March 2026 update)

| Model | Param | Overall ↑ | TextEdit ↓ | Formula CDM ↑ | Table TEDS ↑ | Table TEDS-S ↑ | Read Order ↓ |
|---|---|---|---|---|---|---|---|
| **PaddleOCR-VL-1.6** | 0.9B | **96.34** | 0.0326 | 97.53 | 94.76 | 97.10 | 0.1278 |
| **MinerU2.5-Pro** | 1.2B | 95.75 | 0.036 | 97.45 | 93.42 | 95.92 | 0.120 |
| **GLM-OCR** | 0.9B | 95.22 | 0.044 | 97.18 | 92.83 | 95.39 | 0.133 |
| **PaddleOCR-VL-1.5** | 0.9B | 94.93 | 0.038 | 96.89 | 91.67 | 94.37 | 0.130 |
| PaddleOCR-VL | 0.9B | 94.18 | 0.040 | 95.91 | 90.65 | 93.74 | 0.135 |
| Youtu-Parsing | 2.5B | 93.74 | 0.044 | 93.63 | 92.02 | 95.00 | 0.116 |
| Qianfan-OCR | 4B | 93.90 | 0.04 | 95.08 | 90.53 | 93.31 | 0.13 |
| Logics-Parsing-v2 | 4B | 93.33 | 0.041 | 95.65 | 88.42 | 91.98 | 0.137 |
| FireRed-OCR | 2B | 93.26 | 0.037 | 95.44 | 88.04 | 91.06 | 0.131 |
| MinerU-2.5 | 1.2B | 93.04 | 0.045 | 95.77 | 87.88 | 91.47 | 0.130 |
| Gemini 3 Pro | – | 92.91 | 0.064 | 95.99 | 89.15 | 92.96 | 0.165 |
| **dots.ocr** | 3B | 90.77 | 0.048 | 89.95 | 87.18 | 90.58 | 0.138 |
| DeepSeek-OCR 2 | 3B | 90.25 | 0.050 | 91.84 | 83.89 | 87.75 | 0.144 |
| HunyuanOCR | 1B | 89.95 | 0.088 | 87.68 | 91.01 | 93.23 | 0.171 |
| MonkeyOCR-pro-3B | 3B | 88.57 | 0.074 | 88.74 | 84.35 | 88.62 | 0.189 |
| **olmOCR** (v1) | 7B | 85.74 | 0.139 | 88.10 | 83.00 | 87.17 | 0.216 |
| Nanonets-OCR-s | 3B | 83.61 | 0.108 | 81.46 | 80.18 | 84.51 | 0.213 |

### B. olmOCR-Bench (AllenAI benchmark)

| Model | Param | Overall | ArXiv | Old Scans Math | Tables | Old Scans | Headers | Multi-col | Tiny Text |
|---|---|---|---|---|---|---|---|---|---|
| **Inf-Parser2-Pro** | 35B | **87.6** | – | – | – | – | – | – | – |
| **Chandra OCR 2** | 4B | **85.9** (85.8 hosted) | 86.9/90.4 | 89.1/90.2 | 92.1/90.7 | 51.1/54.6 | 91.4/91.6 | 82.1/83.7 | 93.7/92.3 |
| Inf-Parser2-Flash | 2B | **86.0** | – | – | – | – | – | – | – |
| **dots.mocr** | 3B | **83.9** | 85.9 | 85.5 | 90.7 | 48.2 | 94.0 | 85.3 | 81.6 |
| **Surya OCR 2** | 0.65B | **83.3** | 88.3 | 81.4 | 86.6 | 41.8 | 92.5 | 82.4 | 93.7 |
| Inf-Parser 7B (legacy) | 7B | 82.5 | 84.4 | 83.8 | 85.0 | 47.9 | 88.7 | 84.2 | 86.4 |
| **olmOCR 2 (FP8)** | 7B | **82.4** | 83.0 | 82.3 | 84.9 | 47.7 | 96.1 | 83.7 | 81.9 |
| **PaddleOCR-VL** | 0.9B | **80.0** | 85.7 | 71.0 | 84.1 | 37.8 | 97.0 | 79.9 | 85.7 |
| **DeepSeek-OCR 2** | 3B | 76.3 (DeepSeek-OCR v1: 75.7) | 82 | 72 | 77.4 | 33.8 | – | 79 | 90.7 |
| **MinerU 2.5** | 1.2B | 75.2 | 76.6 | 54.6 | 84.9 | 33.7 | 96.6 | 78.2 | 83.5 |
| GOT-OCR | 0.6B | 48.3 | – | – | – | – | – | – | – |

### C. olmOCR-bench per-task winner: Chandra OCR 2 dominates "Old Scans" (51.1) — best for messy heritage Cyrillic / Russian archival material; Inf-Parser2 wins raw score; dots.mocr wins table subcategory (90.7).

### D. Russian / Cyrillic-language evidence

| Model | Russian score | Source / Notes |
|---|---|---|
| **Surya OCR 2** | **88.8 %** (43-lang multilingual internal); 87.2 % average across 91 languages | datalab.to/blog/surya-2 |
| **Chandra OCR 2** | **85.5 %** (Russian, 43-lang internal); **88.8 %** with hosted API | datalab-to/chandra README |
| **dots.mocr** | Ru: **79.9 %** on MDPBench (PaddleOCR-VL-1.5 hits it as well); also called out for **Cyrillic↔Latin visual confusion** in photographed docs | MDPBench paper §5 |
| **PaddleOCR-VL 1.5** | Strong RU on text blocks; **Cyrillic performance gain noted as side-effect of PP-OCRv5 upgrade** ("Russian accuracy improved by over 40 %") | MinerU changelog 2.5.4 |
| **Qwen3-VL 4B/8B** | Native RU + Cyrillic; expands OCR from 19 → **32 languages** (RU, UK, BG, SR, MK explicitly listed) | Qwen3-VL-4B-Instruct-GGUF card |
| **Nemotron Parse 2.0** | MOSCAR multilingual **0.9102 BoC-F1 (was 0.4410 in v1.2)**; Russian handwritten OMDB text-edit drops from 0.97 → **0.34** | Nemotron-Parse 2.0 model card |
| **GLM-OCR** | No standalone Russian public score; Z.ai training data is bilingual CN/EN; ships a separate KIE pipeline, no multilingual benchmark published in paper |
| **Inf-Parser2 Flash** | Bilingual zh/en only (Infinity-Doc2-5M is CN/EN); **no published RU evidence** |
| **GLM-4.6V-Flash** | GLM family tokenizer covers RU; no document-parsing benchmark; included only as "fits-on-bigger-card" generalist |

Caveat (MDPBench 2026): every open-weights OCR model **mis-classifies Cyrillic-Latin look-alikes** (А, В, С, Е, К, М, Н, О, Р, Т, Х) on photographed documents. Choosing between dots.mocr, PaddleOCR-VL-1.5, Surya 2, or Chandra 2 is mostly about laptop-class-vs-server-class deployment tradeoffs; **Surya 2** is the cleanest small model for RU given its dedicated multilingual benchmark.

---

## Per-model details

### 1. Surya OCR 2 (0.65 B) — best "fits anywhere" Russian-capable stack

- **Primary benchmark**: olmOCR-bench **83.3** (1st under 3 B); multilingual **87.2 % avg across 91 languages**, **Russian 88.8 %**.
- **Layout / bbox / table**: a single VLM emits **layout JSON** *or* full-page HTML with **bbox + reading-order**, plus a **separate** EfficientViT segformer for **line-level text detection** (`text_lines`), and a table-recognition mode with rows + columns. Genuinely line-level text spotting via the dedicated detector.
- **Inference**: OFFICIAL SUPPORT FOR **llama.cpp / Metal** (Apple Silicon) **and vLLM (GPU)**. The `surya-ocr-2-gguf` HF repo and the `SuryaInferenceManager` abstract both backends, with `SURYA_INFERENCE_URL=http://host:port/v1` if you point at an existing llama-server.
- **Quantisation**: GGUF variants (Qwen3.5-style backbone, 0.65 B params). Throughput: **5.35 pages/s on a single RTX 5090 at concurrency 128** (vLLM, 2 400 tok/page); **0.108 pages/s on Apple M-series Metal at parallelism 8** (~30 W). BF16 weights ≈ 1.4 GB.
- **License**: code Apache-2.0, weights modified OpenRAIL-M (free below $5 M ARR).
- **Verdict**: 🥇 the only model with an official **6 GB GPU path AND official Russian multilingual benchmark AND line-level detection**. Best pick for any consumer card.

### 2. GLM-OCR (0.9 B) — best OmniDocBench at 0.9 B

- **Primary**: **OmniDocBench v1.5 = 94.62 (#1)**; OCRBench Text 94.0; UniMERNet 96.5; TEDS_Test 86.0; KIE Nanonets 93.7.
- **Layout / bbox**: 0.4 B CogViT vision encoder + 0.5 B GLM decoder; uses **PP-DocLayout-V3** for layout, then per-region recognition. Two-stage pipeline. Bbox output via the layout model. No published line-level text spotting alone.
- **Russian**: not separately published; trained on GLM corpus (bilingual CN/EN). Use PaddleOCR-VL-1.5 / Surya 2 instead for RU-heavy docs.
- **Inference**: **vLLM, SGLang, Ollama** — official recipes for all three. Throughput **1.86 pages/s PDF**.
- **Quant**: BF16 only officially; ~1.8 GB. INT4 brings it under 1 GB on llama.cpp if a GGUF becomes available (none yet as of Sep 2026).
- **Verdict**: 🥈 best pure "single-endpoint" parse quality when you don't need multilingual RU.

### 3. PaddleOCR-VL 1.5 / 1.6 (0.9 B) — best bbox + text-spotting pipeline

- **Primary**: OmniDocBench v1.5 **94.50** (1.5), **96.34** v1.6 — #1 in v1.6 leaderboard (March 2026); olmOCR-Bench **80.0**; new **text spotting (line-level localisation + recognition)** and **seal recognition** tasks added in 1.5.
- **Layout / bbox**: Two-stage **PP-DocLayout-V3 + ERNIE-4.5-0.3B VLM**. Layout returns `coordinate: [x1,y1,x2,y2]` per element with `cls_id`, `label`, `score`, plus reading-order index. 25+ block types (`doc_title`, `paragraph_title`, `text`, `table`, `image`, `formula`, `seal`, `vision_footnote`, `spotting`...). **Spotting prompt returns text-line coords + recognitions in one shot**.
- **Russian**: **PP-OCRv5 Russian module updated, +40 % accuracy** vs v0.x; Cyrillic language supported; ships layout detection in 109 languages in the broader PaddleOCR stack.
- **Inference**: **vLLM, SGLang, FastDeploy, llama.cpp (merged b8110, Feb 2026), mlx-vlm (Apple Silicon), transformers, PaddlePaddle**. vLLM end-to-end **1.2 pages/s on A100 batched 512**. Tokens/sec on A100 ≈ 1 881.
- **Quant**: GGUF available (community + official `megemini/PaddleOCR-VL-1.5-GGUF`). BF16 ≈ 1.8 GB → fits 6 GB easily.
- **Caveat**: full pipeline needs **PaddlePaddle** for the layout model; llama.cpp/transformers paths do VLM-only.
- **Verdict**: 🥉 if you need bbox + line-level spotting + RU/Cyrillic + std inference, this is the cleanest first-party choice. **Spotting prompt is unique among the lot.**

### 4. Qwen3-VL 4B (Q4_K_M GGUF) — best general-purpose VL on a 6 GB card

- **Params**: 4.28 GB Q8_0 / 2.5 GB Q4_K_M (LLM) + ~840 MB mmproj F16.
- **Primary**: Qwen3-VL-235B leads OmniDocBench Elo; the 4 B inherits the tokenizer ("32 OCR languages up from 19"), strong reading-order and formula skills. Practical benchmarks on OmniDocBench v1.0 dot.ocr-style ≈ 90.6, olmOCR-Bench ≈ 78.5 (same family).
- **Russian**: **native RU support**; Cyrillic alphabet and Cyrillic-script languages (ru, uk, bg, sr, mk) explicitly listed in the expanded language set.
- **Bbox**: grounding outputs `[[xmin,ymin,xmax,ymax]]`, excellent for document-region localisation but **not a structured document parser** — you'd have to wrap it.
- **Inference**: **llama.cpp MTMD (Oct 30, 2025)**, **Ollama**, vLLM (Qwen3-VL is supported). Q4_K_M runs on any 6 GB card.
- **Quant**: GGUF Q4_K_M down to IQ2_XXS available through bartowski / unsloth. mmproj always kept F16.
- **Verdict**: 🥇 if you need a *general* vision-LLM and want document OCR as one capability — this is the 4 B sweet spot. Only model with first-class **llama.cpp** + **Ollama** + **vLLM** + comprehensive Russian.

### 5. Chandra OCR 2 (4B FP16 / 5.3B MoE-style)

- **Primary**: olmOCR-Bench **85.9** (sub-categories: Old Scans Math 89.1, Tables 92.1, Multi-col 82.1, Long-Tiny 93.7); multilingual **77.8 % avg across 43 langs**; **Russian 85.5 %** (hosted API: 88.8 %). SOTA among non-flagship open models.
- **Layout / bbox**: HTML output where **every block is a `<div>` with `data-bbox` and `data-label`**. 15+ layout block types (text, section-header, table, form, equation-block, diagram, chemical-block, code-block, list-group, bibliography, page-header, page-footer, complex-block…). Mermaid for diagrams, structured JSON for charts.
- **Russian / Cyrillic**: **Russian 85.5 %** standalone, **Ukrainian 91.0 %** — strong on Slavic scripts, weaker on Arabic / Devanagari.
- **Inference**: **vLLM** (recommended), HuggingFace transformers (with care for padding tokenizer bug noted in v2.0).
- **Speed**: **2 pages/s on H100 with 96 concurrent requests**; on an RTX 5090, ≈ 18 GB VRAM needed BF16, **but 4.3 GB INT4 / 2.9 GB INT4-AWQ** drops cleanly onto a 6 GB card (one-paragraph-at-a-time; lores context). Confirmed by community discussion on RTX 5090.
- **License**: open (own repo license).
- **Verdict**: best raw olmOCR score under "small" bucket, with the best bbox-block semantic vocabulary, at the cost of needing aggressive quantisation.

### 6. dots.mocr (3 B)

- **Primary**: olmOCR-Bench **83.9 SOTA for OSS ≤3 B** (Elo 1104.4 on the OCR Arena leaderboard, 2nd only to Gemini 3 Pro); OmniDocBench v1.5 TextEdit **0.031 SOTA**, Read Order **0.029 SOTA**.
- **Layout / bbox**: outputs a JSON list of `{"bbox": [x1,y1,x2,y2], "category": ..., "text": ...}` for 11 categories (Caption, Footnote, Formula, List-item, Page-footer, Page-header, Picture, Section-header, Table, Text, Title). Reading-order sorted. **Markdown output combines**.
- **Multilingual**: 17 languages including RU. **Cyrillic Latin-look-alike confusion noted in photographed docs** (MDPBench §5). On Digital-born RU scanned pages ≈ **79 %**.
- **Inference**: **vLLM** primary; **transformers (slower)** path works. FP8 quant available (`binedge/dots.mocr-FP8`, ~5 GB with vision tower kept BF16).
- **Quant**: vLLM FP8 weights ~5 GB. Community GGUF ports exist (~3.9 GB Q8_0). No official llama.cpp integration yet (model is Qwen2.5-derived, paths likely in qwen3-vl PRs).
- **Verdict**: best **document parsing as well as graphics-to-SVG** OSS model at 3 B. Strong RU on digital-born docs.

### 7. DeepSeek-OCR 2 (3 B)

- **Primary**: OmniDocBench v1.5 **91.09** (e2e SOTA among non-pipeline models); olmOCR-Bench **76.3** (DeepSeek-OCR v1 = 75.7, +1); Fox benchmark competitive.
- **Architecture**: 380 M SAM-base + 300 M CLIP-large visual encoder + DeepSeekMoE-3B decoder (≈570 M active per token). DeepEncoder V2 lets you dial visual tokens 256–1 120 per page. **VRAM ≈ 6.8 GB BF16.**
- **Russian**: DeepSeek tokenizer covers RU; no separate Russian benchmark, but reportedly strong (parallel with DeepSeek-V3 series). Photos of Cyrillic perform worse than digital-born (MDPBench 2026).
- **Bbox**: supports `<|grounding|>` prompt for bounding-box grounding; not strictly a layout-block emitter like PaddleOCR-VL/Chandra.
- **Inference**: **vLLM** (officially supported upstream, Oct 23 2025), **transformers**, **Ollama** (deepseek-ocr:3b). **llama.cpp** support via PRs #17400 (v1) and **#20975 (v2 merged)**.
- **Quant**: GGUF available (`sabafallah/`, `SandLogicTechnologies/`) — **BF16 5.88 GB → Q8_0 3.13 GB → Q4_K_M 1.95 GB**. Runs **Q4_K_M + mmproj F16 on a 6 GB card today**.
- **Verdict**: best ready-made **llama.cpp + GGUF end-to-end OCR** path for hardware-constrained environments. **Best for fully offline / air-gapped deployments**.

### 8. Infinity-Parser2 Flash (2B, Qwen3.5-2B)

- **Primary**: olmOCR-Bench **86.0** (Flash) / **87.6** (Pro 35B); OmniDocBench v1.6 **91.98** (Flash) / 93.95 (Pro); tables (PubTabNet) 92.41 (Flash).
- **Architecture**: shared with Pro (joint RL over 8 tasks). Flash is tuned for **3.68 × throughput** → 1 624 tok/s vs Pro's 441 tok/s.
- **Russian**: **Bilingual zh/en only**. Skip if RU heavy.
- **Inference**: **vLLM only** (per HF model card). No llama.cpp yet.
- **Quant**: not in HF repo at moment of writing. 2B BF16 ≈ 4 GB → fits 6 GB but tight on KV cache for 1k+ token pages.
- **Verdict**: 🥉 raw score champion at 2 B; skip until llama.cpp GGUF arrives unless you can deploy vLLM on RTX 3060+ with --max-model-len ≤ 16 384.

### 9. MinerU 2.5 / 2.5-Pro (1.2 B)

- **Primary**: OmniDocBench v1.6 92.98 (vanilla) / **95.75 Pro**; olmOCR-Bench 75.2. Decode **2.12 pages/s on A100** with vLLM, **1.70 pages/s on RTX 4090**. End-to-end throughput 2 337 tok/s.
- **Architecture**: coarse-to-fine (layout via downsampled image + per-crop recognition). NaViT-675 M + Qwen2-0.5 B. **The smallest end-to-end SOTA-class model**.
- **Russian**: **PP-OCRv5 Cyrillic update is integrated into the layout/line-detection modules of the pipeline** (separate from the VLM); Russian accuracy improved **+40 %** vs v0.
- **Bbox / layout**: layout blocks with reading order; structured `middle.json` + `content_list.json`; per-cell bbox for tables.
- **Inference**: **vLLM** primary; legacy SGLang; uses **mineru_vl_utils** package.
- **Verdict**: 🥉 if you already use the MinerU pipeline for non-OCR preprocessing, the 1.2 B model is the easiest upgrade. Per-page GPU memory is the lowest of any SOTA-class model.

### 10. NVIDIA Nemotron Parse 2.0 (0.9B)

- **Primary**: ParseBench **0.6391** (v1.2 0.5782); MOSCAR BoC-F1 **0.9102** (v1.2 was 0.4410); IndicVisionBench **0.7203** (was 0.0612); OmniDocBench Notes handwriting edit distance **0.3395** (was 0.9739).
- **Architecture**: ViT-H (C-RADIOv2) vision encoder + 10-layer mBART decoder, **9 000-token ceiling**, semantic classes (text, title, header, footer, table, formula…). Speculative-decoding PR open.
- **Russian**: MOSCAR includes Cyrillic; **+0.47 BoC-F1 jump** since v1.2 → strong. **The strongest Cyrillic/Slavic among vendor 0.9 B models** if benchmark provenance concerns are acceptable (benchmarks are NVIDIA-internal).
- **Bbox**: layout boxes + classes per region; visual grounding within each.
- **Speed**: **5 pages/s (Nemotron-Parse-TC)** and **4 pages/s (v1.1)** on H100 (~3 800 / 4 500 tok/s respectively).
- **Inference**: **vLLM** (PR open to enable speculative decoding with auxiliary head); Docker + NIM containers shipped.
- **Verdict**: best **Cyrillic + Indic + CJK** coverage per byte of weights for a vendor-grade document specialist. Skip if you only need EN/ZH.

### 11. olmOCR 2 (7B FP8)

- **Primary**: olmOCR-Bench **82.4** (FP8 ≈ BF16 with no quality loss); up from 68.2 in v0.1 (Feb 2025).
- **Architecture**: Qwen2.5-VL-7B-Instruct → fine-tuned with RLVR (binary unit-test rewards) → souped checkpoints.
- **Russian**: tagged **English-only** by AllenAI; not advised for RU.
- **Inference**: vLLM (AllenAI's own `olmocr` toolkit), 3 400 tok/s on H100 FP8.
- **Quant**: **FP8 official** (`allenai/olmOCR-2-7B-1025-FP8`). On 6 GB you'll need INT4 + very tight context; on 12 GB FP8 works.
- **Verdict**: 🥉 excellent English-only generalist; will not fit comfortably under 6 GB for production Russian OCR.

### 12. GOT-OCR 2.0 (0.58 B, StepFun)

- **Primary**: Fox PDF OCR ≈ SOTA-class on word-level metrics; olmOCR-Bench (legacy) ≈ 48; **0.58 B params**.
- **Layout / bbox**: **interactive OCR by colour or coordinate region** (`spotting` mode). Supports OCR / formula / table / chart / sheet music / molecule. Markdown and LaTeX output. **Real line-level text spotting via coordinate prompt**.
- **Russian**: multilingual but EN/ZH focused training data; no public Russian benchmark.
- **Inference**: HF transformers pipeline; does **not** have llama.cpp GGUF (yet). Stable Python binding, but slow.
- **Verdict**: legacy specialty (formulas, sheet music, charts). Useful only if you need those and accept the benchmark gap.

### 13. GLM-4.6V / GLM-4.6V-Flash (9B / 106B)

- **Primary**: GLM family — function-calling multimodal generalist, 128 K context, document/figure reasoning.
- **Russian**: GLM tokeniser covers Slavic languages; not a "document parser" (no Markdown-from-image structure out-of-the-box; you'd prompt-engineer the structured layout).
- **Inference**: **vLLM, SGLang** official. **Ollama** for the Flash variant when quantised. 9B Fits in 6 GB only with heavy INT4 + small context.
- **Verdict**: generalist, **not a document OCR specialist**; included here to answer the prompt correctly, but **do not pick it as your OCR stack**.

---

## Cross-cutting findings

1. **The 0.9 B class is now the sweet spot.** All of GLM-OCR, PaddleOCR-VL-1.6, dots.mocr, Nemotron Parse 2.0, Surya 2 are within ~5–10 points of the strongest 7 B + 35 B models on OmniDocBench v1.5 / olmOCR-Bench — but they fit cleanly in 6 GB.
2. **Two-stage pipelines win on raw tables.** PP-DocLayout-V3 + a small VLM (PaddleOCR-VL / GLM-OCR) is still 2–4 points ahead of any end-to-end model on **Table TEDS** in the same parameter budget.
3. **Elo ranking on OCR Arena (March 2026)** still puts dots.mocr (#1 OSS) > Gemini 3 Pro on graphics reconstruction and second overall behind Gemini 3 Pro.
4. **Real 6 GB winners with first-party inference on small hardware**:
   - **llama.cpp / GGUF**: DeepSeek-OCR 2 (Q4_K_M = **1.95 GB**, includes mmproj), Qwen3-VL 4B (Q4_K_M = 2.5 GB + ~840 MB mmproj), PaddleOCR-VL-1.5 (community GGUF ~1.8 GB BF16, INT4 ≈ 1 GB), Surya OCR 2 (BF16 ≈ 1.4 GB). **All four have first-party GGUF + llama-server compatibility**.
   - **vLLM (one GPU 6 GB)**: Surya OCR 2 (officially supported), PaddleOCR-VL-1.5/1.6, GLM-OCR, dots.mocr FP8, MinerU 2.5, Chandra OCR 2 (INT4 only).
   - **Ollama**: DeepSeek-OCR v1 (deepseek-ocr:3b tag exists), Qwen3-VL 4B / 8B (community).
5. **Cyrillic-aware ranking**: Surya 2 > Chandra 2 > PaddleOCR-VL-1.5 ≈ dots.mocr > Qwen3-VL > Nemotron Parse 2.0 > DeepSeek-OCR 2 > GLM-OCR > GLM-4.6V.
6. **Bbox + line-level spotting**: **PaddleOCR-VL 1.5** has the cleanest line-level spotting prompt (`Spotting:`). Surya 2 uses a **separate text-line detector** (CRAFT-style). dots.mocr emits **region bboxes only**. Chandra 2 emits **block-level bboxes**. GOT-OCR 2 accepts **coordinate-driven region OCR**. DeepSeek-OCR / GLM-OCR / GLM-4.6V / Qwen3-VL emit **grounding bboxes** on demand.

---

## Deployment matrix (6 GB VRAM, single GPU)

| Model | Best fit on 6 GB | Setup notes |
|---|---|---|
| **Surya OCR 2** | pip install surya-ocr; uses vllm *or* llama-server | smallest end-to-end with RU benchmark; **best default**. |
| **DeepSeek-OCR 2** | `ollama run deepseek-ocr` *or* llama.cpp GGUF Q4_K_M | closest "drop-in" llama.cpp path. |
| **Qwen3-VL 4B** | `llama-mtmd-cli --hf unsloth/Qwen3-VL-4B-Instruct-GGUF:Q4_K_M` | best general VLM, very usable OCR. |
| **PaddleOCR-VL 1.5** | `paddleocr doc_parser --vl_rec_backend vllm-server` *or* llama.cpp GGUF + `--jinja` + chat template | needs chat_template + jinja flag on llama-server. |
| **GLM-OCR** | `vllm serve zai-org/GLM-OCR` | requires vLLM; no GGUF path yet. |
| **Chandra OCR 2** | `pip install chandra-ocr` with INT4-quantised weights | quality loss vs BF16; use A100 if quality matters. |
| **dots.mocr** | `vllm serve binedge/dots.mocr-FP8` | only ~5 GB; needs vLLM ≥ 0.20.1. |
| **MinerU 2.5** | `pip install 'mineru[vl]'` + `vllm/vllm-openai` | full two-stage pipeline; smallest end-to-end SOTA-class VLM. |
| **Nemotron Parse 2.0** | Docker NIM + vLLM speculative-decode PR | solid Russian/Cyrillic, vendor-restricted. |
| **Inf-Parser2 Flash** | vLLM only | wait for llama.cpp GGUF or stay on vLLM. |
| **olmOCR 2** | FP8 needs ~7 GB on H100; INT4 will fit 6 GB but with degraded English quality | not for RU. |

---

## Recommendation (committing to a single stack today on 6 GB)

- **Russian-heavy general document parsing** → **Surya OCR 2** (best RU score, first-party llama.cpp).
- **Bbox + line-level text spotting + tables + 109-language layout** → **PaddleOCR-VL 1.5** (Spotting prompt is unique, GGUF available).
- **Generalist with on-the-fly reasoning + OCR** → **Qwen3-VL 4B Q4_K_M** (native llama.cpp MTMD).
- **Pure speed / lowest VRAM / fully offline** → **DeepSeek-OCR 2 Q4_K_M** (1.95 GB, llama.cpp ready).
- **Highest-quality single-endpoint (no Russian)** → **GLM-OCR** (94.62 ODB, BF16, vLLM/SGLang/Ollama).
- **KIE-style extraction** → **GLM-OCR** (93.7 Nanonets-KIE) or Qwen3-VL-4B-Thinking (own reasoning loop).
- **SOTA enterprise-grade with bbox hierarchy + RU + scaling beyond 6 GB** → **Chandra OCR 2** (INT4) or **dots.mocr** (FP8) on 12 GB+ box.

---

## Notes / caveats

- olmOCR-Bench and OmniDocBench v1.5 are reported on **A100 / H100**; consumer GPU page/sec numbers are roughly half of those and depend heavily on page resolution (`<image>` token cap) and KV cache.
- Numbers like "ollmOCR-Bench 83.9" and "OmniDocBench v1.5 94.5" come from **inconsistent evaluations**: PaddleOCR-VL/Paddle team re-evaluated themselves against an updated leaderboard; some numbers are independent reproductions. Always cross-check vs `opendatalab/OmniDocBench` and the `allenai/olmocr` repo before committing.
- Several "n/a" entries mean the model **was not evaluated on that benchmark**, not that it cannot run it — many of these VLMs can be wrapped in `prompt-as-classifier` style and asked to parse.
- The "GLM-4.6V" entry is the **9B Flash**; the **106 B** member of the family exceeds 6 GB by ~20× and is not relevant here.
- For **mixed-script Russian+Kazakh+Tatar+Uzbek** pipelines (post-Soviet state documents), the best combination is **Surya 2** (RU/KK/TR) + **Qwen3-VL-4B** for arbitration. **PaddleOCR-VL 1.6** is the closest single-model solution thanks to its 109-language layout dictionary.
