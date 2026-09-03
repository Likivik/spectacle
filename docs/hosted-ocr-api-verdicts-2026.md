# Hosted OCR API Verdicts — 2025/2026

Comparative research covering Google Document AI, AWS Textract, Azure Document Intelligence, Mistral OCR, Anthropic Claude vision, OpenAI GPT-5.x vision, Gemini 2.5/3 vision, vlm.run, Reducto, LlamaParse, Mathpix, Extend, and Tensorlake.

Every provider has at least one **Russian/Cyrillic accuracy limitation worth flagging** — pure English OCR pipelines behave very differently from multilingual ones. The biggest differentiators for our use-case (large Russian-language documents, structured outputs, line-level bboxes) are page-size ceilings, native bbox granularity, and price per 1k pages.

---

## 1. Google Document AI (Enterprise Document OCR)

- **Pricing (per 1k pages, 2026)**: Enterprise Document OCR **$1.50** (1–5M pages/mo, drops to **$0.60** above 5M). Layout Parser $10. Form Parser / Custom Extractor $30. OCR add-ons (math, language hints, font detection) **$6/1k**. Free first 1k pages/mo. Prebuilt Invoice/Expense parsers ~$10/1k with 10-page rounding.
- **Russian / Cyrillic**: Supports 50+ language hints including Russian (ISO `ru`). Cyrillic accuracy on clean scans is high; lower on handwriting/cursive.
- **Bbox**: Yes — `Layout` block exposes normalized bounding polygons + `boundingBox` on `Page`, per-line, per-word, per-token. Line-level geometry is well documented.
- **Tables**: Form Parser / Layout Parser returns cells with bbox + row/col structure. Independently benchmarked at ~**64.6% TEDS** on Reducto's RD-TableBench (the worst of the big-3 clouds).
- **Limits**: Sync 15 pages, async 30 pages per file (DocX); PDFs up to 200 MB / 30 pages synchronous by default. Quota increase requests supported.
- **Benchmarks**: Not in OmniDocBench v1.5/v1.6 directly. RD-TableBench: 64.6% TEDS. Generally considered the weakest of Big-3 for table extraction.
- **Verdict**: Cheapest of the Big-3, multilingual incl. Russian, mature bbox. Poor table extraction quality compared to peers. No practical "unlimited pages" mode — 30-page async ceiling unless you request a quota increase.

---

## 2. AWS Textract (DetectDocumentText / AnalyzeDocument)

