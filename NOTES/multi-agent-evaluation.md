# Multi-Agent Setup Evaluation for spectacle (NixOS fleet config)

> Research-grounded assessment of whether to adopt a multi-agent LLM setup for this repo.
> Covers all known opencode multi-agent tools/plugins + the 2024→2026 academic evidence.
> Weighted toward recent (2026) findings per the caveat that older research may be less
> relevant as LLMs have improved significantly.

## TL;DR

**Verdict: Do NOT adopt a full multi-agent setup. DO adopt the narrow form — model routing
+ read-only exploration subagents.**

- **Tokens/cost:** Multi-agent burns MORE tokens, not fewer. Anthropic's own line: "Multi-agent
  systems work mainly because they help spend enough tokens." 15× chat vs single-agent 4×.
  The 2026 "Illusion of Multi-Agent Advantage" paper found auto-generated MAS underperform at
  up to 10× cost. The "token savings" pitch from plugins comes from **model routing** (cheap
  model for exploration, expensive for execution), which opencode already supports natively.
- **Quality:** At equal token budgets, single-agent matches or beats multi-agent on reasoning
  across 5 MAS architectures (Tran & Kiela, Stanford, Apr 2026). The "more agents" gap narrows
  to ~0% with modern models like Claude Haiku 4.5 (Cross-Component Interference, 2026).
- **Speed:** Multi-agent can cut wall-clock time for **parallelizable** research (Anthropic:
  hours→minutes with 3-5 parallel subagents). But spectacle's tasks are write-coordinated and
  serial (`nh os switch`, `nix flake check`), so parallelism rarely applies.
- **The real 2026 win = model routing, not agent count.** Morph Router: 4× cost reduction via
  planner (Opus) + executor (Haiku). polydev: Haiku + consultation matches Opus at 38% cost.
- **Recommendation:** Path A (native custom agents with per-agent model routing using our 2
  active model sources: opencode-go + opencode-zen). Zero plugin deps, no telemetry, no Nix
  closure bloat. Optional Tier-1 plugin additions: subtask2, opencode-background-agents.

---

## 1. The question

Is it worth implementing a multi-agent setup for this NixOS fleet config repo? Specifically:

1. Will it save tokens (hence be cheaper)?
2. Will it improve quality?
3. Will it improve speed?

Our context: single-domain repo (NixOS configs), mostly localized edits + eval debugging.
2 active model sources: **opencode-go** (subscription, $10/mo) for daily work and
**opencode-zen free** (big-pickle) for fallback — see `NOTES/OPENCODE-GO.md` and
`NOTES/models-catalog.md`. OpenRouter free kept as backup source (catalogued in
models-catalog.md but not in active routing). Already running a token-conscious stack:
opencode-snip + DCP (context pruning) + tokenscope + throughput.

---

## 2. Research findings (grounded, weighted by recency)

### 2.1 Tokens/cost — multi-agent burns MORE, not less

| Source | Date | Finding |
|---|---|---|
| Anthropic, "How we built our multi-agent research system" | Jun 2025 | Multi-agent = **15× chat tokens**; single agent = 4×. Token usage explains **80% of BrowseComp variance**. "Multi-agent systems work mainly because they help spend enough tokens to solve the problem." |
| Jwalapuram et al., "The Illusion of Multi-Agent Advantage" (arXiv:2606.13003) | Jun 2026 | Auto-generated MAS **consistently underperform CoT-SC despite up to 10× cost**. "As model capability scales, the MAS advantage further erodes due to Signal Saturation: in models like GPT-5, gradients flatten, causing controllers to lose the signal needed for nuanced routing." |
| Fu et al., "Do More Agents Help?" / BenchAgent (arXiv:2606.05670) | 2026 | Single-agent anchor = 74.12% balanced avg. **5 of 6 MAS trail it by 2.56–11.29 pts at higher cost.** Only EvoAgent beats it by +1.44 (within Wilson uncertainty). "Holding model, tools, evaluator, and logger fixed, adding roles or handoffs did not lift overall performance." |
| ECER 2026, "When Do Multi-Agent LLM Systems Outperform" | 2026 | Single-agent outperformed fixed multi-agent on **every task family**. Multi = **~2× cost, 2× latency, lower quality** (single 8.91/10 100% pass vs multi 7.90/10 83.3% pass). |

**The "token savings" pitch from multi-agent plugins is real ONLY via model routing** (cheap
model for exploration, expensive for execution). That's a feature of the orchestrator, not
of multi-agent architecture itself — opencode supports it natively via per-agent `model`
config in agent markdown files.

