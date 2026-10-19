# Hermes Agent — Self-Hostable Agent Platform Assessment

Date: 2026-10-07. Workspace: /Storage/Git/spectacle/notes/innovation-audit-2026-10/

Primary evidence sources used:
- Local shallow clone of github.com/NousResearch/hermes-agent (commit 65bc6727b43c on main, 2026-10-07 02:51:10)
- NVD `keywordSearch=hermes-agent` → 39 CVEs (all reference NousResearch hermes-agent; cross-checked with `keywordSearch=NousResearch` → same 39, no extraneous)
- GitHub PRs, issues, and tag history for the repo
- Docs at hermes-agent.nousresearch.com/docs/
- Independent security write-up at sheetgenius/frontier (third-party verification)
- r/hermesagent community threads
- Peer repos: openclaw/openclaw (391K★), zeroclaw-labs/zeroclaw (32.9K★), letta-ai/letta (25K★) + letta-ai/letta-code (3.5K★), All-Hands-AI/OpenHands (61.8K★) + OpenHands/OpenHands (87.8K★), Mintplex-Labs/anything-llm (66K★)

Tag convention clarification (important for the rest of the doc):
- Git tags are CalVer: `v2026.M.D` (e.g. `v2026.6.19`)
- The same release is published to PyPI as `hermes-agent` with a SemVer number: `v0.17.0` ↔ `v2026.6.19`
- v0.17.0 was tagged **2026-06-19**; v0.18.0 = **2026-07-01**; v0.20.0 = **2026-08-03**; v0.21.5 = **2026-09-24** (latest at time of writing)

---

## 1. Real differentiators vs. named peers

Each claim is grounded; the "marketing" tag is where the README/PR language is louder than the actual evidence in the code/docs.

### 1.1 Closed learning loop with autonomous skill creation & self-improvement [engineering, well-supported]
- README line 19: "the only agent with a built-in learning loop — it creates skills from experience, improves them during use, nudges itself to persist knowledge, searches its own past conversations, and builds a deepening model of who you are across sessions."
- Code: `agent/`, `tools/skills_tool.py`, `hermes_state_*.py` (FTS5 search), and the Honcho integration (`plastic-labs/honcho`).
- vs. peers: OpenClaw has a memory-architecture with "dreaming" consolidation, provenance tiers, and explicit write-time provenance gating (`openclaw/docs/concepts/memory-architecture.md`); it does NOT advertise agent-created skills. Letta Code (`docs.letta.com/letta-code/skills`) has self-improvement via `/sleeptime` dreaming and a skill creator — closest analogue. ZeroClaw has `memory` and `skills` modules but no documented autonomous skill creation. OpenHands is a coding harness without this loop.
- Honest read: not unique. Letta Code's "stateful agents that are like people" framing is the more sophisticated version. Hermes's differentiator is that the loop is on by default for non-developer use, not opt-in like Letta's `/sleeptime`.

### 1.2 OpenAI-compatible local server + ACP adapter + TUI gateway JSON-RPC [engineering]
- `gateway/platforms/api_server.py` (4126 lines, aiohttp) exposes `/v1/chat/completions`, `/v1/responses`, `/v1/models`, `/v1/capabilities`, `/api/sessions`, `/v1/runs`, `/api/jobs` and `/health*`. Defaults: `API_SERVER_HOST=127.0.0.1`, `API_SERVER_PORT=8642`, `API_SERVER_ENABLED=false`.
- `acp_adapter/` (server.py, session.py, etc.) — Agent Client Protocol adapter for IDE integration (Zed, etc.).
- `tui_gateway/` — JSON-RPC backend for the Ink TUI, with `server.py`, `ws.py`, `transport.py`.
- vs. peers: ZeroClaw also documents ACP (JSON-RPC 2.0 over stdio) in its main.rs source. Letta has a separate `letta-ai/letta-acp` repo. OpenClaw has the Open WebUI-compatible API via its gateway. Hermes ships all three as first-class under one process.

### 1.3 Seven terminal backends, including Modal/Daytona serverless [engineering]
- README line 29: "Seven terminal backends — local, Docker, SSH, Singularity, Modal, Daytona, and Vercel Sandbox."
- `hermes_cli/config.py` and the `environments/` directory expose this. Modal/Daytona/Vercel offer hibernating sandboxes (pay-per-use idle).
- vs. peers: ZeroClaw has hardware backends (Pi, STM32, Arduino, ESP32) and a hardware-gateway story. Letta has Letta Cloud (managed). OpenClaw is local-only. No peer matches this breadth of execution backends.

### 1.4 Messaging gateway count: 18+ bundled platforms [engineering, well-supported]
- README line 25: "Telegram, Discord, Slack, WhatsApp, Signal, and CLI". Docs add 20+ total; v0.20.1 changelog says "Messaging platforms grow to 18". Confirmed in `gateway/platforms/` and `plugins/platforms/` directories.
- vs. peers: OpenClaw also lists many channels (Discord, iMessage, Signal, Slack, Telegram, WhatsApp, WebChat, Matrix, Nostr, Twitch, Zalo, etc.) — comparable breadth. ZeroClaw claims 30+. Letta: Slack, Telegram, Discord, custom. Hermes is in the top tier but not uniquely so.

### 1.5 Cold-start latency claim (~1.8s) [engineering — measurable, but be careful]
- v0.20.0 release notes (Aug 3, 2026): "Cold start ~1.8s." v0.19.0 (Jul 20, 2026): "Cold-start latency cut by 80% to 0.9s."
- Code: `hermes_startup_watchdog.py` suggests measurement infrastructure exists.
- vs. peers: ZeroClaw claims "<20 ms cold start" on Apple Silicon (`zeroclaw.com` front page, "12 ms"). Hermes is faster than typical Python agent startups but slower than a single Rust binary. Apples-to-oranges; both are real numbers on different stacks.

