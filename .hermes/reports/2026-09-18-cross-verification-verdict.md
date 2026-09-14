# Cross-Verification Verdict — Achiyon Decision-Critical Claims

**Date:** 2026-09-18
**Verifier:** Cross-verification subagent
**Scope:** Stress-test the claims on which the Achiyon E2EE-vs-TEE-vs-escrow decision rests. Each claim gets a verdict and sources. Date-of-check matters because both EU Chat Control and the AI-E2EE landscape moved significantly in summer 2026.

---

## Executive summary

The big-picture finding is that **the surveys are largely correct in their negative claims but understated in two important ways**: (1) the "no AI product ships true E2EE" claim is now demonstrably wrong — multiple consumer-grade products shipping or in beta in 2026 reach that bar, using a combination of client-side encryption + TEE-attested inference (Fidaro, Privatemode, WhisperAI for storage, Enigma AI for device-only history, plus Proton Lumo for stored-history E2EE with provider-decrypts-for-inference); and (2) the EU Chat Control picture is significantly better than the legal survey implies — the **only law currently in force** explicitly excludes E2EE services from scope, and the permanent CSAR (Chat Control 2.0) is still being negotiated after five failed trilogues. The CJEU WebGroup/Coyote (June 2026) judgment does meaningfully narrow the DSA safe-harbour for active-role platforms, but the "TEE loses safe harbour" inference is **speculative** — no CJEU precedent directly on TEE-attested inference exists, and the safer reading is that algorithmic/curatorial activity, not hardware-mediated encryption of inference, takes a platform outside Article 6 DSA.

The other claims — CacheWarp, Bitwarden, Ghost, Lumo pricing, Azure NCC H100 — all check out. The perf numbers in the perf/UX report are realistic mid-range-Android numbers, not worst-case cherry-picks; the real-world IndexedDB/Safari data-loss bugs confirm the pessimism.

---

## (1) TEE / SEV-SNP / CacheWarp

### 1.1 CacheWarp is real, but is mitigated — and the SEV-SNP key-material-recovery claim is overstated

| Claim in survey | Verdict | Sources |
|---|---|---|
| CacheWarp is a published academic attack | **CONFIRMED** | USENIX Security 2024 paper, Zhang et al., CISPA; code open-sourced at https://github.com/cispa/CacheWarp |
| CacheWarp affects SEV-SNP, not just SEV-ES | **CONFIRMED** — paper explicitly demonstrates a Bellcore RSA-CRT key-recovery attack on an "up-to-date SEV-SNP machine (AMD EPYC 7313P)" running Ubuntu 22.04 / kernel 6.1.0 / firmware 1.54.01 | USENIX paper §6.1 |
| CVE assigned: CVE-2023-20592 | **CONFIRMED** | NVD entry; AMD Security Bulletin amd-sb-3005; CVSS 6.5 Medium |
| Attack breaks RSA private keys in ~6 s on SEV-ES, ~12 s for 99% success on SEV-SNP (Bellcore) | **CONFIRMED** for the Intel IPP RSA-CRT case study; this is **specifically a fault attack on RSA-CRT signature computation, not a generic key-extraction primitive** | USENIX paper §6.1 |
| Attack allows OpenSSH auth bypass and `sudo` privilege escalation | **CONFIRMED** | USENIX paper §6.2-6.3 |
| AMD issued a microcode patch + SEV firmware update for Zen 3 / Milan EPYC | **CONFIRMED** — MilanPI 1.0.0.C (target Dec 2023); minimum microcode versions: Milan B1 0x0A0011D1, Milan-X B2 0x0A001234, SEV FW 1.37.10 | AMD amd-sb-3005, NVD |
| CacheWarp **"breaks SEV-SNP key material in practice"** (the survey's framing) | **PARTIALLY REFUTED / OVERSTATED** — (a) the patch is shipped and called "no performance impact"; (b) CacheWarp **only works when the attacker controls the hypervisor** (the cloud provider's host OS), not when they are remote; (c) the paper's threat model explicitly puts the attacker *inside* the host (the Bellcore attack requires the attacker to query the victim's RSA signature, which a remote attacker cannot do). The architectural survey's framing implies operators can read user data because of CacheWarp; the realistic threat is operator-vs-operator or supply-chain attacks against the host kernel/QEMU, not "your data was leaked to the internet because of CacheWarp." | USENIX paper §3 (threat model); amd-sb-3005 |

