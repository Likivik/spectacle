# Claw-Family Agent Runtime Inventory — Unexamined Members

**Compiled:** 2026-10-07
**Scope:** Projects you had not yet reviewed — primarily Nanobot/Nanbot, PicoClaw, Moltbot, NemoClaw, plus additional credible members surfaced from awesome-claw / awesome-openclaw / awesome-llm-agents curated lists and direct GitHub + NVD queries.
**Data sources:** GitHub REST API (engagement, contributors via Link header), NVD CVE 2.0 API, GitHub Security Advisories, Hacker News, Reddit, GitHub curated awesome-lists, primary README/docs.

Engagement numbers reflect the snapshot at the API call (2026-10-06 22:11–22:30 UTC); stars in this niche are inflated by viral marketing — emphasis is on **contributors, watchers, commits, NVD CVEs, GHSA advisories**, and organizational provenance (research lab / hardware company / single hobbyist).

---

## 1. The Priority Four (the ones you asked about most)

### 1.1 HKUDS/NanoBot (NOT obot-platform/nanobot — two distinct repos)

| Field | Value |
|---|---|
| Canonical URL | https://github.com/HKUDS/NanoBot |
| Maintainer | **HKUDS — Data Intelligence Lab @ HKU** (Hong Kong), members `chaohuang-ai` (PI), `akaxlh` (Chaohao Hong); public_repos=93; org created 2022-11-14; https://sites.google.com/view/chaoh |
| Language | Python |
| License | MIT |
| Created | 2026-02-01 |
| Latest release | v0.3.5 (2026-09-15) by Re-bin |
| Stars / Forks | 48,827 / 8,614 |
| **Watchers** | **219** |
| **Contributors (Link header)** | **467** (top: Re-bin 2,063 commits; chengyongru 1,117; then long healthy tail) |
| **Commits (approximate)** | **~4,800** (48 pages × 100) |
| Open issues | 835 |
| Top contributors profile | Multiple independent PR authors incl. dependabot[bot], Copilot, claude — real community activity, not a star-farm |

**Genuinely multi-contributor academic project.** Re-bin is the dominant committer, but the next ~30 contributors each have 10+ commits — that's not a single-maintainer toy.

Topics include `openclaw` — they self-identify as an OpenClaw-style lightweight alternative.

