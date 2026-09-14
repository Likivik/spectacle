# E2EE / Zero-Knowledge Business Model Survey

**Question:** How do companies whose servers literally cannot read user content sustain a paid hosted product, and what does the open-source self-host community get in return? Is "open-source self-hostable core + paid private-by-design hosting" a proven combined business model?

**Audience:** Achiyon product team — currently weighing whether to ship both an open-source self-hostable core AND a paid hosted tier in a category where the operator cannot read user data (E2EE / zero-knowledge). The worry: client-side-everything removes the obvious reason to pay for hosting.

**Method:** Web research across primary sources (vendor pricing pages, blogs, GitHub), industry analyses, and a 2026 synthesis. Numbers cited are 2024–2026 unless noted.

---

## 1. The core paradox, stated cleanly

A zero-knowledge provider sells something unusual: **the operator cannot see the value the customer is paying for.** The content is encrypted before it leaves the device; the server stores opaque ciphertext. From a SaaS-economics standpoint this should be fatal — you lose the two classic levers (data lock-in and behavioural telemetry) that justify cloud pricing over a downloadable binary.

The companies that have actually survived (or thrived) on this model all sell the same thing instead:

| What they SELL | Why it works even when they can't read content |
|---|---|
| **Convenience / reliability** | Synced, available on every device, backed up, updated, online, "just works". The premium is for *someone else operating the hard part* — TLS certs, DB backups, security patches, edge CDN, SLA. |
| **Cross-device sync + storage** | E2EE ciphertext is still bytes that have to live somewhere. Sync across 5 devices and 10 years of history is not free; "secure at rest" storage is a paid tier almost everywhere. |
| **Productivity features built on top** | Rich-text editors, file attachments, custom domains, audit logs, sharing, family seats, integrations — all gated to paid tiers. The encryption is the table-stakes; the value-adds are what convert free → paid. |
| **Trust infrastructure** | Audits, transparency reports, jurisdictional choice (Swiss / EU / US), compliance certifications, insurance. A user cannot verify these on their own self-hosted Raspberry Pi. |
| **Bundle / ecosystem lock-in** | Mail + Calendar + Drive + VPN + Pass for €9.99/mo. The marginal cost of an extra product is near-zero for the operator (already authenticated) and is the actual reason users upgrade. |
| **Enterprise features** | SSO, SCIM, directory sync, policy enforcement, audit logs, account recovery, self-host option, priority support. This is where the real money is. |

In short: **the hosted tier sells "we make the hard thing easy, keep it online, and bundle it with everything you need"** — not the data itself. The data is the user's. The *service* is the product.

---

## 2. Pricing vs self-host: Proton, Bitwarden, Tuta, Standard Notes

### 2.1 Proton

**Pricing (Feb 2025 / current 2026):**
- Free — €0, 1 GB mail storage, 1 address, limited features
- Mail Plus — €3.99/mo (annual) or €4.99/mo, 15 GB, 1 custom domain, 10 addresses
- Proton Unlimited — €9.99/mo (annual) or €12.99/mo, 500 GB, 3 custom domains, 15 addresses, **bundles VPN + Drive + Pass + Wallet + Scribe**
- Proton Duo — €14.99/mo annual, 1 TB, up to 2 users
- Proton Family — €23.99/mo annual, 3 TB, up to 6 users, up to 90 addresses
- Visionary (legacy) — €29.99/mo annual, 6 TB

**What the paid tier actually unlocks** (above the zero-access encryption everyone gets free): storage, custom domains, addresses, calendar count, catch-all, alias count, hide-my-email aliases, VPN, Drive, Pass. Encryption itself is identical on every plan — Proton explicitly states "Our free email accounts offer the same level of encryption as any of our paid plans."

**Self-host alternatives:** Proton does not offer an official self-hosted server for the public. The Proton ecosystem is closed-source on the backend (clients are open). The community alternative is **Stalwart Mail** (Rust, JMAP/IMAP/SMTP/CalDAV/CardDAV, single ~50 MB binary, used by Privacy Guides for their own org mail) or **mailcow** / **Mailu** / **Mail-in-a-Box** for full groupware. Stalwart + PGP-capable client (Thunderbird + OpenPGP.js) achieves E2E content parity with ProtonMail — and gives the operator metadata sovereignty Proton cannot give.

**Cost comparison (1 user, 3 years, mid-2026 estimates):**
| Plan | 3-year cost | Storage | E2E encryption | Custom domains |
|---|---|---|---|---|
| Proton Mail Plus | €143.64 | 15 GB | Yes (Proton↔Proton) | 1 |
| Proton Unlimited | €359.64 | 500 GB | Yes | 3 |
| Self-host (Mailcow VPS) | ~€216 | Unlimited | Manual PGP | Unlimited |

**Company economics (why Proton is the canonical case study):**
- **100 million accounts**, ~500 employees, **$97.5M ARR (2024)**, growing from $70M (2022).
- **No venture capital.** Crowdfunded in 2014 ($500K from 10,000 backers). Profitability is a stated goal — they explicitly reject the "billionaire-subsidized / VC-subsidized / donation-subsidized" models.
- **Non-profit governance since June 2024.** Proton Foundation is now the primary shareholder of Proton AG; legally irrevocable mission lock. They pledge 1% of net revenue to the foundation; the foundation gives grants (Tor Project, GrapheneOS, European Digital Rights).
- The hosted business is the **funding engine for open-source ecosystem work** (OpenPGPjs, proton-mail-apps, protoncore) and for free infrastructure that never profits (Proton VPN in Iran/Russia).