- **Pricing (per 1k pages, 2026)**: DetectDocumentText **$1.50** (drops to **$0.60** above 1M). AnalyzeDocument Form/Table ~$50; AnalyzeExpense $10; AnalyzeID $5; Queries $15. (Source: Textract pricing page, mirroring Google's tiered structure.)
- **Russian / Cyrillic**: **No first-class Cyrillic support.** Officially supported printed languages are English, Spanish, German, French, Italian, Portuguese. Handwriting and Queries are English-only. AWS Bedrock Data Automation (BDA) broadened language coverage in 2025 but Textract itself did not.
- **Bbox**: Yes — `Geometry.BoundingBox` per line/word on `DetectDocumentText`. Tables and forms expose cell-level bboxes.
- **Tables**: Form and Table features are solid for clean structured forms. RD-TableBench: **80.9% TEDS** (better than Google, worse than Reducto/Azure).
- **Limits**: Synchronous ≤5 MB / 1 page; asynchronous ≤500 MB / up to 3,000 pages per StartDocumentAnalysis call (no practical page-count ceiling within that file size).
- **Benchmarks**: Not in OmniDocBench. RD-TableBench 80.9%.
- **Verdict**: Strong on AWS-native docs and tables, **not viable for Russian/Cyrillic production** without bolting on a Bedrock VLM fallback. Big-page support is excellent (up to 3,000 pages async). Recommend pairing with Claude Sonnet/Bedrock for Cyrillic.

---

## 3. Azure Document Intelligence (Read v4 / Layout)

- **Pricing (per 1k pages, 2026)**: Read / Layout **$1.50** standard, with commitment-tier discounts down to $0.45. Custom models, add-ons priced higher.
- **Russian / Cyrillic**: First-class support. Read model advertises 200+ languages including Russian; Layout and prebuilt models inherit this. Strong Cyrillic accuracy.
- **Bbox**: Yes — polygons (4-point `polygon`) per word/line/region/cell. Geometry returned in original image coordinate space.
- **Tables**: Tables with cells, row/col spans, and bounding polygons. RD-TableBench: **82.7% TEDS** (best of the Big-3, second to Reducto). Also reports 88.1% F1 on Tensorlake's benchmark — second to Tensorlake.
- **Limits**: S0 tier — **max 2,000 pages per request**, max file size **500 MB**, ~15 analyze transactions/sec default (adjustable). F0 free tier processes only first 2 pages.
- **Benchmarks**: Not in OmniDocBench directly. RD-TableBench 82.7% TEDS. Strong all-round doc-AI contender.
- **Verdict**: Best Big-3 for Russian + tables + bboxes. Hard ceiling of 2,000 pages per request — that's the upper bound for any single Azure call. Enterprise OCR accuracy on Cyrillic is the closest peer to Mistral among Big-3.

---

## 4. Mistral OCR (OCR 4 / OCR 4.1)

- **Pricing (per 1k pages, 2026)**: OCR 4 **$4** (Batch API 50% off → $2). Mistral Document AI annotations (structured extraction + bboxes) **$5/1k**. OCR 4.1 same list.
- **Russian / Cyrillic**: Native and explicitly called out as a strength. Mistral's own multilingual eval shows OCR 4 leading in "Eastern European" language group including Russian. Cyrillic accuracy is high.
- **Bbox**: Yes — **paragraph-level bbox extraction** + structural block labels (title, table, equation, signature) + inline confidence scores. Returned in normalized `xywh` plus coordinates per block.
- **Tables**: Markdown-rendered tables with structural block label. OmniDocBench v1.6 Table TEDS for Mistral OCR is **76.78%** (specialized-VLM category); overall **85.66**. CodeSOTA mirrors show OCR 3/2512 at ~70–80% TEDS. Solid but not the top of the table-leaderboard.
- **Limits**: 50 MB file size (PDF). No hard public page-count limit per request, but quality and latency scale with page count; large jobs typically chunked client-side.
- **Benchmarks**: OmniDocBench v1.6 — **85.66 overall** (Text Edit 0.097, Table TEDS 76.78, Formula CDM 89.91). Reducto's RD-TableBench shows Mistral above AWS Textract/Google but below Azure.
- **Verdict**: Best price/quality for **Russian + structured output + bbox** among non-agentic parsers. Paragraph-level bbox granularity is coarser than Reducto's word/line. Cheap batch mode halves cost. Recommended as the default "good and cheap" Cyrillic OCR.

---

## 5. Anthropic Claude vision (Opus 4.8 / Sonnet 5 / Haiku 4.5)

- **Pricing (per 1k pages, 2026, derived from per-token)**: Opus 4.8 ~**$32**, Sonnet 5 ~**$19** (intro $13 through Aug 2026), Sonnet 4.6 ~$16, Haiku 4.5 ~**$5.31**. Includes image tokens + ~750 transcription output tokens per page.
- **Russian / Cyrillic**: First-class (multilingual LLM). One of the strongest Russian OCR engines of the VLM cohort when used on full-resolution images.
- **Bbox**: Yes — Claude **explicitly supports pixel-coordinate bbox output**, including for tables, form fields, charts. Use pixel coordinates (not normalized to 0–1000) and pre-resize so coordinates map back 1:1. PDF document blocks are rasterized server-side and coords cannot be relied on for raw PDFs; you should rasterize yourself.
- **Tables**: Strong reasoning over complex tables; Claude is the best VLM for understanding nested structure.
- **Limits**: **≤100 pages per request** with vision enabled (≤32 MB total). On 1M-token-context models (Sonnet 5, Opus 4.8) the page ceiling rises to **600 pages** — the highest single-request page limit of any LLM vision API. Images ≥1568 px edge auto-downscaled on standard tier (Haiku 4.5, Sonnet 4.6) → 1,560 visual tokens. High-res tier (Opus 4.8, Sonnet 5) keeps full 2,576 px edge / 4,784 visual tokens.
- **Benchmarks**: OmniDocBench v1.5 — **Claude Fable 5: 89.8%**, Opus 4.8: **87.9%**. Among the top non-specialized VLMs (behind Gemini 3 Pro/Flash and Kimi K2.5).
- **Verdict**: Best **bbox-quality + reasoning** combination. Premium price (~$5–32 per 1k pages). Use Opus 4.8 / Sonnet 5 on hard Cyrillic tables/handwriting; Haiku 4.5 for clean high-volume pages if you accept downscaling. No code-friendly "line bbox" — coordinates are whatever you prompt for.

---

## 6. OpenAI GPT-5.x vision (GPT-5, GPT-5.4, GPT-5.5, GPT-5.6 family)

- **Pricing (per 1k pages, 2026, derived)**: GPT-5.4-nano **~$1.67** (Batch ~$0.84 — **first LLM under cloud-OCR pricing**), GPT-5.4-mini **~$5.19**, GPT-5.4/5.6-terra **~$16.45**, GPT-5.5/5.6-sol **~$32.90**, pro models ~$197.
- **Russian / Cyrillic**: First-class multilingual.
- **Bbox**: Yes — request `[x_min, y_min, x_max, y_max]` in a fixed 0..999 normalized grid. Use `detail="original"` for dense scans and Code Interpreter for crop-and-rerun localization. Coordinates are approximate (VLM-style), not pixel-perfect OCR geometry.
- **Tables**: Strong on reasoning over tables; weaker than specialized parsers on dense, structured tables.
- **Limits**: 50 MB request cap (Files API lifts this). Patch budget 2,500/10,000 per image depending on model. Tier 1 rate limit 500 RPM / 500k TPM. Image detail "auto" is the safe default.
- **Benchmarks**: OmniDocBench — GPT-5.2 at **86.59** (Text Edit 0.114, Table TEDS 82.95, Formula CDM 88.21). GPT-5.5/5.6 higher (87.5–89.4). GPT-5.4 Mini/Mid families competitive with Gemini 3 Pro. GPT-4o (legacy) at 75.02.
- **Verdict**: Best **cost/accuracy frontier for VLM-style OCR** when reasoning is the bottleneck. Nano model + Batch API is the cheapest serious OCR endpoint on the market. Bbox is fine for UX highlighting but not pixel-accurate OCR geometry.

---

## 7. Google Gemini 2.5/3 vision (Gemini 3 Pro, Gemini 3 Flash, 2.5 Pro)

- **Pricing (per 1k pages, 2026, derived)**: Gemini 3 Pro — **$1.25/M input** (≤200k), $2.50 (>200k); output $10–15/M. For an OCR-heavy page this is roughly $5–25 per 1k pages depending on prompt size. Gemini 3 Flash cheaper. PDF/image tokens billed at image rate.
- **Russian / Cyrillic**: First-class multilingual VLM. Strong Russian accuracy.
- **Bbox**: Yes via prompt (normalized coords). Native Google OCR/Document AI integration in Drive pipeline provides proper line-level bboxes when used through that path; raw Gemini multimodal output gives approximate coords only.
- **Tables**: Strong on structured content; Gemini 3 Pro/Flash lead the OmniDocBench general-VLM leaderboard.
- **Limits**: **3,000 files per prompt, 3,000 pages per file, 50 MB per file (PDF)** for Cloud Storage / API path. Inline upload 20 MB / 7 MB (Studio). Files API 2 GB per file. 1M token context, 64k output. OCR for scanned PDFs **not enabled by default** — must opt in.
- **Benchmarks**: OmniDocBench v1.6 — Gemini 3 Pro **92.91**, Gemini 3 Flash **92.62** (specialized-VLM tier parity). v1.5 leaderboard: Gemini 3 Pro 90.17 / 88.03 (Gemini 2.5 Pro). Top general-VLM scores.
- **Verdict**: **Best OCR accuracy on OmniDocBench among general VLMs in 2026**. Large pages (3,000 per file) and 3,000 files per prompt. Use Gemini 3 Pro for highest-accuracy Russian OCR; Flash for cost efficiency. Default Gemini multimodal bbox is approximate — for production line-level bboxes, route through Document AI or use grounding.

---

## 8. vlm.run

- **Pricing (per 1k pages, 2026)**: OCR + layout — **$10/1k** (orion-2:fast), **$40/1k** (orion-2:pro). Grounding +$1/1k. Token-billed extraction on top. 50-page OCR + extract ≈ $0.50 + tokens.
- **Russian / Cyrillic**: VLM-based; general multilingual support; published Cyrillic/Russian benchmark numbers not available — relies on the underlying VLM (mostly Florence-2, GLM-OCR, dots.mocr, DeepSeek-OCR-2 via the VLM Run Gateway).
- **Bbox**: Yes — normalized `xywh` per field, multi-page supported, with `_metadata.bboxes[].page` and confidence scores. Layout detection returns per-element xywh.
- **Tables**: Layout detection via the structured outputs API surfaces headers, tables, lists, figures, paragraphs.
- **Limits**: No hard published page limit per request (driven by token budget). Files uploaded via URL or Files API.
- **Benchmarks**: Indirect via its model catalog. When gateway is used with GLM-OCR / dots.mocr / DeepSeek-OCR-2, results track those models (94.35 / 90.77 / 90.25 on OmniDocBench v1.6).
- **Verdict**: **Cheapest "agentic OCR" wrapper** if you want bbox + grounding at ~$10/1k pages (fast tier). Best fit when you want a simple API around open-weight OCR models (PP-OCRv6, GLM-OCR, DeepSeek-OCR-2). Russian support inherits the open-weight model you pick.

---

## 9. Reducto

- **Pricing (per 1k pages, 2026)**: Standard parse **$15** (1 credit/page). Complex pages (VLM-enhanced, agentic) 2 credits → $30. Deep Extract Beta $60/1k pages + $0.125/1k fields. 15k free credits one-time. Bbox-extraction enabled by default.
- **Russian / Cyrillic**: First-class. Multilingual OCR system supports Russian + Cyrillic-family languages explicitly (Ukrainian, Bulgarian, Belarusian, Serbian, Macedonian).
- **Bbox**: Yes — **word-level and line-level** OCR data with bounding boxes, confidence, rotation. Normalized coordinates (fraction of page). `/cite` endpoint returns bbox for arbitrary text query. Layout bounding boxes via extraction output.
- **Tables**: SOTA on tables. RD-TableBench (Reducto-run, open data): **90.2% TEDS** — **the highest among major hosted OCR APIs**, beating Azure 82.7, AWS Textract 80.9, Google 64.6. Deep Extract achieves 99–100% field accuracy on 225-doc LongExtractBench.
- **Limits**: Per-page credits; complex docs cost 2–4× standard. No explicit page-count cap beyond per-call rate limits. Production-tested on docs up to 11,000 pages.
- **Benchmarks**: RD-TableBench 90.2% TEDS. LongExtractBench 99.6% recall on 225 audited long documents. Not in OmniDocBench directly (commercial).
- **Verdict**: **Best table extraction + line-level bbox + Russian combination**. Highest-cost hosted option at scale. If table accuracy is the bottleneck, Reducto is the answer.

---

## 10. LlamaParse (LlamaIndex)

- **Pricing (per 1k pages, 2026)**: Fast **$1.25**, Cost-effective **$3.75**, Agentic **$12.50**, Agentic Plus **$56.25**. Structured extraction stacks parse+extract tiers, $7.50–$75 per 1k pages. 10k free credits/month, renews. 1,000 credits = $1.25.
- **Russian / Cyrillic**: Supports `language="ru"` (ISO 639-1) per docs. Cyrillic handled; in practice, OCR on scanned Cyrillic PDFs has historically needed `gpt4o_mode=True` or Agentic tier — non-agentic modes sometimes silently fall back to English.
- **Bbox**: Yes — element-level metadata with page numbers, node types, **bounding boxes for traceability**. Turbo (preview) explicitly does **not** produce granular bboxes.
- **Tables**: Returns clean Markdown tables with merged cells/multi-line headers. Cost Optimizer routes simple pages to cheaper tier automatically.
- **Limits**: 130+ file types, including PDF/DOCX/PPTX/XLSX. Cached 48h. Free tier has 5 concurrent jobs (Starter/Pro). Pages-per-file limits not publicly documented; large books (1,000+ pages) routinely tested.
- **Benchmarks**: Not in OmniDocBench. Databricks OfficeQA Pro: LlamaParse Agentic 92.1% accuracy at $0.0125/page (Pareto frontier). Cost-effective tier 53.4% at $0.00375/page. RealDoc-Bench internal comparisons rank it ahead of Azure DI / Reducto / AWS Textract per dollar.
- **Verdict**: Strong agentic document parsing with **good Russian support at Agentic tier**. Cost-effective tier is the cheapest option with markdown output. Free tier that renews monthly is unique. No published hard page cap per call.

---

## 11. Mathpix (Convert API v3)

- **Pricing (per 1k pages, 2026)**: PDF service `v3/pdf` — **$5/1k** (0–1M pages), **$3.50/1k** above 1M. Image API `v3/text` — **$2/1k** (0–1M), **$1.50/1k** above. Strokes (digital ink) per-session. Async Files API **$1.50/1k** up to 30M, then $1.
- **Russian / Cyrillic**: Officially supports **28 languages** including Latin and Cyrillic. Cyrillic text OCR is reliable; STEM/math content (Cyrillic academic papers) works. Some users report "non-English math (e.g. Russian or Chinese)" as a weakness in mixed-language documents.
- **Bbox**: Yes — **per-word and per-line contour** as list of (x,y) pairs, axis-aligned in `[TL, TR, BR, BL]` order. Pixel coordinates of original image. `line_data` returns geometry for diagrams/charts/figures.
- **Tables**: Dedicated Table OCR support (return-as-html / return-as-md). Mathpix Markdown (MMD) format for full documents.
- **Limits**: **PDF processing 500 pages/month on free tier**. Paid plans raise the cap. v3/pdf API request limit per call is file-size driven, not page-count driven. Files API for large batch jobs.
- **Benchmarks**: OmniDocBench v1.5 — **80.11** overall, **0.168 text edit**, formula CDM 89.95, table TEDS 70.03. Not a leader on table TEDS (specialized OCR models like PaddleOCR-VL hit 92–94% TEDS), but best-in-class on STEM content.
- **Verdict**: **Best-in-class STEM / formula OCR**; only realistic option when documents contain complex math, chemistry diagrams, or scientific notation. Russian works for general text but math in Russian is weaker. 500-page/month free cap and per-page pricing make it expensive for general OCR.

---

## 12. Extend

- **Pricing (per 1k pages, 2026)**: Performance Parse **$25** (2 credits × $0.0125), Light Parse **$6.25**, Extract **$37.50** (3 credits/page). Scale plan halves per-credit rate ($0.01/credit). 10k free credits on PAYG. Surcharges: agentic text/table correction +$12.50/1k.
- **Russian / Cyrillic**: Multilingual supported. Performance Parse recommended over Light for non-Latin languages; Light Parse explicitly is for Germanic/Latin-family languages.
- **Bbox**: Yes — included on all plans. Left/top/right/bottom coordinate structure on extracted fields; advanced bounding boxes extend coverage to enum/number/boolean/null fields. Per-chunk metadata.
- **Tables**: Advanced table parsing (Performance) handles merged cells, multi-line headers, complex spreadsheets; Advanced Excel parsing billed per cell.
- **Limits**: **2,000+ page support** on all plans. 35+ file types. Synchronous Parse endpoint with chunked outputs.
- **Benchmarks**: RealDoc-Bench — Light Parse 90.5% accuracy at $0.00625/page (first among non-agentic). Databricks OfficeQA Pro — Light Parse 54.9% (first non-agentic). Performance Parse 95.7% at $0.020 (Pareto frontier).
- **Verdict**: Excellent price/accuracy for high-volume multilingual parsing when you don't need agentic reasoning. **2,000+ page support** is explicitly advertised. Performance tier for Cyrillic; Light tier for Germanic/Latin text-heavy.

---

## 13. Tensorlake (Document Ingestion API)

- **Pricing (per 1k pages, 2026)**: Pro plan $500/mo with **85,000 free pages** then $6/1k. Enterprise down to $2/1k. Base OCR $3/1k post-Feb 2026 (was $6 pre-launch). Summarization & structured extraction $4/M tokens (~1¢/page add-on).
- **Russian / Cyrillic**: Supported via its OCR models (model01/02/03, plus optional Gemini 3 backend). Russian accuracy solid.
- **Bbox**: Yes — bounding boxes for every fragment, including **table cells** with `table_cell_grounding` option. Cross-page header detection, page-level classification, signature/strikethrough/strike options.
- **Tables**: Strong — claims highest benchmark score in its own head-to-head: **91.7% F1** on enterprise document perf (100 pages), TEDS 86.79%. **56.2% TEDS on OCRBench v2** (claimed best-in-class for document reading order + structure).
- **Limits**: No hard page cap mentioned; chunking strategy is configurable (none/page/section/fragment). Uses Firecracker microVMs; can handle large documents via chunking. 5M-per-project ceiling. Async queue with webhook completion.
- **Benchmarks**: Self-reported — 91.7% F1 / 86.79% TEDS, beating Azure 88.1 F1, AWS Textract 88.4 F1, Gemini 89 F1 (their own run). Independent RD-TableBench scoring not yet published.
- **Verdict**: Strong **table + bbox + reading order** combination. Multi-OCR-backend (Azure DI, AWS Textract, Gemini, or own DotsOCR) gives flexibility. Enterprise pricing down to $2/1k. No practical per-file page cap; large docs handled via 25-page chunking when using Gemini backend.

---

# Cross-cutting observations

## A. Cyrillic / Russian support — summary

| Provider | Native Cyrillic | Quality |
|---|---|---|
| Mistral OCR 4 | **Yes (first-class)** | High; explicitly evaluated |
| Azure Document Intelligence | **Yes** | High |
| Google Document AI | **Yes (50+ language hints)** | High on clean scans |
| Reducto | **Yes (multilingual 60+ langs)** | High; line bbox |
| Mathpix | **Yes (28 langs incl. Cyrillic)** | High for general text; weaker for Cyrillic math |
| Extend | **Yes (Performance tier for non-Latin)** | High |
| Tensorlake | **Yes (via backend choice)** | High |
| LlamaParse | **Yes (`language="ru"`)** | Good at Agentic tier |
| Claude vision | **Yes (VLM multilingual)** | Excellent (Opus/Sonnet) |
| OpenAI GPT-5.x | **Yes** | Strong (5.4+) |
| Gemini 3 vision | **Yes** | Excellent |
| vlm.run | **Yes (inherits VLM)** | Tracks chosen model |
| **AWS Textract** | **NO** | Not supported — fallback required |

**AWS Textract is the only major provider without Cyrillic support.** For Russian documents on AWS, pair Textract with Bedrock Claude.

## B. Bbox granularity

| Granularity | Providers |
|---|---|
| **Word + line pixel coords** | Reducto, Mathpix (contour), Google DocAI, Azure DI, AWS Textract (DetectDocumentText) |
| **Paragraph/block + structural labels** | Mistral OCR 4 (paragraph-level + block types), Tensorlake (per fragment), Extend (extracted fields) |
| **Prompt-driven normalized coords** | Claude vision, OpenAI GPT-5.x, Gemini 3 vision (approximate), vlm.run (via grounding API) |
| **Element-level metadata + bbox** | LlamaParse (excludes Turbo preview) |
| **Per-cell table bboxes** | Tensorlake, Azure DI, Google DocAI, Reducto, AWS Textract |

If you need **production-grade line/word bboxes for Russian docs**, the right picks are: **Reducto, Mistral OCR 4, Google Document AI, Azure DI**. Mathpix adds word-contour but is STEM-focused.

## C. Pricing per 1,000 pages (lowest published rate per provider)

| Provider | Cheapest OCR tier ($/1k pages) | Notes |
|---|---|---|
| Google Document AI | **$1.50** | $0.60 above 5M/mo |
| AWS Textract | **$1.50** | $0.60 above 1M/mo |
| Azure Document Intelligence | **$1.50** | Down to $0.45 commitment tier |
| Mistral OCR 4 | **$4.00** | Batch: $2/1k |
| OpenAI GPT-5.4-nano (Batch) | **$0.84** | First LLM under cloud-OCR pricing |
| OpenAI GPT-5.4-nano (list) | $1.67 | |
| LlamaParse Fast | $1.25 | Spatial text only, no markdown |
| LlamaParse Cost-effective | $3.75 | Adds markdown |
| LlamaParse Agentic | $12.50 | |
| vlm.run Fast | $10 | $0.01/page |
| vlm.run Pro | $40 | $0.04/page |
| Reducto Standard | $15 | Complex pages 2–4× |
| Reducto Deep Extract | $60 | + $0.125/1k fields |
| Extend Light Parse | $6.25 | Germanic/Latin best |
| Extend Performance Parse | $25 | Multilingual strong |
| Tensorlake | $6 (Pro) / $2 (Enterprise) | + ~$1/1k for extraction |
| Claude Haiku 4.5 | $5.31 | Vision downscaled to 1,560 tokens |
| Claude Sonnet 4.6 | $15.93 | |
| Claude Sonnet 5 | $19.39 (intro $13) | High-resolution tier |
| Claude Opus 4.8 | $32.32 | |
| Mathpix v3/pdf | $5 (then $3.50) | $1.50 Files API async |
| Gemini 3 Pro | ~$5–25 derived | Token-billed |

## D. Page-size limits

| Provider | Per-request page ceiling | File size | Notes |
|---|---|---|---|
| **Claude vision (1M ctx models)** | **600 pages** | 32 MB | Best LLM ceiling |
| **Gemini 3 Pro / Flash** | **3,000 pages / file, 3,000 files / prompt** | 50 MB (API), 20 MB inline, 2 GB Files API | **Largest practical limit among VLMs** |
| AWS Textract async | **3,000 pages** | 500 MB | No practical limit within file size |
| Azure Document Intelligence | 2,000 pages | 500 MB | S0 tier |
| Google Document AI | 30 pages async (default) | 200 MB | QIR to raise |
| Mistral OCR 4 | No hard limit published | 50 MB | Chunked client-side |
| Reducto | No hard cap; 11k pages production-tested | — | Per-page credits |
| LlamaParse | No hard cap published | — | Tested on 1000+ page books |
| Mathpix | 500 pages/month free | — | Paid plans much higher |
| Extend | **2,000+ pages** | — | Advertised |
| Tensorlake | No hard cap; chunks to 25 pages per Gemini call | — | Multi-backend |
| vlm.run | No hard cap published | — | Token-budget driven |
| GPT-5.x vision | 50 MB / token-budget | Files API lifts | Image patch-budget limits |
| Claude Haiku / Sonnet 4.6 | 100 pages | 32 MB | Sub-1M context models |

## E. OmniDocBench scores (overall / table TEDS)

From OmniDocBench v1.6 (April 2026 leaderboard):

| Provider | Overall | Table TEDS | Formula CDM |
|---|---|---|---|
| PaddleOCR-VL-1.6 (specialized) | **96.34** | 94.76 | 97.53 |
| Gemini 3 Pro | 92.91 | 89.15 | 95.99 |
| Gemini 3 Flash | 92.62 | 89.29 | 95.16 |
| GPT-5.2 | 86.59 | 82.95 | 88.21 |
| Mistral OCR | 85.66 | 76.78 | 89.91 |
| Mathpix | 80.11 (v1.5) | 70.03 (v1.5) | 89.95 (v1.5) |
| GPT-4o | 75.02 (v1.5) | 67.07 (v1.5) | 79.7 (v1.5) |

From Atlas v1.5 leaderboard (additional models):
- **Claude Fable 5** 89.8, **Opus 4.8** 87.9, **GPT-5.5** 89.4, **Kimi K2.5** 89.3, **GPT-5.6 Sol** 85.8, **GPT-5.2** 85.8, **Gemini 2.5 Pro** 88.0.

Specialized 2026 open-weight models (PaddleOCR-VL, GLM-OCR, MinerU2.5-Pro) are the new table-extraction SOTA but are not hosted API services in the same category.

## F. RD-TableBench scores (complex tables, hosted APIs)

| Provider | TEDS |
|---|---|
| **Reducto** | **90.2** |
| Azure Document Intelligence | 82.7 |
| AWS Textract Tables | 80.9 |
| Google Cloud Document AI | 64.6 |

---

## Recommendations by use case

1. **Cheapest Russian OCR at scale** → **Mistral OCR 4 (Batch) at $2/1k** or **Google Document AI at $1.50/1k** (or $0.60 above 5M/mo).
2. **Best bbox quality on Russian (word/line)** → **Reducto** or **Mathpix** (line contour) or **Azure DI** (polygon).
3. **Best table extraction overall** → **Reducto** (90.2% TEDS, line bboxes, multilingual).
4. **Best STEM / formula** → **Mathpix** (LaTeX output, contour bboxes).
5. **Best single-document ceiling (VLM)** → **Gemini 3 Pro** (3,000 pages/file, 3,000 files/prompt, 50 MB).
6. **No practical page-size limit** → **Gemini 3** (3,000 pp/file), **Claude Sonnet 5/Opus 4.8** (600 pp/req on 1M-ctx models), **AWS Textract** (3,000 pp async), **Reducto/LlamaParse/Extend/Tensorlake** (no published hard cap).
7. **Best cheap VLM with bbox UX** → **OpenAI GPT-5.4-nano Batch** ($0.84/1k) or **Claude Haiku 4.5** ($5.31/1k).
8. **Highest-accuracy single-page** → **Claude Opus 4.8 / Sonnet 5** with high-resolution tier + pixel-coord bbox prompt.
9. **Cyrillic at Big-3 scale** → **Azure Document Intelligence** (best Cyrillic + table accuracy among AWS/GCP/Azure; AWS Textract cannot do Cyrillic).
10. **For scientific papers in Russian** → **Mathpix** (best formula OCR; Russian text secondary).

---

## Provider verdict matrix

| Provider | Russian | Bbox (line-level) | Tables | $/1k pages | Page limit | Verdict |
|---|---|---|---|---|---|---|
| Mistral OCR 4 | ★★★★★ | ★★★★ (paragraph) | ★★★ | $4 (batch $2) | No hard cap | **Best default** for Cyrillic + structured |
| Reducto | ★★★★★ | ★★★★★ (word+line) | ★★★★★ (SOTA) | $15–$60 | Tested 11k pp | **Best table + bbox** |
| Azure Document Intelligence | ★★★★★ | ★★★★★ (polygon) | ★★★★ | $1.50–$0.45 | 2,000 pp | **Best Big-3 for Cyrillic + tables** |
| Google Document AI | ★★★★ | ★★★★ | ★★ | $1.50 ($0.60 vol) | 30 pp async default | Cheapest, weakest tables |
| AWS Textract | ✗ | ★★★★ | ★★★ | $1.50 ($0.60) | 3,000 pp async | **Skip for Russian**; great page limit |
| Mathpix | ★★★★ (text) | ★★★★★ (contour) | ★★★ | $5–$1.50 | 500 pp free tier | **STEM winner** |
| Claude Opus 4.8 | ★★★★★ | ★★★ (prompt) | ★★★★ | $32 | 600 pp (1M ctx) | **Best reasoning VLM** |
| Claude Sonnet 5 | ★★★★★ | ★★★ (prompt) | ★★★★ | $19 (intro $13) | 600 pp (1M ctx) | **Best VLM price/accuracy** |
| Claude Haiku 4.5 | ★★★★ | ★★ (downscaled) | ★★★ | $5.31 | 100 pp | Cheap VLM, downscaled |
| OpenAI GPT-5.4-nano | ★★★ | ★★ (prompt 0..999) | ★★ | $1.67 / $0.84 batch | Token-budget | **Cheapest serious VLM OCR** |
| OpenAI GPT-5.4 | ★★★★ | ★★★ (prompt) | ★★★★ | $16.45 | Token-budget | Strong VLM with bbox UX |
| Gemini 3 Pro | ★★★★★ | ★★★ (prompt) | ★★★★ | ~$5–25 derived | **3,000 pp/file** | **Largest page ceiling among VLMs** |
| Gemini 3 Flash | ★★★★ | ★★★ (prompt) | ★★★★ | Cheaper | **3,000 pp/file** | Top accuracy/cost in OmniDocBench |
| vlm.run | ★★★ | ★★★★ (xywh + grounding) | ★★★ | $10–$40 | Token-budget | Cheap wrapper for open-weight OCR |
| LlamaParse Agentic | ★★★★ | ★★★ (element-level) | ★★★★ | $12.50–$56.25 | 1k+ pp | Strong agentic parsing |
| LlamaParse Cost-effective | ★★★ | ★★★ | ★★★ | $3.75 | — | Cheapest markdown output |
| Extend Performance | ★★★★ | ★★★★ | ★★★★ | $25 | 2,000+ pp | High-accuracy multilingual |
| Extend Light | ★★ (Latin best) | ★★★★ | ★★★ | $6.25 | 2,000+ pp | Cheapest non-Latin OCR |
| Tensorlake | ★★★★ | ★★★★★ (per-fragment + cells) | ★★★★★ (91.7 F1) | $6–$2 | No hard cap | **Best reading order + table bbox** |

