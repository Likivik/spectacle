# OpenCode-Go models (subscription, $5 first month → $10/mo)

Low-cost subscription provider. No per-token cost — limits are dollar-based.
Config format: `opencode-go/<model-id>` (e.g. `opencode-go/glm-5.2`).

## How limits work

**Limits are DOLLAR-BASED, not request-based:**
- **$12 / 5 hours**
- **$30 / week**
- **$60 / month**

Request counts in the table below are **ESTIMATES** based on typical token usage.
Cheaper models (DeepSeek V4 Flash) allow more requests; expensive models (GLM-5.2)
allow fewer. The dollar budget is the real constraint.

**Fewer allowed requests = more powerful, expensive model.** Higher request limits
point to faster, cheaper, less intelligent models.

## How to check models

| Method | What it shows |
|---|---|
| `opencode models opencode-go` | All models from opencode-go. Add `--refresh` (update cache from models.dev), `--verbose` (costs/metadata). |
| `/models` (TUI) | Interactive picker, shows recommended models. |
| `https://opencode.ai/zen/go/v1/models` | Full list + metadata (JSON). |
| `https://opencode.ai/docs/go/` | Docs page with pricing + limits. |

## Full model table

Per 1M tokens (input / output / cached-read). Request estimates from opencode.ai/docs/go/.

| Model | Input/1M | Output/1M | Cached/1M | req/5hr | req/week | req/month |
|---|---|---|---|---|---|---|
| GLM-5.2 | $1.40 | $4.40 | $0.26 | 880 | 2,150 | 4,300 |
| GLM-5.1 | $1.40 | $4.40 | $0.26 | 880 | 2,150 | 4,300 |
| Kimi K2.7 Code | $0.95 | $4.00 | $0.19 | 1,350 | 4,630 | 9,250 |
| Kimi K2.6 | $0.95 | $4.00 | $0.16 | 1,150 | 2,880 | 5,750 |
| Qwen3.7 Max | $2.50 | $7.50 | $0.50 | 950 | 2,390 | 4,770 |
| Qwen3.7 Plus (≤256K) | $0.40 | $1.60 | $0.04 | 4,300 | 10,800 | 21,600 |
| Qwen3.7 Plus (>256K) | $1.20 | $4.80 | $0.12 | — | — | — |
| Qwen3.6 Plus (≤256K) | $0.50 | $3.00 | $0.05 | 3,300 | 8,200 | 16,300 |
| Qwen3.6 Plus (>256K) | $2.00 | $6.00 | $0.20 | — | — | — |
| DeepSeek V4 Pro | $1.74 | $3.48 | $0.0145 | 3,450 | 8,550 | 17,150 |
| MiMo-V2.5-Pro | $1.74 | $3.48 | $0.0145 | 3,250 | 8,150 | 16,300 |
| MiniMax M3 | $0.30 | $1.20 | $0.06 | 3,200 | 8,000 | 16,000 |
| MiniMax M2.7 | $0.30 | $1.20 | $0.06 | 3,400 | 8,500 | 17,000 |
| DeepSeek V4 Flash | $0.14 | $0.28 | $0.0028 | 31,650 | 79,050 | 158,150 |
| MiMo-V2.5 | $0.14 | $0.28 | $0.0028 | 30,100 | 75,200 | 150,400 |

**Notes:**
- **MiniMax M3** is NEW — currently gets 3× usage limits for a limited time per opencode.ai/go landing page.
- **MiMo-V2.5-Pro** is NEW — same pricing tier as DeepSeek V4 Pro (mid-tier code reasoning).
- Qwen3.7 Plus / Qwen3.6 Plus have a **long-context price jump** at >256K (3-4× cost).
- DeepSeek V4 Pro / MiMo-V2.5-Pro have the **cheapest cached read** ($0.0145) — good for agentic loops that re-read context.

## Tiers

### Flagship (low freq, hard reasoning)
**GLM-5.2 > GLM-5.1 > Qwen3.7 Max**

- **GLM-5.2 / GLM-5.1** (`880 | 2,150 | 4,300`): strictest limits = heaviest, most advanced flagship. Best for highly complex logic, reasoning, multi-step tasks. GLM-5 lineage hit 77.8% SWE-bench single-shot (arXiv:2602.15763).
- **Qwen3.7 Max** (`950 | 2,390 | 4,770`): just above GLM in allowed requests. Alibaba "Max" tier — elite coding, deep analysis, complex reasoning. Massive capability boost over "Plus" versions.