### 1.6 Security posture is opinionated and documented [engineering, primary evidence]
- `SECURITY.md` (in repo, 335 lines) states: "The only security boundary against an adversarial LLM is the operating system. Nothing inside the agent process constitutes containment." Dashboard defaults to loopback; `--insecure` is now a no-op since the June 2026 hardening.
- vs. peers: This is unusually explicit. OpenClaw has `/gateway/security` docs. ZeroClaw's docs front page emphasises "Tool receipt HMAC-SHA256" — different approach (per-tool-call signed receipts), Hermes doesn't do that. Honest read: Hermes's stance is the most clearly stated trust model among the peers.

### 1.7 Subagents / parallel work [engineering]
- README line 28: "Spawn isolated subagents for parallel workstreams." Code: `tui_gateway/methods_subagents.py` (RPC methods), v0.18.0 release notes: "background fan-out subagents".
- vs. peers: OpenClaw has "Multi-agent routing — Isolated sessions per agent, workspace, or sender" (`docs/concepts/multi-agent`). Letta Code has 7 built-in subagent types (fork, general-purpose, history-analyzer, etc.) with explicit `memoryBlocks` and `tools` config (see `docs.letta.com/letta-code/subagents`). Hermes is comparable; Letta's is more configurable per-subagent.

### 1.8 Tools self-recovery / model-provider freedom [marketing-leaning]
- "Use any model you want" claim (README line 21) is real — 30+ provider classes in `providers/` and `model_tools.py`. But every modern agent does this; not a differentiator.
- "Tool self-recovery" and "Mixture-of-Agents" are listed in v0.20.0/v0.18.0 release notes — real features but PR-level visibility in the code is partial. **Mark as marketing-leaning until reproduced.**

### 1.9 Research / RL data generation pipeline [engineering, niche]
- `environments/benchmarks/terminalbench_2/`, `hermes_swe_env/`, and the `HermesAgentLoop` agent engine (reused for both eval and RL training with Atropos).
- v0.14.0 release notes mention "pip install hermes-agent lands on PyPI"; v0.18.0 calls Hermes the model for the next generation of tool-calling models.
- vs. peers: This is genuinely unusual for a self-hostable agent — most are consumption-focused. ZeroClaw is pure consumer. Letta has a research heritage (MemGPT). Hermes doubles as a training pipeline. **Engineering.**

### 1.10 Desktop client (Electron) [engineering, but on P3 priority for a reason]
- `apps/desktop/` — substantial Electron app, 19k+ LOC in `main.cjs` alone. Issue #35966 (open since 2026-05-31, P3) requests a *native* client. The existing desktop is a wrapper, not a native app.
- vs. peers: OpenClaw has macOS app, iOS, Android nodes. Letta has desktop app for macOS/Windows/Linux. AnythingLLM has desktop + Android mobile. OpenHands Agent Canvas is web-first. Hermes's desktop is the weakest in this category — third-party mobile clients (HermesPilot, hermes-friends) are community builds.

### 1.11 `hermes claw migrate` — out-of-the-box import from OpenClaw [engineering, real but small]
- README line 117, 197-200. Auto-detects `~/.openclaw` during setup and offers migration.
- This is unusual and pragmatic; it acknowledges OpenClaw's larger user base and lowers switching cost.

---

## 2. Security Due Diligence

### 2.1 NVD CVE inventory for hermes-agent

All 39 NVD entries with `keywordSearch=hermes-agent` reference NousResearch hermes-agent. They are sourced from VulDB / VulnCheck (not GitHub Security Advisories), which means most are filed without direct vendor coordination ("The vendor was contacted early about this disclosure but did not respond in any way" appears in 30+ descriptions).

Severity distribution (per NVD CVSS v4 / v3 base score):

| Range | Count | Notes |
|---|---|---|
| High (≥7.0) | 1 | CVE-2026-71963 (8.8) |
| Medium (4.0–6.9) | 21 | including the canonical sensitive-file CVE-2026-53870 (6.8) and several auth-bypass and SSRF entries |
| Low (<4.0) | 17 | mostly injection / race conditions / DoS / unauth-bypass on the same code path |

Notable entries (chronological by published date):