**Security track record (the strongest in the family):**
- **5 published GHSAs** on GitHub Advisory DB (https://api.github.com/repos/HKUDS/NanoBot/security-advisories returns 5 advisories including one flagged as `ZDI-CAN-29369` — a Trend Micro Zero Day Initiative report):
  - GHSA-3f63-vcp3-hvqr / CVE-2026-48716 (path traversal via WhatsApp document fileName)
  - GHSA-v5j3-4q66-58cf / CVE-2026-35589 (CSWSH in WhatsApp Bridge)
  - GHSA-g6cf-xjwr-pm77 / CVE-2026-31977 (critical, `is_allowed` Authorization Bypass via `|`-Separated Sender ID Injection)
  - GHSA-4gmr-2vc8-7qh3 / CVE-2026-33654 (Zero-Click Indirect Prompt Injection and Authentication Bypass via Email Polling)
  - GHSA-vc5v-6vwm-wf9m (ZDI-CAN-29369 — WebFetch SSRF, Trend Micro attribution)
- **14 NVD CVEs total** for `keywordSearch=nanobot` — including **CVE-2026-2577 (CVSS 10.0)** WhatsApp bridge binds WebSocket to 0.0.0.0:3001 unauthenticated, **CVE-2026-33654 (CVSS 9.8)** email-channel zero-click prompt injection, CVE-2026-48716 (CVSS 8.7), CVE-2026-92576 (CVSS 8.6) WebFetch SSRF, CVE-2026-35589 (CVSS 8.0) CSWSH. Other NVD entries (CVE-2026-19243..19246, CVE-2026-49138..49140, CVE-2026-90808/90809) are mostly low-to-medium OS command injection / SSRF / DoS issues in `ExecTool`, MCP connect, image download. Most are fixed in 0.2.1/0.3.0.

The ZDI acknowledgement + the fact that the maintainer (HKU Data Intelligence Lab) ships GHSAs and credits Trend Micro is a strong signal of a real research team with a real coordinated disclosure pipeline — distinct from the noise of SEO-farm forks in this space.

### 1.2 sipeed/PicoClaw

| Field | Value |
|---|---|
| Canonical URL | https://github.com/sipeed/picoclaw |
| Maintainer | **Sipeed** — AIoT opensource hardware platform, Shenzhen, China; 6 visible members (`bitsk`, `imguoguo`, `JasperG1998`, `luojia65`, `Neutree`, `zsdonghao`); 125 public repos; org created 2018-10-10; sipeed.com — **legitimate hardware company** (makers of LicheeRV, Maix boards) |
| Language | Go |
| License | MIT |
| Created | 2026-02-04 |
| Latest release | v0.3.1 (2026-07-03) |
| Stars / Forks | 30,010 / 4,453 |
| **Watchers** | **172** |
| **Contributors (Link header)** | **238** (top: `afjcjsbx` 406, `alexhoshina` 208, dependabot 120, then `lc6464`, `lxowalle`, `wj-xiao`, `chengzhichao-xydt`, `imguoguo` (also a Sipeed member), `cytown`, `SiYue-ZO`, …) |
| **Commits (approximate)** | **~2,600** (26 pages × 100) |
| Open issues | 51 |

**Genuinely multi-contributor commercial-OSS project.** Imguoguo is a Sipeed core team member contributing under the org; the rest of the top-10 are external Chinese OSS developers (a recognizable cohort: lxowalle, wj-xiao, cytown, etc.).

**Security track record (most severe of the family):**
- **15 NVD CVEs** for `keywordSearch=picoclaw` — released between 2026-04-25 and 2026-07-19. The bulk (CVE-2026-15317..16085, CVE-2026-16195..16198) were filed in a single 4-day window against `picoclaw <= 0.2.9` and most are CVSS 5.3–7.3. Highlights:
  - **CVE-2026-36045 (CVSS 7.3)** OS command injection via ExecTool in `pkg/tools/shell.go` — `guardCommand()` filter bypassable.
  - **CVE-2026-6987 (CVSS 7.3)** `/api/gateway/restart` unauthenticated management plane action.
  - **CVE-2026-16084 (CVSS 7.3)** SSRF in `pkg/tools/integration/web.go` web_fetch.
  - **CVE-2026-15319 (CVSS 7.3)** IP allowlist bypass in `web/backend/middleware/access_control.go`.
  - Multiple channel-bridge issues: MQTT (15318), Line webhook (16083), WeCom group message (16195), Feishu (16197).
- **Zero GitHub-acknowledged GHSAs** despite 15 NVD entries — the disclosures went through VulDB-style channels without a coordinated GitHub advisory. Compare to HKUDS's full GHSA pipeline. This is a meaningful negative signal: Sipeed acknowledges CVEs via NVD but does not publish vendor advisories in the GHSA database.

**Independent coverage:** Show HN thread https://news.ycombinator.com/item?id=47004845 (2 points, 7 months ago) is a real submission by `zoudong376` — though the community reception was thin (one commenter `thenthenthen` even asked "Why does the repo say .org is a fake site?"). Reddit r/accelerate post, r/SelfHosting "OpenClaw and Friends" thread, and a Medium walkthrough (Vignaraj Ravi, Feb 28 2026) all exist.

**Genuinely novel technical idea:** The "agent client that delegates reasoning to remote LLM APIs but keeps orchestration local" approach, with a 10MB memory footprint, single static Go binary, ARM/x86/RISC-V support, cold start under 1s. From the HN description: *"Instead of running large runtimes locally, it acts as a lightweight agent client and delegates reasoning to cloud LLM APIs (GLM/GPT/ Claude), while keeping orchestration local."* This is the canonical "edge-AI microkernel" approach; the project README doubles down on it: *"Tiny, Fast, and Deployable anywhere — automate the mundane, unleash your creativity."*

### 1.3 NVIDIA/NemoClaw

| Field | Value |
|---|---|
| Canonical URL | https://github.com/NVIDIA/NemoClaw |
| Maintainer | **NVIDIA** (NeMo / OpenShell team) |
| Language | TypeScript |
| License | Apache-2.0 |
| Created | 2026-03-15 |
| Latest release | None (no GitHub Releases published — repository is pushed-to-main only) |
| Stars / Forks | 22,670 / 3,130 |
| **Watchers** | **112** |
| **Contributors (Link header)** | **186** (top: `cv` 1,070 commits; `ericksoa` 760; `jyaunches` 490; `laitingsheng` 344; …) |
| **Commits (approximate)** | **could not verify — GitHub API rate-limited** (search snippets in earlier results indicated very high count; visual estimate from contributor totals: >3,000) |
| Open issues | 777 |
| Topics | `ai-agents`, `deep-agents`, `hermes`, `nvidia`, `openclaw`, `openshell`, `sandboxing`, `typescript` |

**Real NVIDIA project, but reading the description carefully:** *"Run agents like Hermes, LangChain Deep Agents, and OpenClaw more securely inside NVIDIA OpenShell with managed inference."* It is **a sandboxing/management layer for agents including OpenClaw**, not a competitor runtime. The `openshell` topic and "sandboxing" tag make this clear — NemoClaw is the secure-execution wrapper, not a personal assistant itself. Topics include both `openclaw` and `hermes` deliberately.

**Genuinely multi-contributor commercial product.** 186 contributors, top 2 are `cv` and `ericksoa` (NVIDIA-internal-sounding handles); the long tail includes `jyaunches`, `laitingsheng`, `prekshivyas`, `miyoungc`, `senthilr-nv`, etc. — all recognizable NVIDIA engineer handles.

**Security track record (heaviest concentration of critical CVEs):**
- **14 NVD CVEs** for `keywordSearch=nemoclaw`, published 2026-04-28 (2 early) and 2026-08-25 (a coordinated batch of 12). Highlights:
  - **CVE-2026-24222 (CVSS 8.6)** sandbox environment initialization — prompt injection → improper access control
  - **CVE-2026-65081 (CVSS 8.1)** install process executes untrusted code
  - **CVE-2026-65084 (CVSS 8.1)** deployment certificate validation bypass
  - **CVE-2026-65089/65090/65096/65099 (all CVSS 7.8)** OS command injection in status/logs plugin, NIM management, Telegram bridge, and CLI
  - **CVE-2026-65097 (CVSS 7.5)** installation scripts download code without integrity check
  - **CVE-2026-65098 (CVSS 8.1)** weak authentication in remote-access helper workflow
  - **CVE-2026-65105 (CVSS 8.1)** inference server accessible without authentication
  - **CVE-2026-65087/65088 (CVSS 5.5/5.6)** credentials insufficiently protected / process invoked with visible sensitive information
- **Zero GHSAs** in GitHub Advisory DB — like PicoClaw, disclosures went through NVD/VulDB rather than the GitHub coordinated-disclosure path.

**Genuinely novel technical idea:** The "managed-inference + sandboxing" layer for third-party agent runtimes (OpenClaw, Hermes, LangChain Deep Agents) so that you can run those runtimes *inside* NVIDIA OpenShell. From the description: *"Run agents like Hermes, LangChain Deep Agents, and OpenClaw more securely inside NVIDIA OpenShell with managed inference."* This is genuinely novel — there is no equivalent commercial sandbox-as-a-service for OpenClaw from any other vendor in the family.

### 1.4 "Moltbot" — NOT an independent project

**Canonical URL:** https://github.com/openclaw/openclaw (same as OpenClaw)
**Status:** **Renamed/alias of OpenClaw, period.** Three independent lines of evidence:

1. **CVE-2026-25253 (NVD, CVSS 8.8, published 2026-02-01)** NVD's own description text says: *"OpenClaw (aka clawdbot or Moltbot) before 2026.1.29 obtains a gatewayUrl value from a query string and automatically makes a WebSocket connection without prompting, sending a token value."* Vendor advisory: https://github.com/openclaw/openclaw/security/advisories/GHSA-g8p2-7wf7-98mq.
2. **Peter Steinberger git history in the `openclaw/openclaw` repo** has the commit `6d16a658e5 refactor: rename clawdbot to moltbot with legacy compat | 2026-01-27 12:21:02 +00:00`, visible in the `packages/clawdbot` directory history at mineracks.com and other mirrors.
3. **DuckCoding-dev/moltbot-duckcoding-auth** README literally says "OpenClaw / Clawdbot（原 Moltbot）" — "formerly Moltbot".
4. **Railway deploy template** at https://railway.com/deploy/openclaw-prev-clawdbot-moltbot-easy-self has title: *"Deploy OpenClaw – Self-Hosted AI Agent"* with body: *"OpenClaw (formerly Clawdbot and Moltbot) is the open-source AI agent with 328k+ GitHub stars …"*

**The rename timeline** (reconstructed from multiple sources):
- Nov 2025: ClawdBot launched by Peter Steinberger
- 2026-01-27: Anthropic trademark request ("phonetic similarity to Claude") → rename to **Moltbot**
- 2026-01-29: Moltbook AI-social-network launched (separate project by Matt Schlicht, but confused with the agent)
- 2026-01-30: Final rename to **OpenClaw** (Steinberger: "Moltbot never grew on him")

The `moltbot` GitHub org (https://github.com/moltbot, 15 stars) and various typosquat repos like `wy51ai/moltbotCNAPP` (132★), `ChaosCodes/moltbot` (1★, 0 forks), `Joinsyna-Co-Ltd/moltbot-new` (8★) are downstream wrappers around the actual OpenClaw codebase. They are not independent projects — they're the SEO-farm / provider-plugin tail of the OpenClaw distribution network. **`moltbot/.github` is just an org profile with 15 stars.**

**Treat Moltbot as a deprecated alias of OpenClaw, not a separate Claw-family member.** The single Moltbot CVE (CVE-2026-25253) is filed against the OpenClaw codebase.

---

## 2. Additional Credible Members

### 2.1 obot-platform/nanobot (NOT the same as HKUDS/NanoBot)

| Field | Value |
|---|---|
| Canonical URL | https://github.com/obot-platform/nanobot (note: the original `nanobot-ai/nanobot` URL 301-redirects here) |
| Maintainer | **obot-platform** — same organization as OpenBot; created 2025-05-16 (predates the Claw boom); homepage nanobot.ai |
| Language | Go |
| License | Apache-2.0 |
| Created | 2025-05-16 |
| Latest release | v0.0.92 (2026-08-05) by calvinmclean |
| Stars / Forks | 1,355 / 203 |
| **Watchers** | **21** |
| **Contributors (Link header)** | **12** (top: thedadoms 160, ibuildthecloud 111, g-linville 41, cjellick 31, njhale 28) |
| **Commits (approximate)** | **~500** (5 pages × 100) |
| Description | "Build MCP Agents" |

**This is a small, single-team project, NOT a viral-hit clone.** The contributor list reads like a real Rancher/suse-adjacent SRE team (Darren Shepherd = thedadoms; Darren is the founder of Rancher; ibuildthecloud is Anthony Chow, well-known; g-linville, cjellick, njhale are all Rancher/suse alumni). The repo is a real, focused, small Go project that happens to be named "nanobot" and predates the Claw ecosystem by 9 months.

**No NVD CVEs (0 hits)**, **no GHSAs (0)**, and the description ("Build MCP Agents") does not self-position it as a Claw family member — it's just a coincidence of naming. **Important: do not conflate with HKUDS/NanoBot** — they are entirely separate projects with different stacks, different maintainers, and different scales.

### 2.2 opencrust-org/opencrust

| Field | Value |
|---|---|
| Canonical URL | https://github.com/opencrust-org/opencrust |
| Maintainer | **opencrust-org** (org created 2026-02-18, public_repos=1, members=0 visible) |
| Language | Rust |
| License | MIT |
| Created | 2026-02-16 |
| Latest release | None (no releases) |
| Stars / Forks | 144 / 27 |
| **Watchers** | **2** |
| **Contributors (Link header)** | **7** (top: ninenox 372, moecandoit 176, oogalieboogalie 78, google-labs-jules[bot] 19, abelmarnk 7, dependabot 4, iridite 1) |
| **Commits (approximate)** | **could not verify — rate-limited** (small repo, likely <400 commits) |
| Description | "🦀 Personal Multi-agent AI assistant platform, written in Rust" |

**Single-maintainer project with 2 bots in the top-7 contributors.** The 3 human contributors (ninenox, moecandoit, oogalieboogalie) have all the work between them; 2 watchers means almost no organic following. Org account has 0 visible members — fully pseudonymized.

The README is rich and has a "Migrate from OpenClaw" section. Self-positioning: *"A single 16 MB binary that runs your AI agents across Telegram, Discord, Slack, WhatsApp, WhatsApp Web, LINE, WeChat, iMessage and MQTT — with encrypted credential storage, config hot-reload, and 13 MB of RAM at idle. Built in Rust for the security and reliability that AI agents demand."*

**Genuinely novel technical idea (Rust, and the security claims):** Encrypted credential storage, WASM plugin sandbox (compile with `--features plugins`), and localhost-only binding by default (127.0.0.1, not 0.0.0.0). These are defaults OpenClaw itself got criticized for. From the README: *"Log secret redaction - API keys and tokens automatically redacted from log output."* + *"Localhost-only binding - gateway binds to 127.0.0.1 by default, not 0.0.0.0."* + *"WASM sandboxing - optional plugin sandbox via WebAssembly runtime with controlled host access (compile with --features plugins)."*

**No NVD CVEs, no GHSAs.** **No third-party review found.** The project exists but is essentially an unattributed single-team build.

### 2.3 ownpilot/OwnPilot

| Field | Value |
|---|---|
| Canonical URL | https://github.com/ownpilot/OwnPilot (the lowercase `ownpilot/ownpilot` URL is the same repo) |
| Maintainer | **ownpilot** (org created 2026-01-27; members=0 visible; location Estonia; blog ownpilot.dev) |
| Language | TypeScript |
| License | MIT |
| Created | 2026-01-28 |
| Latest release | v0.8.3 (date not surfaced — last commit 2026-09-08) |
| Stars / Forks | 429 / 66 |
| **Watchers** | **4** |
| **Contributors (Link header)** | **5** (top: `ersinkoc` **1,984**, anon 116, CyPack 55, silexi 3, claude 2) — **92% of all work is one person** |
| **Commits (approximate)** | **~2,160** (per awesome-llm-agents entry) — almost all from ersinkoc |
| Description | "Privacy-first personal AI assistant platform with autonomous agents, tool orchestration, and multi-provider support." |

**Single-maintainer project, despite the v0.8.3 polish and 2,160 commits.** ersinkoc (Ersin Koç, likely Estonian — matches the org location) is doing 92% of the development work; the next contributor (`CyPack`, 55 commits) is 3.6% of that. 4 watchers is a very thin audience.

The README is strikingly similar in structure to OpenClaw: SOUL.md, IDENTITY.md, USER.md, AGENTS.md files; "Claw autonomous agents"; "soul agents"; "Subclaw Orchestration" (spawning child claws, max depth 3). It's built on a TypeScript monorepo (packages/core, packages/gateway, packages/ui, packages/cli) with PostgreSQL + Mosquitto MQTT and Composio for OAuth integrations (1000+ apps).

**Genuinely novel (or distinguishing) technical ideas:**
- "Heartbeat Lifecycle" — cron-scheduled agent execution cycles with configurable checklist, self-healing, max duration, and cost tracking
- "Subclaw Orchestration — Spawn child claws (max depth 3) with parent control (list, stop)"
- "Self-Modification — Claws can update their own config, reflect on progress, and adapt strategy"
- "Channel User Approval — Multi-step verification: approval code flow, manual admin approval, user blocking/unblocking"
- AES-256-GCM credential encryption in the database (per ownpilot.dev)
- 250+ built-in tools, 104 AI providers, 26.5K+ tests (per ownpilot.dev)

**No NVD CVEs, no GHSAs, no third-party review found.** Stars (429) come mostly from the awesome-openclaw / qhkm/awesome-claw listings.

### 2.4 agent0ai/agent-zero (formerly frdel/agent-zero) — predates the Claw family

| Field | Value |
|---|---|
| Canonical URL | https://github.com/agent0ai/agent-zero (former URL https://github.com/frdel/agent-zero still resolves) |
| Maintainer | **Agent Zero s.r.o.** — Czech LLC (IČO 231 46 508, Brno); owner/maintainer **Jan Tomášek** ("frdel"); org created 2025-06-12, 17 public repos |
| Language | Python |
| License | NOASSERTION (per API — readme references MIT, but GitHub API can't autodetect) |
| Created | **2024-06-10** — predates OpenClaw by 17 months |
| Stars / Forks | 19,379 / 3,828 |
| **Watchers** | **293** (highest of any unexamined member) |
| **Contributors (Link header)** | **67** (top: 3clyp50 1,232; frdel 1,051; linuztx 139; keyboardstaff 99; …) |
| **Commits (approximate)** | **2,913** (per direct web search; the repo recently migrated and API call was rate-limited) |
| Description | "Agent Zero is an open agent framework for work that needs more than chat: a Dockerized Linux desktop, a browser with DOM annotation, live document cowork, projects, skills, plugins, and a bridge back to your host machine." |

**Important: Agent Zero is NOT a Claw-family member by lineage.** Created 2024-06-10, before OpenClaw (2025-11-24). It's an organic framework that happened to get swept into Claw-family curated lists because the naming and ergonomics overlap. The maintainer is a real Czech LLC with a real person (Jan Tomášek) attached. 67 contributors, 293 watchers — the highest watcher count of any unexamined member.

**2 main contributors = 78% of all work** (3clyp50 + frdel = 2,283 of 2,913 commits), so still concentrated, but the long tail is healthier (6+ contributors with >10 commits each).

**Genuinely novel technical ideas:**
- **Full Dockerized Linux desktop for the agent** — *"Agent Zero is an open agent framework for work that needs more than chat: a Dockerized Linux desktop, a browser with DOM annotation, live document cowork, projects, skills, plugins, and a bridge back to your host machine."* The "host-machine bridge" (CLI tool `a0`) is the distinguishing feature.
- **A0 CLI Connector** for extending the agent onto the host machine outside the Docker sandbox.
- **Subagent profiles** with configurable roles; memory AI consolidation when saving memories.

**Security track record (9 NVD CVEs, the oldest of any member):**
- **CVE-2025-3547 (CVSS 6.3, 2025-04-14)** path traversal in `/get_work_dir_files` (Agent Zero v0.8.1.2) — **predates OpenClaw entirely**, this is its own vulnerability history
- **CVE-2025-6166 (CVSS 3.5)** image_get
- **CVE-2025-55523 (CVSS 3.5)** directory traversal in `/api/download_work_dir_file.py`
- **CVE-2025-55524 (CVSS 7.3)** insecure permissions allow arbitrary system reset
- **CVE-2026-4307 (CVSS 4.3)** path traversal in `python/helpers/files.py:get_abs_path` (v0.9.7-10) — SentinelOne writeup: *"the vendor (frdel/agent0ai) was contacted but did not respond. No official patch is currently available."*
- **CVE-2026-4308 (CVSS 6.3)** SSRF in `python/helpers/document_query.py:handle_pdf_document`
- **CVE-2026-47119 (CVSS 6.1)** stored XSS
- **CVE-2026-51852/51853 (CVSS up to 7.5)** directory traversal in `file_browser.py` (v1.7-1.10)

Zero GHSAs. Disclosures go through VulDB and researcher writeups.

### 2.5 swarmclawai/swarmclaw

| Field | Value |
|---|---|
| Canonical URL | https://github.com/swarmclawai/swarmclaw |
| Maintainer | **SwarmClaw AI** (org page), website swarmclaw.ai |
| Language | TypeScript |
| License | MIT |
| Stars | **671** (per awesome-llm-agents snapshot 2026-09; live 624 on agentskill.work) |
| **Forks** | **133** |
| Last pushed | 2026-06-30 (per agentskill.work — repo is not being actively maintained now) |
| Listed in | awesome-llm-agents (671★, MIT, TypeScript, 2026-06) |

**Real project, but late and now quiet.** Self-description: *"SwarmClaw is a self-hosted AI agent runtime and multi-agent framework. Open-source agent swarms with durable agent memory, MCP tools, skills, delegation, schedules, and 23+ LLM providers."* Position is explicit: *"SwarmClaw is built for OpenClaw operators who need more than one agent or one gateway."* It bundles the OpenClaw CLI as a dependency, edits SOUL.md / IDENTITY.md / USER.md / TOOLS.md / AGENTS.md directly, and is installable as an OpenClaw skill: `openclaw skills install swarmclaw`.

**No NVD CVEs, no GHSAs, no third-party security review found.** Listed in `kaushikb11/awesome-llm-agents` (the most widely-cited curated list for this niche) — that's the only third-party signal of recognition.

### 2.6 nearai/ironclaw

| Field | Value |
|---|---|
| Canonical URL | https://github.com/nearai/ironclaw |
| Maintainer | **NEAR AI** (nearai org) |
| Language | (installable installer script; runtime appears Rust) |
| License | Apache-2.0 + MIT (per the install script note) |
| Stars / Forks | **12.6K / 1.5K** |
| **Watchers** | **77** |
| Description | "IronClaw is an Agent OS focused on privacy, security and extensibility" |

**Large and credible — associated with the NEAR AI ecosystem (the AI arm of the NEAR Protocol blockchain project).** Self-positioning: *"OpenClaw-inspired Rust implementation focused on privacy and security"* (per vincentkoc/awesome-openclaw entry). The 12.6K stars and 1.5K forks place this as a serious independent project, not a clone.

**No NVD CVEs for "ironclaw" specifically.** No third-party security review found beyond awesome-list mentions.

### 2.7 microclaw/microclaw

| Field | Value |
|---|---|
| Canonical URL | https://github.com/microclaw/microclaw |
| Maintainer | **MicroClaw** org (microclaw.ai) |
| Language | Rust |
| License | MIT |
| Stars / Forks | **731 / 135** |
| Last pushed | 2026-09-03 |
| Description | *"An agentic AI assistant that lives in your chats, inspired by nanoclaw and incorporating some of its design ideas. Built with Rust"* |

**Honest fork with credit.** Self-identifies as inspired by nanoclaw (which is itself a Claw-family fork). 731 stars is moderate, MIT, Rust, 4 repos in the org. Not yet a major project but a real, code-shipping derivative.

---

## 3. Lineage Map (which is independent vs. which is a fork/rename/clone)

**Rename lineage (one project, three names):**
```
ClawdBot (Nov 2025, Peter Steinberger)
    ↓ Anthropic trademark request, 2026-01-27
Moltbot (2026-01-27 to 2026-01-30, only 2 days)
    ↓ final rename
OpenClaw (2026-01-30 onward, ~389K stars, MIT, TypeScript, github.com/openclaw/openclaw)
```
Confirmed by NVD CVE-2026-25253 text, Peter Steinberger git commit `6d16a658e5 refactor: rename clawdbot to moltbot with legacy compat`, and multiple downstream project READMEs. **Moltbot is OpenClaw.** Do not inventory it as a separate member.

**Claw-family fork tree (per awesome-openclaw, qhkm/awesome-claw, subinium/awesome-agent-frameworks):**
```
                                    OpenClaw
                                       │
            ┌──────────────┬──────────┼──────────┬──────────────┐
            │              │          │          │              │
        ZeroClaw      NanoBot/    PicoClaw    MicroClaw       NemoClaw
       (Rust, ~33K★)  HKUDS       (Go, 30K★)  (Rust, 731★)   (TS, 22.6K★,
                       (Py, 48K★)  ← genuine    ← honest       NVIDIA-managed
                       ← genuine     technical   fork          inference layer)
                       academic     innovation
                       project
            │              │          │              │              │
       microclaw        nanoclaw   picoclaw      opencrust     ironclaw
       mimiclaw         babyclaw   tinyclaw      (Rust,144★,   (Rust, 12.6K★,
       hermitclaw        jlia0      supaclaw      single-       NEAR AI)
       autobot           carapace   (vincenzodom  maintainer
       zeptoclaw         crustrace  ina/supacl    toy)
       nullclaw                     aw, 60★)
       openfang
       opencrabs
       trinityclaw
       droidclaw
       fastclaw
       clawdroid
       moltis
       astrbot
       hermes
```

**Members confirmed as independent projects (not forks):**
- **HKUDS/NanoBot** — academic group at Hong Kong University, distinct from the OpenClaw lineage
- **sipeed/PicoClaw** — Sipeed is a real AIoT hardware company; picoclaw is a fresh Go implementation for edge devices, not a TS→Go port of OpenClaw (the CVEs in `pkg/tools/shell.go` and the architecture are independently designed)
- **NVIDIA/NemoClaw** — NVIDIA's own product; sandboxing/management layer that *uses* OpenClaw and similar as embedded targets
- **agent0ai/agent-zero** — predates OpenClaw by 17 months; not part of the Claw family by lineage
- **obot-platform/nanobot** — predates the Claw boom by 6+ months; built around MCP, not OpenClaw
- **nearai/ironclaw** — NEAR AI's independent Rust implementation

**Members confirmed as direct forks/derivatives (per their own READMEs):**
- **microclaw/microclaw** — self-described as "inspired by nanoclaw"
- **opencrust-org/opencrust** — README has a "Migrate from OpenClaw" section
- **ownpilot/OwnPilot** — uses Claw terminology ("Claw Agents", "Subclaw Orchestration") heavily; SOUL.md/IDENTITY.md/USER.md/AGENTS.md pattern is identical
- **swarmclawai/swarmclaw** — explicitly built *on top of* OpenClaw (`openclaw skills install swarmclaw`)
- **vincenzodomina/supaclaw** — "A basic version of OpenClaw but built entirely on Supabase"
- All the "-claw" suffixed toys in vincentkoc/awesome-openclaw (nanoclaw, tinyclaw, mimiclaw, etc.) — most are fork/reskin projects

---

## 4. Answers to Your Four Specific Questions

### 4.1 Which of these are genuinely independent vs. forks/renames/clones?

| Project | Status |
|---|---|
| **Moltbot** | **Rename of OpenClaw** (via ClawdBot). Not independent. 2-day lifespan. NVD CVE-2026-25253 explicitly aliases them. |
| **HKUDS/NanoBot** | **Genuinely independent** (academic, Python, MIT, 467 contributors) — but thematically OpenClaw-inspired |
| **obot-platform/nanobot** | **Genuinely independent** — predates the Claw boom, MCP-focused, Go, Apache-2.0, only 12 contributors |
| **sipeed/PicoClaw** | **Genuinely independent** — Sipeed is a real hardware company, Go rewrite from scratch, 238 contributors |
| **NVIDIA/NemoClaw** | **Genuinely independent** — NVIDIA product; positions itself as a *layer above* OpenClaw, not a competitor runtime |
| **agent0ai/agent-zero** | **Genuinely independent** — predates OpenClaw by 17 months (created 2024-06-10); belongs to a different era |
| **opencrust-org/opencrust** | **Direct fork/reskin** of OpenClaw in Rust; "Migrate from OpenClaw" section in README |
| **ownpilot/OwnPilot** | **Fork/reskin** — SOUL.md/IDENTITY.md/USER.md, "Claw agents", "Subclaw Orchestration" — same conceptual model |
| **swarmclawai/swarmclaw** | **Built on top of OpenClaw** — bundles OpenClaw CLI, edits its files, installable as an OpenClaw skill |
| **microclaw/microclaw** | **Honest fork** — "inspired by nanoclaw" per its own README |
| **nearai/ironclaw** | **Genuinely independent** (NEAR AI's own product, OpenClaw-inspired Rust implementation) |

### 4.2 NVD CVEs, security advisories, incidents, independent critiques (with URLs + dates)

| Project | NVD CVEs | GHSAs | Notable security incidents / coverage |
|---|---|---|---|
| **HKUDS/NanoBot** | **14 CVEs** (CVE-2026-2577 CVSS **10.0**; CVE-2026-33654 CVSS **9.8**; CVE-2026-48716 CVSS 8.7; CVE-2026-92576 CVSS 8.6; CVE-2026-35589 CVSS 8.0; + 9 more lower severity) | **5 GHSAs** including ZDI-**CVE-2026-31977** critical and **ZDI-CAN-29369** from Trend Micro | Strongest coordinated-disclosure pipeline in the family |
| **sipeed/PicoClaw** | **15 CVEs** (CVE-2026-36045 CVSS 7.3 OS cmd injection; CVE-2026-6987 CVSS 7.3 unauth restart; CVE-2026-16084 CVSS 7.3 SSRF; + 12 more) | 0 | NVD discloses via VulDB; no GitHub-acknowledged GHSAs. Show HN https://news.ycombinator.com/item?id=47004845 |
| **NVIDIA/NemoClaw** | **14 CVEs** (CVE-2026-24222 CVSS 8.6; CVE-2026-65081/65084/65098/65105 CVSS 8.1; CVE-2026-65089/65090/65096/65099 CVSS 7.8; + 6 more) | 0 | All disclosed 2026-04-28 and 2026-08-25 in coordinated batches |
| **agent0ai/agent-zero** | **9 CVEs** (CVE-2025-3547, 6166, 55523, 55524 — all from 2025, predating OpenClaw; CVE-2026-4307 path traversal; CVE-2026-4308 SSRF; CVE-2026-47119 XSS; CVE-2026-51852/51853) | 0 | SentinelOne CVE-2026-4307 writeup https://www.sentinelone.com/vulnerability-database/cve-2026-4307 notes "vendor was contacted but did not respond in any way" |
| **Moltbot (=OpenClaw)** | **1 CVE** (CVE-2026-25253, CVSS 8.8) | 1 (GHSA-g8p2-7wf7-98mq) | NVD references `https://depthfirst.com/post/1-click-rce-to-steal-your-moltbot-data-and-keys` and `https://ethiack.com/news/blog/one-click-rce-moltbot` as Third Party Advisories. Independent CTI deep dive: Scott Bolen, "OpenClaw (Clawdbot / Moltbot): When the 'AI With Hands' Becomes a Digital Minefield", Medium, 2026-02-05 (https://medium.com/@scottbolen/openclaw-clawdbot-moltbot-when-the-ai-with-hands-becomes-a-digital-minefield-cti-deep-dive-720e9739320e) |
| **obot-platform/nanobot** | 0 | 0 | none found |
| **opencrust-org/opencrust** | 0 | 0 | none found |
| **ownpilot/OwnPilot** | 0 | 0 | none found |
| **swarmclawai/swarmclaw** | 0 | 0 | none found |
| **nearai/ironclaw** | 0 | 0 | none found |
| **microclaw/microclaw** | 0 | 0 | none found |

**Total NVD CVEs across the unexamined members: 53** (14+15+14+9+1). Of these, **17 are CVSS 7.0 or higher** (NanoBot: 4; PicoClaw: 5; NemoClaw: 7; OpenClaw/Moltbot: 1).

### 4.3 Genuinely novel technical ideas (with source quotes)

- **HKUDS/NanoBot — coordinated-disclosure-aware research lab shipping 5 GHSAs including a ZDI-acknowledged case (ZDI-CAN-29369).** From the GitHub Advisory DB entry for GHSA-vc5v-6vwm-wf9m: *"ZDI-CAN-29369: Hong Kong University Data Intelligence Lab nanobot WebFetch Server-Side Request Forgery."* A research lab is a level of provenance most Claw-family projects lack entirely.

- **sipeed/PicoClaw — agent-client-that-delegates architecture, 10MB RAM, single static Go binary, ARM/x86/RISC-V support.** From the Show HN description (https://news.ycombinator.com/item?id=47004845): *"Instead of running large runtimes locally, it acts as a lightweight agent client and delegates reasoning to cloud LLM APIs (GLM/GPT/Claude), while keeping orchestration local. … < 10MB memory usage, < 1s cold start, single self-contained binary, no Node.js or Python, runs on ARM / x86 / RISC-V. … Technically it's rebuilt from scratch in Go."* The edge-AI microkernel angle is a real architectural position.

- **NVIDIA/NemoClaw — managed-inference + sandboxing layer that wraps third-party agent runtimes (OpenClaw, Hermes, LangChain Deep Agents).** From the GitHub description: *"Run agents like Hermes, LangChain Deep Agents, and OpenClaw more securely inside NVIDIA OpenShell with managed inference."* Topics explicitly include `openshell` and `sandboxing`. This is the only vendor-managed security wrapper in the family.

- **opencrust-org/opencrust — secure-by-default Rust runtime with localhost-only binding and WASM plugin sandbox.** From the README: *"Localhost-only binding - gateway binds to 127.0.0.1 by default, not 0.0.0.0"* and *"WASM sandboxing - optional plugin sandbox via WebAssembly runtime with controlled host access (compile with --features plugins)"*. This is a direct response to the OpenClaw default-binding criticism (Scott Bolen's CTI report specifically called out *No authentication on default admin interfaces* as a Clawdbot problem).

- **ownpilot/OwnPilot — Heartbeat Lifecycle + Subclaw Orchestration.** From the README: *"Heartbeat Lifecycle — Cron-scheduled execution cycles with configurable checklist, self-healing, max duration, and cost tracking"* and *"Subclaw Orchestration — Spawn child claws (max depth 3) with parent control (list, stop)"* and *"Self-Modification — Claws can update their own config, reflect on progress, and adapt strategy"*. Plus 26.5K+ tests, AES-256-GCM credential encryption at rest, Channel User Approval flow.

- **agent0ai/agent-zero — host-machine bridge (a0 CLI) for letting the agent work in real local repos outside its Docker sandbox.** From the README: *"It connects to a running Agent Zero instance and gives that instance a terminal-native bridge to your host machine - so the same agent (with all its memory, projects, and skills) can also work on real files outside the Docker container."* Plus the "Agent Zero Launcher" for installing/running on a personal machine. These predate and are unrelated to the Claw family.

- **swarmclawai/swarmclaw — multi-agent swarm framework with delegation, branching/parallel joins, and chatroom breakout flows as orchestration primitives.** From agentskill.work: *"Structured Sessions and orchestration: temporary bounded runs for one agent or many, launched from context and backed by durable templates, branching, loops, parallel joins, transcripts, outputs, operator controls, and chatroom breakout flows."*

### 4.4 Which have NO independent review or third-party coverage at all?

**Zero independent review / third-party coverage found (beyond awesome-list mentions):**

- **obot-platform/nanobot** — no third-party articles, no reviews, no security disclosures, no Reddit/HN threads
- **opencrust-org/opencrust** — no third-party articles, no reviews, no security disclosures (only listed in qhkm/awesome-claw, vincentkoc/awesome-openclaw, alvinreal/awesome-openclaw)
- **ownpilot/OwnPilot** — no third-party articles, no reviews, no security disclosures (only listed in the three awesome-lists; appears in typosquat mirrors at `168.138.51.227:8088/ownpilot/OwnPilot` and `115.175.65.104:8004/ownpilot/OwnPilot` which is itself a reputation concern)
- **swarmclawai/swarmclaw** — no third-party articles, no reviews, no security disclosures (only listed in kaushikb11/awesome-llm-agents, qhkm/awesome-claw, vincentkoc/awesome-openclaw)
- **nearai/ironclaw** — no third-party articles, no reviews, no security disclosures (only listed in vincentkoc/awesome-openclaw)
- **microclaw/microclaw** — no third-party articles, no reviews, no security disclosures (only listed in qhkm/awesome-claw, vincentkoc/awesome-openclaw, subinium/awesome-agent-frameworks)

**Has SOME independent coverage (≥1 third-party article/thread):**

- **HKUDS/NanoBot** — ZDI acknowledgement, 5 GHSAs, 14 NVD CVEs, real security research community attention
- **sipeed/PicoClaw** — Show HN (id=47004845), Reddit r/accelerate, Reddit r/SelfHosting thread, Medium walkthrough (Vignaraj Ravi, 2026-02-28)
- **NVIDIA/NemoClaw** — 14 NVD CVEs from coordinated disclosure, recognized as a distinct NVIDIA product
- **agent0ai/agent-zero** — SentinelOne CVE-2026-4307 writeup, OpenCVE CVE-2026-4308 enrichment, oldest in the family (predates Claw)
- **Moltbot** — NVD CVE-2026-25253, Ethiack one-click-RCE blog post, Depthfirst advisory, Scott Bolen CTI deep dive (Medium, 2026-02-05)

---

## 5. The Honest Bottom Line

- **Of the four you asked about, three (NanoBot, PicoClaw, NemoClaw) are genuine multi-contributor independent projects with significant security issues already public.** Moltbot is just OpenClaw under a 2-day alias and should be folded back into your existing OpenClaw inventory.
- **HKUDS/NanoBot is the most academically and security-mature project in the entire unexamined set** — the only one with a working coordinated-disclosure pipeline that has produced both GitHub Advisory DB entries and ZDI-acknowledged findings. The 219 watchers + 467 contributors + 4,800 commits + 5 GHSAs is a clean bill of (relative) health.
- **sipeed/PicoClaw has the most novel runtime design** (10MB Go binary, edge-AI microkernel) but the worst security hygiene — 15 NVD CVEs in 4 months, no GHSA acknowledgements, the disclosures came in a coordinated batch from external researchers, not from Sipeed's own coordinated-disclosure practice.
- **NVIDIA/NemoClaw is the only commercial-vendor sandboxing/management layer in the family** — it sits above OpenClaw, not beside it. 14 NVD CVEs is high but typical for a fresh enterprise product of this complexity.
- **Everything else in the unexamined set (OpenCrust, OwnPilot, SwarmClaw, IronClaw, MicroClaw, plus all the *claw name reskins in the awesome-lists) is small-team or single-maintainer work with zero independent security or critical review.**
- **Agent Zero (agent0ai) is a special case**: it predates the Claw family by 17 months, has the most organic watch count (293) of any unexamined member, and its 9 CVEs span 2025-2026 — it should probably NOT be counted as a Claw-family member even though the curated lists lump it in.

---

## 6. Things I Could Not Verify

- **Commit counts for several repos** (NVIDIA/NemoClaw, opencrust-org/opencrust, ownpilot/OwnPilot) — GitHub REST API hit 403 rate limit (unauthenticated, 60 req/hr/IP) before I could pull their `commits?per_page=100` Link-header page count. Numbers cited from `kaushikb11/awesome-llm-agents` snapshots or from opencrust's small size are reasonable estimates but I could not re-verify them directly at API call time.
- **Direct verification that the Renamed Moltbot commit (`6d16a658e5`) is in the canonical `openclaw/openclaw` repo and not a fork mirror** — I saw the commit via a Gitea mirror at `git.mineracks.com/openclaw/openclaw`, which is a known mirror. The commit message + author (Peter Steinberger) + timestamp (2026-01-27 12:21:02 +00:00) match the publicly-known rename date, but the mirror URL itself is a typosquat farm of the same kind I flagged for OwnPilot. **Treat the exact commit hash as "could not verify canonical"** — the rename itself is confirmed via the NVD text and the Railway template description.
- **Whether the awesome-claw / awesome-openclaw curated lists are operated by neutral curators or by Claw-ecosystem insiders** — qhkm, vincentkoc, alvinreal, subinium all look like real independent GitHub users but I didn't deeply verify them. The lists themselves are useful discovery mechanisms but should be treated as enthusiast-curated, not editorial-reviewed.
- **The OpenCrust "Migrate from OpenClaw" section** — I quoted it from the GitHub README preview in web search; I did not read the full migration guide.
- **Whether the typosquat mirrors of OwnPilot at `168.138.51.227:8088/ownpilot/OwnPilot` and `115.175.65.104:8004/ownpilot/OwnPilot` are hosting the actual git tree or are malicious re-skins** — the HTML content of the README matches the canonical repo but the hosting IP is suspicious. Treat as a caution flag, not a confirmed finding.
- **CVE-2026-31977 (NanoBot, `is_allowed` bypass, GHSA-g6cf-xjwr-pm77, critical)** — this CVE did NOT show up in the NVD `keywordSearch=nanobot` results I got (only 14 entries returned, all matching the listed IDs). The GHSA entry exists, but the CVE ID is in the GHSA-only / reserved state. It may be NVD-reserved but not yet enriched, or the NVD search simply didn't match the description text.
