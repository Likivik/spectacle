# Self-Hoster & OSS Dynamics — Achlys

**Question:** What do self-hosters of RisuAI / SillyTavern / Bitwarden actually
value, what does E2EE-by-default mean for them when they ARE the operator, does
client-side architecture make self-hosting trivial, how do TEE products
realistically accommodate self-hosters, and what precedents exist for OSS
projects combining paid hosting with an open-source self-hostable core?

**Audience:** Achlys product team — AGPL-3.0 SvelteKit + Tauri 2 + Rust/Axum
roleplay client, planning both a self-hostable open-source release AND a paid
hosted tier (`APP_SPEC.md` §Open Decisions; `e2ee-business-model-survey.md`).

**Method:** Combined the prior Achiyon E2EE surveys
(`/Storage/Git/spectacle/.hermes/research/e2ee-{app-architecture,business-model,
browser-capability}-survey.md`) with fresh research on the active self-hoster
communities of RisuAI / SillyTavern / Bitwarden, the Ghost / Plausible / Bitwarden
"OSS + paid hosting" precedents, and TEE hardware availability on homelab
hardware.

---

## 1. What self-hosters actually value

The self-hoster communities for RisuAI, SillyTavern and Bitwarden are
distinct in culture but converge on a remarkably similar value stack.
Self-hosters in this category are *not* primarily cost-driven; they are
*control-driven*, and they tolerate real friction (Tailscale, reverse proxies,
manual backups, single-maintainer bus-factor risk) to get that control.

### 1.1 RisuAI self-hosters

- **Project posture.** RisuAI is GPL-3.0, 1.5K+ GitHub stars, ~330 forks,
  ships as a hosted web app (`risuai.net`), a Tauri desktop client for
  Win/Mac/Linux, and self-hostable Docker / Node.js source. It is a
  *frontend that connects to a model backend you choose* — BYO-key, no model
  bundled, no subscription for the client itself. (PromptQuorum review,
  Sep 2026.)
- **Active fork ecosystem.** `PocketRisu/PocketRisu` (264★ / 52 forks) is
  explicitly *"refined for self-hosted environments — runs on your PC or
  personal server and access from PC, tablet, smartphone through a web
  browser,"* with a single SQLite DB and an "all data on your server, no
  external cloud dependency" pitch. `nevaeh5379/HaejeokRisuai` and
  `rhplus0831/risuai-fastify` are independent forks of varying age that
  each pick a different trade-off (Docker+Postgres+RustFS S3 vs Fastify
  server-owned data). `devforai-creator/RisuAI-Hardened` is a
  *"security-hardened fork … local-only, no cloud dependencies."*