### 2.2 Quality — single-agent wins or ties at equal budget on modern models

| Source | Date | Finding |
|---|---|---|
| Tran & Kiela, Stanford (arXiv:2604.02460) | Apr 2026 | At **equal token budgets**, single-agent matches/beats multi-agent on multi-hop reasoning (FRAMES, MuSiQue) across **5 MAS architectures** (Sequential, Debate, Ensemble, Parallel-roles, Subtask-parallel). Theoretical basis: **Data Processing Inequality** — inter-agent handoffs can only LOSE information. MAS only competitive when single-agent context is degraded. Also identified API budget-control artifacts (esp. Gemini 2.5) that inflated prior MAS gains. |
| "More Is Not Always Better: Cross-Component Interference" (arXiv:2605.05716) | 2026 | Full-factorial study, 118 configs incl. Claude Haiku 4.5. **Gap narrows with model scale: 8B=32% gap, 70B=19%, Claude Haiku 4.5=~0% gap (saturated).** Directly measures the hypothesis that multi-agent gains shrink with stronger models. |
| OneFlow (arXiv:2601.12307) | Jan 2026 | Single LLM role-playing homogeneous MAS **matches/exceeds accuracy** across 7 benchmarks. Cost: GSM8K $0.623→$0.387 (~38% lower). Escape hatch: can't simulate truly heterogeneous (multi-base-model) workflows — KV cache is model-specific. |
| "Understanding Agent Scaling via Diversity" (arXiv:2602.03794) | Feb 2026 | Extends "More Agents Is All You Need." Homogeneous scaling shows strong diminishing returns: marginal gain "rapidly collapses toward zero." **Just 2 heterogeneous agents match 16 homogeneous (8× reduction).** Diversity is the surviving lever, not count. |
| Cognition (Walden Yan) | Jun 2025 + Apr 2026 | "Don't Build Multi-Agents" — game of telephone, context engineering > agent count. Apr 2026 update: multi-agent works **ONLY when writes stay single-threaded and extra agents contribute intelligence, not actions.** "Manager Devin spawns managed Devins" (isolated VM, single-threaded writes per worker). |

### 2.3 The real 2026 win: model routing, not agent count

The durable gain comes from **routing cheap vs expensive models by role**, not multiplying agents.

| System | Date | Cost reduction | Mechanism |
|---|---|---|---|
| CASTER (arXiv:2601.19793) | 2026 | **72.4%** vs all-GPT-4o | Dual-signal neural router in graph MAS |
| AOrchestra (arXiv:2602.03786) | Feb 2026 | +16.28% on GAIA/SWE-bench/Terminal-Bench | Orchestrator + on-demand subagents + model routing |
| Uno-Orchestra (arXiv:2605.05007) | 2026 | ~10× lower per-query cost, +16% over strongest workflow | Selective delegation (decompose + abstain) |
| Morph Router (Morph Benchmarks) | Jun 2026 | **4× cost reduction**; PEAR 4.4× ($1.24 vs $5.12/task) | Planner (Opus/GPT-5.5) + executor (Haiku/Flash) |
| polydev-swe-bench | Dec 2025 | Haiku 4.5 + consultation = 74.6% Resolve@2 **matching Opus 4.5 74.4% at $0.37 vs $0.97 (38% cost)** | Cheap model + inference-time compute + consultation |

**Counterpoint:** LLMRouterBench (ACL 2026) — many routing methods fail to outperform simple
baselines under unified eval. Routing is not a guaranteed win; it requires careful evaluation.

### 2.4 Where multi-agent STILL wins (2026 consensus, narrow regime)

1. **Breadth-first research / parallel independent searches** — Anthropic's +90.2%, AOrchestra
   +16.28% on GAIA. Genuine win, but it's research, not coding.
2. **Context degradation** — Tran & Kiela's escape condition: when single-agent context
   utilization is degraded (very long/noisy inputs), MAS (especially Debate) becomes competitive.
3. **Read-only exploration subagents** — subagents that **read, summarize, return a string,
   never write** (Claude Code, Devin's Deepwiki subagent, depot.dev's `/orc` loop). Win is
   context isolation, not intelligence. **Unanimous 2026 support.**
4. **Genuine model heterogeneity** — OneFlow's escape hatch: KV cache can't be shared across
   different base models, so a multi-model ensemble can't be simulated by one agent.
