# LLM Subscription Provider Research — 2026-10-04

User profile: ~1850 req/day, ~198K avg input, ~70% cache reads, 97% GLM-5.3-Flash + 3% DeepSeek V4 Flash.
Roughly 55,500 req/month, ~3,300M fresh input + ~7,700M cached input + ~83M output tokens/month.

---

## 1) NeuralWatt (portal.neuralwatt.com)

**No material change to plans since Sept 10 2026.**
- Plans: Basic $20/2.35kWh, Standard $50/6.25kWh, Pro $100/13.33kWh, **new Max $200/28.57kWh** with $7/kWh overage. (Source: portal.neuralwatt.com/pricing, retrieved 2026-10-04.)
- Flex tier: 0.65× metered energy / 0.65× token price; requires streaming, may queue during peak. Same models, same cache. (Source: portal.neuralwatt.com/docs/guides/flex-tier.)
- Models GLM-5.3 (1M ctx, $1.45 in / $4.50 out / $0.14 cached per 1M) and DeepSeek V4.1 Flash (1M ctx, $0.15 / $0.60 / $0.02 per 1M) unchanged. **Speed lane** added on DeepSeek V4.1 Flash. (Source: portal.neuralwatt.com/models/glm-5.3 and /deepseek-v4.1-flash.)
- Energy per request, 64k–256k band: GLM-5.3 ~1.89 Wh, DS V4.1 Flash ~653.49 mWh.
- **Status:** One documented outage on **api.neuralwatt.com — 31 minutes on Sep 6, 2026** ("Down for 31 minutes"). 99.924% uptime 30-day. Status page last updated Sep 28, 2026 (Source: neuralwatt.betteruptime.com). No Sept/Oct incidents since.

**Estimated user cost at NeuralWatt:**
- Token mode: ~$6,232/mo (GLM-5.3 dominates — way worse than other providers).
- Energy mode: ~102.8 kWh/mo. Even **Max plan ($200 + ~74 kWh overage @ $7) ≈ $720/mo**; Flex (0.65×) ≈ $668/mo. (Pro plan + overage ≈ $771/mo.) — Roughly 2.5× cheaper than SC, similar to DevPass Pro.

---

## 2) Synthetic (synthetic.new)

**Major restructuring around Sept 26, 2026.** Old Standard $20/135req/5h and Pro $60/1,350req/5h plans **discontinued**.
- Current: **subscription pack = $30/mo ($1/day), 500 req/5h, 1 concurrent per model**, weekly $24 in API credits ($102/mo equiv). (Source: synthetic.new/pricing & synthetic.new/rate-limits, retrieved 2026-10-02.)
- Buy up to 5 packs ($150/mo) for higher limits.
- Lapsed users can re-subscribe at the current $30/mo rate — no Founder pricing remaining; only legacy Pro users kept "Founder's pack" with 200-msg limit.
- Auto-renew: managed by Stripe, default cancel-at-period-end. No long-term lock-in.
- Models: GLM-5.3-Flash **$0.15 in / $0.50 out / $0.04 cached per 1M**; DS V4.1 Flash $0.60 / $1.20 / $0.03 per 1M. (Source: synthetic.new/pricing?initial=usage.)
- Per docs: a typical GLM-5.3-Flash call costs ~0.1 request-equivalent against the 5h limit (10× cheaper than Kimi-K3).

**Verdict for user:** GLM-5.3-Flash via usage-based ≈ **$844/mo**; a single $30/mo pack covers ~5,000 req/month at GLM-5.3-Flash weight. To cover 55,500 req/mo the user needs ~10 packs ($300/mo) — but weekly $24 credits cap forces PAYG for the overage. **Best practical option = usage-based at ~$844/mo**, more expensive than NeuralWatt energy mode or DevPass Pro.

---

## 3) OpenCode Go (opencode.ai/zen/go)

**Major change Sept 28, 2026: added "Go Plus" tier.**
- **Go: $10/mo.** Go Plus: **$40/mo, higher limits** (announced 2026-09-28; Source: nitter.jaydenha.uk/opencode/status/2104548294718296064).
- Model lineup: 29–30 open-coding models including GLM-5.3-Flash, GLM-5.3, GLM-5.2, Kimi K3, K2.6, K2.7 Code, Qwen3.7+, 3.8 Max/Flash, DeepSeek V4/V4.1 Flash/V4 Pro, MiMo-V2.5/V2.6, MiniMax M3, Hy3/Hy4, plus closed: GPT 6 Luna, GPT 5.6 Luna, Grok 4.6/4.7. (Source: opencode.ai/docs/go/.)
- GLM-5.3-Flash: $0.15 in / $0.50 out / $0.03 cached per 1M. **Hard monthly $60 cap on Go / $180 on Go Plus.**
- DeepSeek V4 Flash: $0.15 off-peak / $0.60 cached read; peak 01–04 & 06–10 UTC doubles rates. (Source: tomrochette.com/agents/model-access/opencode-go/index.md, updated 2026-10-03.)
- DeepSeek retired original V4 Flash on 2026-09-10; V4.1 Flash serves that model name.
- Xiaomi retiring MiMo-V2.5/V2.5-Pro on 2026-10-21.
- DeepSeek ZDR agreement valid through 2026-10-31.