> "If we want to bring about large-scale change, Proton can't be billionaire-subsidized. Proton must have a profitable and healthy business at its core." — Andy Yen, June 2024

### 2.2 Bitwarden

**Pricing (2026):**
- Free — $0, unlimited logins, unlimited devices, basic 2FA
- Premium — **$1.65/mo (annual)**, $19.80/yr — vault health reports, TOTP authenticator, encrypted file attachments, emergency access, advanced 2FA (Yubikey, FIDO2)
- Families — **$3.99/mo (annual)**, $47.88/yr, up to 6 users, all Premium features
- Teams — $4/user/mo annual ($5 monthly)
- Enterprise — $6/user/mo annual ($7 monthly), adds SSO, SCIM, Access Intelligence, enterprise policies, account recovery, **self-host option**

**What paid actually unlocks** beyond the free tier's already-full-featured E2EE vault: vault health reports, 1→5 GB encrypted attachments, advanced 2FA, TOTP storage, emergency access, sharing/organizations, SSO/SCIM/SSO-self-host at the top. Encryption is the same on every plan.

**Self-host alternatives:**
- **Vaultwarden** (formerly `bitwarden_rs`) — community Rust rewrite of the Bitwarden server API. Single Docker container, SQLite, ~50 MB RAM, runs on a Raspberry Pi. **One maintainer (Dani García, with BlackDex) but 58K+ GitHub stars, ~2.7K forks.** Officially "not associated with Bitwarden or Bitwarden, Inc.", though one active maintainer is employed by Bitwarden and contributes on their own time. Provides the full Bitwarden client API including everything Bitwarden gates behind Premium — TOTP, Send, file attachments, organisations, emergency access — for free.
- **Official self-host** — the upstream Bitwarden server is a 11-container stack with MSSQL; ~2 GB RAM minimum. Enterprise tier license required to self-host. Bitwarden now also ships a "Bitwarden Lite" self-hosted deployment aimed at the Vaultwarden use case.
- Bitwarden's own FAQ acknowledges Vaultwarden compatibility and recommends keeping it current for compatibility with official clients, but does not endorse it: "the security audits granted to Bitwarden do not apply to Vaultwarden."

**User base (company economics):**
- **15 million users, 80,000 businesses (Q2 2026)**, up from 10M users / 50K businesses (Jan 2025). 70% YoY growth in new business subscriptions H1 2026.
- "Forever-free basic plan for individuals" is the explicit growth strategy — Freemium. Premium ($19.80/yr) and Families ($47.88/yr) are intentionally cheap to undercut 1Password ($35.88/yr) and LastPass.
- Bitwarden does not publish ARR but is widely reported as the second-most-installed password manager after 1Password, with a meaningfully more privacy-conscious user base. Enterprise is the real revenue engine.