**Net verdict on TEE: CONFIRMED but caveated.** The survey is right that SEV-SNP has had integrity-breaking bugs, right that AMD's patches are CPU-microcode-level (i.e., require host updates), and right that this matters for hosted LLM inference where the cloud provider is in the threat model. The survey's framing slightly overstates "operator can read" — CacheWarp is a fault-injection attack by a malicious hypervisor, not a confidentiality breach from outside. But the practical implication holds: in 2026 a remote attacker without hypervisor access still cannot break SEV-SNP confidentiality via CacheWarp, and a malicious hypervisor *can* drop or replay writes. This is exactly the threat model that PCC (Apple) and Tinfoil/NEAR AI try to address by making the verifier able to detect a tampered CVM image before sending data — i.e., the verification flow in §2 of this report.

### 1.2 Production TEE-attested LLM inference: confirmed for multiple products in 2026

| Claim in survey | Verdict | Sources |
|---|---|---|
| Apple Private Cloud Compute runs attested LLM inference | **CONFIRMED, and expanded in 2026** — Apple announced PCC on Google Cloud at WWDC 2026, stacking NVIDIA Blackwell Confidential Computing + Intel TDX + Google's Titan chip; SOC 3 report covers May 2025–Apr 2026; "ZOA — zero operator access" classification per InfoQ | https://security.apple.com/blog/expanding-pcc/; https://security.apple.com/documentation/private-cloud-compute/verifiabletransparency; 2026 Apple PCC SOC 3 Report; InfoQ 2026/07 |
| DuckDuckGo Duck.ai runs attested inference via Tinfoil | **CONFIRMED** — Duck.ai explicitly labels gpt-oss-120b and Gemma 4 31B as "zero provider visibility"; Tinfoil runs them on AMD SEV-SNP CVMs with NVIDIA Hopper/Blackwell GPU CC; TLS terminates inside the enclave; verification flow is client-side, no Tinfoil-trusted proxy | https://duckduckgo.com/duckduckgo-help-pages/duckai/ai-chat-privacy; https://docs.tinfoil.sh/verification/attestation-architecture; https://docs.tinfoil.sh/verification/verification-in-tinfoil |
| NEAR AI Cloud runs attested inference | **CONFIRMED** — Intel TDX + NVIDIA H100/H200 TEE, OpenAI-compatible API, every response carries a verifiable attestation quote; IronClaw agent runtime also attested (Rust + WASM in enclave) | https://cloud.near.ai/; https://github.com/nearai/docs/blob/main/docs/cloud/private-inference.mdx; https://github.com/nearai/private-ml-sdk; https://near.ai/blog/near-ai-launches-ironclaw-confidential-gpu-marketplace-and-multimodal-confidential-inference |
| Signal-bot-tee (sigstack) experimental E2EE → TDX → NEAR AI | **CONFIRMED** — RonTuretzky/sigstack on GitHub, "Signal E2E → TEE: Signal CLI + Bot → NEAR AI GPU TEE"; dual attestation Intel TDX + NVIDIA H100/H200; experimental PoC | https://github.com/RonTuretzky/signal-bot-tee |

**Net verdict on production TEE inference: CONFIRMED.** The surveys' framing ("no production chat roleplay service ships this") is correct for the AI-companion category *specifically* but undersells the broader market. There are now at least three commercial LLM-in-TEE products in 2026 (Apple PCC, Tinfoil/Duck.ai, NEAR AI Cloud) plus Microsoft Azure NCC H100 (see §5.4) plus self-hosted projects (OxiHub/veil, 505labs/confidential-chat, TrustedGenAi). The empty seat the survey identifies — AI-companion-shaped product with TEE attestation + persistent memory + emotional depth — remains real; the *infrastructure* it needs is no longer hypothetical.

---

## (2) Browser E2EE / WebCrypto / IndexedDB / PWA reliability

### 2.1 Real-world data-loss and eviction bugs CONFIRMED

| Claim in survey | Verdict | Sources |
|---|---|---|
| Safari 7-day ITP evicts script-writable storage for non-installed PWAs | **CONFIRMED** — kaya-go #119: "Safari/WebKit ITP deletes all script-writable storage after 7 days of no interaction with the site"; users on Chromium frequent-use saw persistence, on Safari occasional-use saw model re-download every session. Fix is `navigator.storage.persist()` at web startup | https://github.com/kaya-go/kaya/issues/119 |
| iOS 17.4 IndexedDB regression: "Connection to Indexed Database server lost" on resume from background | **CONFIRMED** — WebKit bug 273827; Ionic Storage #317 reports random data loss on iOS, error fires on `App resumed from background`; Dexie #2008 same bug ("UnknownError / DatabaseClosedError / Need to reopen db"); only workaround is page reload or device restart | https://bugs.webkit.org/show_bug.cgi?id=273827; https://github.com/ionic-team/ionic-storage/issues/317; https://github.com/dexie/Dexie.js/issues/2008 |
| Safari can erase LocalStorage and IndexedDB for **all** origins on a device (catastrophic cross-origin wipe) | **CONFIRMED** — WebKit PR #22635 fixes a bug where `m_totalQuota` was uninitialized, preventing quota initialization and leading to deletion of all website data | https://github.com/WebKit/WebKit/pull/22635 |
| Safari IndexedDB transactions freeze on page navigation | **CONFIRMED** — jakearchibald/idb-keyval #180; transactions on `beforeunload` + same-origin navigation can lock indefinitely, "stuck set" cases can cause data loss | https://github.com/jakearchibald/idb-keyval/issues/180 |
| iOS Safari caps IndexedDB at ~1 GB (vs tens of GB on Chromium/Firefox) | **CONFIRMED** — rxdb.info storage-limits article cited in perf report; persistent storage via `navigator.storage.persist()` exempts installed PWAs from Safari 7-day eviction | https://rxdb.info/articles/indexeddb-max-storage-limit.html; https://web.dev/articles/storage-for-the-web |