**HARD DISQUALIFIER for user:** GLM-5.3-Flash needs ~$767/mo at the user's volume, and the **$60 (Go) or $180 (Go Plus) hard cap caps the user at 4,342 or 13,026 requests/mo** — vs 55,500 needed. After cap, requests fall through to "free models" or Zen PAYG. **OpenCode Go is not viable for this workload.**

---

## 4) StandardCompute (current)

**User is on the Standard plan ($89/mo).** No material change to plans since Sept 2026.
- Plan ladder: Starter $19, Economy $39, **Standard $89**, Pro $249, Pro Plus $499, Growth $999, Scale $2,499. (Source: standardcompute.com/pricing, retrieved 2026-10-04.)
- Standard: $89/mo, $95 compute budget ($142 launch offer for month 1), priority lane, EU/US regions.
- Smart-routing stretches the budget 2–7× vs direct API; the page advertises "up to $310/mo direct-API equivalent" at the $89 plan.
- **Renewal terms:** auto-renew monthly; cancel-at-period-end from dashboard; upgrades effective immediately (any unused time credited); downgrades effective at next renewal. 7-day fair refund (cancel within 7 days, pay only for what you used). No overages — requests return `402 budget_exhausted` when budget runs out. (Source: standardcompute.com/pricing & standardcompute.com/fair-use.)
- Smart pacing optional (off by default) — throttles rather than stops.

**User's history: ~$53.50 effective cost/mo** (subsidized launch offer on the $89 plan). The actual renew-at-list cost is **$89/mo**.

---

## 5) New / changed flat-rate providers since Sept 10 2026

### DevPass by LLM Gateway — **NEW (worth evaluating)**
- 3 plans: **Lite $29 = $87/mo metered**, **Pro $79 = $237/mo metered**, **Max $179 = $537/mo metered**. (Source: devpass.llmgateway.io/pricing, retrieved 2026-10-04.)
- "Every dollar → $3 of model usage at provider list rates." 200+ model catalog, OpenAI-compatible.
- Frontier-fair-use cap: 12%/15%/18% of credits for models priced $5+/M input or $15+/M output (GLM-5.3-Flash is *not* in this category — it sits in main allowance).
- **⚠ Plan changes effective Oct 15, 2026:** Allowance falls from 3× to 2× subscription price. Same dollar, half the headroom. Lite $29 → $58, Pro $79 → $158, Max $179 → $358 metered. New subs from Oct 15 start at 2×.
- 14-day self-serve refund.
- Built into OpenCode (`/connect` → LLM Gateway), Claude Code (2 env vars), Cline, Aider, Continue, Cursor.

**For user:** Pro $79 → $237 metered budget → covers ~$767 of usage at 3× but only ~$158 at 2×. At Oct 15 transition the user would be paying PAYG overflow — **plan around the 2× not 3× post-Oct 15**. Rough effective cost: **$79/mo (but monitor allowance usage daily after Oct 15).**

### Kilo Pass (kilo.ai/pricing/kilo-pass)
- Credit-based, monthly subscription with bonus credits on top. **No hard token caps.** Pricing at provider list rates.
- Tiers: **Starter $19, Pro $49, Expert $199**. (Source: kilo.ai/pricing, kilo.ai/pricing/kilo-pass.)
- 50% welcome bonus month 1, then monthly bonus grows 5% per month up to 40% by month 8. Annual = 50% every month.
- Free bonus credits **expire end of each month**, paid credits persist (no rollover mentioned for paid).
- 5% processing fee on credit top-ups.
- 500+ models including GLM, DeepSeek, Claude, OpenAI, Gemini.
- **For user:** $49 Pro × 1.40 effective (40% bonus) = $68.60 mo balance. User's direct-API cost on GLM-5.3-Flash at Synthetic = $844/mo. **Net effective cost = $49/mo if usage stays in budget.** Hard ceiling: free-bonus credits cap at $68.60, after that you pay-as-you-go from your balance; balance only fills from paid credits when the bonus tier bumps up.

### NanoGPT (nano-gpt.com)
- $12/mo subscription, **60M input tokens/week cap** (Source: nano-gpt.com/pricing, nano-gpt.com/blog/subscription-update-february-2026).
- **Hard disqualifier:** User uses ~3,300M fresh input + ~7,700M cached input tokens/month ≈ ~2,575M/week fresh input alone — **47× over the cap**. Not viable.