**The Vaultwarden migration story:** After the LastPass 2022 breach (encrypted vaults stolen, $438M+ in crypto drained by 2025), Vaultwarden saw its first major migration wave. After the Bitwarden CLI npm supply-chain compromise in 2026, a second wave hit — the repo gained several thousand stars in 48 hours. Critically, multiple analyses noted that the second wave was partly **security theatre** (self-hosting doesn't protect against client-side supply-chain attacks) but a legitimate trust re-evaluation about SaaS provider custody.

### 2.3 Tuta (formerly Tutanota)

**Pricing (2026):**
- Free — €0, 1 GB, 1 calendar, 3 labels
- Revolutionary — **€3/mo**, 20 GB, 15 aliases, 3 custom domains
- Legend — **€8/mo**, 500 GB, 30 aliases, 10 custom domains
- Business Essential — €6/user/mo, 50 GB
- Business Advanced — €8/user/mo, 500 GB, 10 domains
- Business Unlimited — €12/user/mo, 1 TB, unlimited custom domains

**Important architectural difference:** Tuta does **not** support IMAP/POP/SMTP on any plan. There is no standard mail client; users must use Tuta's own apps. This is because Tuta encrypts subject lines, headers, body and attachments with a hybrid AES/RSA scheme that doesn't map cleanly onto standard SMTP. So Tuta sells a fully-managed encrypted mail experience — there is no self-host path even in principle, because the *protocol itself* is Tuta-specific. **The hosting IS the product in a stronger sense than Proton.**

**What paid actually unlocks:** storage, custom domain support, aliases, catch-all, unlimited calendars/labels/filters, business white-label. Encryption is identical on every plan.

**Self-host:** N/A. The Tuta client cannot talk to a standard mail server, and the server is not open source. Self-hosters who want E2EE mail choose Proton → Stalwart, or PGP-on-IMAP.

### 2.4 Standard Notes

**Pricing (2026, stable since pre-Proton acquisition):**
- Free — $0/yr, unlimited plain-text notes, E2EE, cross-platform sync, 2FA, tags
- Productivity — **$90/yr** (~$7.49/mo), all advanced editors (Markdown, rich text, code, spreadsheet, tasks), 1 GB encrypted file storage, custom themes, note history
- Professional — **$120/yr** ($9.99/mo), 100 GB encrypted storage, max note history, family sharing (up to 5), offline file access

**Note (pun intended):** Standard Notes was acquired by Proton in April 2024 (Proton's second acquisition after SimpleLogin in 2022). It continues to operate as a separate product with separate pricing — Proton does NOT fold Standard Notes into Proton Unlimited. CEO Mouayed Makhlouf confirmed Standard Notes has "a community of tens of thousands of paying customers" sustaining development post-acquisition.

**What paid actually unlocks:** rich editors, file storage, attachment size limits, note history, family seats. Encryption (XChaCha20 + Argon2) is the same on every tier.

**Self-host alternative:** Standard Notes has a **fully self-hostable AGPLv3 server** (`standardnotes/server`, 472★ on GitHub). Docker setup with 4 containers and ~570 MB RAM (down from 13 containers / 1.7 GB in the legacy v1 setup). The official web app is also open source; you can serve the static `packages/web` build behind any HTTP server. Self-hosters get 100% data sovereignty and bypass the paid tiers entirely.

### 2.5 Cross-company pricing pattern

| Product | Free tier | Cheapest paid (annual) | Family tier (annual) | E2E on free? | Self-host? |
|---|---|---|---|---|---|
| Proton Mail | Yes, 1 GB | €47.88 | €287.88 (6 users, 3 TB) | Yes | No (community: Stalwart) |
| Proton Unlimited | (above) | €119.88 | (above) | Yes | No |
| Bitwarden | Yes, unlimited | $19.80 | $47.88 (6 users) | Yes | Yes (official, paid) + Vaultwarden (free) |
| Tuta | Yes, 1 GB | €36 | varies | Yes | No (architecture) |
| Standard Notes | Yes, unlimited | $90 | $120 (5 users, 100 GB) | Yes | Yes (AGPLv3, free) |

**Observation:** every one of these companies uses the same recipe:
1. Give the encryption away free. Free tier = free marketing + community.
2. Charge for storage, aliases, custom domains, advanced features, family seats, bundles.
3. Enterprise tier is where the high-margin revenue lives (Proton Business, Bitwarden Teams/Enterprise, Tuta Business Advanced).

---

## 3. The Bitwarden ↔ Vaultwarden split: what does E2EE actually do to host-vs-self-host economics?

This is the closest real-world analogue to the Achiyon question because **the protocol is genuinely the same on both sides** (same clients, same API, same zero-knowledge model). Only the *server* differs.

### Does E2EE make self-hosting MORE attractive?

**Yes, materially.** Three reasons:

1. **The "trust us with our secrets" objection is the dominant objection to SaaS password managers — and E2EE removes the only non-self-host response to it** ("we encrypt in transit and at rest, take our word for it"). With a true zero-knowledge protocol, self-hosters get the same content privacy as hosted customers, *plus* control over metadata and custody. That is a unique value proposition that does not exist for, say, Gmail.

2. **The premium-feature gap collapses.** Bitwarden gates vault health reports, TOTP authenticator, Send, file attachments, organisations, emergency access behind Premium ($19.80/yr) and Families ($47.88/yr). Vaultwarden provides all of these for free, because the *server* gates them, not the protocol. Self-hosters get the entire paid feature set without paying. This is a direct, measurable revenue leak from the hosted tier to the self-hosted tier.

3. **Hardware requirements are absurdly low.** A Raspberry Pi Zero runs Vaultwarden. The official Bitwarden server wants ~2 GB RAM. This removes the "I can't run this at home" objection entirely.

### Does E2EE make hosting LESS defensible?

**Somewhat, but the SaaS remains the default.** The defensive moats for the hosted tier are:

1. **Operational reliability.** Vaultwarden's bus factor is ~2 (Dani García + BlackDex). When the Bitwarden CLI was compromised in 2026, Bitwarden Inc. shipped a fix in hours; the equivalent patch to Vaultwarden depended on two maintainers' weekend availability. For a personal vault this is fine; for a team of 50, it is a real risk.

2. **Compliance and SLA.** Enterprises need SOC 2, GDPR DPA, audit logs, SCIM, directory connector, account recovery, support contracts. Vaultwarden has none of these — Bitwarden Enterprise does. This is where the bulk of Bitwarden's revenue growth (70% YoY new business subs H1 2026) actually lives.

3. **UX / cross-device sync that "just works".** Most users are not willing to set up Tailscale + a reverse proxy + Let's Encrypt + Docker to read their passwords. The hosted tier eliminates that. The HowToGeek and XDA migrations that the second wave of switchers followed took an entire *weekend* for a technical user.

4. **Free tier as funnel.** Bitwarden's free tier is generous enough that the conversion to Premium is gentle. Self-hosters self-select out of that funnel.

5. **Brand + audit signal.** Bitwarden is independently audited and security-audited; Vaultwarden is not ("the security audits granted to Bitwarden do not apply to Vaultwarden" — Bitwarden FAQ). For most users this matters only when they think about it; for security-conscious enterprises it matters a lot.

### Net effect

Bitwarden's hosted business has *grown* through the Vaultwarden era: 10M users Jan 2025 → 15M users Q2 2026. Enterprise revenue grew 70% YoY. Vaultwarden has 58K★ GitHub stars but is unlikely to have more than a few hundred thousand active instances. The market structure looks like:

- **Free users (the vast majority)** use Bitwarden Cloud free tier → conversion to Premium via family/teams/enterprise features.
- **Tech-savvy individuals / families** self-host Vaultwarden. This is a small, committed minority. Bitwarden tolerates this because the alternative is someone uses KeePass or no password manager at all — neither is a Bitwarden customer.
- **Enterprise** is hosted Bitwarden Enterprise, no question. The features Bitwarden gates behind Enterprise (SSO, SCIM, audit logs, account recovery, compliance) cannot be replicated by Vaultwarden without significant engineering work.

> Net conclusion from the Bitwarden/Vaultwarden split: **E2EE pulls power users to self-host, but does not hollow out the SaaS because convenience, reliability, compliance, and ecosystem features still dominate purchase decisions for the 95th percentile.**

---

## 4. AI-companion / chat products with E2EE or privacy as core pitch

This is the most fragile category. **True end-to-end encryption between user and AI model is fundamentally incompatible with how LLMs work** — the model has to read the prompt in plaintext to generate a reply. Anything claiming E2EE on the prompt/response is either:

- **Transport + at-rest encryption only** (TLS in, model reads plaintext, response encrypted at rest) — what every privacy-aware vendor actually offers, despite marketing language
- **Application-layer encryption terminating at the inference endpoint** — content encrypted from user to model, model holds the key in a TEE (trusted execution environment), which is a meaningful privacy upgrade but technically not E2EE in the Signal sense
- **Local-only inference** — true E2EE because the "other endpoint" is your own GPU

### 4.1 Closest existing products

| Product | Privacy model | Reality |
|---|---|---|
| **DuckDuckGo Duck.ai** | Anonymous proxy + no logging + TEE-backed inference with Tinfoil (gpt-oss-120b, Gemma 4 31B). Two models labelled "zero provider visibility". Metadata stripped before reaching upstream providers. Chats stored E2E-encrypted if user opts into Sync & Backup. | The closest to a "private by default" chat product from a major consumer brand. Does NOT claim E2EE on the prompt/response itself. |
| **Enigma AI** (iOS/Android) | Local-only chat history, device-held keys (Secure Enclave / Keystore), PII stripping + blind routing, RAM-only processing. Routes to OpenAI / Anthropic / xAI / DeepSeek. | Marketing leans "end-to-end encrypted" but it's actually "encrypted at rest on your device, blind-routed, RAM-only server side". Still meaningfully more private than the alternatives. |
| **Signal-bot stacks** (e.g. `ollama-signal-bot`, `uoltz`, `Eddie`) | True local-only: Signal protocol from phone → signal-cli-rest-api on your box → Ollama / LM Studio / vLLM. Nothing leaves your network. | Actual E2EE because the LLM runs locally. Requires a dedicated phone number for the bot. Power-user / homelab category. |
| **Signal-bot-tee** (`RonTuretzky/sigstack`) | Signal E2EE from user → TEE (Intel TDX) → NEAR AI Cloud (NVIDIA H100/H200 TEE). Dual cryptographic attestation, in-memory only, no logging. | Closest to "true E2EE with cloud inference" that exists in 2026. Experimental, requires TEE deployment. |
| **OxiHub/veil** | Application-layer encryption envelope around LLM traffic using Signal-protocol-style crypto (X25519 ECDH + HKDF + AES-256-GCM, true forward secrecy via one-time prekeys). Two modes: in-process with inference engine (true E2EE) or sidecar shim. | Working proof-of-concept. Targets llama.cpp / vLLM / Ollama. Pure Rust, ~48 bytes/message overhead. |
| **Agora** (Android, BYOK) | Local-only storage (Room DB), BYOK direct API connections, optional local llama.cpp inference, ECDH+AES-256-GCM for remote shell protocol. | Open-source BYOK client; bypasses any middleman. |
| **Replika / Kindroid / Nomi** | Marketing language sometimes uses "encrypted"; reality is TLS + at-rest encryption + server-held keys. Italian DPA investigated Replika in 2023. | "End-to-end encryption" on AI companion apps is, almost without exception, not what Signal means by the phrase. |

### 4.2 Architectural insight for Achiyon

If the product is genuinely E2EE + the AI is running on the operator's hardware, you have three honest options:

1. **Deny E2EE on the prompt/response** and sell something else (anonymisation, no logging, RAM-only processing, audit, jurisdiction, no-training-on-your-data). This is what DuckDuckGo Duck.ai and most privacy-aware vendors actually do. It is honest and it is the lowest engineering cost.

2. **Run the model in a TEE** (Intel TDX / NVIDIA H100 Confidential Compute) and make attestation verifiable. This is the "OxiHub/veil + Signal-bot-tee" path. Real privacy upgrade; meaningful engineering cost; production-grade TEEs are still relatively new.

3. **Ship a self-host option** so the power users can run the model themselves. This is the path DuckDuckGo has implicitly chosen by supporting Ollama / local model integration, and what Enigma AI / Agora do by making local-first the default.

> The category has not yet produced a profitable "$X/mo for E2EE AI chat" product at scale. The closest is Duck.ai (free, bundled with DuckDuckGo subscription), which is funded by the rest of DuckDuckGo's business. **An "open-source self-hostable core + paid privacy-hosting" AI chat product would be a genuinely novel combination.**

---

## 5. The "trust the company" default: how many users actually pick privacy over convenience?

Hard data is uneven, but the picture is consistent.

### 5.1 Consumer survey data

| Source | Finding | Year |
|---|---|---|
| **Cisco 2024 Consumer Privacy Survey** (2,600+ adults, 12 countries) | **38%** qualify as "Privacy Actives" — willing to spend time AND money to protect data and have switched providers over data practices (up from 32% in 2022). **75%** won't buy from a company they don't trust with data. | 2024 |
| **Statista / US adults** | **60%** willing to pay premium for stronger data protection (15% very, 45% somewhat). 18% very unwilling. | May 2024 |
| **IAB Consumer Privacy Report** (1,500+ consumers) | **91%** react negatively (frustrated, disappointed, angry, confused, sad) if they had to start paying for currently-free sites/apps. **95%** prefer ads to a high fee. 73% understand data-sharing enables personalised ads; 69% willing to share data to support advertising. | Jan 2024 |
| **Consumer Policy journal (Springer, 2024)** | Across 3,436 participants in vignette experiments (music / shopping / news apps, paid vs free): majority "slightly unwilling" to share data for any personalization, paid or free. Consumers more willing to share with *free* apps than *paid* apps — they perceive paid apps as more privacy-protective by default and resist "paying + data". | 2024 |
| **Telecommunications Policy (South Korea)** | Three user segments identified: **32.9%** reluctantly accept "take-it-or-leave-it" (privacy-sensitive but no choice), **47.0%** accept it for free services (privacy-as-cost-of-free), **20.1%** don't care. | 2024 |

### 5.2 The picture

- **A large minority (~30-40%) actively prioritise privacy and will pay for it.** Cisco's "Privacy Actives" segment is growing fast (32% → 38% in 2 years).
- **The middle majority prefer free + ads and tolerate data collection as the cost.** IAB's 91%/95% figures are striking.
- **There is a real but narrow willingness-to-pay-for-privacy market.** Statista's 60% "willing to pay premium" is generous; real conversion is much lower (Proton and Bitwarden's free→paid conversion rates are not published, but their free tier user counts dwarf paid).
- **Paradox:** the Springer study found consumers are *less* willing to share data when also paying — they perceive paying as buying privacy. This is a huge validation for the Proton model: "you pay us so we don't monetise your data." But it also means a free + privacy-respecting tier must explicitly explain why it's still safe (DuckDuckGo's job).

