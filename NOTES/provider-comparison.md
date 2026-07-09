# AI Provider Comparison — OpenCode Go Alternatives

Investigated Jul 2026. Context: replace OpenCode Go ($10/mo, ~$60 value) for
opencode local dev + Hermes agent on erebus (needs vision/OCR).

## TL;DR

| Provider | Best for | Cost | DS Flash | GLM-5.2 | Qwen 3.7 | Vision | OpenAI API | RU pay |
|---|---|---|---|---|---|---|---|---|
| **OpenCode Go** (current) | opencode CLI | $10/mo ($60 cr) | ✅ | ✅ | ✅ | ❌ limited | ✅ built-in | ❌ Stripe |
| **Command Code Provider** | API access, all models | $15/mo + PAYG | ✅ $0.14/$0.28 | ✅ $1.40/$4.40 | ✅ $0.40/$1.60 | ✅ Kimi/Claude/GPT | ✅ Dual OA+Anthropic | ❌ Stripe |
| **DeepInfra** | Cheapest DS Flash, no sub | PAYG, no sub | ✅ **$0.09/$0.18** | ❌ | ✅ $2.50/$7.50 | ✅ Qwen VL, Claude, GPT, Gemini | ✅ `/v1/chat/completions` | ❌ Stripe |
| **Synthetic** | True flat-rate sub | $1/day or **$30/mo** | ❌ none | ✅ GLM-5.2 | ❌ Qwen 3.6 only | ✅ Kimi K2.7 | ✅ `/v1/chat/completions` | ? |
| **Featherless Premium** | Unlimited requests, all OS | **$25/mo** | ✅ $0.14/$0.28 | ✅ $1.39/$4.40 | ✅ Qwen 3.7 Max | ✅ Kimi, Qwen VL | ✅ `/v1/chat/completions` | ❌ Stripe |
| **Neuralwatt PAYG** | Energy pricing, efficient | $5/kWh | ❌ none | ✅ $1.45/$4.50 | ❌ Qwen 3.6 | ✅ Kimi K2.7 | ✅ | ❌ |
| **Nous Portal** | Runs on OpenRouter | PAYG (OR) | ❌ via OR | ❌ | ❌ | ✅ Hermes 4 | ✅ OR pass-through | ❌ Stripe |

## Provider deep-dive

### OpenCode Go ($10/mo — current)

- Models: GLM-5.2, Qwen 3.7 Plus/Max, DS V4 Flash/Pro, Kimi K2.7 Code, MiniMax M3
- Built-in opencode CLI integration — custom endpoint config is hacky
- Vision: limited (only Kimi models on Go plan)
- Payment: Stripe — user paid once successfully but RU card uncertain long-term
- See `NOTES/OPENCODE-GO.md` for full model table

### Command Code AI (commandcode.ai)

**Plans:**
- **Go** ($1/mo, $10 credits): open-source only (DS Flash, GLM-5.2, Qwen 3.7+, Kimi w/ vision)
- **Pro** ($15/mo, $30 credits): open-source + premium (Claude, GPT, Gemini)
- **Provider** ($15/mo + PAYG): API access only, no CLI — for Hermes
- **Max 10×** ($100/mo, $150 credits): everything unlimited

**Models (open-source tier):**
| Model | Input/1M | Output/1M | Cache/1M |
|-------|----------|-----------|----------|
| DS V4 Flash | $0.14 | $0.28 | $0.0028 |
| DS V4 Pro (4× deal → $0.435/$0.87) | $1.74 | $3.48 | $0.0145 |
| GLM-5.2 | $1.40 | $4.40 | $0.26 |
| GLM-5.2 Fast | $3.00 | $10.25 | $0.50 |
| Qwen 3.7 Plus | $0.40 | $1.60 | $0.08 |
| Qwen 3.7 Max (2× deal → $1.25/$3.75) | $2.50 | $7.50 | $0.50 |
| Kimi K2.7 Code (vision) | $0.95 | $4.00 | $0.19 |
| MiniMax M3 (62.5% deal → $0.225/$0.90) | $0.60 | $2.40 | $0.12 |
| MiMo V2.5 Pro (99% deal → $0.435/$0.87) | $2.00 | $6.00 | $0.40 |

**Premium models:** Claude Fable/Opus/Sonnet/Haiku, GPT-5.5/5.4/5.4 Mini/5.3 Codex,
Gemini 3.5 Flash/3.1 Flash Lite — all with vision.

**API:** `https://api.commandcode.ai/provider/v1/chat/completions` (OpenAI)
or `.../provider/v1/messages` (Anthropic). Provider plan required.

**Catch:** Stripe only — no RU cards/SBP. CLI (`cmd`) is separate from API —
needs Pro plan for CLI + Provider plan for API = $30/mo.

### DeepInfra (deepinfra.com)