### Chutes (chutes.ai)
- **Plus $10, Pro $20.** New usage cap = 5× subscription price in PAYG equivalent. Plus = $50/mo, Pro = $100/mo. (Source: chutes.ai/news/community-announcement-february, 2026-02-27, plus chutes.ai/pricing retrieved 2026-10-04.) Older Feb 2026 announcement; no further changes since.
- Per-token: GLM-5.1 $0.98 in / $3.08 out, GLM-5.2 $1.25/$3.95, Kimi-K3 $3.00/$15.00. **No cached-input pricing → user pays full input rate on the 70% cached portion → 70% cache benefit disappears.**
- Estimated user cost: ~$7,250–9,250/mo (much worse than other providers due to no cache discount).

### Featherless (featherless.ai)
- **Chat $25/mo** (4 concurrent units, 32K ctx cap — too small for 198K user).
- **Developer $50+/mo credit-based**, 256K ctx, 100 concurrent units. Per-token pricing, no hard caps. (Source: featherless.ai/docs/plans & /docs/billing, last edited Sep 15 2026.)
- Same problem as Kilo Pass / SC Gateway in that it's pay-per-token, no subscription price advantage for cache-heavy work. **Probably more expensive than Synthetic per token.**

### Targon (apis.io/plans/targon)
- Pay-as-you-go per token (Source: apis.io/plans/targon/targon-plans-pricing/). **No flat-rate subscription tier.** Skip.

### Infer.sh (inference.sh/pricing)
- **Three usage tiers (Starter/Growth/Scale) — no flat $ subscription.** Tiers unlock by cumulative usage. Subscription API updated Sept 25, 2026. (Source: inference.sh/pricing, inference.sh/docs/api/rest/subscription.)
- PAYG only. Skip for flat-rate search.