### 5.3 What this means for Achiyon's hosted tier

- **The "trust the company" default is the modal user.** Most users will not pay for privacy. They will accept the privacy tier because it's the only offering, or because the company has made the choice for them (employer mandate, default in a bundle).
- **The willing-to-pay-for-privacy minority is real, growing, and underserved.** Cisco's 38% Privacy Actives + Statista's 60% "willing to pay more" is a large addressable market for any product that can credibly claim privacy.
- **Bundling works.** Proton Unlimited's €9.99/mo bundles VPN+Mail+Drive+Pass+Wallet — most users pick it because the convenience of "one login, one bill, five apps" exceeds the marginal cost of unbundling. The privacy story is the *reason to start*, the bundle is the *reason to upgrade*.
- **Free tier is not optional.** Every viable E2EE/privacy product has a meaningful free tier. Without it, you cede the funnel to an ad-funded competitor.

---

## 6. The "open-source self-hostable core + paid privacy-by-design hosting" combined model — is it proven?

**Yes. Multiple independent companies have run this exact model sustainably for 5–12 years.** It is not theoretical.

### 6.1 The case studies

| Company | Self-hostable? | Hosted tier? | Model | Years proven | Revenue scale |
|---|---|---|---|---|---|
| **Ghost** | Yes (MIT, self-host your own server) | Ghost(Pro) from $15/mo | "Sustainable open-source model" — paying hosted users fund free open-source development | 12 | $7.5M ARR (2024), profitable, non-profit foundation, 100% reinvested |
| **Plausible** | Yes (AGPLv3, Community Edition) | Managed cloud subscription | "Open source on principle, not because it's good business" — single funding source is managed cloud | ~6 | Not disclosed; small team, sustainable |
| **Proton** | Clients open-source; backend closed. Community alternatives exist (Stalwart). | Hosted only | E2EE suite funded by paid users subsidising free users and grant-funded infrastructure | 12 | $97.5M ARR (2024), 100M accounts, non-profit since 2024 |
| **Bitwarden** | Yes (official + Vaultwarden community) | Yes | Freemium + enterprise; self-host tolerated because alternative is non-customer | 10 | 15M users / 80K businesses; ARR not disclosed |
| **Standard Notes** | Yes (AGPLv3, Docker) | Yes | Acquired by Proton 2024, still runs as separate product with separate pricing | 9 (since 2016) | "Tens of thousands of paying customers" (2024 post-acq) |
| **WordPress.com / Automattic** | Yes (WordPress core GPL) | Yes | Open core, hosted tier bundles support, hosting, premium themes, ecommerce | 20+ | Multi-billion (Automattic valuation $7.5B last private round) |
| **GitLab** | Yes (self-host CE/EE) | Yes (GitLab.com SaaS) | Open core; paid EE adds compliance, security, scaling features | 11 | Public company; ~$700M ARR |
| **Nextcloud** | Yes (AGPL) | Nextcloud Hub hosted via partners | Foundation-supported; revenue from enterprise support + partner ecosystem | 9 | Not disclosed; foundation-backed |