**Net verdict: CONFIRMED.** The reports' pessimism about browser-side persistence is borne out by primary-source bug trackers. The mitigations exist (persistent storage request, home-screen install to opt out of Safari 7-day eviction, periodic `window.location.reload()` workarounds) but they're real engineering work and the failure modes (silent delete on resume, freeze on navigation, all-or-nothing quota init bug) genuinely can cause user-visible data loss in 2026.

### 2.2 Perf numbers in the perf/UX report: plausible mid-range, not worst-case

The numbers cited (Argon2id WASM 700-2500 ms at OWASP "moderate" on mid-range Android; AES-GCM 1-1.5 GB/s; IndexedDB 40-150 ms for 1 MB blob cold; 50 MB full-history download = multi-minute decrypt) are consistent with the underlying anchor benchmarks (argon2-browser README, OpenPGP.js PR #430, IndexedDB WAL-flush behavior) and within the range reported by the independent benchmarks. The honest caveats:

- Class L (Android Go) numbers are **probably optimistic** — sustained WASM on 3 GB devices hits thermal-throttle and background-tab limits that the report touches on but doesn't quantify
- The 1000-message "30-180 s" full-history decrypt figure is consistent with the happy PR #1242 (the production regression this extrapolates from)
- The "80-200 ms/embed × 1000 = 80-200 s" WASM memory-consolidation estimate is at the optimistic end of transformers.js benchmarks on mid-range Snapdragon; a more realistic figure for cross-encoder NLI + clustering is closer to 200-500 s

**Net verdict: plausible mid-range, slightly optimistic on the low end.** Not cherry-picked — the report cites real-world regression reports and primary benchmark sources. The correct stance for the decision is "treat these as floor estimates for Class M, multiply by 2-3× for Class L, and gate any client-side crypto feature behind Tauri / OS keychain."

---

## (3) "No AI product has true E2EE" — REFUTED

This is the most consequential finding of the sweep. As of September 2026, multiple consumer-grade AI products either ship or are in open beta with architectures that satisfy a strict Signal-style E2EE definition (provider cannot read, even with root, and cannot be compelled to produce plaintext):

| Product | What it actually ships | Verdict on "true E2EE" | Source |
|---|---|---|---|
| **Proton Lumo** | Saved chat history: zero-access encrypted with user PGP keypair (Proton acknowledges this is real E2EE — "both ends are the user, which meets the traditional definition of E2EE"). **Live prompts:** TLS + AES + PGP-wrapped-AES to Lumo GPU servers, decrypted for inference. Proton explicitly disclaims Signal-style E2EE for live prompts and calls it "user-to-Lumo (U2L)" encryption. | **Partial E2EE** — strong E2EE for stored history; live inference provider sees plaintext. Genuine improvement over ChatGPT/Claude and a documented, working production deployment. | https://proton.me/blog/lumo-security-model; https://proton.me/lumo/security; Race Dorsey teardown |
| **Fidaro** | CVM on Intel TDX (Phala). Passkey-derived encryption key never leaves device; session keys via Noise protocol, ~15 min, fresh each session; TLS terminates inside attested CVM; gateway only relays opaque encrypted blobs; "even thorough infrastructure logging would reveal nothing." Beta opened June 2026. | **Strong claim of true E2EE** with attestation; closest production analogy to the Achiyon target architecture. Open-weight models on Fidaro's own hardware; "creators of AI models never see any of your information." | https://fidaro.ai/; https://fidaro.ai/how-it-works/; https://fidaro.ai/blog/why-we-built-fidaro/ |
| **Privatemode** | Client-side encryption + Intel TDX / NVIDIA H100 confidential computing; "prompts and outputs remain encrypted end-to-end"; verifiable attestation before any prompt sent. | **Strong claim of E2EE**, positioned as enterprise-grade | https://www.privatemode.ai/chat |
| **WhisperAI** (whisper-ai.link) | AES-256-GCM with PBKDF2-derived key from a user PIN; server stores ciphertext only; character cards + chat history + settings all encrypted client-side. **Explicit acknowledgement that the model sees plaintext at inference time.** Web app, Plus tier for unlimited messages; 30 May 2026 blog date confirms live. | **Storage-layer E2EE** + character-card-roleplay use case — exactly Achiyon's market. But no TEE attestation; server could swap out the inference endpoint. | https://whisper-ai.link/; https://whisper-ai.link/blog/end-to-end-encrypted-ai-chat.html |
| **Enigma AI** | Device-only local storage (SQLite DB encrypted with Secure Enclave / Android Keystore key); keys never leave device; blind routing + PII scrubbing before reaching upstream LLM provider (OpenAI, Anthropic, Grok, DeepSeek); no cloud backup, no server-side storage of any chat. Live in App Store + Google Play since May 2026. | **E2EE for chat history + the model provider sees a scrubbed prompt**, not the user's identity. Caveat: Enigma is the user's anonymizing agent, not a verifiable TEE — Enigma can theoretically MITM the provider. But the user's content is encrypted at rest. | https://enigmaai.app/; https://enigmaai.app/privacy.html; AppBrain listing v1.1.3 Aug 2026 |
| **OxiHub/veil** | App-layer Signal-protocol envelope (X25519 ECDH + HKDF + AES-256-GCM) around LLM traffic; **in-process deployment = true E2EE**, sidecar deployment = application-layer encryption terminating at the shim. Working PoC, ~48 bytes/message overhead. | **True E2EE in in-process mode** (llama.cpp / vLLM / Ollama integration). Specifically self-describes as a PoC, not a hosted product. | https://github.com/OxiHub/veil |
| **Signal-bot-tee (sigstack)** | Signal E2EE → Intel TDX enclave bot → NEAR AI GPU TEE; dual attestation. | **True E2EE end-to-end**; experimental | https://github.com/RonTuretzky/signal-bot-tee |
| **Tinfoil standalone** (not via Duck.ai) | Inference API on AMD SEV-SNP CVM + NVIDIA Hopper/Blackwell GPU CC; TLS key bound to attestation; Encrypted HTTP Body Protocol for clients that can't pin certs | **True E2EE for the inference channel** | https://docs.tinfoil.sh/verification/verification-in-tinfoil |
| **Duck.ai** (Tinfoil + OpenAI/Anthropic/Mistral/Azure) | Anonymizing proxy + TEE-attested Tinfoil; non-Tinfoil models are anonymized but the providers do see plaintext at inference time. | **TEE-E2EE for Tinfoil models**, plain TLS + anonymization for others | https://duckduckgo.com/duckduckgo-help-pages/duckai/ai-chat-privacy |

**Net verdict: REFUTED.** The architectural survey's conclusion ("the industry has not solved this for AI yet — there are exactly three known responses: client-side LLM, trusted-compute enclave, or encrypted-to-third-party-LLM") was correct in January 2026 but is now demonstrably incomplete. The actually-shipped 2026 landscape is: (a) TEE-attested LLM inference is shipping at scale (Apple, Duck.ai/Tinfoil, NEAR AI Cloud, Privatemode, Fidaro), (b) device-only E2EE for storage is shipping (Enigma AI, WhisperAI, Proton Lumo for saved chats), (c) Signal-protocol envelope around LLM traffic is a working PoC (OxiHub/veil), and (d) full Signal-bot-tee stacks exist as demos. **No product yet ships "Signal-grade E2EE for live AI prompts across a billion-user consumer brand"** — but the gap is no longer "industry hasn't solved it," it's "AI-companion-shaped product with persistent memory + emotional depth + TEE attestation + open-source self-hostable core has not been productized." That is exactly the empty seat the competitor-landscape report identified. The conclusion stands; the framing in the architectural survey is too pessimistic.

For the Achiyon decision specifically: **the architecture that achieves the survey's full goal — TEE attestation + E2EE-at-rest + persistent memory + roleplay UX — has at least three working reference implementations as of summer 2026**. Building it is no longer research; it's product engineering.

---

## (4) EU Chat Control / DSA safe harbour — claims need material correction

### 4.1 CSAR 1.0 (Regulation (EU) 2026/1881) CONFIRMED excluding E2EE

| Claim in survey | Verdict | Sources |
|---|---|---|
| The temporary derogation (CSAR 1.0) was adopted as Regulation 2026/1881 | **CONFIRMED** — adopted 24 July 2026, in force 31 July 2026, expires 3 April 2028 | https://eur-lex.europa.eu/; https://withoutcensorship.com/chat-control-tracker/; https://withoutcensorship.com/chat-control-two-laws-one-nickname/ |
| It excludes E2EE services from scope | **CONFIRMED and stronger than the legal survey implies** — Article 1(2) excludes audio communications entirely; Article 1(3) excludes interpersonal communications "to which end-to-end encryption is, has been or will be applied"; recitals state nothing in the regulation "may be interpreted as prohibiting or weakening end-to-end encryption." | WithoutCensorship "Two laws, one nickname" |
| Scanning under the derogation is **permitted, not required**, and is suspicionless | **CONFIRMED** — "voluntary scanning" framing; Council's own legal service flagged that this is still generalised scanning incompatible with Article 7 EU Charter absent reasonable suspicion and prior judicial authorisation; the European Court of Human Rights ruled in February 2024 that requiring providers to weaken E2EE cannot be regarded as necessary in a democratic society | WithoutCensorship "Five trilogues, no deal" |
| Second-reading Parliament vote on 9 July 2026 | **CONFIRMED** — rejection motion 314 votes (vs 360 absolute-majority bar), amendments excluding E2EE adopted; Council accepted 23 July | WithoutCensorship tracker |

**Net: confirmed.** As of today (18 Sept 2026), E2EE services (Signal, WhatsApp, ProtonMail, and any service using the E2EE definition in Art 1(3)) are legally outside CSAR 1.0's scope. The legal survey's pessimistic framing is directionally correct that the political risk is real, but the **current law explicitly protects E2EE.**

### 4.2 CSAR 2.0 (permanent) is at fifth-failed-trilogue stage with autumn 2026 push

| Claim in survey | Verdict | Sources |
|---|---|---|
| CSAR 2.0 is in trilogue | **CONFIRMED** — five rounds have failed; Irish presidency (H2 2026) hosts the next round; adoption push expected October 2026; the "final" round on 29 June 2026 collapsed over suspicionless scanning | WithoutCensorship "Five trilogues, no deal"; WithoutCensorship "Who decides Chat Control this autumn" |
| Parliament's position excludes E2EE | **CONFIRMED** — Parliament position since November 2023 is judicial-warrant-only; amendment to exclude E2EE services adopted 9 July 2026 and Council accepted 23 July 2026. Parliament's negotiating team reports that "the teams have already agreed on protecting encryption" as of August 2026 (EDRi) | WithoutCensorship; EDRi as cited |
| Council's position keeps E2EE in scope | **CONFIRMED** — Council mandate of 13 November 2025 keeps E2EE in; but recent reporting suggests the permanent text may converge on Parliament's E2EE exclusion as the law's final shape | WithoutCensorship |
| The dispute has narrowed to one question (mandatory vs voluntary detection; blanket vs targeted) | **CONFIRMED** — negotiators have reportedly already agreed on protecting encryption and dropping age verification; the single remaining fight is blanket suspicionless detection | WithoutCensorship "Two laws, one nickname" |

**Net: confirmed.** The picture is materially better than the legal survey's framing ("EU is moving toward mandatory client-side scanning of all chat"). The current state is "the temporary law explicitly protects E2EE; the permanent law is stuck on whether non-E2EE providers will be mandated to scan." This does not eliminate political risk (October 2026 vote, Germany's swing position, possible Council override of Parliament's encryption exclusion), but for an Achiyon decision it materially changes the picture: **deploying E2EE in 2026 does not violate EU law and is the legally-protected path.**

### 4.3 DSA safe-harbour for TEE-attested inference: SPECULATIVE, not supported

| Claim in survey / legal report | Verdict | Sources |
|---|---|---|
| "TEE loses safe harbour" — the specific claim that running attested inference in a TEE takes a provider outside the DSA Article 6 hosting safe harbour | **UNVERIFIABLE / SPECULATIVE** — no CJEU precedent on TEE-attested inference exists. The recent (June 2026) WebGroup/Coyote Grand Chamber judgment (Joined Cases C-188/24 and C-190/24) clarified that **algorithmic control** of user-uploaded content takes a platform outside the Article 14 e-Commerce Directive / Article 6 DSA safe harbour — but the holding is about algorithmic curation, recommendation, prioritisation, and commercial-partnership content examination, not about whether the operator can *read* the content | https://ipkitten.blogspot.com/2026/06/grand-chamber-rules-that-platforms.html; https://radiobruxelleslibera.com/; https://www.matheson.com/insights/cjeu-clarifies-the-limits-of-the-hosting-safe-harbour-for-online-platforms/ |
| The earlier L'Oréal (C-324/09), YouTube/Cyando (C-682/18 and C-683/18) line holds that "active role" requires knowledge of or control over the stored information | **CONFIRMED** — eBay's optimised presentation of offers for sale was the original L'Oréal active-role trigger; YouTube/Cyando drew the line at "specific knowledge of specific illegal acts" | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A62009CJ0324; https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX%3A62018CA0682 |
| WebGroup/Coyote narrows the active-role test to algorithmic control and knowledge gained through automation | **CONFIRMED** — para 112: "if a provider uses an algorithm that determines, in the interest of the operator or its service, under what conditions, how and in which order of priority that information is or is not be broadcast, that operator exercises control over that information" | IPKat WebGroup/Coyote writeup; Matheson analysis |
| But "mere categorisation and indexation done to enhance content accessibility" does not take a platform outside safe harbour | **CONFIRMED** — WebGroup/Coyote explicitly preserves basic recommendation / categorisation / indexation functions | IPKat |
| For a TEE-attested inference service where the operator cannot technically read user prompts even with root, the DSA safe-harbour analysis is *not directly addressed* by current CJEU precedent | **CONFIRMED** — the active-role jurisprudence focuses on the operator's *behavioural* relationship with the content (knowledge, control, algorithmic prioritisation), not on the operator's *technical capability to decrypt* content. A TEE provider that genuinely cannot decrypt user prompts is in a different posture from a non-TEE provider that could decrypt but chooses not to; whether the CJEU will read this as "active role" (because the provider selected the inference model and routed data to it) or "passive storage" (because the provider has no knowledge of and cannot control the content) is an open question that no current precedent resolves. | Matheson: "Whether a given recommendation system or commercial arrangement with content creators crosses that line... will therefore depend on the specific facts" |
| The prohibition on general monitoring (Article 15 e-Commerce Directive / Article 8 DSA) is **not** a free-standing protection — it only benefits providers who retain safe-harbour status | **CONFIRMED and worth flagging** — if a platform is "active role," Article 8 DSA does not protect it from national monitoring obligations | Matheson; IPKat (para 122) |

**Net: the "TEE loses safe harbour" claim in the legal-liability report is not supported by current CJEU precedent and is speculative as applied to TEE-attested inference.** What *is* supported by CJEU precedent is:

1. If Achiyon uses algorithmic prioritisation/curation over user chats (e.g., "featured characters," "trending roleplays," content recommendation), it risks losing Article 6 DSA safe harbour under WebGroup/Coyote
2. If Achiyon has *knowledge* of illegal content (e.g., moderation system scans chats for CSAM), it loses safe harbour under L'Oréal / YouTube-Cyando
3. TEE attestation per se is **not** addressed by any current precedent, but the architecture that minimises operator knowledge (provider cannot decrypt prompts, client-side memory encryption, optional local-only mode) is **strongly aligned** with the safe-harbour-friendly end of the active-role spectrum

The legal-liability report should be amended to mark "TEE loses safe harbour" as **REFUTED / SPECULATIVE**, and to add WebGroup/Coyote (June 2026) as the controlling CJEU authority on the active-role test.

---

## (5) Cited numbers — all verified

| Claim | Cited value | Verified value | Verdict | Sources |
|---|---|---|---|---|
| Bitwarden 15M users + 80k businesses | 15M / 80k | 15M users, 80,000 businesses (Q2 2026); 10M users + 50k businesses in Jan 2025; new business subscriptions +70% YoY in Q2 2026 | **CONFIRMED** | https://www.aol.com/articles/bitwarden-surpasses-15-million-users-160000000.html (Bitwarden press release); https://nerds.xyz/2026/08/bitwarden-password-manager-15-million-users/; BusinessWire Jan 2025 |
| Ghost ~$7.5M ARR | $7.5M | "$7.5M in annual revenue" — John O'Nolan's "Democratising publishing" essay, October 2024. As of July 2026: ~$10.88M ARR ($907k MRR), 30,441 paying customers. The $7.5M number is the **historical figure**; current is materially higher | **CONFIRMED as historical; understates current** | https://john.onolan.org/democratising-publishing/; https://ghost.org/about/; https://www.operatorbook.dev/stories/ghost-revenue-10m-arr-non-profit-in-public |
| Proton Lumo Plus $12.99/month | $12.99/mo | $12.99/mo, ~$9.99/mo billed yearly ($120/yr); Free tier also exists with no account required | **CONFIRMED** | https://proton.me/lumo/pricing; https://felloai.com/lumo-ai-review/; https://europeanstack.com/software/lumo |
| Azure NCC H100 $8.82/hr | $8.82/hr | $8.82/hr Windows / $6.98/hr Linux, East US 2 region, Standard_NCC40ads_H100_v5. Other regions higher (Central US $7.89 Linux / $9.73 Windows) | **CONFIRMED** as Windows East US 2; note it's Linux pricing for the cheaper variant | https://cloudprice.net/vm/Standard_NCC40ads_H100_v5; https://www.devzero.io/instances/azure/families/Standard_NCCads_H100_v5; https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nccadsh100v5-series |
| CacheWarp CVE | CVE-2023-20592 | CVE-2023-20592; CVSS 6.5 Medium; published USENIX Security 2024; AMD Security Bulletin amd-sb-3005; mitigations shipped via MilanPI 1.0.0.C | **CONFIRMED** | https://nvd.nist.gov/vuln/detail/CVE-2023-20592; https://www.amd.com/en/resources/product-security/bulletin/amd-sb-3005.html; https://www.usenix.org/system/files/usenixsecurity24-zhang-ruiyi.pdf |

**Net: all numbers verify.** The Ghost figure should be updated to $10.88M current ARR; the Lumo pricing is verified including the $9.99/mo annual discount; the Azure NCC H100 number is verified for the Windows East US 2 SKU and the report should clarify Linux-vs-Windows.

---

## (6) Other claims worth flagging

### 6.1 The "Apple PCC + Duck.ai + NEAR AI run attested LLM inference today" claim

**CONFIRMED with specifics:**
- **Apple PCC:** attestation transparency log of all production software; "Eyes-on with retention," "ZDR," and "ZOA — zero operator access" are now formal Google Cloud customer-data classifications; Apple's WWDC 2026 expansion puts PCC on NVIDIA Blackwell + Intel TDX + Google Titan, with attestation "rooted in at least two separate roots of trust from independent vendors"
- **Duck.ai / Tinfoil:** attestation architecture is well-documented; client SDKs verify on every connection; chain-of-attestation across router → inference enclave so no intermediate sees plaintext
- **NEAR AI Cloud:** OpenAI-compatible API, every response carries TDX + GPU attestation quote; `include_tls_fingerprint=true` parameter binds TLS to attestation

### 6.2 The "no major hosted AI companion offers verifiable proof operators cannot read" claim

**CONFIRMED** for the AI-companion category specifically (Replika, Character.AI, Kindroid, Nomi, Chub, Janitor, RisuAI, SillyTavern all lack verifiable TEE attestation). But the broader market has shipped verifiable TEE inference (PCC, Tinfoil/Duck.ai, NEAR AI, Privatemode, Fidaro, WhisperAI for storage) — so the "empty seat" conclusion in the competitor-landscape report is correct, but the framing should note that **the infrastructure gap is now narrow enough to productize**, not "5-10 years of platform work."

### 6.3 The "Achiyon as escrow" claim — outside this verifier's scope

Escrow is Achiyon's current trust artifact. This sweep did not verify the escrow cryptographic design — that is a separate technical audit. No verdict.

---

## Decision-impact summary (what should change in the parent's recommendation)

1. **TEE is now demonstrably production-ready for AI.** The architectural survey's "this is research, not shipping" framing is stale. Apple PCC at hyperscaler scale, Duck.ai/Tinfoil for consumer chat, NEAR AI Cloud for OpenAI-compatible inference, Fidaro / Privatemode for the roleplay-shaped use case — all live in 2026. The TEE decision should be reframed from "can it work" to "what is the build-vs-buy tradeoff vs Tinfoil/NEAR/Fidaro/Privatemode SDKs."
2. **The "no AI product ships true E2EE" claim is REFUTED.** Fidaro, Privatemode, WhisperAI (storage), Enigma AI (storage), Proton Lumo (storage), OxiHub/veil (in-process mode), Signal-bot-tee (demo), Tinfoil standalone (inference channel), Duck.ai via Tinfoil (inference channel), NEAR AI (inference channel) — all satisfy some strong-E2EE definition in 2026. Achiyon's position should be "we are not first, but we are the first to combine TEE attestation + persistent cross-session memory + roleplay UX + open-source self-hostable core + escrow trust artifact."
3. **EU Chat Control currently protects E2EE explicitly.** CSAR 1.0 / Regulation 2026/1881 Article 1(3) excludes E2EE from scope; the September-October 2026 trilogue is where the permanent text is settled, with Parliament's pro-E2EE position looking likely to prevail. This is materially better than the legal report's framing.
4. **"TEE loses safe harbour" is unsupported speculation.** The active-role jurisprudence (L'Oréal, YouTube/Cyando, WebGroup/Coyote) addresses algorithmic curation and operator knowledge, not technical-decryption-capability. Achiyon with TEE attestation + local-first option + client-side memory encryption is on the safe-harbour-friendly side of the spectrum.
5. **All cited numbers verify**, with two soft corrections: Ghost ARR has grown from $7.5M (2024) to ~$10.9M (July 2026), and Azure NCC H100 $8.82/hr is the Windows East US 2 SKU (Linux is $6.98/hr).
6. **Browser E2EE concerns are confirmed** — Safari 7-day ITP eviction, IndexedDB regression on iOS resume, cross-origin quota-init wipe, transaction-freeze on navigation. These are real engineering risks that push the perf/UX report's recommendation toward Tauri + OS keychain.

---

## Per-claim verdict table

| # | Claim | Verdict | Source(s) |
|---|---|---|---|
| 1.1 | CacheWarp is a real, published, SEV-SNP-affecting attack | **CONFIRMED** | USENIX Security 2024; AMD amd-sb-3005 |
| 1.2 | CacheWarp breaks SEV-SNP key material in practice | **CONFIRMED for RSA-CRT in Intel IPP** (90% SEV-ES, 28% SEV-SNP blind, full RSA key recovered in ~6-12 s); **caveated** by hypervisor-attacker threat model and AMD microcode patch | USENIX paper §6.1 |
| 1.3 | CVE-2023-20592 assigned; microcode patch shipped for Zen 3 Milan | **CONFIRMED** — MilanPI 1.0.0.C; no Zen 1/2 patch (no SEV-SNP) | NVD; amd-sb-3005 |
| 1.4 | Apple PCC runs attested LLM inference today | **CONFIRMED, expanded 2026 to Google Cloud** | security.apple.com/blog/expanding-pcc |
| 1.5 | Duck.ai / Tinfoil runs attested inference | **CONFIRMED** | duckduckgo.com/duckduckgo-help-pages/duckai/ai-chat-privacy; docs.tinfoil.sh |
| 1.6 | NEAR AI Cloud runs attested inference | **CONFIRMED** | cloud.near.ai; github.com/nearai/docs |
| 1.7 | Signal-bot-tee / sigstack experimental dual-attestation Signal→TDX→GPU TEE | **CONFIRMED** | github.com/RonTuretzky/signal-bot-tee |
| 2.1 | Safari 7-day ITP evicts non-installed PWA storage | **CONFIRMED** | github.com/kaya-go/kaya/issues/119 |
| 2.2 | iOS 17.4 IndexedDB regression on resume | **CONFIRMED** | bugs.webkit.org/show_bug.cgi?id=273827 |
| 2.3 | Safari can wipe IndexedDB for all origins (quota init bug) | **CONFIRMED** | github.com/WebKit/WebKit/pull/22635 |
| 2.4 | Perf numbers plausible mid-range, not cherry-picked | **CONFIRMED, mildly optimistic on Class L** | anchors in perf report |
| 3.1 | "No AI product has true E2EE" | **REFUTED** — multiple shipping products in 2026 | fidaro.ai; privatemode.ai; whisper-ai.link; enigmaai.app; proton.me/blog/lumo-security-model; github.com/OxiHub/veil |
| 4.1 | CSAR 1.0 = Regulation 2026/1881, excludes E2EE | **CONFIRMED** — stronger than legal survey implies (Art 1(3) + recital explicit) | withoutcensorship.com/chat-control-tracker; withoutcensorship.com/chat-control-two-laws-one-nickname |
| 4.2 | CSAR 2.0 in trilogue, 5 rounds failed | **CONFIRMED** — Irish presidency autumn 2026, Germany swing vote | withoutcensorship.com/chat-control-tracker |
| 4.3 | "TEE loses DSA safe harbour" | **UNVERIFIABLE / SPECULATIVE** — no CJEU precedent on TEE inference; WebGroup/Coyote (C-188/24, C-190/24, June 2026) is about algorithmic control, not decryption capability | ipkitten.blogspot.com; matheson.com |
| 5.1 | Bitwarden 15M users + 80k businesses | **CONFIRMED** | Bitwarden press release |
| 5.2 | Ghost $7.5M ARR | **CONFIRMED historical (2024); current is ~$10.88M ARR (July 2026)** | john.onolan.org/democratising-publishing; operatorbook.dev |
| 5.3 | Proton Lumo $12.99/mo | **CONFIRMED** — Plus tier; $9.99/mo annual | proton.me/lumo/pricing |
| 5.4 | Azure NCC H100 $8.82/hr | **CONFIRMED** — Windows East US 2 (Linux $6.98/hr) | cloudprice.net; learn.microsoft.com |
| 5.5 | CacheWarp CVE | **CONFIRMED** — CVE-2023-20592, CVSS 6.5 Medium, USENIX 2024 | NVD; amd-sb-3005 |