### llm.chutes.ai
- Same as Chutes (it's their model-serving subdomain). Covered above.

### Zed Pro (zed.dev/pricing)
- **$10/mo for Pro includes $5 of tokens + unlimited edit predictions; usage-based after, at API list price +10%.** (Source: zed.dev/pricing.)
- User would burn through $5 in ~700 GLM-5.3-Flash requests, then pay ~$760 + 10% = ~$836/mo. **Hard NO.**

### Chorus (melty.sh/chorus/changelog)
- **Open-sourced and moved to pay-as-you-go on API keys** (2026 changelog). No flat-rate subscription offering for users. Skip.

---

## Compact comparison table (effective monthly cost for THIS user)

| Provider | Plan | Effective $/mo | Hard cap? | Cache-friendly? | Source date |
|---|---|---|---|---|---|
| **StandardCompute Standard** | $89 (current) | $89–$95 (within budget) | Yes, requests stop at $95 budget | Yes (smart routing) | 2026-10-04 |
| **NeuralWatt Max (energy)** | $200 + overage | **~$720/mo** | Energy cap; Flex OK | Yes (cache rate same) | 2026-10-04 |
| **NeuralWatt Pro (energy)** | $100 + overage | ~$771/mo | Same | Same | 2026-10-04 |
| **NeuralWatt token mode** | Pay-as-you-go | **~$6,232/mo** ✗ | No | Yes | 2026-10-04 |
| **DevPass Pro (LLM Gateway)** | $79 → $237 (Oct 15: $79 → $158) | **$79/mo** until Oct 15 then watch allowance | Soft: pay-as-you-go overflow | Yes | 2026-10-04 |
| **DevPass Lite** | $29 → $87 (Oct 15: $58) | $29 (too tight) | Same | Same | 2026-10-04 |
| **Kilo Pass Pro** | $49 + 40% bonus after mo 8 | **~$49–$68.60/mo** | Soft: PAYG after balance | Yes | 2026-10-04 |
| **Synthetic (PAYG only)** | usage-based | **~$844/mo** | No | Yes ($0.04 cached/M) | 2026-10-04 |
| **Synthetic pack × 5** | $150/mo | Insufficient (5×500=2500 req/5h covers ~25k req/mo, still under 55K) | Hard | Yes | 2026-10-04 |
| **OpenCode Go / Go Plus** | $10 / $40 | ✗ **CAPPED at ~4,342 / 13,026 req/mo** | Yes, $60/$180 model cap | Yes | 2026-10-04 |
| **Chutes Pro** | $20 → $100/mo | ~$7,250+/mo | Hard: 5× cap | ✗ no cache discount | 2026-10-04 |
| **Featherless Developer** | $50+ credit | ~$700+ at per-token | Soft (balance) | Yes | 2026-10-04 |
| **Zed Pro** | $10 + usage | ~$836/mo | Soft | Yes | 2026-10-04 |
| **NanoGPT $12** | $12 | ✗ **60M input/wk cap (47× over)** | Yes, hard weekly cap | – | 2026-02-15 |
| **Targon** | PAYG | depends | No | – | 2026-10-04 |
| **Infer.sh** | PAYG tiered | depends | Tier limits | – | 2026-09-25 |
| **Chorus** | PAYG (open-sourced) | depends | – | – | 2026-09 |

---

## Recommendations

### Hard NO (don't even test):
- **OpenCode Go / Go Plus** — hard per-model monthly caps kill this workload before you start.
- **NeuralWatt token mode** — GLM-5.3 token pricing is ~10× what others charge.
- **Chutes** — no cache discount; 198K prompt × 70% cache means you pay for the cache portion at full rate.
- **NanoGPT** — 60M input tokens/week is ~2% of user's weekly fresh input.
- **Zed Pro** — token-based, designed for editor users not API-heavy agents.

### Watch the fine print:
- **DevPass** — Oct 15, 2026 changes allowance from 3× to 2× of subscription. Decide before that date.
- **Kilo Pass** — bonus credits expire monthly; paid credits persist, but $49 Pro max effective budget is $68.60/mo. User's direct-API cost is $844/mo — even with $49 paid in, the bonus covers only ~$20 worth of usage. Anything beyond balance becomes PAYG (no discount). Better than nothing but not magic.
- **StandardCompute** — already on this plan, $89/mo. No overage protection; first-month launch offer ends.
- **Synthetic** — pack-based model doesn't fit 55,500 req/mo profile unless you go usage-based.

### Best candidates by total effective $/mo:
1. **Stay on StandardCompute $89** if it works (already integrated with Hermes).
2. **DevPass Pro $79** (transition before Oct 15 — Pro 3× → Pro 2× reduces buffer significantly).
3. **NeuralWatt Max energy-mode $200 + overage (~$720)** — significantly cheaper if Flex tier is acceptable for agent work (Flex 0.65× energy ≈ $668/mo; recommended for agents per NeuralWatt docs).
4. **Synthetic usage-based (~$844)** — fallback if smart-routed providers regress.

---

## Sources (all retrieved 2026-10-04 unless noted)

- NeuralWatt pricing: https://portal.neuralwatt.com/pricing
- NeuralWatt GLM-5.3 model: https://portal.neuralwatt.com/models/glm-5.3
- NeuralWatt DeepSeek V4.1 Flash: https://portal.neuralwatt.com/models/deepseek-v4.1-flash
- NeuralWatt Flex docs: https://portal.neuralwatt.com/docs/guides/flex-tier
- NeuralWatt status: https://neuralwatt.betteruptime.com/
- Synthetic pricing: https://synthetic.new/pricing
- Synthetic rate limits: https://synthetic.new/rate-limits
- Synthetic usage pricing: https://synthetic.new/pricing?initial=usage
- OpenCode Go docs: https://opencode.ai/docs/go/
- OpenCode Go pricing page: https://opencode.ai/go
- Go Plus announcement (Sept 28): https://nitter.jaydenha.uk/opencode/status/2104548294718296064
- OpenCode Go review (Oct 3): https://threatfrontier.com/articles/opencode-go-10-plan-review-is-the-budget-multi-model-coding-sub-worth-it
- StandardCompute pricing: https://standardcompute.com/pricing
- StandardCompute fair use: https://standardcompute.com/fair-use
- StandardCompute docs budgets: https://docs.standardcompute.com/budgets-and-limits
- DevPass pricing: https://devpass.llmgateway.io/pricing
- DevPass landing: https://devpass.llmgateway.io/
- Kilo Pass: https://kilo.ai/pricing/kilo-pass
- Kilo Pass launch blog (Jan 16 2026): https://blog.kilo.ai/p/introducing-kilo-pass
- NanoGPT pricing: https://nano-gpt.com/pricing
- NanoGPT subscription update (Feb 15 2026): https://nano-gpt.com/blog/subscription-update-february-2026
- Chutes pricing: https://chutes.ai/pricing
- Chutes Feb 27 2026 announcement: https://chutes.ai/news/community-announcement-february
- Featherless plans: https://featherless.ai/docs/plans
- Featherless billing (last edited Sep 15 2026): https://featherless.ai/docs/billing
- Zed pricing: https://zed.dev/pricing
- Infer.sh pricing: https://inference.sh/pricing
- Infer.sh subscription API (updated Sep 25 2026): https://inference.sh/docs/api/rest/subscription
- Chorus changelog: https://melty.sh/chorus/changelog
- Targon pricing: https://apis.io/plans/targon/targon-plans-pricing/
- Synthetic pricing restructure coverage: https://openclawradar.com/article/synthetic-pricing-restructure-rate-limit-changes