### Code-specialized mid (review, refactor)
**DeepSeek V4 Pro ≈ MiMo-V2.5-Pro > Kimi K2.7 Code > Kimi K2.6**

- **DeepSeek V4 Pro** (`3,450 | 8,550 | 17,150`): legendary for algorithmic thinking, mathematical logic, code synthesis. Excels at highly structured, technical tasks. Cheap cached read.
- **MiMo-V2.5-Pro** (`3,250 | 8,150 | 16,300`): NEW. Same pricing tier as DeepSeek V4 Pro. Solid balanced mid-tier for general agent workflows. Less track record than DeepSeek.
- **Kimi K2.7 Code** (`1,350 | 4,630 | 9,250`): premium specialized model for complex software engineering tasks. Tighter 5hr window than mid-tier but higher weekly/monthly volume.
- **Kimi K2.6** (`1,150 | 2,880 | 5,750`): previous Kimi code model. Fallback to K2.7 Code.

### General mid (exploration, daily work)
**Qwen3.7 Plus (best value) > Qwen3.6 Plus > MiniMax M3 (promo) > MiniMax M2.7**

- **Qwen3.7 Plus** (`4,300 | 10,800 | 21,600`): **best mid-tier value.** Highest req budget. "Punches way above its weight class" — inherits much of the advanced reasoning, instruction-following, and multilingual coding of the Max flagship tier.
- **Qwen3.6 Plus** (`3,300 | 8,200 | 16,300`): previous Qwen Plus generation. Still capable for data parsing + general logic, but behind 3.7 in raw reasoning.
- **MiniMax M3** (`3,200 | 8,000 | 16,000`): NEW, currently 3× usage limits promo. Excellent for creative writing, long-context conversational memory, human-like interaction. Lower on complex logic / code execution / rigorous step-by-step reasoning.
- **MiniMax M2.7** (`3,400 | 8,500 | 17,000`): previous MiniMax. Similar budget. Fallback to M3.

### Lightweight (high-volume mechanical)
**DeepSeek V4 Flash ≈ MiMo-V2.5**

- **DeepSeek V4 Flash** (`31,650 | 79,050 | 158,150`): lightweight speed-demon. Near-free. Highest req budget by far.
- **MiMo-V2.5** (`30,100 | 75,200 | 150,400`): lightweight, similar budget to DeepSeek V4 Flash.

## Strategy

The mid-tier gives **~4× more requests** than flagship:
- Qwen3.7 Plus (4,300) ÷ Qwen3.7 Max (950) ≈ **4.5× more prompts**
- DeepSeek V4 Pro (3,450) ÷ GLM-5.2 (880) ≈ **3.9× more prompts**

**Hybrid approach (recommended):**
1. **Mid-tier (Qwen3.7 Plus / DeepSeek V4 Pro)** for 80% of daily work: prototyping, drafting code, brainstorming, routine data parsing, exploration.
2. **Flagship (GLM-5.2 / Qwen3.7 Max)** for final error handling, complex math/logic, overall project architecture review.

### Performance gap: flagship → mid-tier

Roughly **15-25% on paper**, feels wider on highly complex multi-step tasks:
- **Hallucination on multi-step logic:** flagship completes a 10-step reasoning chain; mid-tier maintains accuracy until step 5-6, then mixes up details or takes shortcuts.
- **Context degradation:** mid-tier loses focus on massive files/long threads — remembers beginning + end, forgets middle constraints. Flagship maintains grasp across whole context window.
- **Code architecture vs snippets:** mid-tier excels at clean isolated scripts / standard debugging; flagship needed for system architecture design or multi-file refactors.

## Model IDs for opencode config

`opencode-go/<model-id>` — use `opencode models opencode-go` to confirm exact IDs. Common ones:
- `opencode-go/glm-5.2`
- `opencode-go/glm-5.1`
- `opencode-go/qwen3.7-max`
- `opencode-go/qwen3.7-plus`
- `opencode-go/deepseek-v4-pro`
- `opencode-go/deepseek-v4-flash`
- `opencode-go/kimi-k2.7-code`
- `opencode-go/mimo-v2.5-pro`
- `opencode-go/minimax-m3`

## Related notes

- `NOTES/models-catalog.md` — full 3-source catalog (opencode-go + Zen free + openrouter free)
- `NOTES/multi-agent-evaluation.md` — model routing strategy for this repo's agents