- **What they value (synthesised from forker READMEs):**
  1. **Server ownership of state** — PocketRisu's central pitch is moving
     *"all data (characters, chats, settings, inlay images) to a single
     SQLite database on your server (no external cloud dependency)."* When
     the upstream RisuAI keeps state in the browser, the entire fork
     culture reinvents this.
  2. **Multi-device access from one trusted server** — *"Run one server,
     access from PC, tablet, smartphone through a web browser."* They want
     to consume from phone without giving a third party the chats.
  3. **Migration compatibility** — *"Existing RisuAI data can be migrated
     wholesale, and all RisuAI ecosystem assets remain usable as-is."* The
     ability to fork *and* keep the cards/presets/lorebooks from the
     upstream ecosystem is what makes a fork viable.
  4. **No vendor coupling** — HaejeokRisuai explicitly excludes RisuRealm
     login ("RisuRealm is treated as an external upstream service … keeps
     its own authentication, terms, and content rules"); RisuAI-Hardened
     removes all cloud/sync deps. The threat model is *operator*
     (upstream author) and *infrastructure* (RisuAI's hosted infra), not
     nation-state adversaries.
  5. **Audit and modify the prompt pipeline** — the RisuAI/SillyTavern
     communities are tinkerers. They want to inspect and modify the exact
     LLM call.

### 1.2 SillyTavern self-hosters

- **Project posture.** "Passion project … brought to you by a dedicated
  community of LLM enthusiasts, and will always be free and open sourced"
  (SillyTavern README). 300+ contributors, forked from TavernAI 1.2.8 in
  Feb 2023, *"will always be free and open sourced,"* no online services,
  no tracking. Two-branch system (`release` stable monthly, `staging`
  several times daily) is itself a self-hoster accommodation: power users
  want bleeding edge, casual users want stability.
- **Self-hoster configuration.** SillyTavern admin docs show a clean
  per-user directory layout (`data/[user-handle]/`), Docker support,
  multi-user account creation, password-protected users, and the
  long-standing pattern of pointing SillyTavern at a *local* inference
  backend (KoboldAI / Oobabooga / Ollama) over `127.0.0.1:<port>`. The
  user brings the model; SillyTavern is the UI.
- **What they value:**
  1. **No subscription, no telemetry.** Direct from the README: *"We do
     not provide any online or hosted services, nor programmatically track
     any user data."* This is the founding contract.
  2. **Power-user customization.** *"Steep learning curve is part of the
     fun"* (README). Self-hosters in this community routinely fork
     extensions, write STscript, modify prompt orders, and pin to
     `staging`.
  3. **BYO-model and BYO-key.** The fact that the backend is pluggable is
     the entire self-host story — they pick the inference hardware and the
     card ecosystem stays theirs.
  4. **Control over the LLM stack end-to-end.** Running on their own
     hardware (often a 3090/4090) gives them control of prompt caching,
     model selection, context size, and uncensored output. The entire
     reason to run a local model is to escape remote operator control.
  5. **Fork-friendliness.** The "300+ contributors" headline is a
     self-hoster culture signal — they expect to send PRs.

### 1.3 Bitwarden self-hosters (the canonical case)

- **The Vaultwarden phenomenon.** Vaultwarden (formerly `bitwarden_rs`)
  is a community Rust re-implementation of the Bitwarden server API, ~50
  MB RAM, runs on a Pi, ~58K GitHub stars, ~2.7K forks. *"Not associated
  with Bitwarden or Bitwarden, Inc."* — though one active maintainer works
  at Bitwarden.
- **What they cite as motivation** (XDA 2026, HowToGeek 2026,
  Selfhostr 2026 analysis, Railway Vaultwarden template 2026):
  1. **Data sovereignty.** *"Encrypted vault never leaves a server you
     control"* (Railway Vaultwarden doc). *"You do not control the exact
     physical location of your data at any given moment. Bitwarden can
     migrate your data between regions to optimize costs or compliance,
     without your direct intervention"* (Selfhostr 2026). This is the
     *legal* sovereignty argument (jurisdiction / GDPR / Schrems II), not
     just the cryptographic one.
  2. **Escape from SaaS breach history.** LastPass 2022 breach drove the
     first Vaultwarden migration wave (XDA, Elestio timelines); Bitwarden
     CLI npm supply-chain compromise in 2026 drove the second wave
     (NovVista analysis).
  3. **Avoiding per-seat cost for teams.** *"A 15-person company pays
     $720 to $1,080 a year just for vault access, and that number climbs
     every time you hire. Vaultwarden self-hosted … costs a flat
     infrastructure fee no matter how many people or organizations you
     add"* (Railway template).
  4. **Lower latency on local networks.** Selfhostr measured Bitwarden
     Cloud at 45–80 ms vs Vaultwarden on local/close VPS at 2–5 ms.
  5. **Premium features for free.** Vaultwarden reports every account as
     "premium" to the official clients, because there is no billing
     system. TOTP authenticator, file attachments, emergency access,
     organisations, advanced 2FA — all unlocked. The XDA 2026 article
     describes this as the *price-hike trigger* (Premium $9.99 → $19.80,
     Families $40 → $47.88) that pushed them off the SaaS.
  6. **No third-party cloud.** *"No cloud subscription. No vendor
     lock-in. No breach notifications from a company you forgot you
     trusted"* (the Zero Password Manager fork's framing, representative
     of the broader self-host ethos).
- **What they explicitly sacrifice.** Maintenance (updates, backups,
  HTTPS, monitoring), no SOC 2 / GDPR DPA / SLA, single-maintainer bus
  factor on Vaultwarden (~2), no official enterprise tier features (SSO
  is awkward, no SCIM/audit logs without manual nginx work). Selfhostr's
  TCO math: *"If your time is worth €50/hour, you only need 1 hour of
  maintenance per month for Vaultwarden to become more expensive than
  Bitwarden Premium."* For a team of 10+ the *time cost* dominates and
  managed cloud wins.

### 1.4 The convergent self-hoster value stack

Strip the surface differences and the values collapse to four:

| Value | RisuAI | SillyTavern | Bitwarden | Achlys implication |
|---|---|---|---|---|
| **Custody / sovereignty** over state | Server-Owned fork culture | Local-first BYO model | Vaultwarden, explicit "no third-party cloud" | Native mobile shell + clear "data lives where you put it" messaging |
| **No subscription, no telemetry** | BYO-key, no charge for client | "Always free and open sourced, no tracking" | Vaultwarden exists *because* of subscription fatigue | AGPL-3.0 self-hostable core, generous free tier, no analytics phone-home |
| **Fork-friendly ecosystem compatibility** | PocketRisu / Haejeok / Hardened forks | 300+ contributors, plugins | Vaultwarden is itself a clean-room re-implementation | Maintain ST card format, Risu asset format, character card v2/v3, lorebook format as importable specs |
| **Customisation depth** | Prompt inspector culture | STscript, extensions, prompt canvas | TOTP, orgs, custom branding | Prompt trace, lorebook activation trace, regex/script hooks, stateful lorebook activation |

The clear consensus: **self-hosters are a power-user minority with
above-average technical competence, an above-average distrust of vendors,
and an above-average willingness to pay in time what they save in
money.** They are not the dominant revenue source — but they are the
community that *validates the software* and produces the content (cards,
lorebooks, presets, prompt guides) that drives the rest of the funnel.

---

## 2. E2EE-by-default — what it means when the user IS the operator

This is the most subtle question for Achlys. The prior
`e2ee-business-model-survey.md` (Bitwarden / Vaultwarden split, §3) and
`e2ee-app-architecture-survey.md` (synthesis §#4) already concluded that
E2EE "mildly strengthens the SaaS rather than hollowing it out" — because
convenience, reliability, storage, compliance, and family seats still
dominate purchase decisions. But there is a self-hoster-specific angle
worth sharpening.

### 2.1 Is E2EE meaningless when self-hosting?

**No, but it means something different.** The prior survey frames this
correctly in §1: self-hosters are not *the operator* in the threat-model
sense — they are *the operator's customer* in the SaaS sense, AND they
are *the operator's infra provider* in the homelab sense. Three concrete
ways E2EE matters to a self-hoster:

1. **Protection against the VPS / cloud provider.** A Vaultwarden-on-Railway
   user explicitly cited *"encrypted vault never leaves a server you
   control"* as the motivating value. But for many self-hosters, "a
   server you control" means "a Hetzner / DigitalOcean / OVH VPS." The
   VPS provider sees the disk image; the VPS provider can be subpoenaed;
   the VPS provider can be breached at the hypervisor level. E2EE keeps
   the *content* opaque even to that provider. Vaultwarden's value
   proposition to a Railway user is *both* "your data, your jurisdiction"
   *and* "your data, opaque to Railway staff." The Bitwarden free tier
   also gives full E2EE — that's the table-stakes feature.

2. **Protection against operator-level mistakes.** A self-hoster who
   sets up RisuAI on a Raspberry Pi with a Tailscale funnel is exposing
   one port to the internet. If a misconfiguration logs plaintext
   requests to disk, the user's chats leak. E2EE means a request-log
   leak is *not* a content leak. This is precisely why Proton-encrypted
   storage protects self-hosters even though Proton can't see the
   content.

3. **Defense against future-you.** A self-hoster's threat model often
   includes "what if I lose the disk and the buyer of the used SSD
   recovers the partitions?" or "what if my partner/roommate/employer
   later gets admin access to the box?" E2EE keeps content opaque
   without root on the same machine.

### 2.2 Does E2EE change the value of self-hosting for the operator?

**Slightly less than you'd think.** The Bitwarden/Vaultwarden split is
the cleanest test, because the protocol is identical on both sides and
the *only* difference is who runs the server. Selfhostr 2026 concludes
*"the debate between Vaultwarden and Bitwarden Cloud is no longer about
'who is safer,' as both offer enterprise-grade security thanks to
Zero-Knowledge encryption. It is a question of who assumes operational
responsibility."* That is, E2EE has *flattened the security argument*
to where it is no longer the deciding factor. What decides is custody,
cost, compliance, and convenience.

For Achlys specifically: the architecture survey (`e2ee-app-architecture-survey.md`
§4) is unambiguous that **server-side LLM inference is fundamentally
incompatible with Signal-style E2EE** — the LLM must read the prompt in
plaintext. So Achlys *cannot* offer E2EE on the hosted AI tier without
one of the three known compromises (client-side LLM, TEE enclave,
end-to-end encryption to a third-party LLM provider). That means
**the E2EE story for hosted Achlys has to be honest**: E2EE protects
metadata, backups, API key storage, card library, lorebook text *at
rest*; it does not protect the prompt/response at inference time on the
hosted tier. This is the same position Proton's "Bridge" mode takes
(their blog post is the most explicit write-up of this trade-off).

For the self-hosted tier, the picture is cleaner. With a local Ollama
backend (or a BYOK cloud API), the user controls the entire chain and
*can* achieve true E2EE if the inference endpoint is local. That is the
configuration SillyTavern / RisuAI users already adopt, and it is
precisely the value they pay in time for.

### 2.3 What E2EE does *not* do for self-hosters

The Zero Password Manager README captures the most extreme self-hoster
position: *"Every major password manager — LastPass, 1Password,
Bitwarden Cloud — ultimately stores your vault on someone else's server.
'Zero-knowledge' in their marketing means they claim not to read your
data. It doesn't mean they can't. Zero Password Manager takes a
different position: the server that holds your vault is one you run
yourself."* In other words, *for the most security-conscious self-hosters,
E2EE is necessary but not sufficient* — they want custody AND E2EE, and
they are skeptical of vendor claims regardless of how good the audit
record is. The architecture survey's synthesis §#1 ("the server reduces
to (a) authenticated encrypted blob store …") is exactly what
self-hosters want the vendor's server to be.

---

## 3. Client-side architecture → trivial self-hosting?

### 3.1 Static files + dumb storage = trivial

If the Achlys architecture degenerates to "Tauri shell holding a SvelteKit
SPA + Axum server that stores blobs and forwards LLM requests" (the
Tier 1 model in the architecture survey §#4), then self-hosting is
genuinely one-container trivial. The current state of the Achlys repo
already tilts this way:

- **SvelteKit with `adapter-static`** (the existing `web/` repo config
  already uses this — verified in `/Storage/Git/spectacle/.hermes/
  reports/2026-09-16-ui-verification-tooling-comparison.md`).
  Static SPA = `nginx`-able from any CDN, any home directory, any
  homelab static-file host.
- **Tauri 2** wraps the SPA in a 3–10 MB Rust binary with native
  crypto hooks, optional embedded Axum on `127.0.0.1`, optional
  standalone server. The APP_SPEC.md describes exactly this dual-mode
  deployment.
- **Achlys APP_SPEC.md** explicitly lists the deployment model as
  *"Server+client split AND all-in-one embedded — User toggles local
  (embedded Axum on 127.0.0.1) vs remote (standalone server URL)."*

That maps almost exactly onto PocketRisu's self-host pitch (*"run on your
PC or personal server and access from PC, tablet, smartphone through a
web browser"*) and Vaultwarden's (*"a single Docker container"*). The
deployment ergonomics are *not* the barrier.

### 3.2 What *is* the barrier

What the survey of RisuAI / SillyTavern / Bitwarden self-hosters reveals
is that the hard parts are *not* deploying the binary:

1. **Reverse proxy + HTTPS.** Every documented self-host workflow —
   Vaultwarden (Tailscale + Caddy), PocketRisu (Docker compose), SillyTavern
   in Docker (the `host.docker.internal` gotcha in the official docs) —
   requires the user to terminate TLS. PocketRisu / SillyTavern use plain
   HTTP and rely on Tailscale / LAN for confidentiality, which is fine
   for a homelab but breaks for cross-network access.

2. **Auth on by default.** APP_SPEC.md §14 says *"Authentication on by
   default."* This is the right call — Bitwarden's whole 2022-era
   incident history (LastPass breach) and the Selfhostr 2026
   recommendation *"It is imperative to set SIGNUPS_ALLOWED=false once
   your accounts exist"* show that authentication defaults matter more
   than encryption defaults for self-hosted safety.

3. **Backups.** APP_SPEC.md §13 covers backup/restore. Vaultwarden
   selfhostrs run `rsync` cron jobs to a second machine + encrypted
   object storage (3-2-1 strategy, per XDA 2026). The Tauri app's
   embedded SQLite makes this trivial (`cp` the file); the
   Postgres+server mode makes it a pg_dump job. Both are doable; neither
   is automatic.

4. **Updates.** Vaultwarden, PocketRisu, SillyTavern-staging all
   require manual `docker compose pull && up -d` discipline. Watchtower
   helps but can corrupt SQLite on migration script failure. Achlys's
   shared Rust crate design (`achlys-core/` shared between `achlys-app/`
   and `achlys-server/`) makes Tauri app updates orthogonal to server
   updates — actually a usability win for split deployment.

5. **The LLM backend itself.** The dominant cost for a serious RP
   self-hoster is the GPU (a 3090/4090/A100), not the Achlys server.
   This is a category-defining constraint: **the Achlys self-host story
   only works if Achlys does not require a GPU to host.** The current
   APP_SPEC assumes BYO model (OpenAI-compatible endpoint, local
   Ollama, etc.), which is correct.

### 3.3 The net answer

**Client-side architecture makes self-hosting *cheap*, not *trivial*.**
The minimum bar (single Docker container, BYOK, optional HTTPS, SQLite
WAL) is well within reach of any user who runs Vaultwarden today. The
*higher* bar (HA, offsite backups, monitoring, multi-user, RBAC) is
where paid hosting earns its margin. This is the same shape as Ghost's
comparison table:

| | Ghost(Pro) | Self-host Ghost |
|---|---|---|
| Base hosting | $15/mo | $10/mo |
| CDN + WAF | included | $20/mo |
| Email newsletter delivery | included | $15/mo |
| Analytics | included | $10/mo |
| Backups | included | $5/mo |
| Image editor | included | $12/mo |
| **Total** | **$15/mo** | **$72+/mo** + maintenance |

The 5× cost differential is *operational*, not infrastructural. Achlys
should plan for this: most users will not DIY it, even at
micro-enterprise scale.

---

## 4. TEE products and the homelab

This is the unique tension for any architecture that wants to use TEEs
as the privacy primitive.

### 4.1 TEE hardware availability on homelab

The 2026 confidential-computing landscape (Servnet UK 2026, Servermall
2026, Ubuntu TDX docs):

- **Intel TDX** is on 4th-gen Xeon Scalable (Sapphire Rapids), 5th-gen
  (Emerald Rapids), Xeon 6 E-cores (Sierra Forest), Xeon 6 P-cores
  (Granite Rapids). Host support begins with Ubuntu 25.10; guest support
  Ubuntu 24.04 LTS onwards. Sapphire Rapids workstation motherboards
  exist (e.g., Aspeed W790 boards), but they are **server SKUs and
  Xeon workstations** — *not* consumer hardware and *not* the
  consumer/homelab chips that self-hosters buy.
- **AMD SEV-SNP** is on EPYC 7003 (Milan), 9004 (Genoa), 9005 (Turin),
  9006 (future). Turin is the current generation; Servermall and AMD
  both confirm production confidential VM support. Again, **server
  silicon only** — EPYC boards are 1P/2P server boards, not desktop.
- **Consumer chips do not have TDX/SEV-SNP.** Intel Core i-series and
  AMD Ryzen do not ship TDX or SEV-SNP. Apple Silicon has the Secure
  Enclave but it is locked to Apple-managed attestation and is not
  available as a general TEE target. ARM Confidential Compute
  Architecture (CCA) is on server-class Neoverse but not on consumer
  Cortex-A.

**Bottom line for self-hosters: no homelab hardware in 2026 has a usable
TEE for LLM inference.** A self-hoster running SillyTavern + Ollama on
a 4090 desktop does not have TDX or SEV-SNP. A self-hoster running
Vaultwarden on a Pi has neither. A self-hoster running RisuAI on a
mini-PC has neither.

### 4.2 What TEE products can realistically offer self-hosters

Given the hardware constraint, the honest options for a TEE-based
architecture (Tier 2 in the architecture survey §#4) are:

1. **"TEE is only on the hosted tier; the self-host tier is honest
   about not having it."** This is the path DuckDuckGo Duck.ai
   effectively takes (TEE-backed Tinfoil models in the cloud; local
   Ollama integration available for the self-hosted use case). It
   preserves architectural honesty: the hosted tier offers
   TEE-attested, RAM-only, no-log inference; the self-host tier offers
   BYO local inference with whatever hardware the user has.

2. **TEE available as a paid add-on with cloud-attested infrastructure.**
   The user pays the vendor for a confidential VM that wraps the model
   (Intel Trust Authority, Azure Attestation, OpenMetal's TDX-as-default
   offering — OpenMetal ships a Granite Rapids bare-metal with TDX
   *active* at deploy for a fixed monthly fee). Self-hosters who care
   *can* pay for this; self-hosters who don't, won't.

3. **No TEE, ever, on the self-host tier.** This is the only honest
   answer for the *self-host community* because they are running
   hardware the operator doesn't control. If the operator can't
   physically possess the CPU, the operator cannot offer TEE
   attestation — only the cloud vendor can. So TEE is, by definition,
   a *hosted* product feature for Achlys.

### 4.3 The implications

- **TEE is a hosted-tier differentiator, not a self-host one.** A
  self-hoster with the budget for TEE silicon is already self-hosting
  on enterprise hardware (Sapphire Rapids workstation, EPYC server,
  Hetzner dedicated with SEV). They will not pay Achlys for it; they
  will set it up themselves.
- **Don't promise TEE to self-hosters in marketing.** The architecture
  survey (§4 synthesis) warns: *"LLM inference enclaves exist as
  research prototypes but no production chat roleplay service ships
  this."* Signal's contact discovery enclave took years and an entire
  ORAM layer; LLM inference inside TDX is meaningfully harder.
  Promising TEE on a self-host tier where the operator can't enforce
  it (and can't verify the user's hardware) is a credibility risk.
- **The honest product narrative is:** "Self-host = full local control,
  no telemetry, BYO model. Hosted = TEE-attested inference on
  confidential cloud silicon, zero-retention contracts, audit
  attestation you can verify. Pick the one that matches your threat
  model." This mirrors DuckDuckGo / Proton / Plausible's transparency
  approach.

---

## 5. Precedents — OSS products going paid-hosting

Three live, durable precedents, all in production for 5–12 years. The
prior `e2ee-business-model-survey.md` §6 covers all three; the angle
worth adding here is the explicit "why not self-host?" tension that
each handles differently.

### 5.1 Ghost — the most articulate expression

- **Structure.** MIT-licensed core, Ghost(Pro) from $15/mo. **Single
  non-profit entity**, 100% of revenue reinvested. ~$7.5M ARR, profitable
  for 12 years. (Ghost /about, John O'Nolan blog.)
- **The "why not self-host" handling.** Ghost's hosting page has an
  explicit side-by-side comparison (Ghost 6.0 announcement). Crucially,
  Ghost publishes a per-feature cost stack for self-hosters:
  hosting $10/mo + CDN/WAF $20 + email $15 + analytics $10 + backups
  $5 + image editor $12 = ~$72/mo *plus* maintenance time, against
  Ghost(Pro)'s flat $15/mo. *"For heavy users of Ghost, self-hosting
  generally works out to be more expensive vs Ghost(Pro), but for
  lightweight blogs it can be cheaper."*
- **The framing.** *"Nobody is required to use our hosting. In fact,
  the majority of Ghost websites in the world do not use Ghost(Pro) —
  but the ones that do, directly fund the project for the benefit of
  everyone."* This converts self-hosting from a competitive threat
  into a *virtuous cycle* — the self-hosters benefit, and they fund
  that benefit by paying *when it's worth it*.
- **Why it works.** Ghost handles the "why not self-host" tension by
  making the cross-subsidy *explicit and acknowledged*. The hosted
  tier isn't "we want to lock you in"; it's "we want to make it easy
  for you so we can keep funding the thing we both love."

### 5.2 Plausible — "open source on principle, not because it's good business"

- **Structure.** AGPLv3 Plausible Community Edition (CE) for self-host,
  managed cloud subscription as the only funding source. ~12,000
  subscribers, 8-person core team, no investors. Plausible's own
  position: *"We released our code on GitHub and made it easy to
  self-host on principle, not because it is good business."*
- **The "why not self-host" handling.** Plausible's
  `/open-source-website-analytics` page has a permanent cloud vs CE
  comparison. Critically, Plausible *has openly gamed* the comparison
  over time: in 2024 they introduced **"Plausible Community Edition"**
  as a rebrand with a different logo and excluded some enterprise
  features (marketing funnels, ecommerce revenue metrics, SSO, sites
  API) from CE while keeping them in cloud. Same AGPLv3 code, but the
  *new* features are licensed differently.
- **The explicit reason.** Plausible blog 2024: *"We're real people who
  have rent to pay … If we cannot capture the economic value of our
  work, the project will become unsustainable and die. … Several
  popular open source projects have shifted away from traditional
  models … adopting licenses such as BSL or SSPL."* Plausible chose to
  keep AGPL but add a *brand split* and an *open-core* layer for
  enterprise features.
- **What this teaches.** Even the most idealistic OSS analytics company
  felt the reseller / cloud-provider-pressure problem and adjusted. The
  hosted-tier wins not by being better-engineered than the self-host
  tier but by having the *inconvenience outsourced* (operational
  responsibility, updates, EU-only infrastructure, premium support).

### 5.3 Bitwarden — the Vaultwarden split

Already detailed in §1.3 and the prior survey. The short version:
Bitwarden tolerates Vaultwarden because the alternative is
*non-customer*, not Bitwarden customer. The SaaS survives because
Enterprise (SSO, SCIM, audit logs, account recovery, SLA) cannot be
self-hosted without significant engineering work, and because the
Vaultwarden user is *already* the kind of person who would have walked
away to KeePass if Vaultwarden didn't exist. The SaaS value is
*operational* and *compliance*, not *capability*.

### 5.4 What the three precedents teach Achlys

Convergent lessons:

1. **Self-hosting is not the threat — non-usage is the threat.** Ghost,
   Plausible, and Bitwarden all state explicitly that the alternative
   to a self-hoster is *not paying you*, it's *using someone else or
   nothing*. The goal is to keep the user in the ecosystem.
2. **The hosted tier must sell something the self-hoster cannot
   easily replicate.** Operational reliability, compliance
   (SOC 2/GDPR DPA), support contracts, premium features that
   scale-as-team, cross-region redundancy, SLA, bundle.
3. **Make the cross-subsidy explicit and acknowledged.** Plausible's
   "funds the continued development of Plausible CE" is the cleanest
   version; Ghost's "directly fund the project for the benefit of
   everyone" is the most poetic; Bitwarden's "tolerated because the
   alternative is non-customer" is the most pragmatic.
4. **Governance matters.** Ghost is a non-profit from day one;
   Plausible is bootstrapped + self-funded; Bitwarden is bootstrapped.
   The absence of profit-extraction motivation is what makes the
   "pay us for convenience" pitch not feel like a shakedown.
5. **Some self-host features will eventually leak into the cloud-only
   tier.** Plausible has done this explicitly with funnels / ecommerce
   revenue / SSO; Bitwarden with SSO/SCIM at Enterprise; Ghost with
   ActivityPub on Pro only. This is acceptable *if* the open-source
   core remains genuinely useful.

---

## 6. What the architecture choice means for the OSS community strategy

Given the above, the architecture choice Achlys makes (client-side
default + optional TEE on hosted + AGPL-3.0 self-hostable core +
planned paid hosted tier) implies the following OSS-community strategy.

### 6.1 The hosted tier's value proposition is *not* the LLM call

The architecture survey is unambiguous: the LLM call is structurally
something the operator must do on the user's behalf if the model is
not local. So the *cheapest* version of "hosted Achlys" is essentially
"pass-through LLM API + auth + queue + metering + storage." That's
commodity infrastructure. The hosted tier's defensible value is
**everything around the LLM call**:

- **Operational reliability** — uptime, multi-region, auto-backup,
  updates without user intervention.
- **Multi-device, multi-user** — sharing characters, shared lorebooks,
  group chats (Phase 2 APP_SPEC), the social-layer above what a single
  Vaultwarden-style self-host gives you.
- **Compliance** — SOC 2 / GDPR DPA / audit logs / SSO for the B2B /
  studio market. APP_SPEC §14 explicitly mentions auth.
- **Cloud LLM routing with zero-retention contracts and verifiable
  audit.** This is a defensible differentiator even when the user
  uses BYOK — the operator's *job* is to handle the metering, the
  rate-limit edge cases, the billing reconciliation, the audit log
  of which requests went where. This is the equivalent of what
  Proton offers for email (routing + storage + audit, never the
  content).
- **Premium content features** — RisuRealm-equivalent community
  marketplace, curated lorebooks, curated prompt presets, premium
  TTS voices (Fish Audio, etc., per APP_SPEC §Open Decisions).
- **Optional TEE-attested inference** — Tier 2 in the architecture
  survey. Available *only* on the hosted tier (because homelab
  hardware doesn't have TDX/SEV-SNP), as a paid add-on for users with
  the threat model that warrants it.

### 6.2 The self-host tier's value proposition is *everything the
operator cannot do*

Concretely:

- **Native Tauri 2 desktop** with encrypted-at-rest local DB
  (SQLCipher equivalent for SQLite via Rust crates), OS keychain
  integration, hardware-backed 2FA (FIDO2/YubiKey). Vaultwarden
  already shows the request (*"Per-operation OTP gating … Hardware
  attestation"*) — a self-hoster wants this *because* the operator
  cannot do it for them.
- **BYO local LLM** with no metering, no rate limit, no content
  filtering beyond what the local model does. The SillyTavern /
  RisuAI self-host community runs local because they want
  uncensored, unmetered, unlimited output.
- **Full card / lorebook / preset ecosystem compatibility.** APP_SPEC
  already commits to ST card format import; commit explicitly to
  Risu `.charx` / `.risum` / `.risup` formats and a Chestnut-compatible
  lorebook spec. The PocketRisu README explicitly says this is what
  made their fork viable.
- **Server ownership of state for multi-device access** — the PocketRisu
  pitch. A SvelteKit SPA static build + Axum server holding SQLite
  makes this one `docker compose up`.
- **Local TTS / STT** — Fish Audio / Edge TTS / Whisper.cpp all run
  locally on modest hardware. APP_SPEC §10 already covers this.
- **The fork-friendliness of the codebase** — AGPL-3.0 + CLA (already
  decided in APP_SPEC.md §Open Decisions) means a self-hoster can
  fork *and* contribute back. PocketRisu / Haejeok / Hardened fork
  culture for RisuAI shows this is the path to community buy-in.

### 6.3 The OSS community strategy, distilled

Six concrete moves:

1. **Ship the self-hostable core first, generously.** The PocketRisu
   / Vaultwarden pattern: a single `docker compose up`, AGPLv3, BYOK,
   no analytics, no telemetry. Treat the self-hostable core as the
   *advertisement* for the hosted tier, not as a competitor to it.

2. **Make the cross-subsidy explicit in the README.** *"This open-source
   project is developed by Achlys Corp. The hosted tier exists to fund
   development that benefits self-hosters too — paid users subsidise
   free users (free tier hosted accounts, free community tools, free
   audits)."* This is the Ghost framing; it works.

3. **Adopt a non-profit / no-extraction governance posture once
   profitable.** Ghost is a non-profit; Proton became one in 2024.
   Bitwarden is bootstrapped. Achlys doesn't need to be a non-profit
   from day one, but signalling "no VC, no exit, no acquisition"
   makes the "why pay us?" question not feel like a shakedown.

4. **Gate *enterprise* features, not *user* features.** This is the
   GitLab / Bitwarden model: free tier + self-host has the full
   single-user feature set. Paid tier (Family / Studio / Business)
   adds multi-user features (org sharing, SSO, audit logs,
   compliance, support, SLA). Plausible's exclusion of funnels /
   ecommerce / SSO from CE is the wrong side of the line — those
   are *operator* features, not *developer* features.

5. **The hosted tier sells ops + convenience + compliance + optional
   TEE.** The architecture survey's recommendation stands: the
   hosted tier sells what a self-hoster would have to build
   themselves (CDN/WAF, email delivery, backups, compliance, support,
   image processing, etc.) at the price Ghost list says.

6. **TEE is a hosted-only feature, never promised on self-host.**
   Self-hosters don't have TDX/SEV-SNP hardware. Don't promise it.
   Position the hosted tier as: *"if you want attested inference,
   you can only get it from us — and here's the attestation receipt
   you can verify against Intel Trust Authority / Azure
   Attestation."* This is the DuckDuckGo / OxiHub-veil path.

### 6.4 What *not* to do

- **Don't compete with the self-host tier on features.** If a
  self-hoster can get 100% of the functionality by running
  `docker compose up`, the hosted tier's *only* differentiation is
  convenience, and convenience alone is a thin moat. Vaultwarden
  proves the self-host tier eventually erodes Premium features.
  The answer is to *invest* in features that require operational
  scale (CDN, multi-user, audit, compliance, support) and that a
  single homelab cannot provide.
- **Don't claim E2EE on the AI prompt/response on the hosted tier.**
  The architecture survey §4 is unambiguous: server-side LLM
  inference cannot be E2EE without one of the three compromises.
  Either commit to a specific compromise (TEE, encrypted-to-third-
  party-LLM) and ship it honestly, or label the hosted tier
  accurately as "encrypted at rest + zero-retention contracts +
  RAM-only processing + no training" — the Proton / DuckDuckGo
  framing.
- **Don't blame the self-host community for "free-riding."** The
  Bitwarden position is the right one: the alternative to a
  self-hoster using your open-source code is *not you*, it's
  *someone else or nothing*. Self-hosters who would have used
  Vaultwarden instead of paying for Bitwarden Premium are not
  customers you lost; they are people who would not have been
  customers at all. Self-hosters who do pay are paying for
  convenience and compliance. Be grateful, not defensive.

---

## Sources

### RisuAI / SillyTavern self-host community

- **RisuAI GitHub** — https://github.com/kwaroran/RisuAI — README, GPL-3.0, 1.5K★
- **PromptQuorum RisuAI review 2026** — https://www.promptquorum.com/power-local-llm/risuai-review
- **RisuAI on Docker / self-host** — https://github.com/kwaroran/RisuAI (Docker compose in README)
- **PocketRisu (self-host-first fork)** — https://github.com/PocketRisu/PocketRisu — *"derived from RisuAI and refined for self-hosted environments"*
- **HaejeokRisuai (Docker+Postgres+RustFS fork)** — https://github.com/nevaeh5379/HaejeokRisuai
- **risuai-fastify (server-owned-state fork)** — https://github.com/rhplus0831/risuai-fastify
- **RisuAI-Hardened (local-only fork)** — https://github.com/devforai-creator/RisuAI-Hardened
- **SillyTavern README** — https://github.com/SillyTavern/SillyTavern/ — *"always be free and open sourced … no tracking"*
- **SillyTavern admin docs** — https://docs.sillytavern.app/administration/ — per-user `data/[user-handle]/` layout, multi-user accounts
- **SillyTavern self-hosted LLM backend guide** — https://github.com/sillytavern/sillytavern-docs/blob/main/Usage/API_Connections/self-hosted.md — KoboldAI / Oobabooga, Docker `host.docker.internal` gotcha

### Bitwarden / Vaultwarden self-host community

- **Vaultwarden GitHub** — https://github.com/dani-garcia/vaultwarden — 58K★, *"not associated with Bitwarden"*
- **Selfhostr 2026 Vaultwarden vs Bitwarden Cloud** — https://selfhostr.com/comparatifs/vaultwarden-vs-bitwarden-cloud-2026/ — TCO, latency, sovereignty analysis
- **XDA 2026 self-hosted Vaultwarden** — https://www.xda-developers.com/self-hosted-vaultwarden-free-bitwarden-premium-features/ — price-hike migration story
- **HowToGeek 2026 Vaultwarden migration** — https://www.howtogeek.com/i-quit-my-bitwarden-subscription-and-self-hosted-it-with-this-open-source-fork/ — Tailscale + Caddy workflow
- **Railway Vaultwarden template 2026** — https://railway.com/deploy/vaultwarden-updated-aug-26--vaultwarden-7.md — *"encrypted vault never leaves a server you control"*
- **Bitwarden self-host FAQ** — https://bitwarden.com/help/self-host-bitwarden/ — official position on Vaultwarden compatibility
- **Bitwarden 2026 growth / Vaultwarden CLI compromise analysis** — NovVista 2026
- **Zero Password Manager (extreme self-host position)** — https://github.com/soulnaturalist/zero_password_manager — *"your server, your key, your secrets"*
- **Chronicler (self-hosted AI RP client)** — https://github.com/yantrikos/chronicler — local-first, MCP, three-tier memory

### Ghost / Plausible / Bitwarden precedents

- **Ghost /about** — https://ghost.org/about/ — non-profit, 100% reinvested
- **John O'Nolan founder blog** — https://john.onolan.org/democratising-publishing/ — $7.5M ARR, sustainable open-source model
- **Ghost 6.0 announcement** — https://ghost.org/changelog/6/ — ActivityPub, analytics, hosted vs self-host trade-offs
- **Ghost hosting comparison** — https://docs.ghost.org/hosting — $15/mo vs $10+20+15+10+5+12 self-host stack
- **Plausible self-host page** — https://plausible.io/self-hosted-web-analytics — *"on principle, not because it's good business"*
- **Plausible open-source page** — https://plausible.io/open-source-website-analytics — Cloud vs CE side-by-side
- **Plausible Community Edition blog 2024** — https://plausible.io/blog/community-edition — rebrand, enterprise-feature exclusion, brand split
- **Plausible /about** — https://plausible.io/about — bootstrapped, profitable, no investors

### TEE hardware availability on homelab

- **Ubuntu Intel TDX docs** — https://ubuntu.com/server/docs/_sources/how-to/virtualisation/intel-tdx.md.txt — Sapphire Rapids / Emerald Rapids / Sierra Forest / Granite Rapids only
- **Servnet UK Confidential Computing 2026** — https://www.servnetuk.com/learn/confidential-computing-explained — TDX vs SEV-SNP, cost, AI workload fit
- **Servermall AMD SEV-SNP vs Intel TDX 2026** — https://servermall.com/blog/amd-sev-and-intel-tdx-who-needs-it/ — Xeon 6, EPYC Turin only
- **AMD SEV specs** — https://www.amd.com/en/developer/sev.html — per-CPU-generation SEV features
- **OpenMetal TDX bare metal** — https://openmetal.io/resources/hardware-details/bare-metal-dedicated-server-xl-v5-tdx/ — TDX-as-default on Xeon 6530P (Granite Rapids)

### Prior research (this repo)

- **e2ee-app-architecture-survey.md** — `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md` — Signal / WhatsApp / Standard Notes / Notesnook / Cryptomator / Anytype / Obsidian Sync / Matrix / Proton synthesis, Tier 1–4 LLM paths
- **e2ee-business-model-survey.md** — `/Storage/Git/spectacle/.hermes/research/e2ee-business-model-survey.md` — Proton / Bitwarden / Tuta / Standard Notes pricing, Vaultwarden split, Ghost / Plausible / Standard Notes / WordPress / GitLab / Nextcloud precedents
- **e2ee-browser-capability-survey.md** — `/Storage/Git/spectacle/.hermes/research/e2ee-browser-capability-survey.md` — WebCrypto, OPFS, IndexedDB, native app shells
- **APP_SPEC.md** — `/Storage/Git/spectacle/APP_SPEC.md` — Achlys feature scope, stack, deployment model, Phase 2/3 hosted SaaS option