- Pure PAYG, no subscription
- **Cheapest DS V4 Flash anywhere: $0.09/$0.18 per 1M** (vs $0.14/$0.28 on OC Go/CC)
- DS V4 Pro: $1.30/$2.60, cache: $0.10/$0.018
- Has Claude, GPT, Gemini (all vision), Qwen 3.7 Max, Qwen VL (vision)
- **No GLM-5.2** — missing flagship model
- OpenAI-compatible API: `/v1/chat/completions`
- Custom model deployment (dedicated GPUs) available
- Standard/priority service tiers (priority = 1.5× cost)
- Stripe only — no RU cards

### Synthetic (synthetic.new)

- **Only true flat-rate subscription**: $1/day or $30/mo
- All included models unlimited (no token counting) — 500 req/5hr limit, 1 concurrent
- **Included models:** Kimi K2.7 Code (vision), GLM-5.2, MiniMax-M3, Nemotron 3 Super,
  GPT-OSS 120B, Qwen 3.6 27B, GLM-4.7 Flash
- **No DeepSeek models at all** — no Flash, no Pro
- **No Claude/GPT/Gemini**
- Embedding models (nomic-embed-text-v1.5) included free
- API: OpenAI-compatible
- All open-source, self-hosted models
- Good for: light use of GLM-5.2 + vision via Kimi at fixed $30/mo
- Bad for: daily DS Flash workload

### Featherless (featherless.ai)

- **Premium plan ($25/mo):** unlimited requests, 4 concurrent units, any model
- **Agent Standard ($100-200/mo):** agent sandboxes, 8 concurrent, 256K ctx
- 45,000+ models in catalogue (crowd-sourced from HuggingFace)
- **DS V4 Flash:** $0.14/$0.28 (same as OC Go)
- **GLM-5.2:** $1.39/$4.40
- **DS V4 Pro:** $1.60/$3.20
- Vision models: Kimi K2.7 Code, Qwen VL series
- OpenAI-compatible API: `/v1/chat/completions`
- Also has Hermes Agent docs — good for deployment reference
- Stripe only — no RU cards

### Neuralwatt (portal.neuralwatt.com)

- **Unique: energy-based pricing** — pay for GPU compute ($5/kWh), not tokens
- **Subscriptions:** Basic $20/mo (6 kWh), Standard $50/mo (16 kWh), Pro $100/mo (33 kWh)
- **Only 11 models:** GLM-5.2 (variants), Kimi K2.6/K2.7 Code, Qwen 3.5 397B, Qwen 3.6 35B
- **No DeepSeek at all**
- **No Claude/GPT/Gemini**
- Vision: Kimi K2.7 Code, Qwen VL
- Token pricing also available but expensive vs energy for efficient MoE models
- Good for: GLM-5.2-heavy workloads (MoE is very efficient on energy pricing)
- Bad for: DS Flash usage (not available)
- Stripe likely

### Nous Portal (portal.nousresearch.com)

- Runs on OpenRouter pass-through — 240+ models
- Models: Hermes-4-70B ($0.05/$0.20), Hermes-4-405B ($0.09/$0.37)
- Has Hermes Agent product (browser-use, FAL, firecrawl, krea, modal, audio)
- No fixed subscription — credit-based
- Stripe

## Hermes agent compatibility

All providers with OpenAI-compatible API work with Hermes agent.
Key considerations:

| Need | Best option |
|------|-------------|
| Vision/OCR (image → text) | Kimi K2.7 Code (all providers), Claude/GPT/Gemini (CC/DI) |
| Daily text (DS Flash) | DeepInfra ($0.09/$0.18 — cheapest), CC, Featherless |
| Heavy reasoning (GLM-5.2) | CC, Featherless, Synthetic ($30 flat), Neuralwatt (energy) |
| Flat-rate simplicity | Synthetic $30/mo (but no DS, no premium) |
| Cheapest combined | DeepInfra PAYG (DS Flash $0.09/$0.18 + Qwen VL for vision) |

## Payment methods

All major providers are US-based → Stripe → no Russian cards/SBP.
The user paid OpenCode Go once successfully — may have a non-RU card or
alternative method. For Russian providers see `NOTES/erebus-provision.md`
(Hubris, NeuralDeep, VseGPT, ZvenoAI).

## Raw cost comparison (DS Flash, 100K req/mo at ~$0.0003/req = $30/mo)

| Provider | Sub | Usage | Total/mo |
|----------|-----|-------|----------|
| DeepInfra | $0 | $30 | **$30** |
| OpenCode Go | $10 | covered by $60 cr | **$10** |
| Command Code (Go) | $1 | need $30 cr, $10 included → top up $20 | **$21** |
| Command Code (Provider) | $15 | $15 cr included, top up $15 | **$30** |
| Featherless Premium | $25 | unlimited | **$25** |
| Synthetic | $30 | unlimited (no DS though) | **$30** (no DS Flash) |
| Neuralwatt | $20-50 | depends on energy | ~$20+ |