### 6.2 The Ghost model is the most articulate expression of this

> "The business model was simple: We would make a great open source product that people wanted to use. Those people would need a server to use the product, so we would also sell web hosting. The revenue from our hosting would fund further development of the open source product. Nobody is required to use our hosting. In fact, the majority of Ghost websites in the world do not use Ghost(Pro) — but the ones that do, directly fund the project for the benefit of everyone." — John O'Nolan, founder

Ghost has been profitable for 12 years, generates ~$7.5M/yr, is a non-profit, and explicitly frames itself as "we don't want to grow a giant company we control, we want to grow a giant ecosystem that we support."

### 6.3 The Proton model is the privacy-specific articulation

> "We believe that if we want to bring about large-scale change, Proton can't be billionaire-subsidized (like Signal), Google-subsidized (like Mozilla), government-subsidized (like Tor), donation-subsidized (like Wikipedia), or even speculation-subsidized. Instead, Proton must have a profitable and healthy business at its core. For this reason, our services will continue to be offered through the for-profit Swiss corporation Proton AG." — Andy Yen, June 2024

Proton's hosted tier is the *funding engine* for open-source libraries (OpenPGPjs), for free infrastructure that never profits (Proton VPN in Iran/Russia), and for grants to aligned projects (Tor, GrapheneOS). The hosted tier is the means; the open-source privacy ecosystem is the end.

