# Awesome Opencode Ecosystem Catalog

> Source: https://github.com/awesome-opencode/awesome-opencode
> Generated: 2026-06-20
> Star counts as of generation date

---

## OFFICIAL

| Repo | Stars | Description |
|------|-------|-------------|
| [anomalyco/opencode](https://github.com/anomalyco/opencode) | 176k | The open source AI coding agent. Terminal + desktop, TypeScript, built-in build/plan agents, extensive plugin ecosystem. |
| [anomalyco/opencode-sdk-python](https://github.com/anomalyco/opencode-sdk-python) | 242 | Python SDK (3.8+). Sync + async clients via httpx. Full type definitions. |
| [anomalyco/opencode-sdk-go](https://github.com/anomalyco/opencode-sdk-go) | 133 | Go SDK (1.22+). Functional options, pagination, typed structs. |
| [anomalyco/opencode-sdk-js](https://github.com/anomalyco/opencode-sdk-js) | 85 | TypeScript SDK. SSE streaming, retries, timeouts. |

---

## PLUGINS

### Auth & Providers

| Repo | Stars | Description |
|------|-------|-------------|
| [NoeFabris/opencode-antigravity-auth](https://github.com/NoeFabris/opencode-antigravity-auth) | 10.9k | OAuth via Antigravity (Google IDE). Multi-account rotation, thinking models, Google Search grounding. |
| [numman-ali/opencode-openai-codex-auth](https://github.com/numman-ali/opencode-openai-codex-auth) | 2.1k | OAuth for ChatGPT Plus/Pro. 22 model presets across GPT-5.x families. |
| [jenslys/opencode-gemini-auth](https://github.com/jenslys/opencode-gemini-auth) | 1.7k | Gemini OAuth. Use existing Gemini plan/quotas (incl. free tier). Thinking models, proxy config. |
| [theblazehen/opencode-antigravity-multi-auth](https://github.com/theblazehen/opencode-antigravity-multi-auth) | 18 | Antigravity multi-account OAuth (archived). |
| [open-hax/codex](https://github.com/open-hax/codex) | 38 | OAuth for OpenAI Codex backend via ChatGPT Plus/Pro. |
| [Alph4d0g/opencode-omniroute-auth](https://github.com/Alph4d0g/opencode-omniroute-auth) | 47 | OmniRoute API auth. Dynamic model fetching, provider auto-registration. |
| [JungHoonGhae/opencode-kilo-auth](https://github.com/JungHoonGhae/opencode-kilo-auth) | 37 | Kilo Gateway — 342+ models incl. 29 free tier. |
| [baranwang/opencode-provider-alias](https://github.com/baranwang/opencode-provider-alias) | 9 | Alias/curate providers with models.dev metadata. Glob includes, model aliases. |
| [Lyapsus/opencode-optimal-model-temps](https://github.com/Lyapsus/opencode-optimal-model-temps) | 11 | Nudges Gemini 3 Pro to 0.35 temperature. |

### Memory & Context

| Repo | Stars | Description |
|------|-------|-------------|
| [code-yeongyu/oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode) | 62.9k | Multi-agent harness. 11 agents, 54+ hooks, 5 MCPs, Team Mode, hashline edits, ultrawork mode. |
| [Opencode-DCP/opencode-dynamic-context-pruning](https://github.com/Opencode-DCP/opencode-dynamic-context-pruning) | 3.4k | Intelligent context compression, dedup, error purging. Dev moved to Sleev. |
| [tickernelz/opencode-mem](https://github.com/tickernelz/opencode-mem) | 939 | Persistent memory via SQLite + USearch vector DB. Web UI, 12+ local embedding models. |
| [cortexkit/opencode-magic-context](https://github.com/cortexkit/opencode-magic-context) | 978 | Unbounded context with self-managing memory. Historian, decay, dreamer consolidation. |
| [joshuadavidthomas/opencode-agent-memory](https://github.com/joshuadavidthomas/opencode-agent-memory) | 288 | Letta-style editable memory blocks. Global + project-scoped, journal with semantic search. |
| [cnicolov/opencode-plugin-simple-memory](https://github.com/cnicolov/opencode-plugin-simple-memory) | 126 | Persistent memory in `.opencode/memory/` as daily logfmt files. |
| [iHildy/opencode-synced](https://github.com/iHildy/opencode-synced) | 123 | Sync global config between machines via GitHub repo. Secrets, sessions, prompt stash. |
| [boxpositron/with-context-mcp](https://github.com/boxpositron/with-context-mcp) | 46 | Enhanced note-taking for agents. Project-scoped Obsidian integration. |
| [boxpositron/envsitter-guard](https://github.com/boxpositron/envsitter-guard) | 52 | Prevents agents from reading/editing sensitive .env files. |
| [one-bit/oc-mnemoria](https://github.com/one-bit/oc-mnemoria) | 13 | Shared hive mind memory for all agents. Hybrid BM25 + semantic search. |
| [Edison-A-N/opencode-worktree-memory-sync](https://github.com/Edison-A-N/opencode-worktree-memory-sync) | 1 | Auto-syncs `.opencode/memory/` to new git worktrees. |
| [errhythm/opencode-log-sanitizer](https://github.com/errhythm/opencode-log-sanitizer) | 2 | Redacts secrets from pasted logs before sending to AI. |

### Agent Orchestration

| Repo | Stars | Description |
|------|-------|-------------|
| [alvinunreal/oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim) | 5.8k | Slim oh-my-opencode fork. 7 specialized agents, much lower token usage. |
| [joelhooks/opencode-swarm-plugin](https://github.com/joelhooks/opencode-swarm-plugin) | 707 | Multi-agent swarm with learning, issue tracking, file reservations. |
| [vtemian/micode](https://github.com/vtemian/micode) | 422 | Brainstorm → Plan → Implement workflow. Parallel research, TDD, mindmodel system. |
| [kdcokenny/opencode-workspace](https://github.com/kdcokenny/opencode-workspace) | 505 | Bundled 16-component orchestration harness. 4 plugins, 3 MCPs, 4 agents, 4 skills. |
| [kdcokenny/opencode-background-agents](https://github.com/kdcokenny/opencode-background-agents) | 304 | Claude Code-style background agents. Async delegation, disk-persisted results. |
| [spoons-and-mirrors/subtask2](https://github.com/spoons-and-mirrors/subtask2) | 223 | Stronger /command handler. Chain prompts, loop/parallelize subagents, context passing. |
| [smartfrog/opencode-froggy](https://github.com/smartfrog/opencode-froggy) | 91 | Hooks, specialized agents (architect, reviewer, rubber-duck), skills, tools. |
| [nigel-dev/opencode-mission-control](https://github.com/nigel-dev/opencode-mission-control) | 17 | Parallel sessions in isolated git worktrees via tmux. Dependency graphs, merge trains. |
| [spoons-and-mirrors/pocket-universe](https://github.com/spoons-and-mirrors/pocket-universe) | 48 | Closed-loop async agents with broadcast messaging and recall. |
| [hffmnnj/opencode-goopspec](https://github.com/hffmnnj/opencode-goopspec) | 33 | Spec-driven 5-phase workflow. Orchestrator + 12 specialist agents. |
| [gotgenes/opencode-agent-identity](https://github.com/gotgenes/opencode-agent-identity) | 24 | Agent self-identity injection + per-message attribution. |
| [ramarivera/opencode-model-announcer](https://github.com/ramarivera/opencode-model-announcer) | 29 | Injects current model name into chat context. |
| [martinzokov/open-conclave](https://github.com/martinzokov/open-conclave) | 4 | Multi-agent debate orchestrator. 3 parallel agents + moderation + consensus. |
| [raisbecka/opencode-subagent-output](https://github.com/raisbecka/opencode-subagent-output) | 4 | Pipes subagent output to console in `opencode run` mode. |
| [RoderickQiu/opencode-workaholic](https://github.com/RoderickQiu/opencode-workaholic) | 4 | Prevents AI from ending tasks prematurely. Enforces minimum duration. |

### Workflow & Planning

| Repo | Stars | Description |
|------|-------|-------------|
| [backnotprop/plannotator](https://github.com/backnotprop/plannotator) | 6.4k | Visual plan/diff annotation in browser. Team sharing, one-click feedback to agents. |
| [joshuadavidthomas/opencode-beads](https://github.com/joshuadavidthomas/opencode-beads) | 248 | Beads issue tracker integration. Auto-runs bd prime, /bd-* commands, subagent for issues. |
| [malhashemi/opencode-sessions](https://github.com/malhashemi/opencode-sessions) | 167 | Multi-agent session collaboration. Turn-based, handoff, fork, manual compression. |
| [joshuadavidthomas/opencode-handoff](https://github.com/joshuadavidthomas/opencode-handoff) | 129 | Focused handoff prompts for new sessions. Context analysis + @file references. |
| [Octane0411/opencode-plugin-openspec](https://github.com/Octane0411/opencode-plugin-openspec) | 129 | OpenSpec integration. Dedicated plan mode + Architect agent. |
| [IgorWarzocha/Opencode-Roadmap](https://github.com/IgorWarzocha/Opencode-Roadmap) | 120 | Repo-wide shared todolist between sessions. Specs + actionable plans. |
| [athal7/opencode-pilot](https://github.com/athal7/opencode-pilot) | 73 | Automation daemon. Polls GitHub issues/Linear, spawns sessions with template prompts. |
| [ndom91/open-plan-annotator](https://github.com/ndom91/open-plan-annotator) | 72 | Browser-based plan annotation UI. Strikethrough, replace, insert, comment. |
| [yurihbm/opencode-plan-manager](https://github.com/yurihbm/opencode-plan-manager) | 7 | AI-native planning. Filesystem Kanban, zero-hallucination schemas, cross-session continuity. |

### Token & Cost Tracking

| Repo | Stars | Description |
|------|-------|-------------|
| [slkiser/opencode-quota](https://github.com/slkiser/opencode-quota) | 597 | Sidebar panel, popup toasts, status line. Zero context pollution. Multi-provider. |
| [vbgate/opencode-mystatus](https://github.com/vbgate/opencode-mystatus) | 253 | Check all AI subscription quotas in one command. Progress bars, reset countdowns. |
| [ramtinJ95/opencode-tokenscope](https://github.com/ramtinJ95/opencode-tokenscope) | 220 | Token analysis + cost tracking. System prompts, tool outputs, visual breakdowns. |
| [IgorWarzocha/Opencode-Context-Analysis-Plugin](https://github.com/IgorWarzocha/Opencode-Context-Analysis-Plugin) | 141 | Token distribution visualization. Bar charts across prompt categories. |
| [Ainsley0917/opencode-token-monitor](https://github.com/Ainsley0917/opencode-token-monitor) | 16 | Real-time monitoring, agent breakdown, trend analysis, budget thresholds. |
| [Howardzhangdqs/opencode-throughput](https://github.com/Howardzhangdqs/opencode-throughput) | 10 | TTFT, TPS, latency, cost per model. Toast notifications + JSONL logging. |
| [eserete/opencode-token-tracker](https://github.com/eserete/opencode-token-tracker) | 0 | Token usage in sidebar footer. TUI, toast, and classic modes. |

### Notifications

| Repo | Stars | Description |
|------|-------|-------------|
| MOVETO:AGENTS @probably-not [Th0rgal/opencode-ralph-wiggum](https://github.com/Th0rgal/opencode-ralph-wiggum) | 1.8k | Autonomous iterative loop. `ralph "prompt"` runs agent repeatedly until done. |
| [kdcokenny/opencode-notify](https://github.com/kdcokenny/opencode-notify) | 233 | Native OS notifications. Task complete, error, needs input. macOS/Windows/Linux. |
| [MasuRii/opencode-smart-voice-notify](https://github.com/MasuRii/opencode-smart-voice-notify) | 64 | Voice notifications. ElevenLabs, Edge TTS, SAPI. AI-generated messages, webhooks. |
| [pantheon-org/opencode-warcraft-notifications](https://github.com/pantheon-org/opencode-warcraft-notifications) | 55 | Warcraft II audio clips on idle. 110 bundled sounds, toast notifications. |
| [lannuttia/opencode-ntfy.sh](https://github.com/lannuttia/opencode-ntfy.sh) | 28 | Push notifications via ntfy.sh. Phone/desktop alerts on finish/error/permission. |
| [Wangmerlyn/vibe-coding-slack-notifier](https://github.com/Wangmerlyn/vibe-coding-slack-notifier) | 7 | Slack DM + Feishu/Lark completion alerts. |
| [Yusuzhan/opencode-simple-notify](https://github.com/Yusuzhan/opencode-simple-notify) | 3 | Minimal desktop notifications. Linux + macOS. |
| [Zaradacht/opencode-host-notify-bridge](https://github.com/Zaradacht/opencode-host-notify-bridge) | 2 | Devcontainer → macOS notification forwarding. |
| [StefanoChiodino/opencode-tts](https://github.com/StefanoChiodino/opencode-tts) | 0 | TTS on idle. Edge TTS, macOS say. Summary or full text modes. |

### Terminal & Visual

| Repo | Stars | Description |
|------|-------|-------------|
| [AnganSamadder/opencode-agent-tmux](https://github.com/AnganSamadder/opencode-agent-tmux) | 138 | Smart tmux integration. Auto-spawn panes, stream output, manage workspace. |
| [JosXa/opencode-snippets](https://github.com/JosXa/opencode-snippets) | 78 | Hashtag snippet expansion. Aliases, shell substitution, recursive includes. |
| [mailshieldai/opencode-canvas](https://github.com/mailshieldai/opencode-canvas) | 68 | Interactive terminal canvases in tmux splits. Calendars, docs, bookings. |
| [24601/opencode-zellij-namer](https://github.com/24601/opencode-zellij-namer) | 54 | AI-powered Zellij session naming via Gemini 3 Flash. |
| [psinetron/opencode-visualiser](https://github.com/psinetron/opencode-visualiser) | 12 | 2D pixel office visualizer. Agents work/idle/celebrate in virtual office. |
| [Mark1708/opencode-agents-sidebar](https://github.com/Mark1708/opencode-agents-sidebar) | 0 | Universal TUI sidebar for browsing agents. Collapsible sections, aliases. |
| [d3vv3/opencode-ascii](https://github.com/d3vv3/opencode-ascii) | 0 | Replace unicode with ASCII equivalents in AI responses and edits. |

### Safety & Security

| Repo | Stars | Description |
|------|-------|-------------|
| [kenryu42/claude-code-safety-net](https://github.com/kenryu42/claude-code-safety-net) | 1.4k | Safety net for destructive git/fs commands. Semantic analysis, shell wrapper detection. Multi-agent. |
| [lgladysz/opencode-ignore](https://github.com/lgladysz/opencode-ignore) | 66 | .ignore patterns (gitignore-style) for AI. Blocks read/write/edit/glob/grep. |
| [tlinhart/opencode-system-prompt-logger](https://github.com/tlinhart/opencode-system-prompt-logger) | 2 | Logs full system prompt on every message. Debugging/inspection. |

### Code Editing & Performance

| Repo | Stars | Description |
|------|-------|-------------|
| [JRedeker/opencode-morph-fast-apply](https://github.com/JRedeker/opencode-morph-fast-apply) | 155 | Morph Fast Apply — 10x faster edits. 10,500+ tok/s, 98% accuracy. No MCP needed. |
| [VincentHardouin/opencode-snip](https://github.com/VincentHardouin/opencode-snip) | 119 | Prefix shell commands with snip to reduce token usage 60-90%. |
| [JRedeker/opencode-shell-strategy](https://github.com/JRedeker/opencode-shell-strategy) | 109 | Teaches LLMs non-interactive shell flags. Prevents TTY hangs. |

### Skills Management

| Repo | Stars | Description |
|------|-------|-------------|
| [numman-ali/openskills](https://github.com/numman-ali/openskills) | 10.4k | Universal skills loader. One CLI, every agent, Claude Code format. |
| [joshuadavidthomas/opencode-agent-skills](https://github.com/joshuadavidthomas/opencode-agent-skills) | 235 | Dynamic skill discovery, context injection, compaction resilience. Now maintenance mode (native support). |
| [zenobi-us/opencode-plugin-template](https://github.com/zenobi-us/opencode-plugin-template) | 72 | Plugin template with TypeScript, ESLint, Prettier, GitHub Actions. |
| [tim-hilde/opencode-update-notifier](https://github.com/tim-hilde/opencode-update-notifier) | 1 | Checks pinned plugins for updates. Supply-chain defense. |
| [Randroids-Dojo/ManageSkills](https://github.com/Randroids-Dojo/ManageSkills) | 0 | Wizard-driven skill management. Multi-select pickers, repo-scoped lists. |

### Integrations

| Repo | Stars | Description |
|------|-------|-------------|
| [bergside/typeui](https://github.com/bergside/typeui) | 1.2k | AI-first UI platform. Design skills, prompts, resources for better UI generation. |
| [Xquik-dev/x-twitter-scraper](https://github.com/Xquik-dev/x-twitter-scraper) | 115 | Twitter/X scraper. 100+ REST endpoints, 2 MCP tools, HMAC webhooks. |
| [angristan/opencode-wakatime](https://github.com/angristan/opencode-wakatime) | 174 | Wakatime integration. AI coding metrics, file tracking, session lifecycle. |
| [athal7/opencode-devcontainers](https://github.com/athal7/opencode-devcontainers) | 196 | Isolated branch workspaces via devcontainers/git worktrees. Auto-port, secret copy. |
| [IgorWarzocha/Opencode-Google-AI-Search-Plugin](https://github.com/IgorWarzocha/Opencode-Google-AI-Search-Plugin) | 59 | Google AI Mode (SGE) queries via Playwright. Full markdown conversion. |
| [simonwjackson/opencode-direnv](https://github.com/simonwjackson/opencode-direnv) | 50 | Auto-loads direnv environment at session start. |
| [DEVtheOPS/opencode-plugin-otel](https://github.com/DEVtheOPS/opencode-plugin-otel) | 78 | OpenTelemetry export (OTLP). Mirrors Claude Code monitoring signals. |
| [zenobi-us/opencode-background](https://github.com/zenobi-us/opencode-background) | 68 | Background task management. Real-time output, tagging, selective termination. (Archived) |
| [Tarquinen/opencode-smart-title](https://github.com/Tarquinen/opencode-smart-title) | 49 | AI-generated session titles. Auto-updates on idle. |
| [joostvanwollingen/opencode-personality](https://github.com/joostvanwollingen/opencode-personality) | 17 | Configurable personality/mood system. Multiple personalities, dynamic drift. |
| [aerovato/opencode-quotes-plugin](https://github.com/aerovato/opencode-quotes-plugin) | 12 | Motivational quotes replacing default tips. |
| [Looted/kibi](https://github.com/Looted/kibi) | 6 | Repo-local knowledge base. Prolog graph, MCP server, end-to-end traceability. |
| [pawelma/opencode-autotitle](https://github.com/pawelma/opencode-autotitle) | 6 | AI-powered automatic session naming. Two-phase: keyword + refined AI title. |
| [shihyuho/opencode-command-inject](https://github.com/shihyuho/opencode-command-inject) | 2 | Auto-inject Makefile targets, package.json scripts as OpenCode commands. |
| [arttttt/opencode-pr-signature](https://github.com/arttttt/opencode-pr-signature) | 2 | Auto AI model signature on PRs/Issues. Detects Kimi, Claude, GPT, Gemini. |
| [romain325/opencode-hooks-plugin](https://github.com/romain325/opencode-hooks-plugin) | 3 | Run Claude Code hooks inside OpenCode. Command, http, prompt, agent types. |
| [saim-x/opencode-research-papers](https://github.com/saim-x/opencode-research-papers) | 3 | arXiv + OpenAlex paper search. Recency, citation, relevance filtering. |
| [amestsantim/opencode-github-release](https://github.com/amestsantim/opencode-github-release) | 0 | Git tags + GitHub releases with semantic versioning from conventional commits. |

---

## THEMES

| Repo | Stars | Description |
|------|-------|-------------|
| [b0o/lavi](https://github.com/b0o/lavi) | 54 | Soft & sweet colorscheme. 15+ app ports, Nix flake, home-manager module. |
| [postrednik/opencode-ayu-theme](https://github.com/postrednik/opencode-ayu-theme) | 38 | Dark Ayu-based theme. Deep background, golden accent, green strings. |
| [brunogabriel/opencode-moonlight-theme](https://github.com/brunogabriel/opencode-moonlight-theme) | 13 | Moonlight VS Code port. Dark purple/blue tones. |
| [ajaxdude/opencode-ai-poimandres-theme](https://github.com/ajaxdude/opencode-ai-poimandres-theme) | 10 | Poimandres-inspired. 3 variants: original, turquoise-expanded, WCAG AA accessible. |
| [VyomJain6904/charcoal-theme](https://github.com/VyomJain6904/charcoal-theme) | 2 | Deep-black grayscale. No hues, only shades of gray. Multi-tool support. |
| [fatihtoprakk/opencode-light-themes](https://github.com/fatihtoprakk/opencode-light-themes) | 2 | 20+ light themes collection. Atom One Light, Solarized, GitHub Light, etc. |
| [regen45t/opencode-vscode-themes](https://github.com/regen45t/opencode-vscode-themes) | 0 | VS Code built-in theme ports (Modern, Plus, VS, High Contrast). Dark + light variants. |

---

## AGENTS

| Repo | Stars | Description |
|------|-------|-------------|
| [Cluster444/agentic](https://github.com/Cluster444/agentic) | — | — |
| [VoltAgent/awesome-claude-code-subagents](https://github.com/VoltAgent/awesome-claude-code-subagents) | — | — |
| [darrenhinde/opencode-agents](https://github.com/darrenhinde/opencode-agents) | — | — |
| [amrahman90/python-expert-agent](https://github.com/amrahman90/python-expert-agent) | — | — |
| [BackGwa/Redstone](https://github.com/BackGwa/Redstone) | — | — |

---

## PROJECTS

### GUI Clients

| Repo | Stars | Description |
|------|-------|-------------|
| [Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec) | 55.7k | Spec-driven development framework. Proposal → specs → design → tasks per change. 25+ AI tools. |
| [BloopAI/vibe-kanban](https://github.com/BloopAI/vibe-kanban) | 27.1k | Kanban planning + isolated agent workspaces + diff review + browser preview. **Sunsetting.** |
| [different-ai/openwork](https://github.com/different-ai/openwork) | 16.2k | Desktop app (macOS/Win/Linux). Open-source Claude Cowork alternative. 50+ LLMs, team sharing. |
| [openchamber/openchamber](https://github.com/openchamber/openchamber) | 5.6k | Desktop + web + phone GUI. Branchable timelines, multi-agent, integrated terminal. |
| [grinev/opencode-telegram-bot](https://github.com/grinev/opencode-telegram-bot) | 826 | Telegram mobile client. Session mgmt, voice prompts, file attachments, scheduled tasks. |
| [verseles/codewalk](https://github.com/verseles/codewalk) | 161 | Native Flutter client. 14 languages, STT/TTS, Mermaid, LaTeX. |
| [leohenon/opencode-vim](https://github.com/leohenon/opencode-vim) | 62 | OpenCode fork with vim mode. Motions, copy mode, minimal UI toggle. |
| [theblazehen/P4OC](https://github.com/theblazehen/P4OC) | 57 | Android client. SSE streaming, inline diffs, embedded terminal, 9 themes. ~2.9 MB APK. |

### Monitoring & Analytics

| Repo | Stars | Description |
|------|-------|-------------|
| [junhoyeo/tokscale](https://github.com/junhoyeo/tokscale) | 3.8k | Rust TUI + web dashboard. GitHub-style contribution graphs, 30+ agents, leaderboard. |
| [Shlomob/ocmonitor-share](https://github.com/Shlomob/ocmonitor-share) | 337 | CLI analytics. Cost tracking, multi-currency, Prometheus export, live dashboards. |
| [luoyuctl/agenttrace](https://github.com/luoyuctl/agenttrace) | 76 | Local-first TUI for session history. Multi-agent cost/token/time analysis. |
| [joeyism/opencode-history-search](https://github.com/joeyism/opencode-history-search) | 73 | Keyword, regex, fuzzy search across conversation history. Date/role filtering. |
| [kcrommett/oc-manager](https://github.com/kcrommett/oc-manager) | 38 | TUI for inspecting/pruning OpenCode metadata. Fuzzy search, token counting, SQLite backend. |

### Proxy & API Gateways

| Repo | Stars | Description |
|------|-------|-------------|
| [router-for-me/CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) | 37.9k | Proxy wrapping Antigravity/Codex/Claude/Grok as OpenAI/Gemini/Claude API. Multi-account LB. |
| [gzzhongqi/geminicli2api](https://github.com/gzzhongqi/geminicli2api) | 590 | FastAPI proxy converting Gemini CLI → OpenAI-compatible + native Gemini endpoints. |
| [Mirrowel/LLM-API-Key-Proxy](https://github.com/Mirrowel/LLM-API-Key-Proxy) | 508 | Universal LLM gateway. Auto key rotation, failover, rate limit handling, cooldowns. |
| [aptdnfapt/qwen-code-oai-proxy](https://github.com/aptdnfapt/qwen-code-oai-proxy) | 178 | OpenAI-compatible proxy for Qwen via OAuth. **Deprecated** — Qwen free usage ended. |
| [unluckyjori/Codex-Proxy-Server](https://github.com/unluckyjori/Codex-Proxy-Server) | 33 | Rust/Axum proxy for Codex/ChatGPT models. Auth, logging, OpenAI-compatible. |
| [JUVOJustin/opencode-ddev](https://github.com/JUVOJustin/opencode-ddev) | 12 | DDEV compatibility. Auto-detect + container execution + ddev_logs tool. |

### Sandboxing & Isolation

| Repo | Stars | Description |
|------|-------|-------------|
| [holtwick/bx-mac](https://github.com/holtwick/bx-mac) | 79 | macOS sandbox wrapper. Blocks everything except specified project dir. No containers/VMs. |
| [stacklok/brood-box](https://github.com/stacklok/brood-box) | 43 | Hardware-isolated microVMs via libkrun/KVM. Copy-on-write snapshots, secret forwarding. |
| [seznam/jailoc](https://github.com/seznam/jailoc) | 25 | Docker Compose sandboxes with network isolation. DinD sidecar, no host socket mounting. |
| [cofy-x/deck](https://github.com/cofy-x/deck) | 14 | Desktop cockpit for AI sandboxes. Docker containers with full Linux desktop + noVNC. |

### Agent Communication

| Repo | Stars | Description |
|------|-------|-------------|
| [cjpais/Handy](https://github.com/cjpais/Handy) | 24.3k | Offline speech-to-text desktop app. Whisper + Parakeet V3. Cross-platform. |
| [aannoo/hcom](https://github.com/aannoo/hcom) | 348 | CLI for agents to message/spawn each other across terminals. Single Rust binary. |
| [0xranx/golembot](https://github.com/0xranx/golembot) | 304 | Any Agent × Any Provider × Anywhere. Connects coding agents to Slack/Telegram/Discord/etc. |
| [Intelligent-Internet/opencode-a2a](https://github.com/Intelligent-Internet/opencode-a2a) | 11 | A2A protocol for OpenCode. Auth, streaming, session continuity, interrupt handling. |

### Session & Workspace Management

| Repo | Stars | Description |
|------|-------|-------------|
| [njbrake/agent-of-empires](https://github.com/njbrake/agent-of-empires) | 2.6k | Session manager. TUI + web dashboard. Parallel agents, branch isolation, Docker sandbox. |
| [kdcokenny/ocx](https://github.com/kdcokenny/ocx) | 807 | Extension manager with portable profiles. SHA-verified components, curated registries. |
| [Th0rgal/sandboxed.sh](https://github.com/Th0rgal/sandboxed.sh) | 453 | Self-hosted cloud orchestrator. Isolated Linux workspaces, multi-runtime. |
| [vtemian/octto](https://github.com/vtemian/octto) | 419 | Browser brainstorming UI. 14 visual input types, parallel branches, live updates. |
| [remorses/kimaki](https://github.com/remorses/kimaki) | 1.2k | Discord-based agent orchestrator. Channels = projects, threads = sessions. |
| [bobum/open-dispatch](https://github.com/bobum/open-dispatch) | 24 | Control agents via Slack/Teams/Discord. 75+ providers, Fly.io Sprites. |
| [mbenhard/unship](https://github.com/mbenhard/unship) | 14 | Local DOM picker for temporary agent-authored UI variants. |

### Development Tools

| Repo | Stars | Description |
|------|-------|-------------|
| [steveyegge/beads](https://github.com/steveyegge/beads) | 24.6k | Persistent structured memory via Dolt. Dependency-aware graph, semantic decay, hash IDs. |
| [eqtylab/cupcake](https://github.com/eqtylab/cupcake) | 270 | OPA/Rego policy enforcement for agents. WebAssembly-compiled rules, zero context cost. |
| [saqibameen/agent-dotfiles](https://github.com/saqibameen/agent-dotfiles) | 3 | Write rules once in AGENTS.md, propagate to every coding agent. |
| [ar27111994/agent-harness](https://github.com/ar27111994/agent-harness) | 2 | Reviewable supply chain for reusable AI-agent assets. Mirror, stage, activate. |
| [Comfanion/workflow](https://github.com/Comfanion/workflow) | 2 | AI-assisted dev workflow. Requirements → PRD → Architecture → Epics → Stories → Code. |
| [jjserenity/opencode-chat-export](https://github.com/jjserenity/opencode-chat-export) | 0 | MCP server exporting chat history to Markdown. Collapsible tool calls, token summaries. |

---

## RESOURCES

| Repo | Stars | Description |
|------|-------|-------------|
| [sorenisanerd/gotty](https://github.com/sorenisanerd/gotty) | 2.5k | Share terminal via browser. TLS, basic auth, tmux/screen sharing, WebGL rendering. |
| [jjmartres/opencode](https://github.com/jjjmartres/opencode) | 130 | Custom config suite — agents, commands, rules, skills, themes, MCPs. GNU Stow. **Archived.** |
| [evermeer/CodingAgentOrchestration](https://github.com/evermeer/CodingAgentOrchestration) | 5 | Reference architecture + handbook for multi-agent coding. Layered config, skills, Jira/Azure DevOps. |
| [orionpax1997/kickstart.opencode](https://github.com/orionpax1997/kickstart.opencode) | 2 | Annotated starter config. Custom agents, skills, slash commands. Free models only. |
| [sunnja69/akephalos](https://github.com/sunnja69/akephalos) | 0 | Markdown-first passport for AI agents. Carry preferences/tools/rules/memories across agents + machines. |
