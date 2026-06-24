# Model catalog — all 3 sources

Full catalog of the 3 model sources available in this opencode setup:
1. **opencode-go** (subscription, $10/mo) — primary, high-volume daily work
2. **opencode Zen free** ($0/token, "limited time") — read-only exploration backup
3. **openrouter free** ($0/token, authenticated) — heterogeneity backup

For opencode-go full model table + tier strategy, see `NOTES/OPENCODE-GO.md`.

## How to check models (canonical methods)

| Method | What it shows |
|---|---|
| `opencode models [provider]` | All models from configured providers as `provider/model`. Flags: `--refresh` (update cache from models.dev), `--verbose` (costs/metadata). |
| `/models` (TUI) | Interactive model picker, shows recommended models. |
| `https://opencode.ai/zen/go/v1/models` | opencode-go full list + metadata (JSON). |
| `https://opencode.ai/zen/v1/models` | opencode Zen full list + metadata (JSON). |
| `openrouter.ai/models?supported_parameters=tools&order=top-weekly` (+ `:free` filter) | OpenRouter current free list. Roster rotates. |
| Config format | `provider_id/model_id` (e.g. `opencode-go/glm-5.2`, `opencode/gpt-5.5`, `openrouter/qwen/qwen3-coder:free`) |
| models.dev | The AI SDK registry opencode uses for built-in provider/model names. |

## Source 1: opencode-go (subscription, $10/mo)

**Limits are dollar-based: $12/5hr, $30/week, $60/month.** Request counts are estimates — cheaper models allow more requests. No per-token cost. Best for high-volume daily work. 15 models including new MiniMax M3 + MiMo-V2.5-Pro.

Full model table + tier strategy: see `NOTES/OPENCODE-GO.md`.

**Tiers at a glance:**
- **Flagship (low freq, hard reasoning):** GLM-5.2, GLM-5.1, Qwen3.7 Max
- **Code-specialized mid (review, refactor):** DeepSeek V4 Pro, MiMo-V2.5-Pro, Kimi K2.7 Code, Kimi K2.6
- **General mid (exploration, daily work):** Qwen3.7 Plus (best value), Qwen3.6 Plus, MiniMax M3 (promo), MiniMax M2.7
- **Lightweight (high-volume mechanical):** DeepSeek V4 Flash, MiMo-V2.5

## Source 2: opencode Zen free (provider `opencode`, $0/token)

Provider ID: `opencode`. Model IDs: `opencode/<model-id>`. Pay-as-you-go per 1M tokens, but these 5 models are free for a limited time. Hosted in US. **All 5 may retain/use data during free period — OK for non-secret NixOS configs, NOT for secrets/keys.**

| Model ID | Strengths | Weaknesses | Use case |
|---|---|---|---|
| `opencode/big-pickle` | Stealth model, unknown base. Free. | Unknown capability. Data may be used to improve it. Could vanish. | Experimentation only. NOT for fleet config reliability. |
| `opencode/deepseek-v4-flash-free` | DeepSeek V4 Flash arch (284B total, 13B active MoE). 1M context. Fast. Strong reasoning+coding for $0. | Free-period only. Data retained. Weaker than V4 Pro. | **Read-only exploration backup** when opencode-go budget exhausted. 1M context good for repo-wide searches. |
| `opencode/mimo-v2.5-free` | MiMo V2.5 arch. Free. | Free-period only. Data retained. Lightweight tier. | High-volume mechanical tasks (grep/locate summaries) when opencode-go budget low. |
| `opencode/north-mini-code-free` | Cohere North. 30B sparse MoE (3B active). Agentic-optimized for OpenCode/SWE-Agent harnesses. | **Cohere terms — data may be retained. DO NOT submit confidential data.** Small active params. | Agentic exploration experiments. NOT for fleet config (Cohere retention + small model). |
| `opencode/nemotron-3-ultra-free` | NVIDIA Nemotron. Logged for security/improvement (not identity-linked). | **DO NOT submit confidential data.** Trial only. | Experimentation only. NOT for fleet config. |

**Ephemeral warning:** all 5 are "available for a limited time" — could disappear. Don't make fleet config depend on them. Use as commented swap options in agent files, not defaults.

**Zen paid models (NOT free) — for reference:** Claude Fable 5 ($10/$50), Opus 4.8/4.7/4.6/4.5 ($5/$25), GPT 5.5 ($5/$30), GPT 5.5 Pro ($30/$180), Sonnet 4.6/4.5 ($3/$15), Gemini 3.5 Flash ($1.50/$9), Gemini 3.1 Pro ($2/$12), GLM 5.1 ($1.40/$4.40), Kimi K2.6 ($0.95/$4), Qwen3.7 Max ($2.50/$7.50), Qwen3.7 Plus ($0.40/$1.60), DeepSeek V4 Pro ($1.74/$3.48), DeepSeek V4 Flash ($0.14/$0.28), Haiku 4.5 ($1/$5).

## Source 3: openrouter free (provider `openrouter`, $0/token, authenticated)

Provider ID: `openrouter`. Model IDs: `openrouter/<org>/<model>:free`. Rate limits: ~20 req/min, 50-1000 req/day (varies per model + provider-side). **Roster rotates** — always check `openrouter.ai/models?supported_parameters=tools&order=top-weekly` with `:free` filter for current availability.

