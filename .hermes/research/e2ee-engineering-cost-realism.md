# E2EE Engineering Cost Realism — Achiyon / Achlys

**Compiled:** 2026-09-18
**Authored by:** subagent (hermes) for parent agent
**Question:** What is the actual build effort for (A) full client-side E2EE in a SvelteKit PWA backed by Rust/Axum/SurrealDB, versus (B) TEE-hosted confidential computing with attested inference? And what does the shared-Rust-crate toolchain reality look like?

**Grounding:**
- `/Storage/Git/spectacle/APP_SPEC.md` — the product spec (SvelteKit PWA, Rust/Axum server, shared `achlys-core` crate, Tauri 2 desktop/mobile shell)
- `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md` — surveyed shipping E2EE apps (Signal, WhatsApp, Standard Notes, Notesnook, Cryptomator, Anytype, Obsidian Sync, Matrix, Proton)
- `/Storage/Git/spectacle/.hermes/research/e2ee-browser-capability-survey.md` — browser-first E2EE capability survey (Bitwarden, Proton, Tuta, Notesnook, Local-first movement, BYOK/Lumo)
- `/Storage/Git/spectacle/.hermes/research/e2ee-business-model-survey.md` — open-source + paid privacy-hosting economics

---

## TL;DR

Both paths are **engineering-comparable in calendar time (3–6 months with a team of 2–3 senior Rust+TS engineers)** but differ radically in what they cost. **Path A** is dominated by WASM toolchain friction and re-platforming the prompt/lorebook/memory pipeline into the browser. **Path B** is dominated by attestation infrastructure and a one-time CC audit ($80–150K external). **For the roleplay-chat workload specifically, neither is sufficient — the right answer is hybrid A+B+C**: encrypted-on-the-wire client → either local inference (Tier 1) or attested remote inference with HPKE key release to a third-party LLM provider or TEE-hosted Achiyon operator (Tier 2/3). See Synthesis §6 below.

**Headline numbers** (one senior engineer, sequential; team of 2–3 in parallel cuts calendar ~50%):

| Path | Engineer-weeks | Cash cost | Calendar (solo) | Calendar (team 3) |
|---|---|---|---|---|
| **A — Client-side E2EE** | **26–38 wk** | ~$0 extra infra | 6–9 months | 3–4 months |
| **B — TEE / attested inference** | **28–44 wk** | **$80–150K external CC audit** + 25–40% higher cloud bill | 7–11 months | 4–5 months |
| **A+B hybrid (recommended)** | **34–50 wk** | audit cost of B + WASM cost of A | 8–12 months | 4–6 months |

---

## 1. Current Achiyon architecture (the thing we are costing the change against)

From `APP_SPEC.md`:

```
achlys-core/    ← shared crate: card parser, lorebook engine, prompt pipeline, macro engine, tokenizer
achlys-server/  ← Axum server binary (standalone or embedded)
achlys-app/     ← Tauri 2 shell (wraps Svelte SPA, optionally spawns embedded Axum)
achlys-web/     ← Svelte 5 PWA (the actual UI, loaded by browser/Tauri/phone)
```

**What runs server-side today** (and must move for E2EE):
- Prompt assembly pipeline (system + char desc + personality + scenario + greeting + world info + chat history) — server-side in `achlys-core` prompt layer module
- Lorebook gate evaluation + stateful activation (the "signature feature" — recursive scan, AND_ANY/AND_ALL/NOT_ANY/NOT_ALL, sticky/cooldown/delay, state-machine conditions, variable reads/writes)
- Dynamic character emergence (background agent extracts entities, auto-generates V2/V3 cards from narrative output)
- AI summarization (compress old messages into summaries)
- Tool calling execution (the agent loop: detect tool call → execute → resume generation)
- Context window management (sliding window, summarization trigger)
- Macro expansion (`{{char}}`, `{{user}}`, `{{time}}`, `{{getvar}}`, `{{setvar}}`, etc. — ST-compatible)

**What runs client-side today**: UI rendering, message input, settings, IndexedDB cache of decrypted messages for offline read (limited).

**Trust boundary today**: the Achiyon operator's Axum server sees every prompt and every response in plaintext. The product is a hosted SaaS AI roleplay chat; the operator is the LLM intermediary.

---

## 2. Path A — Full client-side E2EE

### 2.1 What this means concretely

Everything the server currently sees in plaintext has to either (a) move into the browser as encrypted client logic, (b) be replaced by a privacy-preserving server primitive, or (c) be deleted.