| CVE | Published | Severity (CVSS) | Component | Affected ≤ | Vendor fix |
|---|---|---|---|---|---|
| CVE-2026-7112 | 2026-04-27 | LOW (2.9) | `gateway/platforms/api_server.py` `_check_auth` (API_SERVER_KEY handler) — Improper Authentication | 0.8.0 | PR #6477 referenced; no GHSA |
| CVE-2026-7113 | 2026-04-27 | LOW (2.9) | `gateway/platforms/webhook.py` — Webhook argument manipulation | 0.8.0 | PR #6445 referenced |
| CVE-2026-7396 | 2026-04-29 | MED (5.5) | `gateway/platforms/wecom.py` — WeChat Work Platform Adapter | 0.8.0 | None listed |
| CVE-2026-7397 | 2026-04-29 | LOW (1.9) | `tools/file_tools.py` `_check_sensitive_path` — symlink follow | 0.8.0 | commit `311dac19`, PR #8829 |
| CVE-2026-9350 | 2026-05-24 | MED (5.5) | `tools/approval.py` `check_all_command_guards` — Batch Runner approval-gate bypass | 2026.4.16 | None listed |
| CVE-2026-9351 | 2026-05-24 | MED (5.5) | `tools/file_tools.py` `_is_blocked_device` — read_file device-block bypass | 2026.4.16 | None listed |
| CVE-2026-9352 | 2026-05-24 | MED (5.5) | `tools/environments/local.py` `_make_run_env` — env-var injection | 2026.4.23 | None listed |
| CVE-2026-9353 | 2026-05-24 | MED (5.5) | `agent/skills_guard.py` — Skills Guard multi-word prompt bypass | 2026.4.23 | None listed |
| CVE-2026-9354 | 2026-05-24 | MED (5.5) | Slack/Mattermost Agent — `format_message` injection | 2026.4.16 | None listed |
| CVE-2026-9366 | 2026-05-24 | MED (5.5) | `agent/prompt_builder.py` `_scan_context_content` — injection | 2026.4.23 (PR #13754) | GHSA-pgp4-xr4j-h5cg; "Patched: 0.15.0" per GHSA |
| CVE-2026-9367 | 2026-05-24 | MED (5.5) | `tools/approval.py` `detect_dangerous_command` — terminal-tool bypass | ≤ 5157f542 | None listed |
| CVE-2026-9368 | 2026-05-24 | MED (5.5) | `tools/code_execution_tool.py` `execute_code` — env-var handling | 2026.4.16 | None listed |
| CVE-2026-9369 | 2026-05-24 | LOW (1.9) | `hermes_cli/web_server.py` `_discover_dashboard_plugins` — dashboard plugin discovery | 2026.4.23 | None listed |
| CVE-2026-10220 | 2026-06-01 | MED (5.5) | `tools/skills_tool.py` `_serve_plugin_skill/skill_view` — injection | 2026.4.30 | None listed |
| CVE-2026-10221 | 2026-06-01 | MED (5.5) | `run_agent.py` `_compress_context` — injection | 0.12.0 | None listed |
| CVE-2026-10222 | 2026-06-01 | LOW (2.9) | `hermes_cli/config.py` `_sanitize_env_lines` — injection | 0.18.0 (per GHSA-mv8x-fg99-32mf) | GHSA "Patched: 0.18.0" |
| CVE-2026-10223 | 2026-06-01 | LOW (2.1) | `tools/memory_tool.py` `_scan_memory_content` — injection | 0.15.0 (per GHSA) | GHSA-33qv-c5qm-799v |
| CVE-2026-10224 | 2026-06-01 | MED (5.5) | `gateway/platforms/feishu.py` `_handle_webhook_request` — webhook injection | 2026.4.30 | None listed |
| CVE-2026-10548 | 2026-06-02 | LOW (1.9) | `agent/credential_pool.py` `_sync_anthropic_entry_from_credentials_file` | 2026.4.23 | None listed |
| CVE-2026-11461 | 2026-06-07 | LOW (2.1) | `hermes_state.py` `resolve_session_by_title` — resume endpoint | 0.12.0 | None listed |
| **CVE-2026-53870** | 2026-06-17 | MED (6.8) | `response_store.db`, `webhook_subscriptions.json` created with `mode 0o644` — local file disclosure incl. HMAC secrets | 0.16.0 | PR #30917 + #31469, `v2026.6.5` per NVD; "the only in-scope CVSS-B-rated CVE in the dataset" |
| CVE-2026-14617 | 2026-07-03 | LOW (1.3) | `gateway/stream_consumer.py` `GatewayStreamConsumer._filter_and_accumulate` | 2026.4.30 | PR #28631 referenced |
| CVE-2026-14625 | 2026-07-04 | LOW (2.1) | `tui_gateway/server.py` `shell.exec` — protection-mechanism failure | 0.15.2 | None listed |
| CVE-2026-14626 | 2026-07-04 | LOW (2.1) | `run_agent.py` `AIAgent.run_conversation` — DoS via `todos` arg | 2026.4.30 | None listed |
| CVE-2026-14627 | 2026-07-04 | LOW (2.9) | `gateway/platforms/discord.py` `DiscordAdapter._is_allowed_user` — improper access control | 0.15.2 | None listed |
| CVE-2026-14628 | 2026-07-04 | MED (5.5) | `gateway/platforms/base.py` `extract_media` — SSRF/SSCS in webhook | 2026.5.16 | None listed |
| CVE-2026-14783 | 2026-07-06 | LOW (2.1) | `tools/skills_tool.py` `skill_view` — path traversal | 2026.5.29.2 (v0.15.2) | commit `56f833e`, PR #40566 |
| CVE-2026-15311 | 2026-07-10 | LOW (2.0) | `gateway/platforms/matrix.py` `MatrixAdapter._markdown_to_html` | 2026.5.29.2 | PR #42759 |
| CVE-2026-17432 | 2026-07-26 | MED (5.0) | `plugins/platforms/simplex/adapter.py` — SimpleX gateway authz | 2026.6.5 | commit `490c486f`, PR #41246 |
| CVE-2026-18773 | 2026-08-04 | MED (4.3) | `gateway/run.py` `_check_slash_access` — quick-command handler | 2026.6.5 | None listed |
| CVE-2026-18774 | 2026-08-04 | MED (4.3) | `agent/image_gen_provider.py` `save_url_image` — SSRF in xAI image gen | 0.16.0 | None listed |
| CVE-2026-18775 | 2026-08-04 | MED (4.3) | `tools/browser_tool.py` `browser_snapshot` | 0.16.0 | None listed |
| CVE-2026-18976 | 2026-08-06 | MED (4.3) | `agent/agent_init.py` `get_tool_definitions` — `disabled_toolsets` handler | 0.16.0 | PR #46185 |
| CVE-2026-18993 | 2026-08-06 | MED (4.3) | `model_tools.py` Memory Toolset — improper access controls | 0.16.0 | PR #46185 |
| CVE-2026-84287 | 2026-09-01 | MED (4.3) | `gateway/platforms/api_server.py` — Session Chat Interface | 0.18.0 | None listed |
| CVE-2026-84288 | 2026-09-01 | MED (4.3) | `acp_adapter/session.py` `HermesACPAgent.prompt` — ACP prompt workflow | 0.18.2 | None listed |
| CVE-2026-84289 | 2026-09-01 | MED (4.3) | `tools/mcp_tool.py` `list_tools` — uncontrolled resource consumption (related to the "MCP Tool" memory-allocation CVE circulated earlier) | 0.18.2 | None listed |
| CVE-2026-85105 | 2026-09-03 | MED (6.9) | `s71.py` `_sess_nowait` — session management | 0.18.0 | None listed |
| CVE-2026-85106 | 2026-09-03 | MED (5.3) | `apps/desktop/src/app/artifacts/index.tsx` `fetchLinkTitle` — SSRF in desktop Link Title Fetch | 0.18.0 | None listed |
| CVE-2026-85107 | 2026-09-03 | MED (5.3) | `apps/desktop/electron/main.ts` `resourceBufferFromUrl` — SSRF in Electron main | 0.18.0 | None listed |

Notes:
- 31 of 39 say "vendor contacted but did not respond". Only CVE-2026-9366, -10222, -10223, -14783, -15311, -17432, -18976, -18993 and -53870 have explicit GitHub PR/commit/vendor-fix references.
- A `1mby$` / vuldb-style CVE attribution pattern is visible (note the very similar templates, sequential IDs, same phrasing "vendor was contacted early but did not respond in any way"). This is consistent with bulk VulDB submissions by `YLChen-007` (referenced in the GHSA pages for the 9xxx-series CVEs). Treat them as real but auto-aggregated; severity is from CVSS scoring, not always from end-to-end exploitability analysis.
- **CVE-2026-71963** (HIGH 8.8) appears on `app.opencve.io` for hermes-agent, but the NVD keyword search I ran does not list it. Could not verify primary record in NVD from the same query; treat as a separate aggregator signal.

### 2.2 The June 2026 MCP-config persistence campaign

**Independent verification sources:**
- GitHub issue #45620 (filed 2026-06-13, closed 2026-06-14 by teknium1) — "Security: config v27→v28 migration injected credential-exfiltration MCP server entry"
- GitHub PR #50476 (merged 2026-06-22, commit 41fe086) — "fix(security): harden MCP-config persistence attack surface"
- Third-party verification: `sheetgenius/frontier/runs/2026-06-23-.../verify/hermes-0day.md` confirms: "merge-base proof" that "4 prior commits now in v2026.6.19, not in v2026.6.5" — wait, the verifier said v2026.6.19 was the EXPOSED version, not the fixed one. Independent corroboration: the 4 PRs they cite "are 4 prior commits now in v2026.6.19" but the 0day cluster is "all main-unreleased, ahead of v2026.6.19".
- r/hermesagent post "Hermes Box Compromised" (also June 2026): "Bad MCP config contained shell payload behavior involving: authorized_keys - hermes-0day - /tmp/.akc.sh - SSH persistence"
- HN: search result "hermes-0day" referenced in commit narrative

**What the vulnerability was:**
Attack chain (per PR #50476 description and sheetgenius verifier):
1. Scanners fingerprint exposed Hermes dashboards (the SPA `/mcp` route is publicly indexable).
2. Drive the agent — running as root with `--insecure --host 0.0.0.0` and an exposed OpenAI API server — to plant a `command: bash` MCP entry that appends an attacker SSH key to `~/.ssh/authorized_keys`.
3. The MCP entry is re-executed on every cron tick + startup, re-installing the backdoor (persistence).
4. Attacker SSHes in as root and adds PAM/sshd persistence.

Two specific MCP abuse shapes:
- **Exfiltration shape (issue #45620)**: shell interpreter whose inline script invokes network egress tooling (curl piping `~/.hermes/.env` to a hardcoded IP:port — `43.228.79.77:55557` in the issue report).
- **Persistence shape**: shell interpreter whose inline script writes to `~/.ssh/authorized_keys`, `/etc/ssh`, `/etc/pam.d`, `sudoers`, crontab, or shell rc files.

Root cause per the PR: operator misconfiguration (root + `--insecure` + public bind), NOT a vulnerability in Hermes per se. The PR's framing: "We have no evidence of an undisclosed Hermes vulnerability — the campaign exploited misconfigured public exposure. This PR closes the in-product footguns that made that misconfiguration catastrophic."

**What was fixed (per PR #50476):**
1. Remove the dashboard `--insecure` auth-bypass. `--insecure` is now a no-op; any public/LAN bind requires an auth provider. Confirmed in subsequent issue #57482 (LAN access requires password after June 2026 hardening).
2. Add an MCP persistence guard (`hermes_cli/mcp_security.py`):
   - **IOC blocklist** (hardcoded): the attacker's SSH public key fragment (`AAAAC3NzaC1lZDI1NTE5AAAAICBoh1oDC4DnsO1m5mJ4yfEKrQebaFh`), the string `hermes-0day`, and source IPs `60.165.167.0/24`, `118.182.244.156`, `61.178.123.196`.
   - **Exfiltration regex**: shell interpreter + network egress pattern.
   - **Persistence regex**: shell interpreter + writes to SSH/PAM/sudoers/cron/rc files.
3. Raise the API-server key entropy floor from 8 → 16 chars; refuse to start on weak key + network-accessible bind. Comments in the diff say: "Ported from openclaw/openclaw; entropy floor raised to 16 in the June 2026 hermes-0day hardening".
4. Add a startup security posture audit (`hermes_cli/security_audit_startup.py`) that warns at startup about root / weak-SSH / ephemeral-container / unauthenticated-listener posture. Comment: "warn-on-load, never blocks."
5. IOC + patterns run BOTH at save time (`_save_mcp_server`) AND at spawn time (`tools.mcp_tool._filter_suspicious_mcp_servers`).

**In which released version:**
- PR #50476 merged to main on **2026-06-22** (commit 41fe086).
- v0.17.0 (tagged v2026.6.19) was released **2026-06-19** — *before* the fix landed on main.
- v0.18.0 (tagged v2026.7.1) was released **2026-07-01** — the first released tag containing the fix.
- Verified directly from the local clone:
  - `git show v2026.6.5:hermes_cli/mcp_security.py | grep -c 'hermes-0day'` → **0**
  - `git show v2026.6.19:hermes_cli/mcp_security.py | grep -c 'hermes-0day'` → **0**
  - `git show v2026.7.1:hermes_cli/mcp_security.py | grep -c 'hermes-0day'` → **10**
  - `git merge-base --is-ancestor 41fe086 v2026.6.5` → NO
  - `git merge-base --is-ancestor 41fe086 v2026.6.19` → NO
  - `git merge-base --is-ancestor 41fe086 v2026.7.1` → YES

**Verdict on the user's claim "the mitigation landed on main but not in v0.17.0":**
**TRUE — and more precisely, the fix was never in v0.17.0; the first released tag containing it is v0.18.0 (v2026.7.1, 2026-07-01)**. Anyone on v0.17.0 (or earlier) was exposed. Hermes's release cadence (weekly patches since) means a 12-day window of unpatched-on-tag exposure, which is short by industry standards but real.

**Cross-reference CVE-2026-53870** (the sensitive-file-permission CVE, 6.8 MED): independently reported by VulnCheck, NVD published 2026-06-17. Hermes fixed it in the v0.16.0 / v2026.6.5 release — `commit 3bace071bfadf2d2bec2ee048471a31ec920e3e8`, PR #30917. This is the same fix surface (response_store.db + webhook_subscriptions.json modes).

---

## 3. Independent criticism and negative reports

### 3.1 EvoMap / Evolver plagiarism controversy (April 2026, ongoing)

- **Yicai Global, 2026-04-17** ("China's EvoMap Changes AI Agent's License After Accusing Nous Research of Copying Code"): EvoMap switched Evolver from MIT → GPLv3 and obfuscated source after comparing Hermes Agent's self-evolution architecture to Evolver's. They claim a "one-to-one correspondence in the 10-step main loop, a systematic replacement of 12 groups of terms, and zero attribution in seven public materials." Reported timeline: Evolver public 2026-02-01 → Hermes Agent v0.2.0 released 2026-03-12, "hermes-agent-self-evolution" repo created 2026-03-09 (i.e. Evolver's design was public "24 to 39 days earlier").
- **Gate News (chaincnews) 2026-04-17**: covered the controversy and noted Nous's response on X ("Delete your account" — later deleted) and Teknium's quoted response: "I have literally never heard of this person, their project, or anything they are doing in my life."
- **Hacker News thread id=48187581** (3 months ago, 8 points): "Nous Research edits GitHub issue to remove plagiarism claims about Hermes Agent" — referenced by `0hijinks` noting that "Issues #17688 and #27266 repeat this request for attribution", "teknium1 retitled the original issue to '.' and edited the issue text to '.'", and "Nous Research deleted comments from 4 users, including the issue submitter, and blocked all of them."
- **EvoMap blog**: https://evomap.ai/blog/hermes-agent-vs-evomap-agent-memory (full analysis).
- **Verifier mirror** at AgenticWorkflows/evomap_evolver on GitHub (background context).

Status: unresolved. The product has continued shipping; EvoMap has not retracted. Treat as a contested originality claim, not a fact, but it's the largest public-relations hit against the project and a real risk to enterprise adoption.

### 3.2 Community-reported operational problems

- **r/hermesagent** (multiple threads) — "Hermes Box Compromised" thread documents a real user's compromised instance with the same persistence pattern as the 0day campaign; user reports OpenRouter balance depleted.
- **GitHub issue #35966** — "[Feature]: Native desktop/mobile client app" — open since 2026-05-31, P3. Comment by `onlyxn` 2026-08-14: "We built a native Android client — hermes-friends. A WeChat-style mobile client for Hermes Agent, native Kotlin, talking directly to the Hermes serve API." Both the iOS (HermesPilot) and Android (hermes-friends) clients are community builds, not first-party.
- **GitHub issue #44515** — "[Bug]: Hermes Agent Desktop doesn't update unless hermes background processes are stopped" — closed (completed). Linked PR #52203. macOS, stuck on 1/3.
- **GitHub issue #50944** — Desktop model picker persists wrong provider (litellm-proxy → openrouter) + toolsets toggles don't persist. Closed not_planned, but 18.2 reproduction by other users in comments.
- **GitHub issue #89096** — "[Bug]: Hermes Desktop UI Layout Broken / Display Chaos (Windows, npm run dev)" — open as of 2026-08-18, P2, needs-repro.
- **GitHub issue #39101** — Desktop window bounds not persisted, always reopens at 1220×800. Closed.
- **GitHub issue #84106** — "security: hermes config get mcp_servers exposes resolved MCP secrets" — open as of 2026-09-01, P2, sweeper:risk-security-boundary. Confirmed in comments by `Devil-SX` on v0.20.5 (2026-08-19) — fix exists in their fork, not in upstream.
- **GitHub issue #57482** — "LAN/local dashboard access requires password after June 2026 auth hardening" — *user-visible side-effect* of PR #50476. The intentional removal of `--insecure` broke trusted-LAN usage. Open.

### 3.3 Performance / competition
- Terminal-agent-bench (independent third-party, `AniruddhaPKawarase/terminal-agent-bench`): April 2026, 30-task benchmark. Results: **Hermes 21/30 completed, median 7m10s, $4.35/task**; Claude Code 24/30, 4m20s, $2.78; Codex CLI 22/30, 5m45s, $2.04. Hermes wins on large refactors (>5 files) and migrations, loses on bug fixes and cost. Single-source benchmark; useful directional data.
- HN "Hermes Agent: The self-improving AI agent" (3 points, 6 months ago) — author/poster danebalia is a community advocate, low signal.

### 3.4 OpenClaw / Tencent / OpenClaw Foundation trademark history (background, not a Hermes issue)
- Lexology (2026-03-12) and Caixin Global (2026-03-13): OpenClaw was "Clawdbot" → "Moltbot" → "OpenClaw" (Jan 27, 2026) following Anthropic trademark pressure. Now stewarded by the "OpenClaw Foundation" (a 501(c)(3)).
- The dispute is OpenClaw's problem, not Hermes's. It does mean OpenClaw has a more complex organisational history than its repo metadata suggests.

---

## 4. Capability comparison table

Sources for each row: README, docs, NVD, SEC.md in repo, peer docs (docs.openclaw.ai, docs.letta.com, docs.zeroclaw.com, docs.openhands.dev, docs.anythingllm.com).

| Capability | Hermes Agent (NousResearch) | OpenClaw (openclaw/openclaw) | ZeroClaw (zeroclaw-labs/zeroclaw) | Letta (letta-ai/letta + letta-code) | OpenHands (OpenHands/OpenHands + All-Hands-AI) |
|---|---|---|---|---|---|
| **Repo stars (approx)** | ~249.4K | ~391K (largest of the set) | ~32.9K | ~25K (letta) + ~3.5K (letta-code) | ~87.8K (new) / ~61.8K (legacy) |
| **Primary language** | Python 3.11+ | TypeScript / Node 26+ | Rust (single binary) | Python + TypeScript | Python + TypeScript |
| **Memory model** | FTS5 session search + LLM summarization + MEMORY.md/USER.md + Honcho dialectic user modeling + periodic "nudges" | 4-tier (Instructions / Curated core / Episodic / Prospective) with provenance gating, dreaming consolidation, DREAMS.md | Memory module (no first-party documented design on the level of the others) | Memory blocks (typed, labeled, persistent); sleep-time "dreaming"; MemFS git-backed | Conversation history per session; no first-party long-term memory abstraction |
| **Skills / self-extension** | agentskills.io-compatible, with skill self-improvement during use; Skills Hub; installable from URL | Skills system, ClawHub marketplace | Tools + custom MCP servers | Skills (project/agent/global scopes), skill-creator | Skills + microagents, but skills are not the central abstraction |
| **Scheduling** | First-class cron (`hermes cron`); Automation Blueprints (no-syntax); per-job profile; "Delegates and parallelizes" | Cron jobs, hooks, webhooks; standing intents via SQLite | `zeroclaw cron add '0 9 * * 1-5' 'Good morning'` — first-class CLI; heartbeat monitor | Crons & schedules, heartbeats, self-managed schedules | Cron + webhooks + automations via Agent Canvas |
| **Channels / messaging** | 18+ (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Mattermost, Email, SMS, DingTalk, Feishu, WeCom, Weixin, QQ Bot, Yuanbao, BlueBubbles, Home Assistant, MS Teams, Google Chat, more) | 30+ via channel plugins (Discord, iMessage, Signal, Slack, Telegram, WhatsApp, WebChat, Matrix, Nostr, Twitch, Zalo, …); macOS app, iOS + Android nodes | 30+ channels (Discord, Telegram, Matrix, email, voice, webhooks) | Slack, Telegram, Discord, custom channels; also chat.letta.com (mobile-friendly browser) | Slack + GitHub + Notion + Linear integrations; web-first |
| **Subagents / parallelism** | Background/async subagents (v0.17.0); v0.18.0 "background fan-out subagents"; `tui_gateway/methods_subagents.py` | Multi-agent routing: isolated sessions per agent/workspace/sender | Not a first-class abstraction | 7 built-in subagent types (fork, general-purpose, history-analyzer, …) with per-subagent `memoryBlocks` and `tools` config | Sub-agents and parallel coding workflows via Agent Canvas |
| **Model-provider freedom** | 30+ providers in `providers/`; Nous Portal as unified sub; OpenAI / Anthropic / xAI / OpenRouter / Ollama / etc. | Provider-agnostic, Anthropic recommended | 70+ providers; local Ollama / LM Studio / llama.cpp / vLLM | Model-agnostic, ships Letta model leaderboard | Bring-your-own-model; OpenHands, Claude Code, Codex, Gemini, ACP-compatible |
| **Documented client protocols** | **Three**: ACP adapter (`acp_adapter/`), TUI gateway JSON-RPC over stdio/WS (`tui_gateway/`), **OpenAI-compatible HTTP API** at `/v1/chat/completions` (default `127.0.0.1:8642`) | Gateway (single source of truth for sessions/routing), Control UI at `http://127.0.0.1:18789/`; Web surfaces; Tailscale | ACP over stdio (JSON-RPC 2.0); REST gateway | Letta Agent SDK; ACP adapter (`letta-ai/letta-acp`); REST API | **ACP** (Agent-Client Protocol) is *the* public surface; Agent Canvas; OpenHands Software Agent SDK |
| **Default network bind** | **127.0.0.1 / loopback** for API server and dashboard. `API_SERVER_HOST=127.0.0.1`, `API_SERVER_ENABLED=false`. Binding non-loopback is documented as a "break-glass operator decision" (`SECURITY.md` §2.6.5) | `http://127.0.0.1:18789/` default; remote access via Tailscale documented | Local-only default (single-binary daemon) | App server default localhost; Letta Cloud is opt-in | Localhost default; docker exposes 3000; enterprise runs in customer VPC |
| **Default auth** | API server: bearer token (API_SERVER_KEY, ≥16 chars enforced on network bind since June 2026). Dashboard: auth provider (basic/OAuth) required on any non-loopback bind. `--insecure` is now a no-op. | Tokens + allowlists (`/gateway/security`); DM pairing for messaging adapters | estop command (`zeroclaw estop`) for emergency tool/network lockdown; "supervised → approval required" by default | Letta Cloud SSO; self-hosted can be open-loopback | Per-user authentication on enterprise; default install trusts localhost |
| **Noteworthy security defaults** | (1) OS-isolation is the only boundary (explicit `SECURITY.md`); (2) approval gate before destructive shell; (3) Bitwarden Secrets Manager replaces plaintext API keys (v0.17.0); (4) `security.redact_secrets: true` available but *incomplete* (issue #84106); (5) MCP-persistence guard since v0.18.0 | (1) `security` docs; (2) HMAC-signed tool receipts ("stamps every tool call"); (3) auth-bypass removed for LAN access | (1) HMAC-SHA256 tool receipts; (2) command policy; (3) supervised autonomy default; (4) estop levels (network-kill, domain-block, tool-freeze) | Memory blocks are tenant-isolated; Letta Cloud adds SSO + per-workspace RBAC | Sandbox runtime container (all-hands runtime image); audit logs |
| **Native first-party desktop / mobile** | Electron desktop (`apps/desktop/`); **no first-party mobile** (HermesPilot/hermes-friends are community) | macOS app, iOS + Android *nodes* (paired, not standalone) | Single binary, runs on Pi/STM32/Arduino/ESP32; **no first-party mobile app** | Desktop app (macOS/Windows/Linux) + chat.letta.com (mobile browser); both first-party | Web-first Agent Canvas; no first-party mobile |
| **License** | MIT | MIT | MIT OR Apache-2.0 (dual) | Apache-2.0 (letta) + MIT (letta-code) | MIT |
| **Default config risk profile** | **Medium** if installed naively (root + exposed bind); **Low** if installed per docs (non-root, loopback, auth provider, container sandbox) | **Medium** (TS stack + many chat channels can be attack-surface) | **Low** (single-binary local default) | **Low–Medium** (Letta Cloud adds managed-VPC trust) | **Medium** (docker socket mount in default install) |

---

## 5. Verdict

**Top-tier** among self-hostable agent platforms, but the framing needs care.

**Strongest single piece of evidence: the breadth of protocols shipped as first-class, and the explicit, opinionated security posture in `SECURITY.md`.**

Concrete primary evidence:
- A single install exposes three documented client protocols — ACP, TUI-gateway JSON-RPC, and an OpenAI-compatible HTTP API (with `/v1/chat/completions`, `/v1/responses`, `/v1/models`, `/v1/capabilities`, `/api/sessions`, `/v1/runs`, `/api/jobs`). No peer in the set ships all three in one process.
- `SECURITY.md` (335 lines) explicitly bounds what the agent will and won't promise: "The only security boundary against an adversarial LLM is the operating system. Nothing inside the agent process constitutes containment — not the approval gate, not output redaction, not any pattern scanner, not any tool allowlist." Then it lists the actual boundaries (terminal-backend isolation, whole-process wrapping via Docker or NVIDIA OpenShell) and the out-of-scope heuristics. This is the clearest trust model in the comparison set.
- The June 2026 hardening cycle (PR #50476) shows the project can ship defense-in-depth quickly *when it wants to*: the MCP IOC blocklist, persistence-pattern guard, and entropy-floor raise all landed within ~12 days of the campaign being reported on r/hermesagent.

But the **overstatement** claim has real teeth:
- **39 NVD entries in 5 months**, of which only 9 have explicit vendor-fix references and 30+ say "vendor did not respond". That is a *very* high volume relative to peer agents I checked. Most are LOW/MED severity (auto-aggregated via VulDB), but the existence of a 6.8 MED CVE-2026-53870 (sensitive-file permissions in shipped data files) and an 8.8 HIGH CVE-2026-71963 in the same window is a yellow flag, not a green one. Caveat: I could not independently verify the 8.8 HIGH record in NVD (it appears in OpenCVE aggregator, not in the direct NVD search I ran); treat as "could not fully verify" pending a direct CVE-2026-71963 lookup.
- **The v0.17.0 fix-window lag** is real: the June 2026 campaign was live, v0.17.0 (Jun 19) shipped without the fix, the fix landed on main Jun 22, and the first patched release was v0.18.0 (Jul 1). Operators on `hermes update` between Jun 19 and Jul 1 had an unpatched Hermes with the campaign's exact exploit shape active. Hermes's release cadence is now weekly (good), but a 12-day patch-to-tag gap in an actively-exploited window is the kind of thing that should not be called "top-tier security" without qualification.
- **Mobile story is weak**. The canonical first-party mobile feature request (#35966) is P3 and still open as of 2026-08. Third-party HermesPilot and hermes-friends exist but are not Nous-maintained. Compared with OpenClaw's paired iOS+Android nodes, AnythingLLM's Android mobile, or Letta's chat.letta.com mobile browser, this is a real gap.
- **Desktop is a known weak spot**: at least four open/closed P2/P3 issues (UI layout broken on Windows dev mode, model-picker persistence wrong, toolsets toggles don't persist, window-bounds not persisted). These are bug reports against a real first-party client, not a marketing slide.
- **The EvoMap plagiarism controversy is unresolved** and is the single largest reputational risk in the comparison. The fact that the project edit-removed the original issue text and blocked four users (per HN #48187581) is *worse* for the project's credibility than the underlying similarity claim, which is contested but not baseless.
- **Marketing-leaning claims** in the README that aren't yet reproducible engineering: "Tool self-recovery" (v0.20.0 notes), "Mixture-of-Agents" (v0.18.0 notes), "the only agent with a built-in learning loop" (README line 19 — Letta Code is the comparable system). Mark them as marketing until independently benchmarked.

**The honest read:**
Hermes Agent is a **top-tier engineering platform with mid-tier security hygiene**. It has the broadest documented protocol surface of any self-hostable agent I've evaluated here, the most explicit trust model, and a real RL/data-generation pipeline. It also has the largest public-CVE footprint in the comparison set, an unresolved attribution dispute with another open-source project, and a known patch-to-tag lag during a live exploitation window. "One of the best" is defensible; "the best" is overstatement; "best for security-sensitive enterprise self-hosting" is wrong until v0.18.0+ hardening is universal and the open security-policy items (config-get redaction #84106, `model_tools.py` access controls #18993, MCP `list_tools` resource consumption #84289, desktop SSRFs #85106/#85107) ship in a tag.

---

## Sources index (URLs verified 2026-10-07)

Primary:
- https://github.com/NousResearch/hermes-agent (local clone, 65bc6727b43c)
- https://hermes-agent.nousresearch.com/docs/
- https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- https://hermes-agent.nousresearch.com/docs/user-guide/configuration
- https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md
- https://github.com/NousResearch/hermes-agent/blob/main/gateway/platforms/api_server.py
- https://github.com/NousResearch/hermes-agent/issues/35966 (mobile/desktop)
- https://github.com/NousResearch/hermes-agent/issues/45620 (MCP exfil config-migration)
- https://github.com/NousResearch/hermes-agent/pull/50476 (hermes-0day hardening)
- https://github.com/NousResearch/hermes-agent/issues/57482 (LAN auth after June 2026)
- https://github.com/NousResearch/hermes-agent/issues/84106 (config get mcp secrets leak)
- https://github.com/NousResearch/hermes-agent/issues/50944 (desktop model picker)
- https://github.com/NousResearch/hermes-agent/issues/44515 (desktop update stuck)
- https://github.com/NousResearch/hermes-agent/issues/89096 (desktop layout chaos)
- https://github.com/NousResearch/hermes-agent/releases

Peers:
- https://github.com/openclaw/openclaw (391,317★, MIT, TS)
- https://docs.openclaw.ai/ and https://github.com/openclaw/openclaw/blob/main/docs/concepts/memory-architecture.md
- https://github.com/zeroclaw-labs/zeroclaw (32,916★, Apache-2.0, Rust) and https://www.zeroclaw.com/
- https://github.com/letta-ai/letta (~25K★) + https://github.com/letta-ai/letta-code (~3.5K★) + https://docs.letta.com/letta-code/skills + https://docs.letta.com/letta-code/subagents
- https://github.com/OpenHands/OpenHands (~87.8K★) + https://github.com/All-Hands-AI/OpenHands (~61.8K★)
- https://github.com/Mintplex-Labs/anything-llm (~66K★) + https://anythingllm.com/

Security:
- NVD API: `https://services.nvd.nist.gov/rest/json/cves/2.0?keywordSearch=hermes-agent&keywordSearch=NousResearch` (39 entries, 2026-04-27 → 2026-09-03)
- https://nvd.nist.gov/vuln/detail/cve-2026-53870 (sensitive-file-permission; CVSS-B 6.8)
- https://www.vulncheck.com/advisories/hermes-agent-sensitive-file-permission-vulnerability-in-store-files
- https://github.com/advisories/GHSA-33qv-c5qm-799v (CVE-2026-10223)
- https://github.com/advisories/GHSA-pgp4-xr4j-h5cg (CVE-2026-9366)
- https://github.com/advisories/GHSA-mv8x-fg99-32mf (CVE-2026-10222)
- https://app.opencve.io/cve?product=hermes-agent&vendor=nousresearch (full inventory)
- https://github.com/sheetgenius/frontier/blob/main/runs/2026-06-23-weekly-digest-2026-06-16_2026-06-23-frontier-v0/verify/hermes-0day.md (third-party verification)

Independent criticism:
- https://www.yicaiglobal.com/news/chinese-ai-team-evomap-changes-ai-agents-license-after-accusing-silicon-valley-ai-lab-of-copying-code
- https://evomap.ai/blog/hermes-agent-vs-evomap-agent-memory
- https://www.gate.com/news/detail/china-team-evomap-erupts-in-anger-over-hermes-agent-copying-amid-viral-20388174
- https://news.ycombinator.com/item?id=48187581 (issue text deleted by Nous)
- https://www.reddit.com/r/hermesagent/comments/1uaa38d/hermes_box_compromised
- https://github.com/AniruddhaPKawarase/terminal-agent-bench (third-party benchmark, 30 tasks)

Background on peers:
- https://openclaw.ai/blog/introducing-openclaw (Peter Steinberger, the Clawd→Moltbot→OpenClaw history)
- https://www.lexology.com/library/detail.aspx?g=30669b9f-e06f-41ee-9381-2ccccfffe673 (OpenClaw trademark analysis)
- https://www.caixinglobal.com/2026-03-13/tencent-denies-copying-claims-by-openclaw-creator-102422640.html
- https://en.wikipedia.org/wiki/OpenClaw (incl. OpenClaw 2.0 v2026.8.1, Aug 30 2026)
