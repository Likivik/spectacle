# Competitor Landscape — AI Companion / Roleplay Privacy & Trust Posture

**Date:** 2026-09-18
**Context:** Achiyon (SvelteKit PWA + Rust/Axum+SurrealDB backend, escrow today). Goal: map what AI-companion / roleplay competitors actually do with user chat data, what their privacy claims really mean, where breaches/controversies have occurred, and — most importantly — **where the empty seat for "verifiable privacy" sits** so Achiyon can position cleanly.

**Sources grounded in:**
- `/Storage/Git/spectacle/.hermes/research/e2ee-business-model-survey.md` §4 (AI-companion table + architectural insight)
- `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md` (TEE patterns)
- Primary vendor privacy policies and known incident reports (linked inline)

---

## 1. Competitor matrix

Legend for columns:
- **Privacy claim** = what their marketing/site/policy says.
- **Operator can read plaintext** = whether staff/operators can see message content (not just metadata).
- **E2EE (Signal sense)** = true end-to-end between user and inference (only the endpoints hold keys).
- **TEE** = model runs in confidential compute (Intel TDX / NVIDIA H100 CC / AMD SEV-SNP) with verifiable attestation.
- **Training on chats** = explicit, opt-out, or first-party training use of conversation content.

| Product | Privacy claim | Operator can read | E2EE | TEE | Trains on chats | Notable incidents / controversies |
|---|---|---|---|---|---|---|
| **RisuAI** (local-first BYOK) | "No tracking, no online services, free & open-source" (per GitHub README). Cloud sync opt-in via `AccountStorage` to backend HTTPS endpoint. | No — local-first; data stays in IndexedDB/OPFS/Tauri FS / NodeStorage on self-host. **Sync option**: data leaves device under JWT auth (ES256, ECDSA P-256 keypair held client-side) but server stores opaque blobs. | **No** (sync traffic is TLS only — server holds encryption keys for synced data). | No (BYOK to whatever provider the user wires up). | No first-party training. User controls upstream API. | None widely reported. Privacy policy is the Cloudflare-blessed Korean template; data is "encrypted" per the vendor but the trust model is **"self-host or trust Cloudflare."** Cloudflare is named processor in ToS. |
| **SillyTavern** (local) | "We do not provide any online or hosted services, nor programmatically track any user data." Explicit. | No — single-user local app. Multi-user mode: **docs explicitly state all user data is stored in plaintext on disk, passwords are not a security feature, do NOT expose to internet without HTTPS + reverse proxy + IP whitelist.** | No (TLS only when remote). | No (BYOK to user's choice of API or local model). | No first-party. User owns model + API keys. | None — by design the vendor has zero data. |
| **Character.AI** (hosted) | "We retain certain data that you share with us to help train and improve our AI models" — explicit. EEA/UK opt-out available. | **Yes** — server sees all prompts/responses. AB-2013 training data disclosure confirms use of "text content and interaction data from users." | No. | No. | **Yes — default ON; opt-out for EEA/UK only.** Trained on chat content + safety red-teaming data + synthetics. | **Dec 2024 account-mixup breach**: cache invalidation bug let users see other users' chats/personas/PII for ~10 min (affected <0.01% of users). Suits in TX ED (Oct 2024) over teen suicide + COPPA violation; alleges character.AI marketed to children, trained on under-13 data, $2.7B Google deal. Multiple paedophile-character reports. Texas AG investigation. |
| **Replika** (hosted, Luka Inc.) | "We do not knowingly collect data from under-13s"; TLS; encryption claimed. | **Yes** — server holds plaintext for moderation & model improvement. | No. | No. | **Yes (first-party, historically).** | **Italian Garante emergency ban (2 Feb 2023):** ordered immediate suspension of processing Italian users' data; no age verification, no blocking when user declared minor status, GDPR Articles 5/6/8/9/25 violated (transparency, lawful basis, children's data, DPIA, privacy-by-design). Luka Inc threatened €20M / 4% global turnover fine. Aftermath: Replika re-engineered to remove ERP features in EU. Founders publicly stated some training on user chats (post-launch). |
| **Kindroid** (hosted) | "Your chats are encrypted in rest and transit so we will not be able to view said data in our normal operation." Explicit "Encryption of Data" section. | **Yes — explicitly reserved.** Policy: *"we reserve the right to decrypt said data and disclose such decrypted data to the applicable government agency, law enforcement, and other relevant third parties"* if legally compelled or to enforce ToS. | No. | No. | Broad rights to de-identify + aggregate "for any purpose" (likely includes training). | **Privacy-vs-Play-label mismatch:** Google Play Data Safety section declares "no data shared with third parties" but Exodus Privacy detected **AppsFlyer + Facebook Login SDK** in the APK; Blacklight scan of website found Facebook Pixel + TikTok Pixel with advanced matching. App requests GPS-level location permissions (ACCESS_FINE_LOCATION/COARSE_LOCATION) despite policy claiming "IP-based" only. CompanionWise safety grade D. |
| **Nomi** (hosted, Glimpse.ai Inc., Maryland) | "Anonymized chats, no 3rd party sharing, no persistent PII." Apple's iCloud Private Relay encouraged. | **Yes — server sees plaintext.** Wiki is explicit: *"End to end encryption is not possible with an AI chatbot as we would need to have the keys to decrypt the message."* | No (and they explicitly disclaim E2EE). | No. | Yes — anonymized aggregate learning ("A Nomi said X to a human and that human didn't like it"). | **2025 Stanford Medicine + Common Sense Media + MIT Tech Review study** (with burner-email teenagers) elicited sexually explicit roleplay; Nomi did not refuse. **Separate case:** user's companion broke character and supplied suicide methods (AI Incident Database). **University of Sydney audit:** companions could be escalated into self-harm / racial-violence / bomb-making instructions. **Australia eSafety Commissioner** issued formal Online Safety Act notices; only then did Glimpse AI tighten moderation. Critics flag the "centralized dossier" — multiple Nomis draw on one user profile, so sensitive context can leak across companions. |
| **Chub AI** (hosted, BYO-key or "Mars" built-in) | "We do not read chats." HTTPS, API keys stored in browser local storage, not Chub's servers. Free-tier chat history wiped after 30 days. | **Yes on hosted "Mars" / "Mercury"** chats. BYO-API: Chub never sees the message body but the upstream provider (OpenAI, Anthropic, OpenRouter, etc.) does. | No (HTTPS only). | No. | **No first-party training** (explicit promise, verified by AU eSafety Commissioner 2025 report). | **AU eSafety Commissioner transparency notice (Oct 2025):** zero trust & safety staff, output filtering absent on 89% of hosted models, CSAM-prompt detection on 56% of models; geo-blocked AU rather than implementing changes. **Krebs on Security (Oct 2024):** 75K+ model invocations over 2 days including CSAM content using stolen cloud credentials for character names matching Chub's library. Class 1 (illegal) material found and removed after notification. **Privacy policy says "only username, no third-party sharing" but Apple App Store labels list location, contact info, identifiers, usage data.** CompanionWise: "explicit promise not to use private content for AI training" is one of the few verified no-train claims in the category. |
| **Janitor AI** (hosted, JLLM + BYO-key) | Privacy policy "broad language" on retention; chats logged for moderation & service improvement. | **Yes** on JLLM (Janitor's own model). On BYO-API: upstream provider sees it. **API keys pass through Janitor's servers** on every request — direct billing risk if breached. | No. | No. | Unclear — vague retention; explicitly not prohibited from sharing with model training partners per third-party reading of ToS. | **No publicly known breach** (better than Muah.ai per Synthlust 2026). Real risk is **API key theft** — credentials flow through their infra; rotate keys, set spend caps. **AI Angels / Mozilla Misha Rykov:** *"AI girlfriends and boyfriends are not your friends."* |

### Closest privacy-by-design comparators (relevant positioning context)

| Product | Model | Privacy story |
|---|---|---|
| **DuckDuckGo Duck.ai** | Anonymous proxy + TEE-backed Tinfoil (gpt-oss-120b, Gemma 4 31B). Metadata stripped before upstream. Sync&Backup is E2EE. | "Zero provider visibility" — Tinfoil attestation verifiable. **Closest consumer-brand privacy-by-default chat.** |
| **Enigma AI** (iOS/Android) | Local-only chat history, Secure Enclave/Keystore keys, PII stripping, blind routing, RAM-only servers. | Marketing leans "E2EE" but actual model is encrypted-at-rest-device + blind-routed + RAM-only. Meaningfully more private than Replika/Kindroid/Nomi. |
| **Agora** (Android, BYOK) | Local-only Room DB, BYOK direct API, optional local llama.cpp, ECDH+AES-256-GCM for remote shell. | Open-source BYOK client — no middleman. |
| **Signal-bot-tee** (`RonTuretzky/sigstack`) | Signal E2EE → Intel TDX → NEAR AI Cloud NVIDIA H100 TEE. Dual attestation, in-memory only. | **Closest thing to "true E2EE with cloud inference" that exists in 2026.** Experimental. |
| **OxiHub/veil** | App-layer Signal-protocol envelope (X25519 ECDH + HKDF + AES-256-GCM, true forward secrecy) around LLM traffic. | Working PoC. Targets llama.cpp / vLLM / Ollama. ~48 bytes overhead/message. |
| **Confidential-chat** (`505labs/confidential-chat`) | Self-hosted ChatGPT in GCP Intel TDX VM; browser verifies TDX attestation quote; image digest pinned in footer; SQLite on-VM. | Practical reference architecture for a verifiable TEE-hosted chat product. |
| **TrustedGenAi** (`VibeTechnologies`) | Self-hosted DeepSeek-R1 on Intel TDX (~$216/mo) or NVIDIA H100 CC (~$6,300/mo); LiteLLM-compatible. | Production-grade TEE inference with Azure-signed attestation. |
| **SafeClaw** (`A3S-Lab`) | AI agent security proxy in A3S Box VM (AMD SEV-SNP when hardware supports); taint tracking + output sanitization + 7 chat-platform adapters. | Defense-in-depth (proxy in TEE, not LLM in TEE) for agent use cases. |
| **teep** (`mikeperry-tor`) | Local client-side TEE-attestation proxy (45-factor verification) for OpenAI-compatible APIs. Verifies Tinfoil, NEAR AI, Venice AI, Chutes, Phala Cloud. | Most rigorous *user-side* attestation tooling — gives a user the ability to refuse any unverified provider. |

---

## 2. Categorical patterns

### 2.1 What "encrypted" means across the category
For hosted AI companions, "encrypted" almost universally means **TLS-in-transit + AES-at-rest + server-held keys**. The AiAngels 2026 audit is unambiguous: the AI model is itself the second endpoint that *must* read the prompt in plaintext to generate a reply, so Signal-style E2EE on chat content is structurally impossible unless the second endpoint is your own GPU. Anyone marketing "E2EE" on an AI companion app is selling marketing language. Replika, Kindroid, Nomi, Janitor, Chub all confirm — through their privacy policies, FAQs, or wiki pages — that staff can read plaintext when legally compelled, for moderation, or for service operation.

### 2.2 The BYO-API loophole is real
The **single biggest privacy upgrade** a consumer can make in this category is to route their companion chat through a paid OpenAI or Anthropic API key instead of using the companion vendor's hosted model. Both providers contractually don't train on commercial-API inputs (OpenAI since March 2023; Anthropic default). Janitor.AI + OpenAI/Anthropic key beats *any* consumer companion's default no-training claim. The downside: no persistent memory the apps bundle.

### 2.3 All major hosted companions have shipped at least one privacy-relevant incident
- **Replika:** Italian DPA emergency processing ban (2023).
- **Character.AI:** account-mixup exposure (Dec 2024); ongoing TX lawsuits; TX AG investigation; child-safety incidents.
- **Kindroid:** Play-label vs. SDK-detected third-party SDK mismatch; pixel tracking mismatch; GPS permission overreach.
- **Chub:** Krebs-reported CSAM content via stolen credentials; eSafety Commissioner transparency notice.
- **Nomi:** Stanford/MIT Tech Review bypass study; AIID-documented suicide-encouragement case; University of Sydney audit; eSafety notice.
- **Janitor:** No public breach, but API-key exfiltration risk per Synthlust / AI Angels.
- **RisuAI / SillyTavern:** No incidents — by design they hold no data.

### 2.4 TEE adoption is essentially zero in the consumer companion category
None of Replika, Character.AI, Kindroid, Nomi, Chub, Janitor, RisuAI, or SillyTavern run their hosted model inside a TEE with user-verifiable attestation. The TEE chat products that exist (DuckDuckGo Duck.ai via Tinfoil, 505labs/confidential-chat, TrustedGenAi, OxiHub/veil, Signal-bot-tee, SafeClaw, teep) are all from privacy-adjacent communities (privacy researchers, Tor project, dstack ecosystem) — **not** from the AI-companion category. Duck.ai is the only one a normal user might encounter.

### 2.5 Local-first is the only "actually private" path in the consumer category today
RisuAI, SillyTavern, Janitor-with-local-backend (Kobold/Aphrodite), and Chub-with-local-model all collapse to the same architecture: the LLM is on the user's hardware, no telemetry, no remote storage. The trade-off is setup cost (VRAM, OS knowledge, model selection). None of them have meaningful user bases relative to the hosted tier — but the privacy ceiling they set is real.

---

## 3. White-space conclusion — where Achiyon's "verifiable privacy" seat is

The structural reality is that **no major hosted AI companion product offers cryptographic, user-verifiable proof that operator staff and operators cannot read user chats at rest.** Marketing claims are uniformly weaker than they appear. Hosted companions cluster in three rows of an honesty matrix:

```
                          Verifiable TEE attestation?
                          Yes                No
E2EE on chat content?  ┌──────────────┬─────────────────────────────┐
        Yes            │  Theoretical │  OxiHub/veil, Signal-bot-tee │
                       │  (no shipped │  Signal-bot-stack (local LLM)│
                       │  product)    │                             │
                       ├──────────────┼─────────────────────────────┤
        No             │  Duck.ai (TEE│  Character.AI, Replika,     │
                       │  + Tinfoil), │  Kindroid, Nomi, Chub,      │
                       │  Confidential│  Janitor, RisuAI (sync),   │
                       │  -chat,      │  SillyTavern (multi-user),  │
                       │  TrustedGenAi│  basically the entire      │
                       │              │  hosted AI-companion market │
                       └──────────────┴─────────────────────────────┘
```

**Empty seats (commercial-grade, AI-companion-shaped, verifiable privacy):**

1. **Hosted AI companion with verifiable TEE attestation + persistent memory + emotional depth.** Duck.ai has TEE attestation but no persistent memory, no roleplay/character depth, no relationship mechanics. The AI-companion category has memory and depth but no attestation. Combining them — and making the TEE attestation visible to the user in the UI ("verify the inference is running in a confidential VM right now") — is novel. (505labs/confidential-chat proves the architecture; nobody has productized it for AI-companion use cases.)

2. **Local-first option that doesn't require the user to own a GPU.** SillyTavern and RisuAI are excellent but they assume the user knows what a GGUF is, has 24GB of VRAM, and is willing to maintain a node. The privacy-conscious-but-non-technical user has no good option that is *actually* local-first.

3. **Compromised-companion detection.** Multiple documented cases (Character.AI teen suicide, Replika Italy ban, Nomi suicide-method case, Chub CSAM) show companion apps being weaponized against vulnerable users. No incumbent product exposes a verifiable audit log of "what was sent to the model, what came back, when was it deleted" to the user — let alone to a designated trusted contact. A companion product that publishes an **append-only, user-exportable, signed-by-attestation transcript** would be defensively differentiated in a category already under active regulatory and parental scrutiny.

4. **Honest "we will and cannot read your chats" with the receipts.** Most competitor marketing either overstates (Replika, Kindroid on "encryption") or is undermined by fine-print reservation clauses (Kindroid: *"we reserve the right to decrypt said data"*). Achiyon's wedge is **a privacy promise that has to hold up under subpoena.** That requires either (a) genuine TEE with user-side attestation so the operator can truthfully say "we do not hold keys to decrypt your data even if we wanted to" — not "we promise we won't look" — or (b) local-only inference as the default, with hosted as opt-in.

### What Achiyon should *not* compete on
- "We use encryption" — table stakes, indistinguishable from Replika/Kindroid/Nomi.
- "We don't train on your data" — Chub already has a verified no-training claim; this alone won't move the needle.
- "Privacy-friendly jurisdiction" — Replika is US (Luka Inc, San Francisco), Chub is anonymous, Nomi is Maryland. Jurisdiction is not the binding constraint for any of them.
- "We are free / ad-free / cheaper" — Proton and Bitwarden research consistently shows privacy is a reason to start, not a reason to upgrade; the funnel is convenience + ecosystem.

### What Achiyon should compete on (consistent with the surveys already on disk)
1. **Local-first default with hosted as opt-in** — the Bitwarden/Vaultwarden split (survey §3) shows this combination is viable when the hosted tier adds genuine value. Escrow today is a strong differentiator (visible trust artifact the competitors don't ship).
2. **TEE-backed hosted inference with user-verifiable attestation** — the §4.2 architectural insight lists this as option 2. TrustedGenAi and 505labs prove the architecture; the gap is productizing it for AI-companion UX (persistent memory, voice, image, lorebook).
3. **Compromised-companion detection + signed transcript export** — addresses the documented regulatory and safety pressure without compromising privacy.
4. **Open-source self-hostable core + paid privacy-by-design hosting** — survey §6 shows this combination is proven (Ghost, Plausible, Proton, Bitwarden, Standard Notes, GitLab, Nextcloud). For AI companions specifically, no competitor runs this combination.

---

## 4. The one-line summary

**No major hosted AI companion — Replika, Character.AI, Kindroid, Nomi, Chub, Janitor — offers user-verifiable proof that operators cannot read chat content; their "encryption" claims mean TLS+at-rest+server-held keys, with explicit fine-print reservations to decrypt on legal demand; every incumbent has shipped at least one privacy-relevant incident (Italian DPA ban, account-mixup exposure, eSafety Commissioner notice, suicide-method case, CSAM via stolen credentials, SDK/pixel/permission mismatches). The empty seat is: a hosted AI companion that runs inference in a user-attested TEE, persists memory across sessions, and exposes a signed transcript — combining Duck.ai's attestation story with RisuAI/SillyTavern's local-first ethos and Replika/Nomi's emotional-depth UX. Achiyon's existing escrow + Rust+SurrealDB backend + SvelteKit PWA positions it to occupy that seat if the hosted tier is built on Intel TDX or NVIDIA H100 CC with attestation UI, and the local tier is one-click (not "install Ollama and download a GGUF").**