5. **Clean-context review** — reviewer catches bugs the coder can't see (different context,
   no shared false starts). Cognition's recommended pattern.
6. **Multi-agent debate as a TRAINING signal** (MACA, OpenReview 2026): +26.87% MATH, +27.6%
   GSM8K self-consistency. This is about self-improvement, not inference-time deployment.

### 2.5 2024 claims now stale (per caveat: older research less relevant as LLMs improved)

| 2024 claim | 2026 status |
|---|---|
| "More Agents Is All You Need" — +12–24% GSM8K via ensemble voting (Li et al., TMLR 2024, Llama2/GPT-3.5 era) | Homogeneous-scaling marginal gain "rapidly collapses toward zero" (arXiv:2602.03794); 5/6 MAS lose to single anchor (BenchAgent). The original paper itself predicts this: gains scale with the model-task difficulty gap, which closes as models improve. |
| Agent Forest: Llama2-13B ensemble matches Llama2-70B at N=15 | Modern frontier models (GLM-5 77.8% SWE-bench single-shot, Opus 4.5 80.9%, GPT-5.5 82.6%) closed that gap. Single-shot reasoning is much stronger now. |
| MAS gains from architectural coordination | Anthropic: 80% of variance is token spend. Tran & Kiela: "unaccounted computation and context effects." Illusion paper: "architectural bloat." |
| Gemini 2.5 multi-agent benchmarks | Tran & Kiela identify API budget-control artifacts that inflated these. |
| Multi-agent coding as default upgrade | Cognition (Devin) ships single-agent. Anthropic caveats coding has "fewer truly parallelizable tasks." ECER 2026: single-agent wins on every coding task family. SWE-bench top scores (Jun 2026: Fable 5 95%, Opus 4.8 88.6%) come from single-loop harnesses. |

### 2.6 Industry stances (2025-2026)

- **Anthropic (Jun 2025):** +90.2% multi-agent over single-agent Opus — BUT breadth-first
  RESEARCH only, not coding. 15× tokens. Own caveat: "most coding tasks involve fewer truly
  parallelizable tasks than research, and LLM agents are not yet great at coordinating and
  delegating to other agents in real time."
- **Cognition (Devin, Jun 2025 + Apr 2026):** "Don't Build Multi-Agents." Narrowed in Apr 2026
  to: multi-agent works ONLY when writes stay single-threaded and extra agents contribute
  intelligence, not actions.
- **LangChain (Jun 2025 + Jan 2026):** Multi-agent wins on **context-scaling** (2+ distractor
  domains), not raw intelligence. Subagents use 67% fewer tokens than Skills on multi-domain
  tasks due to context isolation.
- **2026 consensus (FlowHunt synthesis):** "At equal token budgets, single-agent matches or
  beats multi-agent on reasoning. The burden of proof is on multi-agent. Multi-agent wins
  where work is parallelizable and read-heavy."

---

## 3. Applied to the spectacle repo