### 6.4 Conditions for the model to work

The combined "open-source self-hostable + paid hosted" model is proven when ALL of these hold:

1. **Self-hosting is meaningfully harder than hosted.** If self-hosting is one-click and free, the hosted tier collapses. The tier must add genuine convenience, reliability, support, or features that 95% of users will not DIY. Vaultwarden being one Docker container is exactly the failure mode — Bitwarden survives it because (a) most users don't want to self-host and (b) Enterprise features can't be self-hosted.

2. **Paid tier sells something the user cannot easily replicate.** Storage, custom domains, sharing, family seats, SSO/SCIM, audit logs, SLAs, support contracts, integrations, regional compliance. Not "the same thing, on our server".

3. **Free tier is generous and is the funnel.** Both Proton and Bitwarden give away the core encryption feature free. Premium converts on the convenience and ecosystem layer.

4. **Mission / brand / non-profit governance reduces "why pay the vendor?" friction.** Both Ghost and Proton are non-profit. Bitwarden is for-profit but bootstrapped (no VC). The absence of a profit-extraction narrative is what makes "you can self-host, but the easiest thing is to pay us" not feel like a shakedown.

5. **Cross-subsidy is explicit.** Proton's paying users subsidise free users (1 GB free mail, Proton VPN in censored countries). Ghost's paying users subsidise the open-source codebase that everyone (including non-customers) uses. The model only works if the cross-subsidy is acknowledged and is the reason the free tier exists.

### 6.5 Does E2EE change the calculus?

Mildly. E2EE removes one common moat (data lock-in), but it does NOT remove:

- **Convenience and reliability.** Most users will not self-host.
- **Storage, sharing, family, integrations.** Pure encryption doesn't help here.
- **Compliance and enterprise features.** These are *more* valuable when the content is sensitive.
- **Bundle lock-in.** E2EE suites (Proton) and E2EE ecosystems (Bitwarden) cross-sell aggressively.
- **Brand + audit signal.** Independent security audits are expensive; users trust them.

The experience of Bitwarden through the Vaultwarden era is conclusive: **a zero-knowledge protocol makes self-hosting more attractive, but the SaaS business is not hollowed out.** The 95th percentile user does not self-host; the 99th percentile pays Enterprise; the 99.9th percentile (Vaultwarden power users) is a small, tolerated minority.

---

## 7. Synthesis and recommendation for Achiyon

### The headline

**"Open-source self-hostable core + paid private-by-design hosting" is a proven business model.** Multiple companies have run it sustainably for 5–12 years. The hosted tier is not threatened by E2EE; it is enabled by it. The single most important thing E2EE does for the hosted business is make the *trust story* credible — and the trust story is what unlocks paying customers.

### Specific answers to the brief

1. **What does the hosted tier actually sell when the operator can't read user data?** Convenience, reliability, storage, cross-device sync, family seats, custom domains, sharing, integrations, bundle/ecosystem, compliance, audit, jurisdiction, support. Encryption is table-stakes; the value-adds are what convert free to paid.