**Selected free models for our use cases (not all 27+):**

| Model ID | Context | Strengths | Weaknesses | Use case for spectacle |
|---|---|---|---|---|
| `openrouter/qwen/qwen3-coder:free` | 262K-1M | **Strongest free coding model on OpenRouter.** 480B MoE, 35B active. Tool use, long-context repo reasoning. | Free-tier rate limits. Roster may rotate. | **Heterogeneity backup for nix-reviewer** when opencode-go DeepSeek V4 Pro budget exhausted. Code-reasoning tasks. |
| `openrouter/deepseek/deepseek-v4-flash:free` | 1M | 284B MoE, 13B active. Fast. Hybrid attention for long context. Strong reasoning+coding. Supports reasoning effort high/xhigh. | Free-tier rate limits. | **Heterogeneity backup for nix-explorer.** 1M context = good for repo-wide searches. |
| `openrouter/meta-llama/llama-3.3-70b-instruct:free` | 128K | Solid all-purpose, well-supported, reliable availability. | Weaker at coding than Qwen3 Coder / DeepSeek. | General-purpose fallback. Low priority for NixOS-specific work. |
| `openrouter/openrouter/free` (Free Models Router) | varies | **Auto-selects a free model matching request requirements** (tool calling, vision, etc). Zero setup. | Cannot control which model. Random from filtered pool. | Experimental heterogeneity — use when you don't care which free model answers. Not for reliability-critical fleet config. |

**Other notable free models (not selected, for reference):** DeepSeek R1 (free, 64K, reasoning/math), Qwen3 235B (free, 128K, coding), Qwen3 Next 80B A3B (free, fast MoE), Gemma 4 31B (free, 256K, multimodal), Llama 4 Scout (free, 10M context — largest free context), Laguna M.1 (Poolside, free in preview, coding agent), Owl Alpha (OpenRouter stealth, 1M context, $0).

## Routing strategy for spectacle

Per `NOTES/multi-agent-evaluation.md`: the real 2026 win is **model routing, not agent count** (Morph Router 4× cost reduction, polydev 38% cost matching Opus). Route by role:

### Final routing (implemented Jun 2026)

| Agent | Model | Source | Cost/session |
|---|---|---|---|
| plan | MiniMax M3 | opencode-go | $0.72 |
| build | DeepSeek V4 Flash | opencode-go | $0.15 |
| flagship | GLM-5.2 | opencode-go | $2.50 |
| plan-free | Nemotron 3 Ultra 550B | OpenRouter free | $0 |
| consultant | GLM-5.2 | opencode-go | $0.10 |
| reviewer | DeepSeek V4 Pro | opencode-go | $0.20 |
| explore | Nemotron 3 Ultra 550B | OpenRouter free | $0 |

**What changed from the initial concept:**
- **No `nix-` prefix** — agents are general names (plan-free, flagship, consultant, reviewer).
- **MiniMax M3 over Qwen3.7 Plus** — 3× promo enabled this. Will switch to Qwen3.7 Plus when promo ends.
- **Nemotron 3 Ultra 550B for free tier** — strongest free reasoning model on OpenRouter (550B MoE, 55B active, 1M context, no data retention). Replaces Zen free models (which have privacy caveats).
- **Zen free models unused** — privacy caveat (data retained during free period) makes them unsuitable even for NixOS configs without secrets. Only use manually if OpenRouter free is exhausted.
- **Theme of results:** conversational + strong reasoning mid-tiers. MiniMax M3 scores low coding benchmarks but high conversational ELO — fine for planning (plan asks questions). DeepSeek V4 Flash handles the actual coding/implementation.

### Tab cycle: plan → build → flagship → plan-free
### Escalation: plan/plan-free → Task tool → consultant (GLM-5.2, hidden)
### Reviewer: edit:deny, bash restricted (git diff*/nix eval*/nix flake check*), task:deny
### Explore fallback: /model switch to big-pickle/gpt-oss-120b/qwen3-coder

## Privacy

- **All Zen paid models:** US-hosted, zero-retention, no training use.
- **Zen free models (5):** data may be retained/used during free period. **OK for non-secret NixOS configs. NEVER use for secrets/keys.**
- **OpenAI APIs (via Zen):** retained 30 days.
- **Anthropic APIs (via Zen):** retained 30 days.
- **openrouter:** varies per underlying provider — check provider terms.
- **spectacle repo:** no secrets in tracked files (AGENTS.md discipline). Free-model data retention is acceptable for read-only exploration subagents.

## Deprecation dates (Zen, relevant)

- **GPT 5.2 Codex, GPT 5.1 Codex/Max/Mini, GPT 5 Codex** → July 23, 2026
- **Claude Sonnet 4** → June 15, 2026 (already deprecated)
- **GLM 5** → May 14, 2026 (already deprecated)
- **Claude Haiku 3.5** → Feb 16, 2026

## Related notes

- `NOTES/OPENCODE-GO.md` — opencode-go full model table + tier strategy
- `NOTES/multi-agent-evaluation.md` — multi-agent evaluation + model routing rationale
- `NOTES/awesome-opencode-catalog.md` — full catalog of opencode plugins/tools