The spectacle repo is **single-context, config-heavy, write-coordinated** (flake.nix is
generated, modules/users/*/dotfiles, host configs sharing modules/defaults/). Applying the
evidence:

- **Task shape = Cognition's coding regime, NOT Anthropic's research regime.** Most changes
  touch a handful of `.nix` files with cross-dependencies. The +90.2% number does NOT transfer.
- **Parallelism is low.** `nh os switch` is serial; `nix flake check` is whole-flake; host
  configs share `modules/defaults/`. Few genuinely independent subtasks per change.
- **Context is not the bottleneck.** Repo is well-structured with AGENTS.md conventions,
  NOTES/, per-user dotfile dirs. A single agent with good context engineering fits the
  2026-favored pattern.
- **Verification is cheap and deterministic** — `nix-eval-host` / `nix flake check --no-build`
  give fast ground truth. This is the regime where Tran & Kiela's SAS dominance holds: no
  context degradation, verifiable answers, no need for debate/ensemble.
- **The real lever = model routing, not multi-agent.** Per Morph/CASTER/PEAR data: keep
  frontier (GLM-5.2 / Qwen3.7 Max) for planning + hard Nix eval reasoning; route mechanical
  edits/searches to mid-tier (Qwen3.7 Plus / DeepSeek V4 Pro) or lightweight (MiMo-V2.5 /
  DeepSeek V4 Flash). This captures most of the cost/quality win without the 15× token tax
  or coordination fragility.

**Narrow multi-agent form that IS worth adopting (if any):**
1. **Read-only exploration subagents** (one-shot, return summary string) for repo-wide
   searches across `modules/` — unanimous 2026 support.
2. **Planner/executor model routing** (frontier for plan + Nix eval, mid-tier for file
   reads/mechanical edits).
3. **Clean-context reviewer subagent** for diff review before `nh os switch` — different
   context from the implementer, catches what the implementer's stale assumptions hide.

This captures the two durable wins (context isolation for search; cost via routing) without
the 15× token tax or coordination fragility.

### Current routing (updated Jun 2026, post-restructuring)

After Nemotron free endpoint died, restructured to **6 agents across 2 active model sources**.
Merged flagship + consultant into flagship-consultant (same model GLM-5.2). All custom
agents (anything not `plan` or `build`) are now `mode: subagent` — uniform policy: Tab cycle
contains only `plan` and `build`; everything else lives in @ autocomplete and is Task-callable.

| Agent | Model | Mode | Cost/session | Role |
|---|---|---|---|---|
| plan | Qwen3.7 Plus ($0.40/$1.60) | primary | ~$0.70 | Daily plan mode (Tab cycle default) |
| build | DeepSeek V4 Flash ($0.14/$0.28) | primary | $0.15 | Implementation (Tab cycle) |
| flagship-consultant | GLM-5.2 | subagent | $2.50 | Heavy sessions + escalation oracle (via @ or Task) |
| plan-free | big-pickle (`opencode/big-pickle`) | subagent | $0 (logged) | Free tier plan fallback (via @ or Task) |
| reviewer | DeepSeek V4 Pro ($1.74/$3.48) | subagent | $0.20 | Diff review (via @ or Task) |
| explore | DeepSeek V4 Flash ($0.14/$0.28) | subagent | $0.15 | Read-only search (via @ or Task) |

**Sources:** 1) opencode-go subscription ($10/mo): 4 agents (plan, build, flagship-consultant, reviewer)
and 1 reused (explore = same model as build). 2) opencode-zen free: 1 agent (plan-free = big-pickle,
stealth model, prompts logged for improvement). OpenRouter removed from active routing — Nemotron
endpoint died; no free replacement that fits the routing.

**Tab cycle:** plan → build. All other agents are subagents (not in Tab, but @-mentionable and
Task-callable).
**Budget:** ~$39/mo at current routing (plan ~$0.70 + build $0.15 + explore $0.15 = $1.00/session
× ~38 sessions ≈ $39). Tighter headroom under $60 opencode-go cap. flagship-consultant ($2.50)
reserved for heavy work / escalation. plan-free (big-pickle) prompts are logged — avoid for
sensitive work.
**Escalation:** primary agents (plan/build) auto-delegate to flagship-consultant (GLM-5.2) via
Task tool when stuck. Works by standard problem description — no special invocation needed.
**Reviewer constraint:** edit:deny, bash restricted to `git diff*` / `nix eval*` /
`nix flake check*`, task:deny. Invoked manually via @reviewer before `nh os switch`.

---

## 4. Tool comparison (comprehensive)

All known opencode multi-agent tools/plugins, with per-agent model routing, token cost,
NixOS fit, and license. Per-agent model routing is the key column — it's the mechanism that
delivers the real 2026 win.

### Tier 1 — adopt (aligned with 2026 evidence)

| Tool | Stars | Architecture | Per-agent model routing? | Token cost | NixOS fit | License | Notes |
|---|---|---|---|---|---|---|---|
| **Native custom agents** (no plugin) | — | Define `~/.config/opencode/agents/*.md` + per-agent `model` field. Use built-in Task tool for subagent isolation. Built-in Explore subagent is read-only. | **Yes** (opencode built-in) | **Lowest** — no orchestration overhead, just model routing | **Best** | — | Zero deps, no telemetry, no Nix closure bloat. Uses our 2 active model sources (opencode-go + opencode-zen) directly. `permission.task` glob patterns control delegation graph. `mode: subagent` keeps custom agents out of Tab cycle. `steps` field = max agentic iterations (cost control). |
| **subtask2** (spoons-and-mirrors) | 223 | Orchestration framework for existing /commands + subagents. Parallel/loop/chaining. `$RESULT[name]` named outputs. `$TURN[n]` precise context injection. `until:` conditions evaluated by reading real files/git/tests. | **Yes** (inline `{model:anthropic/claude-sonnet-4}`) | Low (only when you invoke parallel) | **Very Good** | **PolyForm Noncommercial** | Build custom `/eval-host` loops that run `nix eval` until it passes. Parallel multi-model research. **Caveats: PolyForm NC license (check if commercial use applies); `parallel` feature needs unmerged opencode PR #6478.** |
| **opencode-background-agents** (kdcokenny) | ~300 | Async background delegation. `delegate(prompt, agent)` fires read-only subagent, results persist to `~/.local/share/opencode/delegations/` as markdown. Solves context-compaction amnesia. 15-min timeout. | No (subagent uses its own model; no per-delegation override) | **Low** (context isolation saves tokens — only distilled result returns) | **Good** | MIT | Delegate "research NixOS options for service X" to background, keep editing. Persisted results survive long eval cycles. Lightweight (1 plugin). **Limitation:** no per-delegation model override — see aptdnfapt fork below. |

### Tier 2 — consider selectively

| Tool | Stars | Architecture | Per-agent model routing? | Token cost | NixOS fit | License | Notes |
|---|---|---|---|---|---|---|---|
| **aptdnfapt/opencode-async-agent** | — | Fork of background-agents **with** `delegate(prompt, agent, model)` + AI-powered session analysis + `/delegation` command. | **Yes** | Low | **Good** | MIT | Background delegation + model routing. Use if background-agents' lack of model override is a blocker. |
| **opencode-goopspec** (hffmnnj) | 33 | Spec-driven 5-phase: Discuss→Plan(lock)→Execute→Audit→Confirm. 1 Conductor orchestrator (never writes) + 12 specialists (5 executor tiers low/med/high/frontend-low/high, planner, researcher, explorer, verifier, debugger, tester, writer). | **Yes** (tiered: low/med→Sonnet, high→Opus, configurable via `/goop-setup`) | Medium (orchestration overhead) | **Good** | MIT | Flow maps to describe→lock→edit→nix eval→accept. Verifier agent = eval check. 1660 tests. Would adapt executor tiers to Nix (no frontend needed). |
| **micode** (vtemian) | 422 | 12 agents (commander, brainstormer, planner, executor, implementer, reviewer, codebase-locator, codebase-analyzer, pattern-finder, etc.). Brainstorm→Plan→Implement with git worktrees. Think Mode 128k budget. Auto-Compact at 50%. Token-Aware Truncation. Session continuity via ledgers. | **Yes** (micode.json per-agent overrides: model, temperature, maxTokens, thinking budget) | Medium | Good | unstated | Strong per-agent routing + session continuity. **Caveat: TDD-opinionated** (NixOS evals aren't "tests"). Per-agent routing lets cheap model do codebase-locator, strong does implementer. |
| **opencode-froggy** (smartfrog) | 91 | 6 agents (architect, doc-writer, code-reviewer, code-simplifier, partner, rubber-duck). Hooks layer fires on `session.idle`, `tool.before.*`, `tool.after.*` (can block tools via exit code 2). Skills load on demand. | No | Low | Medium | MIT | **Hooks are the valuable part** — block `flake.nix` edits (generated, don't hand-edit), auto-run `nix eval` after writes to module files. Blockchain tools irrelevant. Lightweight, low-risk. |

### Tier 3 — skip for this repo

| Tool | Stars | Architecture | Per-agent model routing? | Token cost | NixOS fit | License | Why skip |
|---|---|---|---|---|---|---|---|
| **oh-my-openagent** (ex oh-my-opencode, code-yeongyu) | 63k | 11 agents (Sisyphus orchestrator→kimi-k2.6/glm-5.1, Hephaestus deep worker→gpt-5.5, Prometheus planner, Oracle, Librarian, Explore, Multimodal Looker). Team Mode v4.0: lead + up to 8 parallel members in tmux. hyperplan = 5 hostile critics. Hashline hash-anchored edits. 54+ hooks, 5 built-in MCPs (Exa, Context7, grep_app — runtime-injected). | Yes (central, agent→model matrix) | **Highest** | Powerful but heavy | **SUL-1.0 (Source Available, NOT OSI-open-source)** | **PostHog telemetry** (opt-out: `OMO_DISABLE_POSTHOG=1`). Non-OSI license. Team Mode overkill for single-domain Nix edits. ultrawork discipline + hashline + LSP could help but adoption cost is high. |
| **oh-my-opencode-slim** (alvinunreal) | 5.8k | 7 agents (Orchestrator/Explorer/Oracle/Council/Librarian/Designer/Fixer). Scheduler-first V2. Has explicit opencode-go preset. Background agents. | Yes (opencode-go preset) | Medium | Medium | (check) | Decent for big multi-file refactors, overkill for daily Nix edits. |
| **opencode-workspace** (kdcokenny) | 505 | BUNDLE of 16 components (4 plugins + 2 npm + 3 MCPs + 4 agents + 4 skills + 1 command). 2 orchestrators (plan, build) + 5 specialists (explore, researcher, coder, scribe, reviewer). `webfetch:deny` globally. "Free Models Only" profile. | No (profile-based) | Medium | Medium-Good | MIT | 3 MCPs (Context7, Exa, GitHub Grep) + OCX installer = heavy dep surface for single-domain repo. researcher+coder split maps to Nix but deps outweigh benefit. |
| **opencode-swarm-plugin** (joelhooks) | 707 | Coordinator + N parallel Workers + Learning stage. Actor-model coordination. Git-backed Hive task tracker. Swarm Mail event store. File reservations. Learning system: patterns mature candidate→established→proven, anti-patterns auto-generate at >60% failure. | No | High (N parallel sessions) | Medium | MIT | Deps: Bun + Ollama (optional, local embeddings). Parallel workers + file reservations overkill for localized NixOS edits. Better for large multi-file codebases. |
| **opencode-mission-control** (nigel-dev) | 17 | Parallelizes agents in isolated git worktrees + tmux sessions. Plan System with dependency graphs, merge trains with test gating. TouchSet enforcement. | No | High | Poor-Medium | MIT | Deps: tmux, git, gh CLI. **Worktree isolation fights NixOS's cross-cutting shared `modules/`** — flake inputs, flake.lock, shared modules/defaults don't isolate cleanly per worktree. 40 open issues. Test gating could run `nix eval` per merge (one useful feature). |
| **pocket-universe** (spoons-and-mirrors) | ~39 | Closed-loop async subagent coordination. broadcast/subagent/recall tools. max_depth:3. | No (inherits caller's model) | Medium | **Poor (blocked)** | (likely PolyForm NC) | **BLOCKED: requires unmerged opencode PRs #9272 and #7725.** Marked [WIP]. Non-functional without patching opencode. Watch, don't adopt. |
| **conclave / open-conclave** (adndvlp) | exp | **FORK of opencode** (replaces binary). Multi-LLM debate engine: LEAD/SUPPORT/ALIGN/BUILD/CHALLENGE/SYNTHESIZE signals. Winner by endorsement scoring. Breaking Teams = autonomous sub-team splitting. 22+ providers. | Yes (core, 22+ providers) | **3× explicitly stated** (3 models × 3 rounds = 9 API calls/message) | Poor | MIT | Fork = high adoption friction, track upstream merges. 3× cost unjustifiable for routine edits. **Useful conceptually for architecture decisions only** — invoke for "how should I restructure this fleet?" not daily edits. CLI Bridging uses existing CLI auth (Gemini CLI free tier, Claude Code subscription). |
| **opencode-group-discuss** (Erinable) | 1 | Debate Mode (Advocate vs Critic, Moderator) + Collaborative Mode. 7 required subagents. Smart Context Budgeting. File sandbox (max 10 files). | No | High | Low | MIT | Too immature (1★). |
| **Dinesh7N/multi-agent-orchestration** | — | Gemini/Claude/Codex debate with PostgreSQL + Redis state, cost tracking, worker queues. | Yes | High | **Poor** | — | Heavy infra (Postgres + Redis). Overkill. |

### Debate-pattern tools (special case)

| Tool | What | NixOS fit |
|---|---|---|
| **agent-council** (marcel-tuinstra) | 10 business personas (CTO/CEO/PM/DEV etc.) debate. Mention-driven `@cto @dev`. Budget limits + reason codes. MIT. | Medium — business personas don't map to NixOS, but customizable. Useful for fleet-wide architecture decisions. |
| **signalnine/conclave** | Fork of obra/superpowers. Multi-agent consensus at key workflow points. 796 trials → 10-12 pt quality improvement. Skills-based. | Medium — skills-based, not debate-heavy. |

### Other discovered tools (briefer)

| Tool | Repo | What | NixOS fit |
|---|---|---|---|
| **opencode-plugin-openspec** (Octane0411, ~123★) | spec-driven | Dedicated openspec-plan agent, read-only codebase, write only spec files. | Good — like goopspec but OpenSpec-standard. |
| **opencode-openspec** (AngDrew) | spec-driven | OpenSpec workflow with 7 skills + 7 tools, Ralph Loop. | Good — spec-driven alt. |
| **bg-subagents** (Maicololiveras) | policy-driven | Policy-driven background/foreground routing of `task` calls + TUI sidebar. | Medium — useful if you want auto-backgrounding. |
| **opencode-superagents** (paulp-o) | DEPRECATED | → `mainsoft-2024/better-opencode-async-agents`. | Use successor. |
| **opencode-background-task** (zeigarnick, ~2★) | trivial | Minimal `background_task`/`background_output`/`background_cancel`. | Trivial. |

### Cross-cutting observations

- **Telemetry:** Only oh-my-openagent explicitly states telemetry (PostHog, opt-out). Others
  don't mention it — assume none, but verify if it matters.
- **Licenses to watch:** subtask2 + pocket-universe = **PolyForm Noncommercial**. oh-my-openagent
  = **SUL-1.0 (source-available, not OSI)**. Everything else MIT.
- **Per-agent model routing available in:** native opencode, micode, subtask2, goopspec,
  conclave, oh-my-openagent, agent-council, opencode-async-agent. NOT in: swarm, workspace,
  background-agents, froggy, mission-control, pocket-universe.
- **The debate pattern** (conclave, agent-council, group-discuss) is genuinely useful for
  **fleet-wide architecture decisions** but wasteful for routine module edits. Consider a
  debate tool invoked only for "how should I restructure this fleet?" questions, not daily edits.

---

## 5. Recommendation

### Primary: Path A — Native custom agents (no plugin)

opencode already has the subagent primitive (Task tool), per-agent model config, per-agent
permissions, and max-steps cost control. This means Path A needs **zero plugins** — just
markdown agent files in `~/.config/opencode/agents/` (global) or `.opencode/agents/` (project),
with per-agent `model` routing using our 3 sources.

**Concept (no example files per scope):**
- Define read-only exploration subagents (e.g. `nix-explorer`) on a mid-tier model
  (Qwen3.7 Plus / DeepSeek V4 Pro) for repo-wide searches across `modules/`. One-shot,
  return summary string, never write. This is the pattern with unanimous 2026 support.
- Define the primary builder/plan agent on a frontier model (GLM-5.2 / Qwen3.7 Max) for
  planning + hard Nix eval reasoning.
- Define a clean-context reviewer subagent (e.g. `nix-reviewer`) on a mid-tier or frontier
  model for diff review before `nh os switch` — different context from the implementer,
  catches what the implementer's stale assumptions hide.
- Use `permission.task` glob patterns to control the delegation graph (which agents can
  invoke which subagents).
- Use `steps` field per agent as a cost cap (max agentic iterations).

**Why this fits the evidence:**
- Captures the two durable 2026 wins: **context isolation for search** (read-only subagents)
  and **cost via model routing** (frontier for hard reasoning, mid-tier for mechanical work).
- Avoids the 15× token tax of full multi-agent.
- Avoids coordination fragility (Cognition's "game of telephone").
- Zero plugin deps = no Nix closure bloat, no telemetry, no license concerns.
- Fits the 2026-favored "single-agent with strong context engineering + narrow subagent
  delegation" pattern.

**Model routing strategy using our 2 active sources:**
- **Frontier (planning, hard Nix eval, architecture):** GLM-5.2 / GLM-5.1 (880 req/5hr),
  Qwen3.7 Max (950), Kimi K2.7 Code (1350) — from opencode-go. Reserve for final error
  handling and architecture decisions per `NOTES/OPENCODE-GO.md`.
- **Mid-tier (80% of daily work, mechanical edits):** Qwen3.7 Plus (4300 req/5hr),
  DeepSeek V4 Pro (3450) — from opencode-go.
- **Lightweight (file reads, grep, simple searches):** MiMo-V2.5 / DeepSeek V4 Flash (30k+
  req/5hr) — from opencode-go. Reused for both `build` and `explore` (one model, two roles).
- **Free fallback (big-pickle):** opencode-zen `opencode/big-pickle` — prompts logged for model
  improvement; use only for non-sensitive work. Replaces former Nemotron free tier (endpoint died).
- **Heterogeneity backup:** openrouter free models kept as catalogued backup per
  `NOTES/models-catalog.md` but not in active routing.

### Optional Tier-1 plugin additions (if specific needs arise)

- **subtask2** — if you want custom `/eval-host` loops that run `nix eval` until it passes,
  or parallel multi-model research on a question. Watch the PolyForm Noncommercial license
  and the pending `parallel` PR #6478.
- **opencode-background-agents** (or aptdnfapt fork for model override) — if you want to
  delegate "research NixOS options for service X" to background and keep editing. Persisted
  results survive long eval cycles and context compaction.

### When to reconsider full multi-agent

Revisit if the repo's task shape changes:
- If you start doing **breadth-first fleet-wide audits** (e.g. security audit across all hosts
  in parallel) — Anthropic's +90.2% regime applies.
- If context windows become a bottleneck (very long inputs, many distractor domains) —
  LangChain's context-scaling regime applies.
- If you want **debate for architecture decisions** — invoke a debate tool (agent-council,
  conclave) only for "how should I restructure this fleet?" questions, not routine edits.

---

## 6. Citations

### Academic papers (2026 weighted highest)

1. Tran & Kiela, "Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning
   Under Equal Thinking Token Budgets," Stanford/Contextual AI, arXiv:2604.02460, Apr 2026.
2. Jwalapuram et al., "The Illusion of Multi-Agent Advantage," arXiv:2606.13003, Jun 2026.
3. Fu et al., "Do More Agents Help?" / BenchAgent, arXiv:2606.05670, 2026.
4. Xu et al., "OneFlow: Rethinking the Value of Multi-Agent Workflow," arXiv:2601.12307,
   Jan 2026.
5. "More Is Not Always Better: Cross-Component Interference," arXiv:2605.05716, 2026.
6. "Understanding Agent Scaling via Diversity," arXiv:2602.03794, Feb 2026.
7. "When Do Multi-Agent LLM Systems Outperform," ECER 2026.
8. "Towards a Science of Scaling Agent Systems," arXiv:2512.08296, Dec 2025.
9. "Comprehensive Evaluation Single-Model to Multi-Agent," arXiv:2601.13243, Jan 2026.
10. "When Does Multi-Agent RL Improve LLM Workflows?" arXiv:2605.24202, 2026.
11. CASTER, arXiv:2601.19793, 2026.
12. AOrchestra, arXiv:2602.03786, Feb 2026.
13. Uno-Orchestra, arXiv:2605.05007, 2026.
14. MACA (multi-agent debate as training signal), OpenReview 2026.
15. LLMRouterBench, ACL 2026 (counterpoint on routing).
16. Li et al., "More Agents Is All You Need," TMLR 2024, arXiv:2402.05120 (2024 baseline,
    now stale per 2026 replications).
17. Huang et al., "AgentCoder," arXiv:2312.13010, 2024 (fewer well-designed agents with
    feedback loops >> more agents).
18. Qian et al., "ChatDev," ACL 2024 (7-agent waterfall, ~184K tokens/HumanEval).

### Industry sources

1. Anthropic, "How we built our multi-agent research system," Jun 13 2025.
2. Cognition (Walden Yan), "Don't Build Multi-Agents," Jun 12 2025; "Multi-Agents: What's
   Actually Working," Apr 22 2026.
3. LangChain, "Benchmarking Multi-Agent Architectures," Jun 11 2025; "Choosing the Right
   Multi-Agent Architecture," Jan 14 2026.
4. FlowHunt, 2026 industry consensus synthesis, Apr 2026.
5. Morph Router / Morph Benchmarks, Jun 15 2026.
6. polydev-swe-bench, Dec 2025.
7. SWE-bench Verified leaderboard (vals.ai), Jun 17 2026.
8. GLM-5 report, arXiv:2602.15763, Feb 2026.

### Tool repositories

See tool comparison table in §4. Key repos:
- opencode native agents: https://opencode.ai/docs/agents/
- subtask2: spoons-and-mirrors/subtask2
- opencode-background-agents: kdcokenny/opencode-background-agents
- opencode-goopspec: hffmnnj/opencode-goopspec
- micode: vtemian/micode
- opencode-froggy: smartfrog/opencode-froggy
- oh-my-openagent: code-yeongyu/oh-my-openagent (formerly oh-my-opencode)
- conclave: adndvlp/conclave
- agent-council: marcel-tuinstra/agent-council

### Related notes in this repo

- `NOTES/OPENCODE-GO.md` — opencode-go rate-limit tiers (flagship/mid/lightweight model strategy)
- `NOTES/awesome-opencode-catalog.md` — full catalog of opencode plugins/tools
- `NOTES/memory-and-mcp.md` — MCP server patterns (ad-hoc via nix shell, not in closure)
