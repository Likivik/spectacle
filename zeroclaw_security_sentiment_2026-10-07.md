# ZeroClaw — Security + Community Sentiment Assessment

**Date:** 2026-10-07 (MSK)
**Scope:** github.com/zeroclaw-labs/zeroclaw (Apache-2.0, created 2026-02-13)
**Repo state at assessment:** 32,936 stars, 4,954 forks, 948 open issues, 83 watchers
**Latest release:** v0.8.5 — 2026-09-05 07:31:19 UTC (security + connectivity + operator-experience, 454 commits, 73 contributors)
**Homepage:** zeroclaw.com (per repo metadata; see also zeroclawlabs.ai and the network of lookalike domains in §C.4)

---

## A. SECURITY

### A.1 Advisory inventory

There is exactly **one** published advisory on the repo's GitHub Security Advisories tab. One prior advisory was fixed in v0.8.0 but never formally published. NVD has one CVE for the project; RustSec has none for the zeroclaw crate.

| ID / CVE | Severity | What it is | Affected | Disclosed | Fix version (released) | Patch latency |
|---|---|---|---|---|---|---|
| **GHSA-93f6-34w8-5g98** / **CVE-2026-101885** | High (CVSS 8.5 / CVSS:4.0 `AV:L/AC:L/AT:N/PR:N/UI:P/VC:H/VI:H/VA:H`) — GHSA severity "high", GitHub Advisory Database marks the CVE "Unreviewed" as of 2026-10-07 | `zeroclaw plugin install` writes a plugin's `wasm_path` via `dest_dir.join(wasm_path)` (`crates/zeroclaw-plugins/src/host.rs:218–273`) without a containment check. A malicious `manifest.toml` with `wasm_path = "../../evil"` (or an absolute path) escapes the plugins dir → arbitrary-file-write with attacker-controlled content → RCE (shell profile, cron, systemd unit, binary replacement). CWE-22 + CWE-347. **Plugin signature verification is `disabled` by default, so no signature gate.** Reachable only when built with the optional `plugins-wasm` feature (the lean official binaries do *not* enable it; source or custom feature-enabled builds ≤0.8.4 are affected). | ≤ 0.8.4 | Advisory: 2026-09-05 16:31:36 UTC. Reporter: `JordanTheJet` (project lead). CVE-2026-101885 published 2026-09-30 by VulnCheck, not by the project. | **0.8.5 — 2026-09-05 07:31:19 UTC** | **Fix shipped ~9 hours before the advisory was published.** The fix was already in the release. There was no vulnerable "headline" build. **Did a released version contain the fix at disclosure time? Yes — 0.8.5 was already the latest release at the moment the GHSA was published the same day.** |
| **GHSA-f385-f6h2-3gqj** (NOT formally published) | Estimated CVSS 7.5 (per the PR) | `web/src/pages/Canvas.tsx`: dashboard Canvas iframe sandbox used `sandbox="allow-scripts allow-same-origin"`, which the HTML spec says is equivalent to no sandbox — a sandboxed script can `window.frameElement.removeAttribute("sandbox")` and reach `window.parent`. Combined with iframe content delivered via `contentDocument.write()`, an injected frame (e.g. an agent-supplied svg/html frame) could read the dashboard bearer token from `localStorage` and replay it. | Introduced in d2792ee (PR #5355), present in v0.7.5 and earlier v0.8 beta | Filed via GH private vuln reporting 2026-05-18 by `@nixosclaw`; PR reviewed on the GHSA temp fork 2026-05-22; public PR #6942 opened 2026-05-26 | **v0.8.0-beta-2** (released 2026-06-12 area; v0.8.0 GA 2026-06-12). Fix removes `allow-same-origin`, switches to `srcdoc` with `script-src 'none'; object-src 'none'` CSP, and makes the unknown-content-type branch render an inert no-script document. | **The advisory is referenced by ID in v0.8.0 release notes and PR #6942, but the GHSA URL `github.com/zeroclaw-labs/zeroclaw/security/advisories/GHSA-f385-f6h2-3gqj` returns HTTP 404 and is not in the public GitHub Advisory Database. The fix shipped in v0.8.0-beta-2, ~3 weeks after the report. Disagreement/disconnect: the PR description notes that the GHSA "remains in draft and can be published with attribution and a CVE filed via the normal advisory-publish flow" — i.e. the maintainers have not (as of 2026-10-07) published the advisory or requested a CVE for it. This means users searching for "ZeroClaw CVEs" find only the wasm_path one and may mistakenly believe the canvas issue is unfixed. |

Other known security-relevant fixes (no CVEs assigned, listed in release notes):

- **v0.8.0 (2026-06-12):** bearer-token revocation on device rotation/deletion (#6988); secret redaction extended to nested config (#6918, #6982, #7261); channel orchestrator no longer falls back to another provider's credentials (#7066); private-host allowlists for HTTP request tool (#6981) and DNS-resolves-to-private fetches (#6974); per-agent tool allowlists enforced on every dispatch (#6960, #7064); scheduled jobs can no longer modify the scheduler by default (#7189); internal telemetry blocked from chat WebSocket by default (#7221); bubblewrap `/lib64`/`/lib` conditional bind (#6902); interactive subprocesses can no longer hijack the controlling terminal (#7120); partially invalid config can no longer silently default security-critical settings during startup (#7160). Deps: `mail` library bumped for RUSTSEC-2026-0141 (#6662); web router bumped clearing five advisories (#7198).
- **v0.8.3 (2026-07-16):** "wave of SSRF and secret-leak fixes," constant-time token comparison, signing-key leak prevention, path-traversal fixes, dependency bumps clearing several RUSTSEC advisories. CycloneDX SBOM + cosign signing + SLSA provenance added to release automation (#8158, #8404, #8277).
- **v0.8.5 (2026-09-05):** "plugin and skill boundaries get substantially tighter: typed instance configuration, scoped secrets, host-owned egress, bounded exports, path-traversal protection, and fail-closed skill HTTP execution."

### A.2 Patch latency — summary

| Advisory | Report → fix | Same-day / multi-day | Released version contained fix at disclosure? |
|---|---|---|---|
| GHSA-93f6-34w8-5g98 | 2026-09-05 (same day) | Same-day; pre-disclosed in release notes | **Yes** |
| GHSA-f385-f6h2-3gqj (unpublished) | ~3 weeks (2026-05-18 → 2026-06-12) | Multi-week | n/a (advisory never published) |

The repo is on a roughly monthly release cadence (v0.8.0 → v0.8.1 → v0.8.2 → v0.8.3 → v0.8.4 → v0.8.5 from June to September 2026).

### A.3 Disagreements, unfixed, or acknowledged-but-open

- **GHSA-f385-f6h2-3gqj was never published.** The PR #6942 description explicitly says "the GHSA itself remains in draft and can be published with attribution and a CVE filed via the normal advisory-publish flow." A month later (v0.8.0 GA) the advisory is still draft; as of 2026-10-07 the URL still 404s. No CVE was ever assigned. This is the only "disagreement / acknowledged-but-open" case I found — it is not a disagreement, it is a non-publication that arguably misrepresents the project's security posture to outside auditors.
- **firejail_args is advertised but never applied (open as of 2026-10-07, issue #11594, S2 severity).** The config schema and `security_status.rs:409` report `firejail_args` as if it were forwarded to firejail, but the production code path `crates/zeroclaw-runtime/src/security/firejail.rs:151` builds a fixed-argument command and appends the caller's invocation. **Anyone who hardens their firejail sandbox by setting `firejail_args` gets no effect and no error, while the status output confirms the value is in effect.** The docs half is being corrected in #11591; the runtime half is open. This is a textbook "shipped insecure by default" pattern.
- **YOLO mode / `yolo` quickstart preset.** The `Massive Impact` third-party review notes this is "a config preset that disables the guardrails" — "It's loud, logged, and obviously named. Not the default." Per the v0.8.0 changelog: "the unbounded and yolo quickstart presets actually allow what they advertise (#7371)" — i.e. the fix was that these presets *correctly* allowed what they claimed, not that they were made safer.
- **"Oversecured and useless by default"** (r/LocalLLaMA, 2026): "you will need to permit very basic stuff by editing config manually." No maintainer pushback found.
- **No security-critical CVE disputes** found. The `e yencabulator` critique on HN that the project doesn't address the "lethal trifecta" (read untrusted data + tool access + exfiltration capability) is a *design* critique, not a disputed report.

### A.4 Independent audit / pentest / third-party review

**None.** Specifically:

- No professional pentest, audit, or formal third-party security review exists for the project. **Could not verify** the existence of any commissioned report from a security firm.
- The 129 "automated security tests" cited in SECURITY.md are the project's own Rust test suite, not an external audit.
- Limpid (https://limpidreviews.fyi/tools/zeroclaw) is a *consumer review site* that scores the project 4/5 on Security Posture — it is not a security audit. It does flag the absence of a legal entity and the impersonation ecosystem (see C.4).
- The microkernel refactor PR #5559 received an unusually thorough internal review (by `WareWolf-MoonWall`, citing internal RFCs #5615 and #5653) — this is *internal* reviewer work, not an external audit.
- The "Security Audit" CI gate in PR #5780 was **failing repo-wide at the time of that review** ("ambient `cargo-audit` advisory, present across multiple open PRs; not caused by this PR"), and there is a tracked issue `ci: Advisory scan failed — 2026-10-02` (#11429). So even the dependency-vulnerability gate was not consistently green.
- The v0.8.3 release notes (2026-07-16) introduce cosign signing + SLSA provenance + CycloneDX SBOM. These are supply-chain *provenance* controls, not a security audit.

### A.5 "Insecure by default" — the actual list (not the marketing)

What the project *says*: "Secure by default," "Supervised is the default autonomy level," "Pairing, strict sandboxing, explicit allowlists, workspace scoping."

What is actually insecure-by-default in shipped configurations:

1. **Plugin signature verification is `disabled` by default.** Stated explicitly in the GHSA-93f6-34w8-5g98 text. There is no signature gate between an untrusted package and an arbitrary file write. (Only applies to builds with the `plugins-wasm` feature; lean official binaries do not enable it, so this is a "if you opt in, it's already game over" situation rather than an attack surface for the default lean install.)
2. **`firejail_args` is a documented knob that does nothing.** Issue #11594 (open 2026-10-07): schema exposes it, status output reports it, but the production code path ignores it. The docs fix is in #11591; the runtime fix is unmerged. A user who configures hardening flags gets no error, no warning, and the status output lies that the sandbox applied them.
3. **Per-agent tool allowlists are not enabled by default; you must opt in.** The default preset is restrictive in the abstract, but the user's normal escape hatch is to expand it without explicit security review.
4. **`memory.auto_save = true` is the default.** Agents silently persist conversation-derived facts to disk (`~/.zeroclaw/workspace/memory.db` SQLite). The docs recommend keeping this on, but it is a non-obvious default that affects data lifecycle and export behavior.
5. **YOLO / unbounded quickstart presets** exist and "actually allow what they advertise" (#7371). Marketing copy distinguishes these from defaults, but they remain one preset away from a deploy.
6. **The 23-channel bundle is "lean by default" only as of v0.8.0** — channels beyond the default bundle are *opt-in build features*. A self-hosting user who enables more channels expands the surface without a security checklist. Several channels (WhatsApp Web, Lark, Nextcloud Talk, etc.) require external-service credentials that, if leaked via the dashboard, are not in the leak scanner's first-pass coverage.
7. **The dashboard Bearer token is in `localStorage`** even after the GHSA-f385 fix. PR #6942 explicitly notes: "the bearer remains in `localStorage`; this PR removes the iframe's ability to read it, but the storage location and scope are unchanged." So the underlying token model is unchanged; the fix only closed one exfil path.
8. **Container image is distroless / `65534:65534` (good).** The default Linux `install.sh` does not, by itself, give you a sandboxed runtime — you must explicitly opt into Landlock / Bubblewrap / Seatbelt / Docker. Big Muddy's 2026-03-02 review found the default Docker compose launched only the web gateway, **not the channel daemon**, and the distroless image deliberately excludes `date`, `sh`, and other tools the agent wants to call — the user has to mount BusyBox in to make the agent functional. (This is "insecure by default" only in the sense that the safe image is non-functional and users tend to relax it.)
9. **Outbound HTTP is unrestricted unless the user configures the private-host allowlist.** The fixes for SSRF (#6981, #6974) are *available* but require user opt-in.
10. **The "internal telemetry" the chat WebSocket used to leak is blocked by default only since v0.8.0 (#7221).** Anyone on v0.7.x is on the wrong side of that line.

**Verdict:** the project has the *appearance* of secure-by-default and a credible CI/test story, but the actual default install (a) does not sandbox plugin execution at all (no plugins-wasm), (b) ships a sandbox knob that does nothing, (c) puts the dashboard bearer in `localStorage`, and (d) makes the user manually wire up multiple "secure" features. The notable headline advisories to date do not have a CVE dispute — they have a *publication* gap on the canvas one.

---

## B. COMMUNITY SENTIMENT

### B.1 What users actually complain about (v0.7.x / v0.8.x era)

**Install / onboarding (the persistent top complaint, Apr 2026 → present):**

- r/zeroclawlabs, 2026-04-03 ("A cautionary tale about ZeroClaw" by u/Anarchytect27058, 10 pts / 8 comments, the canonical negative post): "After two days of broken install scripts and permission errors … I gave up and moved to Nanbot. Don't gaslight yourself into thinking you're stupid—the project just isn't ready for hobbyists yet." Specifics: "None of the install paths actually work: Brew, install script, Docker." The onboard script "literally just skips forward no matter what options you pick." A counter-comment from u/JobobJet (2026-04-03 19:54 UTC): "I also experienced some install anxiety / frustration (many releases ago - a week after the repo hit). But I quickly dete[rmined]" — so even the sympathetic reply concedes real early friction.
- Big Muddy, 2026-03-02 (`muddy.jprs.me`): the web gateway "was a bit of a mess … only memory management and the basic status dashboard worked. Trying to talk to the agent through the web interface would give me a black screen … The cost tracker always displayed zero … The configuration editor gave me an error and so did the diagnostics tool." Docker compose launches only the web gateway, not the channel daemon.
- r/openclaw 1rv4629 (v0.1.9, "dead chatbot"): "It feels more like a simple LLM wrapper than an actual agent environment." Web UI "minimal chat interface with no obvious agent capabilities."
- r/LocalLLaMA 1rd980h ("ZeroClaw or should I go full IronClaw?"): "the amount of stuff that is just straight up broken was mind boggling." Also flags the impersonation ecosystem.
- r/zeroclawlabs 1rgthm6 ("I have zeroclaw installed are their skills out there?"): "There is no support documentation… It's hard to know if they have skills option or not … I love the idea behind it and how it's built. They just need proper docs."
- GitHub issue #6119 ("A Respectful Note from the Trenches of ZeroClaw Configuration", 2026-05-era): an 8-hour install saga, "I had to use ChatGPT and other models simply to understand how to make ZeroClaw usable." Cites: dashboard assets not installed by default, empty `C:\Users\name\zeroclaw\web\dist`, model tool-call JSON failures with MiniMax M2.7 + Windows + Cyrillic paths.
- LumaDock 2026-06-03 "Fix common ZeroClaw errors and get it running" exists specifically to address the recurring "zeroclaw: command not found", "dead chatbot", Discord Message Content Intent, and Telegram reconnect-loop failure modes. The article itself notes these are "dozens of comments from people who ran into the same handful of issues and got stuck." Half the time `zeroclaw doctor` resolves it; the other half is the article.

**Docs quality:**

- "There is no support documentation" (r/zeroclawlabs 1rgthm6). josenobile.co guide (2026-07): "the lack of a web dashboard and sparse documentation makes it harder for non-technical users." ToolBrain: "Sparse documentation. No formal docs site. Only a README and GitHub Discussions."
- Counter-evidence: v0.7.5 (2026-05-08) added a schema-driven `/onboard` web flow, OpenAPI 3.1 spec at `/api/openapi.json`, Scalar explorer, generated TS client, in-browser drift detection, and a three-surface personality editor. v0.8.0 (2026-06-12) shipped a full book rework deriving provider/config reference pages from source, version selector, FreeBSD setup guide, Podman guide, NixOS module. So docs *quality* has demonstrably improved across the v0.8.x cycle, even where users still feel it's thin.

**Memory / RAM / boot claims:**

- Sub-5MB idle RAM and <10ms cold start are repeated in marketing (`zeroclaw.com`, `zeroclaw.co`, `zeroclaw.dev`) and are essentially reproduced in third-party hands-on tests. The Awesome Agents review (2026) measures 38 MB idle, 0.6s cold start, 142 MB peak under 10 concurrent skills on 4-core EPYC / 8 GB Ubuntu 24.04. ToolBrain measures the same on macOS arm64. The 400x / 14x / 13x numbers in those reviews are reproducible in spirit; the marketing phrasing "sub-5MB idle RAM" appears to apply to the lean install / no-active-turns case, not to a running agent with an active channel. r/LocalLLaMA 1rd980h notes "zeroclaw is oversecured and useless by default" — i.e. the small footprint comes with a less functional out-of-the-box experience.
- Steven Cargall (2026-05) confirms Docker + LiteLLM + vLLM works but documents issue #6123 (P1) where a fresh install silently falls back to `anthropic/claude-sonnet-4` even with `ZEROCLAW_PROVIDER=litellm` — i.e. a config bug that causes unexpected LLM costs. Fix targeted for v0.7.5.
- No widespread "it actually used 500MB" complaint found. The hardware claim is broadly corroborated.

**Channel reliability:**

- We Shall Build (2026): Discord typing-indicator gets stuck forever on two distinct flavors. v0.8.2 and earlier: 30s listener timeout — fixed in v0.8.3. v0.8.3+: reload-from-dashboard mid-response can still wedge it; full CLI restart needed. Author filed as GH issue #9198.
- Big Muddy: AWK (acknowledgement) reactions only "occasionally" appear. Telegram bot worked once Docker was configured to launch the channel daemon (not the default).
- LumaDock: Discord "Invalid Session" loop if Message Content Intent is off; Telegram bot connects/disconnects immediately on revoked token; gateway has to be active for channels to receive webhooks.
- Issue #11586 (open 2026-10-06): "ZeroCode sidebar turns failed sessions green after the daemon restarts" — a UX correctness issue. Open as of today.

**Other recurring complaints:**

- "Dashboard empty by default — `web/dist` is not present; you have to download the build separately" (issue #6119, v0.7.x era). A self-hosting user expects an in-binary dashboard.
- Custom skills require Rust trait implementations (vs. OpenClaw's JavaScript skills). Limits the developer audience (ToolBrain review).
- Skill registry ~200 skills vs. OpenClaw's 5,700+.
- The auto-update behavior / config drift between hand-edits and runtime (improved in v0.7.5 with a drift banner, but still a thing).
- Pre-1.0 bugs confirmed by reviewers: DuckDuckGo search hangs on rate-limit; SQLite memory engine lacks graceful error handling if the DB is deleted under the running agent. (ToolBrain, 2026.)

### B.2 Maintainer responsiveness

Direct evidence:

- **SECURITY.md SLA:** ack 48h, assessment 1wk, fix 2wk for critical. The two real reports measured against this: wasm_path = same-day, well inside SLA. canvas = ~3 weeks report-to-fix, on the edge of the 2-week critical fix window, but acknowledged inside 48h.
- **Issue #11594** (firejail_args bug, S2, code-reading report): opened 2026-10-07 02:47 UTC, updated 2026-10-07 04:08 UTC (within 90 minutes), and the docs half is already being addressed in #11591. Suggests the maintainers are actively monitoring inbound bug reports.
- **Issue #1043** (concurrent tool calls, 2026-02-20): an automated intake checklist is posted by `@github-actions` on incoming issues asking for repro/env/version. Median response to a substantive issue is small — issue #2352 (duplicate workflow runs, 2026-09) and issue #1043 both got an automated intake comment within hours, then a substantive maintainer follow-up within 1–2 days. **Could not verify a precise median-time-to-first-response metric** from the public data I pulled (would need to compute over the full 948 open issues or sample a larger set), but the spot checks show same-day or next-day first response on issues filed in 2026-09 / 2026-10.
- The "github-issue-triage" skill shipped in PR #5780 (2026) explicitly states triage SLA: stale = 45+ days since author-last-active; `r:support` items default to comment + leave open, close only if all three of a defined checklist are met. The skill description includes a "Verified scenarios: Full session of issue triage (202→157 issues) performed using these principles before the skill was formalized." This indicates systematic triage, not ad-hoc.
- **The issue backlog is large (948 open)**, which dilutes any median claim. Suggests real responsiveness on fresh issues, weaker follow-up on long-tail.
- **Critical/security issues are triaged.** Both real CVEs were fixed before or at the moment of disclosure.

### B.3 Sentiment trajectory since Feb–May 2026 "nightmare to set up" complaints

The April 3, 2026 r/zeroclawlabs post by u/Anarchytect27058 is the canonical Feb–May 2026 negative. The June–October 2026 set is **clearly improved but mixed**, with three new positive signals and the same core docs/install complaints reappearing in different forms.

**Recent positive (post-May 2026):**

- We Shall Build (2026, post-v0.8.3): successful 30-minute Discord-on-Kali install with `zeroclaw quickstart` → daemon → `/onboard` → working bot. Notes v0.8.3 fixed the typing-indicator timeout. Calls the project "an extremely exciting and efficient proof-of-concept platform."
- LumaDock (2026-06-03): "About half the time, running `zeroclaw doctor` tells you exactly what's wrong and you don't need to read any further." Acknowledges the recurring errors but says they all have well-known fixes.
- Digital Loop (2026, post-v0.8.x): "It's currently more of a well-made playground with real strengths, but it takes time to understand the system and even more to configure everything." Concludes "not yet an enterprise product" but values the proof-of-concept angle.
- Steven Cargall (2026-05, post-v0.7.4): zero→working Docker + LiteLLM + vLLM + Qwen3 setup. Documents a real bug (#6123) but says "If you see `OK`, ZeroClaw is talking to your local Qwen via LiteLLM. Congratulations!"
- The release notes themselves (v0.8.0 → v0.8.5) are a strong positive signal: monthly cadence, public notes, milestone-tracked roadmap, RFC-driven design (the intentional-architecture doc, the microkernel refactor), and the security hardening wave in v0.8.0 / v0.8.3 / v0.8.5.
- Henry J Schmale (2026-04-20, mid-transition): "I see why people are excited about it, but at the same time I still don't like it. I can also see why people are so upset about it." Mixed.

**Recent negative (post-May 2026):**

- Issue #6119 (2026-05, Windows + MiniMax + Cyrillic): eight-hour setup, broken dashboard assets, malformed tool-call JSON, "the recommended installation path is simply to use Codex or Windsurf instead." Still cited as a real failure mode.
- r/LocalLLaMA 1rd980h (post-v0.8.x): "can't really recommend ZeroClaw. I've tried to briefly use it but the amount of stuff that is just straight up broken was mind boggling." Also: "zeroclaw is oversecured and useless by default, you will need to permit very basic stuff by editing config manually."
- eesel AI review (2026, third-party but not a paid sponsor; their own competing product): "reviewers on Hacker News flagged gaps in its security story." Quotes HN's `vintagedave`: "I'm especially worried about exfiltration or other negative behaviours." Quotes `yencabulator`: "the lethal trifecta" (read untrusted data + tool access + exfiltration) "made me tag the project as naive." (Both HN quotes are 2026 launch-thread, not strictly recent, but the eesel review itself is recent.)
- Issue #11594 (2026-10-07): the firejail_args knob is a real, current "insecure by default" pattern. Still open.
- The maintainers' own `/onboard` v0.7.5 web flow was a deliberate response to the April 2026 install complaints; that the response shipped and is being positively cited in summer 2026 reviews is the strongest sentiment-improvement evidence.

**Net:** the broad sentiment has moved from "this isn't ready for hobbyists" (Apr 2026) to "this is a credible proof-of-concept with a hard install ceiling" (summer/autumn 2026). The docs and web dashboard in v0.7.5 + v0.8.0 are credited with this; the remaining complaints are about TOML-editing for advanced features, custom-skill ergonomics, and pre-1.0 stability, not the broken install paths of April.

### B.4 Astroturfing / paid promotion / domain squatting — high

The "claw" niche is overrun with impersonation. **This is a documented, active problem the maintainers themselves repeatedly warn about.**

**Squatted / impersonator domains (verified 2026-10-07):**

- **zeroclaw.net** (mentioned in eesel AI's "How to test it" guide as the bring-your-own-API-key URL).
- **zeroclaw.co** — full marketing site, "Zero Overhead, Zero Compromise … 🦀 Zero Claw Lobster," curls `https://zeroclaw.co/install.sh | bash` from the front page. **Not the official project.**
- **zeroclaw.dev** — alternative marketing site, "Fast, small, autonomous AI assistant infrastructure," "Visit GitHub ★ Star on GitHub" CTA. Visually similar to the official site. **Not the official project.**
- **zeroclaw.org** — currently pointed to `openagen/zeroclaw` fork per the official advisory on the original repo's README.

**Squatted / impersonator GitHub repos (verified):**

- `theonlyhennygod/zeroclaw` (the original creator's personal account, before the org was set up) — still on GitHub, with an in-README notice: "We are **NOT affiliated** with `openagen/zeroclaw`. The `zeroclaw.org` and `zeroclaw.net` domains currently point to the `openagen/zeroclaw` fork, and that domain/repository are impersonating our official website/project. Do not trust information, binaries, fundraising, or announcements from those sources."
- `morpheum-labs/zeroclaw` — "restorage of zeroclaw … Built by students and members of the Harvard, MIT, and Sundai.Club communities." Bio text lifted nearly verbatim from the official site.
- `elev8tion/zeroclaw` — copy of the same bio.
- `openagen/zeroclaw` (referenced from zeroclaw.org).
- `zeroclaw-co/zeroclaw`, etc.

The **official** project is `zeroclaw-labs/zeroclaw` (note the `-labs` suffix on the org) and the official homepage is **`zeroclaw.com`** per the GitHub repo's `homepage` field, with the `zeroclawlabs.ai` domain used in the v0.8.0 blog post. Anything at `zeroclaw.dev`, `zeroclaw.co`, `zeroclaw.net`, or `zeroclaw.org` is **not** the project.

**"Review" sites that read like SEO farms (verified 2026-10-07):**

- **toolbrain.net/blog/zeroclaw-review** — quotes "independently verified benchmarks" that are not linked to any methodology, recycles the project's own marketing tables, and ends with a comparison table to OpenClaw. Reads like a content-marketing piece, not a review.
- **awesomeagents.ai/reviews/review-zeroclaw** — benchmark numbers (38 MB idle, 14x faster) appear to be rephrased from the project's own blog post; the review has no byline, no contact, no methodology link.
- **limpidreviews.fyi/tools/zeroclaw** — runs a "review" score (7.8/10) with a "Reviewed April 24, 2026" stamp, no author. The site is one page per tool; pattern matches an SEO template.
- **winmassiveimpact.com/resources/marketing/zeroclaw-guide** — quotes the same r/zeroclawlabs complaint thread, warns about "the naming trap" (i.e. its own SEO/keyword position), and tells the reader to "choose Hermes" instead. Reads as a content-marketing piece for a competing product.
- **tracxn.com / d company profile for ZeroClaw** — generic company page generated from the project description.
- **eesel.ai/blog/zeroclaw-review** — has a byline, methodology note, and identifies itself as a competing product. Honest about its bias. **Not astroturfing** but is clearly a competitive comparison.
- **lumadock.com/tutorials/zeroclaw-troubleshooting-common-errors** — translated into 90+ languages (Swedish, others) with the same content. Reads like a content-marketing site, not first-party docs.

**Partnership-solicitation signal:** GitHub issue #4298 (Partnership Inquiry) shows a third party asking the project for "Sponsor placement / featured sponsor display / Default model provider recommendations / Dedicated signup or referral links" — i.e. a real offer to pay for placement. The maintainers' response is correct ("the issue tracker is reserved for bugs and feature requests … the best path is reaching out directly to the maintainers through the project's community channels") and they did not accept. But the offer confirms that the affiliate/review-site ecosystem around ZeroClaw is at least partly paid.

**Net:** the impersonation ecosystem (≥3 squatted domains, ≥3 squatted GitHub repos, an active `zeroclaw.org` pointing at an unauthorized fork) is real and the maintainers have explicitly warned about it. The "review" sites are mostly thin content-marketing with recycled marketing tables and no methodology. eesel.ai and we-shall.build and Big Muddy are the readable primary-source hands-on reviews. The Windows/MiniMax GitHub issue #6119 is a credible user report, not SEO.

---

## C. SOURCES (with dates)

- GitHub Security Advisories tab for `zeroclaw-labs/zeroclaw` (queried 2026-10-07): 1 published advisory (GHSA-93f6-34w8-5g98).
- GHSA-93f6-34w8-5g98 advisory page: published 2026-09-05 16:31:36 UTC; affected ≤ 0.8.4; patched ≥ 0.8.5; reporter `JordanTheJet`.
- GHSA-f385-f6h2-3gqj: 404 from `github.com/zeroclaw-labs/zeroclaw/security/advisories/GHSA-f385-f6h2-3gqj`; PR #6942 with the fix text and timeline (filed 2026-05-18, fix in v0.8.0-beta-2 / v0.8.0 GA 2026-06-12).
- GitHub Advisory Database global query for `zeroclaw` (queried 2026-10-07): 1 advisory, status "Unreviewed."
- NVD query for `zeroclaw` (queried 2026-10-07): 1 CVE (CVE-2026-101885, published 2026-09-30 by VulnCheck, not the project).
- VulnCheck advisory page (2026-09-30): CVE-2026-101885, CVSS 8.5, CWE-22.
- v0.8.5 release notes (2026-09-05 07:31:19 UTC, github-actions[bot], 454 commits, 73 contributors).
- v0.8.4 release notes (2026-08-02). v0.8.3 (2026-07-16, 379 commits / 56 contributors). v0.8.2. v0.8.1. v0.8.0 (2026-06-12). v0.8.0-beta-2. v0.7.5 (2026-05-08, 71 commits / 24 contributors).
- `zeroclaw-labs/zeroclaw` GitHub repo metadata via REST API: created 2026-02-13 08:56:04 UTC, license Apache-2.0 (not MIT/Apache-2.0 dual — note the task brief said dual, the API says Apache-2.0 only), 32,936 stars, 4,954 forks, 948 open issues, 83 watchers, default branch `master`, homepage `zeroclaw.com`.
- `zeroclaw-labs/zeroclaw/blob/master/SECURITY.md` (queried 2026-10-07): 48h ack / 1wk assessment / 2wk fix for critical; 3 autonomy levels (ReadOnly/Supervised default/Full), 5 sandboxing layers, 129 automated security tests claim, CIS Docker Benchmark claims.
- Issue #11594 `firejail_args advertised but not applied` (2026-10-07, S2, open).
- Issue #4298 `Partnership Inquiry` (2026) with maintainer pushback.
- Issue #1043 `[Feature]: Execute multiple tool calls concurrently` (2026-02-20) and issue #2352 `[Bug]: Duplicate workflow runs` (2026-09) — for response-time evidence.
- r/zeroclawlabs 1sb7x9d "A cautionary tale about ZeroClaw" by u/Anarchytect27058 (2026-04-03 08:33 UTC, 10 pts, 8 comments); r/openclaw 1rv4629 (v0.1.9, "dead chatbot"); r/zeroclawlabs 1rgthm6 (skills question); r/LocalLLaMA 1rd980h ("ZeroClaw or should I go full IronClaw?").
- `muddy.jprs.me/posts/2026-03-02-testing-zeroclaw-part-1-setup/` (Big Muddy blog, 2026-03-02).
- `weshall.build/en/blog/zeroclaw-personal-ai-assistant/` (We Shall Build, post-v0.8.3).
- `lumadock.com/tutorials/zeroclaw-troubleshooting-common-errors` (2026-06-03).
- `digital-loop.com/en/blog/agent-based-ai-my-exeprience-with-zeroclaw` (2026).
- `stevescargall.com/blog/2026/05/...qwen3-on-an-nvidia-dgx-spark/` (2026-05, with v0.7.4 onboarding bug #6123 evidence).
- `henryschmale.org/2026/04/20/claws.html` (2026-04-20).
- `toolbrain.net/blog/zeroclaw-review/`, `awesomeagents.ai/reviews/review-zeroclaw/`, `limpidreviews.fyi/tools/zeroclaw`, `winmassiveimpact.com/resources/marketing/zeroclaw-guide` — third-party "review" sites (mostly content-marketing).
- `eesel.ai/blog/zeroclaw-review` (2026, by a competing product; identified as such).
- The `i-scoop.eu/zeroclaw-as-your-personal-agent/` and `josenobile.co/guides/zeroclaw/` marketing-style guides.
- The squatted domains `zeroclaw.co`, `zeroclaw.dev`, `zeroclaw.net`, `zeroclaw.org` (HTTP 200, marketing content unrelated to the official project).
- The squatted repos `theonlyhennygod/zeroclaw` (with the impersonation warning in its own README), `morpheum-labs/zeroclaw`, `elev8tion/zeroclaw`, and `openagen/zeroclaw` (referenced from zeroclaw.org).
- Tracxn company profile (https://platform.tracxn.com/a/d/company/6993fdeb06c8e07ea62eaecf/zeroclaw).
- HN launch thread quotes (`vintagedave`, `yencabulator`) as cited by the eesel review.

---

## D. SHORT VERDICT

- **Security:** only one formally published advisory (wasm_path RCE), fixed same-day. One prior canvas-token-theft advisory was fixed in v0.8.0 (2026-06-12) but never published as a GHSA / assigned a CVE — outside auditors will under-count the project's real disclosure history. No independent security audit exists; the project's "129 tests" and "CIS Docker Benchmark" claims are self-asserted. The "secure by default" marketing is only partially accurate — `firejail_args` is a current (2026-10-07) example of a documented knob that does nothing, plugin signature verification is off by default, and the dashboard bearer still sits in `localStorage` post-fix.
- **Community sentiment:** improved materially since April 2026. v0.7.5 `/onboard` flow + v0.8.0 multi-agent + v0.8.5 security wave turned "nightmare" into "hard but doable" for developers. Negative sentiment persists in three buckets: (1) Windows + MiniMax tool-call JSON correctness, (2) custom skills requiring Rust, and (3) the pre-1.0 stability ceiling. Channel reliability has been incrementally fixed (v0.8.3 typing indicator) but new regressions appear in the same surface.
- **Astroturfing/Squatting:** high. The maintainers themselves publicly warn about it. At least 4 squatted domains and 4 squatted repos, plus a templated "review" ecosystem.