For Achiyon specifically (from the architecture survey §Synthesis #4), the options narrow because the AI inference is the value:
- **Option A1 — Pure E2EE with BYOK + browser-direct inference**: the user supplies their own LLM API key, the browser builds the prompt locally, encrypts to the LLM provider's public key, the Achiyon server never sees plaintext. This is Proton Lumo's architecture (verified shipped in browser). Achiyon server becomes a watermark/sequencer/queue and an opaque LLM relay.
- **Option A2 — Pure E2EE with local inference**: model runs on the user's GPU. The "server" is just a sync engine. Real E2EE; only works on desktop/laptop with strong GPUs (not phones).
- **Option A3 — Achiyon-hosted LLM with E2EE-via-key-release**: Achiyon server holds the inference engine, but encrypted prompts flow through. Requires either (i) encrypting to the LLM provider's public key if it's a third party (Proton Lumo style), or (ii) running inside a TEE (path B).

For a hosted product, **A1 (BYOK + browser-direct) is the cleanest and most-aligned with what the surveyed apps do.** A2 is opt-in for power users. A3 collapses into path B.

### 2.2 Phase-by-phase estimate

| # | Phase | Engineer-weeks | Notes |
|---|---|---|---|
| **A.1** | **Split `achlys-core` into pure-logic + adapters** | **3–4** | This is the hard prerequisite. Today's `achlys-core` is monolithic and assumes a tokio/sqlx server runtime. Split into `core-domain` (pure rules — card parser, lorebook gates, macro expansion, state machine, tokenizer) + `core-adapter-wasm` (browser glue: `#[cfg(target_arch = "wasm32")]`, js-sys bindings, IndexedDB persistence, WebCrypto key storage) + `core-adapter-server` (current tokio/sqlx stuff, refactored to call into core-domain). Requires careful `Cargo.toml` feature matrix; ~30-40% of the existing crate will need surgical edits to remove `async` boundaries, replace `tokio::sync::Mutex` with `std::sync::Mutex` or `parking_lot`, drop `reqwest`/`sqlx` imports from shared modules. This is the project's most expensive single risk (see §3 Risk #1). |
| **A.2** | **Vault-key crypto in browser** | **2–3** | Argon2id KDF via `argon2-wasm` (~Tuta's pattern — wrap reference C impl in WASM with thin glue) or use `argon2` crate compiled to `wasm32-unknown-unknown` (works since 2023; wasm-bindgen PR #4277 made `js-sys`/`web-sys`/`wasm-bindgen-futures` `no_std`-capable). Master key + per-device key + per-chat wrapping keys. WebCrypto `CryptoKey` non-exportable when possible, with PBKDF2/scrypt fallback for browsers without `extractable=false` support. Argon2id parameters need to be tuned per device tier (~250ms desktop, ~1s mobile) — interactive unlock UX matters a lot. |
| **A.3** | **Client-side prompt assembly** | **3–4** | Move the prompt pipeline from `achlys-core`'s server runtime into the browser. Render macro strings, evaluate lorebook gates (recursive scan, AND_ANY/AND_ALL, sticky/cooldown/delay), state machine conditions, character context injection. Uses the split `core-domain` from A.1. Token counting in WASM (re-use the existing tokenizer crate). Output is the final prompt string — encrypted before leaving the device. |
| **A.4** | **Client-side memory consolidation** | **2–3** | The summarization/extraction that today happens in a background agent on the server moves to the client. Two approaches: (a) call the LLM directly with the user's BYOK key from the browser (full E2EE; works with OpenAI/Anthropic/etc.), (b) do it locally in WASM with a small summarization model (heavier bundle, slower, but fully private). Recommend (a) with on-demand opt-in to keep bundle small. |
| **A.5** | **WASM memory consolidation from existing Rust crate** | **(included in A.4)** | The "memory consolidation" features (background agent, dynamic character emergence, state machine) become browser-side WASM modules calling the LLM directly. No new compilation work — uses A.1's split. |
| **A.6** | **Encrypted IndexedDB cache** | **2–3** | Wrap every existing IndexedDB read/write in AES-GCM with per-chat keys derived from the master key. Use `idb` crate or direct `idb-keyval`. Encrypt message bodies, lorebook entries, character cards, settings, all session state. Service worker holds the unlocked key in memory only — never serialized to disk. Handle eviction: Safari 7-day rule on non-installed PWAs; call `navigator.storage.persist()` on first unlock. |
| **A.7** | **SSE resume of encrypted streams** | **2–3** | This is the genuinely hard design problem. SSE connections drop in background tabs on mobile (~30-60s), on network change, on screen lock. Resuming requires (a) a `Last-Event-ID` mechanism on the server (current Axum SSE has this), (b) the **server holding session state it can replay from** — which conflicts with E2EE because the server never had the keys. **Resolution**: server buffers encrypted SSE chunks by `Last-Event-ID`; on resume, client supplies the resume offset; server replays the **same ciphertext** the original stream produced (deterministic re-encryption from the same input) — this requires the LLM provider (or local inference) to be re-callable with the same prompt, which works for stateless endpoints but not all. **Net: this is harder than it looks; expect ~3 weeks and a careful protocol design doc.** |
| **A.8** | **Multi-device sync of encrypted blobs** | **4–6** | Signal-style prekey bundle + Double Ratchet per device, or simpler CRDT (Yjs/Automerge) over the encrypted payload store. Server holds ciphertext + monotonic `lastSyncId` watermark (Linear's pattern). Each device has its own identity key + signed prekey + one-time prekeys (X3DH bootstrap). New-device-link flow does direct device-to-device encrypted history transfer (Signal 2021 multi-device rebuild pattern) — never via server. **This is a real engineering project, not a weekend hack.** Expect 4–6 weeks for a clean implementation including conflict resolution. |
| **A.9** | **Key recovery UX (escrow design)** | **1–2** | Users will lose passwords. Standard Notes "recovery code" pattern (a 24-word seed printed at vault creation, encrypted under the user's master key) + optional (a) recovery contact (one other device trusted to help unlock) or (b) Shamir secret sharing across N of M. Crucial for product UX; often skipped by engineers and then retrofitted painfully. |
| **A.10** | **BYOK LLM key storage + browser-direct calls** | **1–2** | API keys stored encrypted in IndexedDB (already in APP_SPEC §14). Browser uses `fetch()` directly to OpenAI/Anthropic/OpenRouter/local Ollama. No proxy. Mirrors Proton Lumo's pattern. |
| **A.11** | **Security audit + hardening** | **2–3** | Internal threat model writeup (STRIDE), dependency audit (`cargo-audit`, `cargo-deny`), penetration test (small-budget external: $40–80K, or in-house red team), bug-bounty program setup. Achlys is an AGPL-3.0 + CLA project — security budget is real cash, not just labor. |
| **A.12** | **Migration tooling + backwards compatibility** | **1–2** | Existing Achiyon users have unencrypted plaintext data in the server's DB. Migration path: one-time server-side "encrypt + zero-out" pass during login (server derives a per-user key from the user's new password, encrypts all data, deletes plaintext); user re-logs-in to bootstrap the new client. ~1-2 weeks if smooth, longer if schema changes are needed. |
| **A.13** | **Documentation + UX write-up** | **1–2** | Threat model page, "what we promise vs what we don't" page, key-recovery doc, multi-device pairing guide. The Proton model — clear public docs are part of the trust story. |
| | **TOTAL (sequential)** | **26–38 wk** | **6–9 months solo, 3–4 months with 2–3 senior engineers in parallel** |

### 2.3 Top-5 technical risks for Path A

1. **WASM bundle size + cold start.** `achlys-core` carries the lorebook state machine, tokenizer, macro engine, card parser. Compiled to `wasm32-unknown-unknown` with full optimization (`opt-level = "z"`, LTO, `wasm-opt -Oz`), expect ~1.5–3 MB initial bundle. This is acceptable on desktop but punishes first-paint on mobile (3G/4G warm cache helps, cold cache does not). **Mitigation**: code-split the prompt assembly into a lazy-loaded chunk (load lorebook engine only when user opens lorebook editor; load tokenizer only when token counter is visible). Bundle-stats tracking in CI (fail the build if `dist/*.wasm` > 2 MB).

2. **Argon2 unlock UX in browser.** Argon2id at safe parameters (t=3, m=64MB, p=4) takes ~250–500ms on a desktop, ~1–2s on a mid-range phone. iOS Lockdown Mode disables WASM entirely (Tuta's documented caveat). WebAuthn PRF extension can substitute for Argon2 entirely on supporting browsers (Touch ID / Windows Hello unlock → 32-byte PRF output → master key). **Mitigation**: WebAuthn PRF as primary path where available, Argon2 fallback; tunable parameters per device; cached unlock with 5-minute idle timeout before re-prompt.

3. **IndexedDB persistence + multi-device sync drift.** "Stick it in IndexedDB and call it a day" is wrong — sync needs a CRDT or an oplog with server-side ordering (Linear's pattern from the browser-capability survey §4.2). Multi-device-key-bundle distribution is a real cryptographic protocol with subtle bugs (Signal's 2021 multi-device rebuild was "a significant re-engineering of the key management layer underneath"). **Mitigation**: use an existing mature library (Yjs for CRDT document sync, libsignal-protocol-rust for Double Ratchet), not roll your own.

4. **SSE resume of encrypted streams.** Most browsers drop SSE in background tabs (Chrome ~60s, Safari ~30s, Firefox variable). Resuming requires server-side replay — which means either (a) the server held the plaintext to be able to replay (breaks E2EE), or (b) re-running inference with the same prompt and emitting identical ciphertext (only deterministic encryption + deterministic LLM output works; in practice, inference is non-deterministic, so this fails), or (c) holding ciphertext chunks server-side indexed by `Last-Event-ID` and replaying those (works, but the server now holds the ciphertext stream and can do timing/size analysis). **Mitigation**: option (c) is the realistic compromise; document the metadata-leak trade-off honestly. For real resumability across network drops, the browser should reconnect via WebSocket and request a continuation by chunk ID; the server replays encrypted chunks it cached.

5. **Client-side prompt assembly leaks via side channels.** Even with E2EE content encryption, the server sees message size, streaming cadence, request frequency, and timing. For an AI roleplay chat this leaks a lot: when the user is "in a scene" (high request frequency, longer messages) vs idle; which characters are being role-played (heuristics from token count and timing); what tools are being called (request size spikes). **Mitigation**: pad prompts to fixed token buckets, add random delay jitter, batch requests client-side. None of this fully hides behavior; it raises the cost of traffic analysis. Real users may not care; nation-state targets will. **Honesty**: this is a limitation, not a bug.

---

## 3. Path B — TEE / confidential computing path

### 3.1 What this means concretely

The server stays the LLM host, but inference runs inside a hardware-isolated Trust Domain (Intel TDX, AMD SEV-SNP, or NVIDIA H100 Confidential Compute). The Achiyon operator cannot read prompts or responses even with root on the host. The user's client verifies a remote attestation quote from the TD before sending any plaintext. Optionally, a **key-release service** (HPKE per RFC 9180) releases the inference key to the enclave only after verifying the attestation quote matches a published build provenance.

This is the **OpenGradient / Signal-bot-tee / Duck.ai (Tinfoil)** pattern. It is the right path when Achiyon wants to keep running a hosted LLM (own GPUs, own inference stack) without being able to read user data.

### 3.2 Phase-by-phase estimate

| # | Phase | Engineer-weeks | Notes |
|---|---|---|---|
| **B.1** | **Confidential VM deployment (Intel TDX or AMD SEV-SNP)** | **2–4** | First deployment is genuinely hard. As of 2026-09, Intel TDX is GA on Azure (DCesv6/ECedsv6 series in West US / West US 3), GA on VMware Cloud Foundation 9.1 (Sept 2026), and available on self-hosted 4th/5th Gen Xeon and Xeon 6 (Granite Rapids). AMD SEV-SNP is GA on AWS (EC2 M6a/R6a with SNP), GCP Confidential Space. **Real ops work**: PRMRR sizing, BIOS configuration, MKTME enabled, SEAM loader, kernel ≥6.11 for TDX guests, attestation registration with Intel IRS. Expect 2–4 weeks for first deployment including all the BIOS/firmware/NTP gotchas documented in the VCF walkthrough (Sept 2026). Cost: **confidential VMs are 20–40% more expensive per hour than equivalent standard VMs.** |
| **B.2** | **Attestation chain design (OHTTP + HPKE + key-release)** | **4–8** | The architectural hard part. Pattern (from OpenGradient): (1) user has a long-term identity key; (2) client computes an HPKE context to a key-release service (KRS) public key; (3) KRS verifies a TD quote from the Achiyon inference TD against a published build provenance (SLSA-L3 source attestation); (4) if the quote matches, KRS releases the per-session HPKE-wrapped inference key; (5) client unwraps, uses the key to encrypt prompts to the TD; (6) TD holds the key only in encrypted memory, decrypts inside the enclave, runs inference, re-encrypts response. OHTTP (RFC 9458) provides network-level anonymity (the KRS doesn't see the client's IP, the inference TD doesn't see who asked). **This is real systems-protocol work.** 4–8 weeks for a clean production implementation, longer if you do OHTTP too. |
| **B.3** | **Published build provenance (SLSA L3 + reproducible builds)** | **3–4** | Without this, the attestation proves only "some code is running in some TD" — not "the code Achiyon published is running." SLSA-L3 requires: hermetic builds, provenance generated by a trusted builder (e.g., GitHub Attestations, Sigstore Rekor), two-party review on builds, isolated build environments. Reproducible builds (so anyone can re-build and bit-compare the enclave image) is the gold standard but is **multi-month work for a non-trivial Rust codebase** (timestamps, build paths, compiler determinism issues). Recommend: SLSA-L3 first (3-4 weeks), reproducible builds as Phase 2. |
| **B.4** | **LLM inference inside TD** | **4–8** | Get your inference stack (vLLM, TGI, llama.cpp, or your own) running inside the TD. This is non-trivial — the inference server needs to be linked against `libtdx-attest` for quote generation, the model weights need to be loaded into enclave memory (which means the operator needs a TD-aware loader). NVIDIA H100 CC has the cleanest story (Hopper Confidential Compute), Azure TDX confidential VMs work but require AMX for AI acceleration. **4–8 weeks** to get a working end-to-end inference path; longer to make it production-grade (streaming, batching, multi-tenant). |
| **B.5** | **Intel Trust Authority or self-hosted DCAP integration** | **2–4** | Two choices: (a) Intel Trust Authority SaaS (subscription-based; quote verification logic runs inside Intel's TEE; clean, but vendor lock-in and recurring cost), (b) self-hosted DCAP (Data Center Attestation Primitives) with PCCS (Provisioning Certification Caching Service) — you run the quote verification yourself, integration with Intel's public API for platform certs. Self-hosted is more work but removes the SaaS dependency. 2–4 weeks either way. |
| **B.6** | **Attestation-verified client SDK** | **2–3** | The SvelteKit/PWA client needs to (1) on first connection, fetch the KRS public key from a pinned location; (2) initiate HPKE; (3) receive the TD quote and verify it locally (or trust the KRS to do so and just receive the released key); (4) handle quote expiry, key rotation, TD re-provisioning events. 2–3 weeks of careful work; verification logic must be auditable. |
| **B.7** | **IaC for cost control** | **1–2** | Confidential VMs are expensive; idle VMs burn money. CanaryBit Tower-style tooling wraps provisioning, attestation, teardown into reproducible Terraform/OpenTofu modules. Without this, costs spiral. 1–2 weeks if you use existing tools (CanaryBit Tower is Apache-2.0, free for Azure/AWS/GCP). |
| **B.8** | **Operator trust model documentation + no-training contracts** | **1–2** | Public threat model page (what TEE protects against, what it doesn't: Achiyon SREs, CI/CD pipeline, build dependencies), user-facing "what we promise" page, signed no-training-on-your-data contract with any upstream model provider. 1–2 weeks of writing + legal review. |
| **B.9** | **External Confidential Computing audit** | **4–8 wk + $80–150K cash** | NCC Group, Trail of Bits, or Leviantio. This is the expensive line item. CC audits are rarer than regular security audits, so auditor availability is limited and prices are higher. The audit covers: attestation flow, key-release service, build provenance, TCB analysis, side-channel review. **Budget 4–8 weeks of engineer-time to support the audit + $80–150K cash.** Without this, "we run in a TEE" is a claim, not evidence. |
| **B.10** | **CC ops training + runbooks** | **1–2** | Debugging inside a TD is harder (can't `strace`, can't `gdb`, can't read /proc). On-call engineers need new muscle memory. 1–2 weeks of training + runbook authoring; ongoing ops overhead. |
| | **TOTAL (sequential, ex. audit cash)** | **28–44 wk** | **7–11 months solo, 4–5 months with 2–3 senior engineers + a security/infra specialist in parallel** |
| | **TOTAL cash** | **$80–150K external audit + 25–40% higher cloud bill** | Confidential VM SKUs + Intel Trust Authority subscription (if used) + ongoing CC ops time |

### 3.3 Top-5 technical risks for Path B

1. **The "trust the operator" story has more holes than people admit.** TEE protects against the OS, hypervisor, and physical hardware attacker. It does **not** protect against: (a) a compromised Achiyon developer who adds a backdoor to the inference code before it's built into the TD image, (b) a compromised CI/CD pipeline that ships a poisoned image, (c) an Achiyon SRE with `tdxquote` access who can substitute a different image at boot, (d) the LLM provider's own logging/training policies, (e) side-channel attacks (cache-timing on shared cores, speculative execution). SLSA-L3 + reproducible builds + signed key-release service mitigate (a)-(c) but are themselves complex systems that can fail. **The honest pitch is "TEE + strong build provenance gives you cryptographic proof that *our code* ran unmodified on *Intel hardware*."** It is not "we cannot see your data."

2. **Attestation chain UX is awful.** Every client must verify a TD quote on every connection (or every quote-validity-period; quotes expire when the TD reboots or migrates). Cached quotes have a TTL. If Intel Trust Authority or the KRS is down, users see errors. Cross-cloud (Azure TDX vs AWS Nitro Enclaves vs GCP Confidential Space) requires **separate attestation verification paths** — the quote formats and certificate chains are incompatible. Mobile clients with flaky connectivity are particularly fragile. **Mitigation**: robust error UX, retry-with-backoff, fallback to a "verify-on-next-stable-connection" mode. Accept that some users will hit these errors.

3. **LLM inference inside TD has real performance + cost cost.** Intel TDX adds 3–10% overhead on 4th/5th Gen Xeon (per the OpenMetal 2026 evaluation); the overhead is concentrated in specific operations and higher on older hardware. Plus, **confidential VM SKUs are 20–40% more expensive per hour than equivalent standard VMs** (Azure DCesv6 vs Ddsv6, AWS M6a vs M6i, etc.). For a chat workload that's streaming many small tokens, this adds up. NVIDIA H100 CC is the cleanest performance story but the most expensive. **Mitigation**: benchmark on real workloads before committing; consider TDX for on-prem (cost = power + hardware) and H100 CC for cloud (cost = $/hr).

4. **The key-release service is a critical-path dependency.** If the KRS is down, no one can use the product. Needs to be HA (multi-region, active-active), rate-limited (abuse resistance), DDoS-protected, and continuously audited. The KRS holds **all session keys in plaintext transitively** (it releases them after verifying attestation; if breached, an attacker who can also produce a valid attestation can request any user's key). Operating a KRS is itself a significant ongoing ops burden. **Mitigation**: use a hardened minimal KRS (small Rust binary, no general-purpose compute), 2-of-3 quorum signing for releases, aggressive monitoring.

5. **The user threat model may not need TEE — and explaining why is hard.** Most roleplay users are not nation-state targets. They want "the company can't read my chats" — which **path A delivers**, more cheaply, with a simpler user-facing story ("your messages are encrypted on your device; only you have the key"). TEE delivers "even Achiyon engineers with root can't read your chats" — which is a strictly stronger promise but **sounds the same to a non-technical user**. The marketing burden of explaining "what's an enclave, why isn't this just Signal-style E2EE, what does attestation prove" is significant and ongoing. **Honest framing**: most users don't need TEE; the power users who do are a small fraction; building TEE to capture them is expensive. Consider whether path A + a clear "no-training, RAM-only, audit-logged" promise is a better ROI for the segment that cares.

---

## 4. Rust-WASM toolchain reality (relevant to Path A and the hybrid)

The Achiyon architecture (`achlys-core` shared between `achlys-server` and `achlys-app`) is the textbook case for the **isomorphic-Rust** pattern that Dioxus/Leptos document, and the textbook case for its costs.

### 4.1 What works cleanly

- **Pure data + business logic** (card parser, macro expansion, lorebook gate rules, tokenizer): these are CPU-bound, deterministic, have no I/O. They compile to `wasm32-unknown-unknown` with no changes. Just gate with `#[cfg(not(target_arch = "wasm32"))]` for any `std::fs`/`std::net` access.
- **Crypto primitives** (AES-GCM, ChaCha20-Poly1305, X25519, Ed25519, HKDF, BLAKE3): all available via `wasm-bindgen` and work in `no_std` on `wasm32-unknown-unknown`. The RustCrypto ecosystem is the canonical path.
- **Serialization** (serde + serde_json + postcard): works in WASM, including in `no_std`. Use postcard for binary (smaller payloads across the WASM/JS boundary) or JSON for debuggability.

### 4.2 What requires real work

- **Async + I/O**. `tokio` does not run in `wasm32-unknown-unknown` (no threads, no epoll). You need `wasm-bindgen-futures` + `gloo-net` (or direct `fetch`) + a JavaScript event loop. Any `async fn` in shared code must either (a) be `Send`-less and called via `wasm-bindgen-futures::spawn_local`, or (b) be `#[cfg]`'d out and replaced with a sync version. **Most async code in `achlys-core` is server-side (`tokio::sync::Mutex`, `reqwest`, `sqlx::query`) and must be moved into a server-only adapter crate.**
- **File system / persistent storage**. WASM has no FS. `std::fs` becomes IndexedDB via a wrapper. **Expect every `std::fs::read*` call in shared code to need an `#[cfg]` branch.**
- **Crypto-bound state via OS keychain**. WASM can't directly call macOS Keychain, Windows Credential Manager, or Linux Secret Service. WebCrypto's `extractable=false` is the closest equivalent (the key is held by the browser, not exportable to JS) but doesn't survive a browser uninstall. WebAuthn PRF is the substitute for "key in TPM/SE" — supports ~70% of users in 2026.
- **Bundle size + cold start**. A serious `achlys-core` compilation in WASM with `opt-level = "z"`, LTO, `wasm-opt -Oz`, will land at **1.5–3 MB** for the initial bundle. This is acceptable on desktop (cache helps), punishing on mobile (3G cold cache = 5-10s parse + compile). **Mitigation**: split into multiple WASM modules loaded lazily (prompt-canvas WASM, lorebook-editor WASM, character-extraction WASM). Vite/Rollup + `wasm-pack` makes this manageable.
- **Two test matrices**. CI must run `cargo test` (native), `wasm-pack test --headless --chrome` (browser), and the cross-target compatibility check (`cargo check --target wasm32-unknown-unknown`). Triple the test runtime; budget for it.
- **Two build pipelines**. Server binary: standard `cargo build --release`. WASM: `wasm-pack build --target web` (or `bundler`/`no-modules`), then `wasm-opt`, then bundle into the SvelteKit app via Vite. CI cache for both (cargo-chef for the server, wasm-bindgen's own cache for the WASM).

### 4.3 The feature-flag pattern (canonical)

The Dioxus "isomorphic Rust" post is the canonical reference pattern. The shape:

```toml
# achlys-core/Cargo.toml
[features]
default = []
server  = ["dep:tokio", "dep:sqlx", "dep:axum", "dep:reqwest", "dep:tracing"]
wasm    = ["dep:wasm-bindgen", "dep:wasm-bindgen-futures",
           "dep:web-sys", "dep:js-sys",
           "dep:console_error_panic_hook"]
```

Then in source:

```rust
#[cfg(feature = "server")]
use tokio::sync::Mutex;

#[cfg(feature = "wasm")]
use wasm_bindgen::prelude::*;

#[cfg(feature = "server")]
async fn load_lorebook(id: &str) -> Result<Lorebook, Error> { /* sqlx */ }

#[cfg(feature = "wasm")]
#[wasm_bindgen]
pub fn load_lorebook_sync(id: &str) -> Result<JsValue, JsError> { /* IndexedDB */ }
```

The Rust compiler enforces the split at link time. A `tokio::spawn` in shared code will not compile with the `wasm` feature. **This is the right pattern, but it requires that the shared crate's public API not assume async.** Expect to introduce sync versions of every async function used by the browser path.

### 4.4 What the SvelteKit app must restructure

1. **Add a "unlock" screen** before any chat data is loaded. WebAuthn PRF or password → Argon2id → master key → CryptoKey in memory. No data renders until unlock completes.
2. **Replace direct `fetch('/api/messages')` calls** with calls that go through an encrypted-blob layer: client decrypts before render, encrypts on send. The server sees only `{ciphertext, iv, lastSyncId}`.
3. **Move the prompt-assembly UI** from "send a request, get a response" to "compose locally, encrypt, stream-encrypt to LLM." The SvelteKit `+page.svelte` chat component needs new state for: unlock status, key fingerprint, sync watermark, streaming-decryption buffer.
4. **Add a service worker** for offline read of decrypted content + push notifications (Android works, iOS is fragile per the browser-capability survey §2.4).
5. **Restructure IndexedDB schema** to store encrypted blobs keyed by sync-watermark. Migration tooling for existing unencrypted data (one-time re-encrypt on next login).
6. **Bundle-split** the WASM modules (prompt-canvas, lorebook-editor, character-extraction agent) so the initial load is <500 KB WASM, with the heavy stuff lazy-loaded.
7. **Add threat-model + key-recovery UI** to onboarding (24-word recovery code, optional recovery contact, multi-device pairing via QR QR-code scan).
8. **Replace the chat background agent** (currently server-side) with a browser-side WASM module that calls the LLM directly with BYOK, or with a deferred background sync job that runs in a Web Worker.

---

## 5. Toolchain cost summary (Path A vs Path B)

| Concern | Path A (Client-side) | Path B (TEE) |
|---|---|---|
| **Shared crate split** | Required. ~3-4 wk. | Not required (server code unchanged). |
| **WASM toolchain** | Required. cargo-chef + wasm-pack + wasm-opt in CI. ~1 wk setup. | Not required. |
| **Bundle size discipline** | Required. CI gate on `dist/*.wasm` size. | N/A. |
| **External audit** | Standard security audit: $30–80K. | Confidential Computing audit: $80–150K. |
| **Cloud bill** | Server is dumb relay: lower cost. | Confidential VM SKU: +20–40% per hour. +Intel Trust Authority subscription. |
| **Ongoing ops** | Standard web ops. | CC ops: debugging inside TD, quote expiry handling, attestation infra monitoring. ~0.5 FTE ongoing. |
| **Time-to-market** | 3–4 months with a team of 3. | 4–5 months with a team of 3 + audit window. |
| **Marketing story** | "Your messages are encrypted on your device. Only you have the key." (Proton Lumo / Notesnook) | "Even Achiyon engineers can't read your chats. Verified by cryptographic attestation." (OpenGradient / Signal-bot-tee) |
| **Competitive position** | Crowded. Bitwarden, Notesnook, Proton, Tuta, Standard Notes all do this for notes; Lumo is the only chat E2EE. | Niche. OpenGradient, NEAR AI Cloud, Duck.ai are the only shipped examples. |
| **Long-term defensibility** | Medium. Commoditizing. | Medium-High. Hardware-rooted trust is harder to copy in software. |

---

## 6. Synthesis — the right answer is hybrid A+B+C, not either alone

From the architecture survey §Synthesis #4: Achiyon is structurally different from the surveyed E2EE apps because **the product IS the server computing over plaintext** (LLM inference, character memory consolidation, lorebook activation). Pure E2EE (path A) forces all of that into the browser; pure TEE (path B) keeps it server-side but adds enormous attestation overhead.

**The realistic deployment** that the surveyed apps support:

- **Tier 1 (default for desktop power users with GPUs):** pure client-side E2EE + local LLM inference (Ollama, LM Studio, vLLM on the user's box). Achiyon server is just a sync relay. This is **path A** scoped to "no remote inference." Trust boundary: only the user's machine.
- **Tier 2 (default for BYOK users):** client-side E2EE + direct-to-LLM-provider API calls from the browser (OpenAI, Anthropic, OpenRouter, etc.). The user's API key never touches Achiyon servers; prompts and responses are encrypted in transit. Achiyon server is a watermark/sequencer/queue. This is **path A + Proton Lumo pattern**. Trust boundary: only the LLM provider (and the user) sees plaintext.
- **Tier 3 (default for hosted users without their own GPU or API key):** TEE-hosted inference (path B). Achiyon runs the model inside an Intel TDX / H100 CC TD; the client verifies attestation before sending. Users who don't trust TEE are nudged to Tier 1 or 2. This is **path B + OpenGradient pattern**. Trust boundary: TDX hardware + build provenance + key-release service.
- **Tier 4 (explicit fallback, honestly labeled):** the current Achiyon model — operator can read prompts and responses. Sold as "convenient, no setup, RAM-only, no-training-on-your-data, audited, jurisdiction-choice." This is what most users actually want. Not E2EE in any technical sense.

**Recommended roadmap**: build **Tier 1 + 2 first (path A in 3-4 months with a team of 3)**, then **layer Tier 3 (path B in another 3-4 months) for users who want hosted inference without operator plaintext access**. Tier 4 stays as the default tier with clear "this is not E2EE" labeling — this is what Duck.ai, Enigma AI, and most privacy-aware vendors actually ship.

**Cash ask** (minimum viable):
- Path A only: $30–80K external audit.
- Path A + Path B: $30–80K security audit + $80–150K CC audit = **$110–230K**.
- Cloud bill uplift (Path B): +25–40% on the inference SKU; rough budget $500–2000/month for a small hosted user base, scaling linearly.

**Headcount** (minimum viable):
- 1 senior Rust engineer (shared crate, server, WASM)
- 1 senior TS/SvelteKit engineer (client crypto, IndexedDB, sync UI)
- 1 senior infra/security engineer (CC deployment, attestation, audit support) — only for Path B
- Optional: 0.5 product designer (UX for unlock, key recovery, multi-device pairing)

---

## 7. Sources

### Survey grounding (this analysis's input)
- `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md` — Signal, WhatsApp, Standard Notes, Notesnook, Cryptomator, Anytype, Obsidian, Matrix, Proton architecture; §Synthesis #4 (AI workload caveat)
- `/Storage/Git/spectacle/.hermes/research/e2ee-browser-capability-survey.md` — Bitwarden, Proton, Tuta, Notesnook browser-first E2EE; §3 BYOK; §4 Local-first movement; §2.4 iOS push caveats; §2.2 Argon2/WASM; §2.3 IndexedDB quotas
- `/Storage/Git/spectacle/.hermes/research/e2ee-business-model-survey.md` — Bitwarden/Vaultwarden split, Proton economics, Ghost/Plausible open-source+hosted model
- `/Storage/Git/spectacle/APP_SPEC.md` — current architecture and feature scope

### External references (toolchain + TEE reality)
- Paulo Suzart (Mar 2026), "True Isomorphic Rust: One Codebase for Server and Browser with Dioxus" — https://paulosuzart.github.io/blog/2026/03/03/dioxus-fullstack-cfg-feature-isomorphic-rust/
- Wild.codes, "When should Rust web stacks use WASM and how to share logic?" — https://wild.codes/candidate-toolkit-question/when-should-rust-web-stacks-use-wasm-and-how-to-share-logic
- OpenMetal, "Evaluating Intel TDX for Production Workloads in 2026" — https://openmetal.io/resources/blog/evaluating-intel-tdx-for-production-workloads-in-2026/
- CanaryBit, "How to deploy and attest Azure Intel TDX Confidential VMs in a glimpse" (2026) — https://www.canarybit.eu/how-to-deploy-and-attest-azure-intel-tdx-confidential-vms-in-a-glimpse/
- VMware Cloud Foundation Blog (Sept 2026), "Confidential Computing: Complete Setup Walkthrough - Intel TDX in VCF 9.1" — https://blogs.vmware.com/cloud-foundation/2026/09/15/confidential-computing-complete-setup-walkthrough-intel-tdx/
- Intel Developer, "Configure and Attest Confidential VMs in Kubernetes with Intel TDX" — https://www.intel.com/content/www/us/en/developer/articles/technical/configure-confidential-vms-kubevirt-intel-trustdom.html
- OpenGradient docs — "End-to-end encryption to an attested enclave" — https://docs.opengradient.ai/learn/onchain_inference/private_inference.html
- Proton blog, "Lumo security model" — https://proton.me/blog/lumo-security-model
- Signal blog, "Private contact discovery" + "Building faster ORAM" — https://signal.org/blog/private-contact-discovery/, https://signal.org/blog/building-faster-oram/
- Rust WASM working group, wasm-bindgen PR #4277 (no_std support) — https://github.com/rustwasm/wasm-bindgen/pull/4277
- wasmCloud, "Rust Language Guide for WebAssembly" — https://wasmcloud.com/docs/wash/developer-guide/language-support/rust/
- Tuta blog, "Argon2 / WASM" — https://tuta.com/blog/best-encryption-with-kdf
- RFC 9180 (HPKE), RFC 9458 (OHTTP), SLSA framework v1.0 — referenced for the key-release service pattern