2. **Does E2EE make self-hosting MORE attractive and hosting LESS defensible?** Yes on the first half (Vaultwarden exists, has 58K★, and gives away Bitwarden's Premium features for free). Mildly yes on the second half — but the SaaS survives because (a) most users don't self-host, (b) Enterprise features can't be self-hosted, (c) compliance and SLA matter, (d) the free tier is the funnel. Bitwarden grew from 10M to 15M users Jan 2025 → Q2 2026 *despite* Vaultwarden.

3. **Are there AI-companion/chat products with E2EE or privacy as core pitch?** Not really, in the consumer market. The architectural reason: the LLM is a third endpoint that must read plaintext, so Signal-style E2EE is impossible without local inference or TEE-based confidential computing. Closest existing products: DuckDuckGo Duck.ai (TEE-backed Tinfoil models), Signal-bot-tee (Signal → TDX → NEAR AI Cloud), Enigma AI (device-held keys, blind routing), OxiHub/veil (Signal-protocol-style E2EE for inference traffic). **A "self-hostable open-source core + paid private-by-design hosting" AI chat product would be a genuinely novel combination and would have the trust story that no existing competitor has.**

4. **What share of users pick privacy vs convenience?** ~30-40% actively prioritise privacy and a subset will pay (Cisco Privacy Actives: 38% in 2024, growing). The middle majority prefers free + ads. The niche willing to pay for privacy is real, growing, and undersupplied — but the conversion funnel must include a generous free tier and a bundle story.

### Design implications for Achiyon

- **Ship both, openly.** Open-source self-hostable core + paid hosted. The open-source core is the trust signal and the funnel; the hosted tier is the conversion. This is the Ghost / Plausible / Bitwarden / Standard Notes / Proton pattern. Frame the hosted tier explicitly as "funding the open-source development that everyone benefits from" — this is what makes the cross-subsidy feel like a community contribution rather than a shakedown.

- **Make the hosted tier sell something the self-hoster cannot easily replicate.** Convenience (one-click setup, automatic updates, cross-device sync that "just works"), reliability (uptime SLA, redundant regions, automatic backups), storage and bundle (extra encrypted storage, family sharing, integrations), compliance (SOC 2, GDPR DPA, audit logs, SSO/SCIM at the top), and — importantly — **AI inference features that are expensive to self-host** (e.g. cloud GPU inference that requires hardware the self-hoster doesn't have, but with anonymisation + TEE attestation + audit instead of E2EE).

- **Be honest about E2EE on AI features.** If the AI runs on your hardware, you cannot claim Signal-style E2EE. You CAN credibly claim: (a) no training on user data, (b) RAM-only processing, (c) TEE attestation that the model and operator cannot see plaintext, (d) zero-retention contracts with model providers, (e) local-only mode that ships a model on the user's device for true E2EE. This is what Enigma AI / Duck.ai / Signal-bot-tee do. The marketing language must be precise; "encrypted" ≠ "end-to-end encrypted" and the Springer-style research papers show that users notice the difference when they pay.

- **Tee the free tier into a meaningful funnel.** Free tier = the open-source self-hostable core, plus a hosted free tier with the encryption but limited storage / features. Paid = storage, custom domains, integrations, family seats, AI inference minutes, compliance features.

- **Consider non-profit governance once profitable.** Proton did this in 2024 specifically to lock in mission after scale. Ghost was a non-profit from day one. Both use governance to convert "you can self-host but the easiest thing is to pay us" into "by paying us you fund the open-source ecosystem we all share." This converts the self-host escape valve from a competitive threat into a community virtue.

### The one-sentence answer

**Yes, the model is proven — multiple companies have run it sustainably for 5–12 years — and E2EE strengthens rather than weakens it, because what the hosted tier sells (convenience, reliability, ecosystem, compliance) is exactly what a zero-knowledge architecture makes the user most willing to delegate.**

---

## Sources

### Primary / vendor

- **Bitwarden pricing & plans**: https://bitwarden.com/pricing/ — premium $19.80/yr, families $47.88/yr, teams $4/user/mo, enterprise $6/user/mo
- **Bitwarden self-host FAQ**: https://bitwarden.com/help/hosting-faqs/ — official position on Vaultwarden compatibility
- **Bitwarden 2024 growth**: https://www.businesswire.com/news/home/20250129567175/en/Bitwarden-Achieves-Landmark-Growth-in-2024 — 10M users, 50K businesses
- **Bitwarden Q2 2026 growth**: https://finance.yahoo.com/technology/ai/articles/bitwarden-surpasses-15-million-users-160000253.html — 15M users, 80K businesses, 70% YoY new business subs
- **Bitwarden Premium pricing blog**: https://bitwarden.com/blog/bitwarden-launches-enhanced-premium-plan/ — $1.65/mo premium introduction
- **Bitwarden migration docs**: https://bitwarden.com/help/migration/ — official cloud ↔ self-host migration procedure
- **Vaultwarden GitHub**: https://github.com/dani-garcia/vaultwarden — 58K★, "not associated with Bitwarden"
- **Vaultwarden CLI-compromise analysis**: https://novvista.com/vaultwarden-the-rust-self-hosted-bitwarden-alternative-surging-after-the-cli-compromise-we-examined-the-single-maintainer-risk/ — 2-maintainer bus factor, second migration wave
- **HowToGeek Vaultwarden migration**: https://www.howtogeek.com/i-quit-my-bitwarden-subscription-and-self-hosted-it-with-this-open-source-fork/ — typical self-host migration story
- **XDA LastPass → Vaultwarden**: https://www.xda-developers.com/i-migrated-from-lastpass-to-self-hosted-vaultwarden-in-one-weekend/ — LastPass breach → Vaultwarden migration pattern
- **MakeUseOf self-host analysis**: https://www.makeuseof.com/self-host-password-vault-avoid-breach-lockout/ — LastPass 2022 → MFA lockout, Bitwarden migration
- **Proton Mail pricing**: https://proton.me/mail/pricing — current plans, free encryption on every tier
- **Proton plan explanations**: https://proton.me/support/proton-plans — Mail Plus €47.88, Unlimited €119.88, Family €287.88
- **Proton non-profit transition blog**: https://proton.me/blog/proton-non-profit-foundation — June 2024, Proton Foundation structure
- **Proton 100M accounts**: https://proton.me/blog/proton-100-million-accounts — 100M accounts milestone
- **Proton mission blog**: https://proton.me/blog/sustaining-mission-over-time — "must have a profitable and healthy business at its core"
- **Proton Pass price change**: https://proton.me/blog/proton-pass-price-change — "not the cheapest option in any market", community-funded not VC-funded
- **Proton revenue (GetLatka)**: https://getlatka.com/companies/protonmail — $97.5M ARR 2024, 500 employees
- **Forbes on Proton non-profit**: https://www.forbes.com/sites/hessiejones/2024/06/17/exclusive-protons-landmark-shift-to-non-profit-heralds-a-people-first-internet-with-unprecedented-accountability/ — coverage of June 2024 transition
- **Tuta pricing**: https://tuta.com/pricing — Revolutionary €3, Legend €8, Business €6/€8/€12 per user
- **Tuta plans announcement**: https://tuta.com/blog/announcement-new-prices — pricing history
- **Standard Notes plans**: https://standardnotes.com/plans — Productivity $90/yr, Professional $120/yr
- **Standard Notes self-host docs**: https://standardnotes.com/help/self-hosting/docker — 4-container V2 setup, 570 MB RAM
- **Standard Notes GitHub**: https://github.com/standardnotes/server — 472★, AGPLv3
- **Standard Notes Proton acquisition**: https://standardnotes.com/blog/joining-forces-with-proton — April 2024 acquisition
- **TechCrunch on Standard Notes acquisition**: https://techcrunch.com/2024/04/10/proton-standard-notes/ — 300K users, separate pricing
- **Standard Notes post-acquisition update**: https://standardnotes.com/blog/progress-with-proton — "tens of thousands of paying customers"
- **Ghost about page**: https://ghost.org/about/ — non-profit foundation, 100% reinvested
- **John O'Nolan founder blog**: https://john.onolan.org/democratising-publishing/ — $7.5M ARR, 12 years profitable
- **Plausible self-host page**: https://plausible.io/self-hosted-web-analytics — "open source on principle, not because it's good business"
- **Stalwart Mail analysis**: https://remoterails.com/stalwart-mail-vs-protonmail-a-technical-deep-dive-into-modern-email-security-deliverability/ — Stalwart vs ProtonMail deep dive
- **Stalwart GitHub**: https://github.com/stalwartlabs/mail-server — Rust, JMAP/IMAP/SMTP, ~50 MB RAM
- **Selfhosting.sh Proton alternatives**: https://selfhosting.sh/replace/proton-mail/ — mailcow, Stalwart, Mailu comparison
- **Alexi.sh self-host email vs ProtonMail 2026**: https://alexi.sh/posts/self-hosted-email-vs-protonmail-fastmail-2026 — cost & UX comparison

### AI / privacy products

- **Duck.ai privacy**: https://duckduckgo.com/duckduckgo-help-pages/duckai/ai-chat-privacy — Tinfoil TEE-backed models, anonymous routing, no logging
- **Enigma AI**: https://enigmaai.app/ — local-only chat, device-held keys, blind routing
- **Signal-bot-tee / sigstack**: https://github.com/RonTuretzky/signal-bot-tee — Signal → TDX → NEAR AI Cloud with attestation
- **OxiHub/veil**: https://github.com/OxiHub/veil — Signal-protocol-style E2EE for inference
- **Ollama-signal-bot**: https://github.com/kasp0r/ollama-signal-bot — true self-hosted Signal+local-LLM
- **uoltz**: https://github.com/maciejjedrzejczyk/uoltz — local-first Signal chatbot, multi-agent
- **Eddie**: https://github.com/yavin5/eddie — Signal LLM agent
- **Agora**: https://github.com/dabeecao/Agora — BYOK Android client, local-first
- **AI Angels on Replika/Kindroid/Nomi "E2EE"**: https://www.aiangels.io/blog/end-to-end-encryption-replika-kindroid-nomi-fine-print — why AI companion "E2EE" is misleading

### Surveys / data

- **Cisco 2024 Consumer Privacy Survey**: https://www.cisco.com/c/dam/en_us/about/doing_business/trust-center/docs/cisco-consumer-privacy-report-2024.pdf — 38% Privacy Actives, 75% won't buy from untrusted companies
- **IAB Consumer Privacy Report**: https://www.iab.com/wp-content/uploads/2024/01/IAB-Consumer-Privacy-Report-January-2024.pdf — 91% would react negatively to paying for currently-free sites, 95% prefer ads to a high fee
- **Statista US willingness to pay**: https://www.statista.com/statistics/1469800/us-adults-willingness-to-pay-for-personal-data-protection/ — 60% willing to pay premium (15% very + 45% somewhat)
- **Springer Consumer Policy 2024**: https://link.springer.com/article/10.1007/s10603-024-09568-9 — N=3,436, paid vs free data-sharing willingness
- **Telecommunications Policy South Korea**: https://doi.org/10.1016/j.telpol.2024.102794 — 32.9% / 47.0% / 20.1% three-segment model

### Comparative analyses

- **Selfhostr Vaultwarden vs Bitwarden Cloud 2026**: https://selfhostr.com/comparatifs/vaultwarden-vs-bitwarden-cloud-2026/ — full feature/cost comparison
- **Bachelor Tech migration guide**: https://bachelor-tech.com/detailed-guides/deploy-vaultwarden-in-high-availability-docker-opnsense-galera-cluster-nginx/9-migrate-your-data-from-bitwarden-to-vaultwarden/ — migration procedure
- **Bitwarden community forum thread**: https://community.bitwarden.com/t/self-hosted-vs-cloud-bitwarden-for-a-small-solo-run-business/100624 — community perspective
- **Dedimax self-host guide**: https://www.dedimax.com/en/blog/self-host-vaultwarden-your-own-bitwarden-compatible-password-manager — Vaultwarden TCO analysis
- **Elestio LastPass replacement**: https://blog.elest.io/how-to-replace-lastpass-with-vaultwarden/ — LastPass breach timeline, $438M crypto stolen
