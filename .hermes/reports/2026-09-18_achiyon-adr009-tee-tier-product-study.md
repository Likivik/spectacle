# ADR-009 `tee` tier — TEE / Confidential-Computing Product Lessons

**Compiled:** 2026-09-18
**For:** Achiyon ADR-009 maintainer — companion to `2026-09-18_achiyon-adr009-lessons-learned-verdict.md`
**Reads:** ADR-009 (`development-docs/adr/009-privacy-three-modes.md`) `tee` tier; the verdict above (which establishes the per-chat schema, monotonicity rule, and the `plain` default); `tee-confidential-deployment-survey.md` for SEV-SNP/TDX/Hopper-CC side-channel reality.
**Scope:** Six operator-side lessons from real products that shipped TEE/confidential-computing tiers, told plainly so the ADR can either match the pattern or document why Achiyon deliberately diverges. Each section ends with the *operator-side* lesson (build cost, attestation UX, deprecation risk) and the ADR-009 implication.

---

## 0. One-page headline

Across the studied set — Signal CDSi (SGX, 2017→2025+), Apple Private Cloud Compute (2024→), Duck.ai/Tinfoil (SEV-SNP, 2025→), Azure Confidential Inferencing (Intel TDX + NVIDIA H100 CC, 2024 preview), and the abandoned/deprecated set (Intel SGX client, Azure DCsv2, AKS Confidential Containers Kata-CC, Intel SGX DCsv2→ retirement 30 Jun 2026, Intel IAS end-of-support 2 Apr 2025) — the operator-side lessons are remarkably consistent:

1. **TEE silicon has a 5–7 year useful lifetime; vendor deprecation is a when, not an if.** Signal's SGX CDSi is now eight years old with three generations of broken-into side-channels (Plundervolt 2019 → ÆPIC 2022 → V12 Aug 2025, the latter extracting the Noise responder private key from a live attested enclave on Signal's actual Azure SKUs). Intel itself deprecated SGX-on-client in 2022; Azure retires DCsv2 on 30 Jun 2026; Intel retired the SGX Provisioning Certification Service API v2/v3 on 30 Apr 2026; AKS retires Kata-CC Confidential Containers node pools in Mar 2026. *Lesson:* any product whose `tee` tier is locked to one silicon SKU will be forced to migrate. ADR-009 must specify multi-CVM substrate and a content-key architecture that survives silicon loss.

2. **Attestation is *evidence*, not a *trust model*.** Every product that markets attestation to users is selling "verification theater" (Oasis coined the term; Apple / Tinfoil are the positive counter-example). Apple publishes a transparency log + virtual research environment + signed Apple Intelligence Reports; Tinfoil's SDK verifies the attestation on every connection and refuses to send data if it fails. The normies (Duck.ai, Azure standard OpenAI) just say "encrypted" or "confidential" without giving users anything to verify. *Lesson:* in ADR-009's `tee` tier the user-visible artifact must be either (a) a check-mark they can actually act on (a verifiable attestation receipt they could in principle re-verify), or (b) a plain honest label ("operator cannot read plaintext while this enclave is in active vendor support"). Anything in between is the Kindroid/Replika failure pattern.

3. **Enterprise-buyer vs consumer-user gap is real and is the regulatory fault line.** Microsoft ships Azure Confidential Inferencing in gated preview since 2025 — it works for an RBC-style enterprise with a procurement team, FedRAMP needs, and a 12-month Azure enterprise agreement. It does not work for a Discord user trying to verify their DM is private. VoltageGPU / Tinfoil / NEAR AI exist precisely to address the consumer-side gap with self-serve onboarding. *Lesson:* Achiyon's `tee` tier has to pick: consumer-side (self-serve, default-flagged-on-create, attestation-UX in the client) or enterprise-side (compliance documentation, audit trails, procurement-ready). The verdict above already picks consumer-side.

4. **Attestation UX is harder than attestation engineering.** Firebase's AI Logic attestation (App Check + DeviceCheck + Play Integrity + reCAPTCHA Enterprise + replay protection) is a five-layer stack — and Google's own docs admit "if you implement App Check in your app's codebase right away, then all your app versions can send valid App Check tokens" + "App Check needs to be enforced for all versions of your app" — i.e., the developer has to know they need it before they ever ship. *Lesson:* Achiyon's `tee` tier cannot rely on the developer (or the user) to set it up correctly; attestation must be invisible-correct in the default path or it will not be used.

5. **Promise-keeping risk on TEE tiers is severe and largely unpublicised.** The pattern is "product ships TEE-tier; vendor deprecates silicon; product quietly drops the tier or folds it into another feature; no public announcement." Signal's CDSi v1 repo literally carries a `# Deprecation notice — This version of the Contact Discovery Service has been retired and is no longer supported. Please see the CDSv2 repository.` Microsoft retired DCsv2 (announced years in advance, well done) but AKS's Kata-CC Confidential Containers is being sunset Mar 2026 with `customer nodepools will have the kata-cc-isolation runtime class removed` and the only migration paths are SEV-SNP CVM-backed ACI or Red Hat OpenShift Confidential Containers. Brave sunset its TEE-based E2EE video product in 2021. *Lesson:* ADR-009 must promise less than the tech supports, or it will fail to keep the promise within the 5-year window.

6. **The cryptographic pivot is happening already.** Signal's 2024 "Building a Faster ORAM Layer for Enclaves" blog is explicit: the *purpose* of the new Path-ORAM CDSi is "the backbone for a new era of contact discovery in Signal, one that will let users choose usernames that they could opt to share with people instead of their phone numbers" — i.e., the trust anchor is moving from TEE to phone-number-privacy via cryptographic protocols. The Hetz/Schneider USENIX 2024 "DISCO" paper replaces SGX with two-server PSI+OPRF+PIR, with <2 s online for 1024 contacts against a 2B+ database and 32× lower setup comms. *Lesson:* Achiyon's `tee` tier is on a 5–7 year half-life; the cryptographic-only alternative is improving on a 2-year half-life. The ADR must accept that `tee` will eventually be folded into `e2ee + hardware-roots-of-trust` (or simply into `e2ee`).

The TEE tier is a real, shippable tier in 2026 — but its promise is narrow ("attested non-disclosure against the cloud operator while the CVM CPU family is in active vendor support and the verifier is current") and its cost is non-trivial (multi-substrate portability, attestation-stack CVE monitoring, content-key architecture independent of the TEE, time-bounded UI). ADR-009 should ship it; should promise less than it can technically deliver; and should plan the migration to cryptographic-only on the same roadmap as Phase 1.

---

## 1. Signal Private Contact Discovery via SGX (2017→2025+)

### 1.1 What shipped

Signal shipped its **Private Contact Discovery Service (CDS / CDSi)** in 2017 using **Intel SGX** on Azure. The threat model was: Signal needs to tell a user which of their contacts are also Signal users, but Signal does *not* want to know the user's address book (the social-graph leakage that WhatsApp/Telegram were criticized for in Hagen et al. NDSS '21). The solution: run the entire contact-discovery database inside an SGX enclave; the host (Signal's own servers, run on Azure) cannot see the enclave's memory; clients verify the enclave's measurement via remote attestation; queries are encrypted end-to-end between client and enclave.

Signal layered **Oblivious RAM (ORAM)** on top of SGX to defend against access-pattern leakage (the SGX CPU sees *which* memory pages are touched, so a naive lookup would leak "the user's address book contains phone number X" by page access). The original CDS used linear scan over the full database with ORAM; the 2024 upgrade replaced this with **Path ORAM** (the same construction as Oblix/Snoopy, per Signal's blog), giving roughly 555,000× fewer memory accesses per query (from 1B reads for linear scan of 1B users to ~1800 reads with Path ORAM over a 2B-node tree).

The current production deployment is **`ContactDiscoveryService-Icelake`** (`signalapp/contactdiscoveryservice-icelake` on GitHub) — a Micronaut Java host-side service with SGX C code in the `c/` subdirectory. The original `ContactDiscoveryService` repo now carries a `# Deprecation notice` banner: "This version of the Contact Discovery Service has been retired and is no longer supported. Please see the CDSv2 repository."

The architectural pivot is explicit in Signal's 2024 blog: "Path ORAM is the backbone for a new era of contact discovery in Signal, one that will let users choose usernames that they could opt to share with people instead of their phone numbers… Phone number privacy which will offer new privacy controls around your phone number's visibility on Signal."

### 1.2 What failed

Three classes of serious vulnerability have hit CDSi on production hardware:

| Year | Vulnerability | Outcome |
|---|---|---|
| 2019 | **Plundervolt** (USENIX) — voltage-fault injection to flip enclave AES-NI results | Mitigated by Intel microcode updates |
| 2022 | **ÆPIC Leak** (USENIX) — "an attacker only needs one up-to-date system to extract secrets from an enclave (e.g., bypassing Signal private contact discovery, leaking DRM secrets or even SGX attestation keys)" | Architecture-level; not fully patched |
| 2025 (Aug) | **V12 Labs** (v12.sh/blog/signal) — two object-lifetime vulnerabilities on the *same Azure SGX SKUs Signal uses in production*. Stale write → arbitrary enclave memory read; client-handle bug → full register-context control. PoC extracts the 32-byte Noise responder private key from a live, attested enclave. | Signal fixed both; commits `df22988b` (one-worker-per-shard enforcement) and `b1c5ac44` (atomic canary+state merge). |

V12's PoC is devastating because it's the actual threat model that the attestation was supposed to prevent: the host now impersonates the enclave. The fix is good engineering, but the *category* of bug (use-after-free / TOCTOU in enclave-host interaction) keeps recurring.

### 1.3 The migration direction (2024–2026)

Signal is *not* leaving SGX. CDSi Icelake is still SGX as of Sep 2026. But the architectural direction is **crypto-only trust** (path-ORAM + PSI / PIR):

- **Hetz / Schneider USENIX 2024 — "Scaling Mobile Private Contact Discovery to Billions of Users"** (eprint.iacr.org/2023/758, "DISCO"). Two-server PSI + OPRF + PIR; <2 s online runtime for 1024 contacts against a 2B+ database; 32× lower setup communication than the prior state of the art. Already implemented and measured on smartphones.
- **TU Darmstadt thesis — "PSI Meets Signal"** (2022) integrates malicious-secure PSI into Signal for Android as an academic prototype.
- **Sonnino et al. — "Arke"** (arxiv) — first contact-discovery system with performance independent of database size, Byzantine-fault-tolerant, no single point of trust.
- **Signal's own July 2026 commits** — building support for accounts without phone numbers (paid "Signal Login"); separate backend handling; phone-number identity operations blocked on numberless accounts. This is the *consumer product* pivot away from phone-number-based contact discovery, which is exactly what makes phone-number-privacy viable (you no longer need to know whose phone number is in the address book).

The architectural takeaway is: **SGX is still in maintenance mode at Signal, but it is on the way out.** The next generation of contact discovery will not need an enclave.

### 1.4 Operator-side lesson (plain terms)

Building on Signal's experience, the operator-side lesson is:

> **Operating a TEE tier is a multi-year maintenance commitment against a moving target.** Signal has spent eight years keeping CDSi alive on SGX; three of those years included serious production-relevant vulnerabilities; the silicon itself (SGX on consumer PCs) was deprecated by Intel in 2022; and the architectural direction of the team's own roadmap has already moved on. A team betting its `tee` tier on a single silicon vendor must plan for a 5–7 year useful lifetime and a migration that is *more* work than the initial build.

**ADR-009 implication.** The `tee` tier's promise must be:
- *time-bounded* — "while the CVM CPU family is in active vendor support";
- *multi-substrate* — at least SEV-SNP (Azure DCasv5/v6, AWS m6a.2xlarge) AND TDX (Azure DCesv6) shipping side-by-side;
- *content-key independent of the TEE* — the per-chat content key is wrapped under the user's vault key (or equivalent PIN / OS-keychain key); the TEE holds a wrapped copy and only the attestation unlocks the wrapping. TEE gone → user can still decrypt with the vault key.

This is the pattern the verdict above already commits to (L2.3, L4.1). The Signal timeline validates it: the day Intel retires a CVM SKU, content is unreadable by anyone — Achiyon, the user, anyone — unless the architecture preserves the content key out-of-band.

---

## 2. Apple Private Cloud Compute (PCC)

### 2.1 What Apple published about attestation UX

PCC is the production AI inference tier Apple shipped in 2024 for Apple Intelligence requests. Apple's published model is **verifiable transparency** — five explicit requirements: (a) stateless processing of individual requests, (b) non-targetability of requests, (c) no privileged access for Apple employees, (d) enforceability of the guarantees in code (not just policy), and **(e) verifiable transparency** — security researchers must be able to verify the end-to-end security and privacy guarantees.

The attestation UX Apple actually built:
- **Append-only transparency log** — every production PCC software build is published to a cryptographically tamper-proof log. Software and leaf metadata is published within 90 days of inclusion in the log. Once signed in, it cannot be removed without detection (same log-backed Merkle structure as iMessage Contact Key Verification).
- **Public software images** — every production PCC build (OS, applications, executables) is published for independent binary inspection. PCC images include sepOS firmware and the iBoot bootloader in plaintext — a first for any Apple platform.
- **Virtual Research Environment (VRE)** — researchers can spin up a simulated PCC node on a Mac with Apple silicon; boot a version of PCC software; perform inference against demonstration models; modify and debug the PCC software. Tools include `pccvre release`, `pccvre transparency-log audit`, `pccvre transparency-log verify-inclusion`.
- **Apple Security Bounty** — PCC included in the Apple Security Bounty program; "especially significant payouts for any issues that undermine our privacy."
- **Apple Intelligence Report** (Settings → Privacy & Security → Apple Intelligence Report) — a user-facing artifact that exports a record of every request, including per-PCC-node attestations, Merkle inclusion proofs against the transparency log, and signed log heads.

The attestation UX is **opt-in for the user, default for the security researcher.** Most Apple Intelligence users will never look at their Apple Intelligence Report. But every PCC attestation that the user's device sends data to *cryptographically* proves it's in the log.

### 2.2 The "verification theater vs verification use" lesson

Apple's design is the *positive* counter-example to "verification theater." It works because:

1. **The attestation is enforced cryptographically by the client device.** The user's device *refuses to send data* to a PCC node whose attested measurement is not in the transparency log. The user does not have to *choose* to verify — the device does it on their behalf, in-band.
2. **The log is append-only and public.** Apple cannot retroactively modify a published build without detection. So the cryptographic commitment is meaningful.
3. **Researchers can actually inspect.** The VRE + Apple Security Bounty mean independent parties are incentivized and equipped to find bugs.

But note: **the user never sees attestation in a meaningful way.** They see "Apple Intelligence" as a feature; they may see "Privacy" in a settings panel; they will not see a check-mark that says "PCC verified, build 0xabcd… included in transparency log as leaf 0x1234…". The verification is *delegated to the device* and *delegated to security researchers*. The normie UX is: "Apple Intelligence is private."

This is a deliberate Apple choice and it works because:
- Apple's brand depends on privacy-as-default, and Apple is willing to publish the receipts.
- The cryptographic verification happens at the OS / Secure Enclave layer, where it cannot be bypassed.
- Apple's regulatory exposure is asymmetric: a published-bug is worse than a bug never found.

Compare to Tinfoil: the Tinfoil SDK verifies the attestation on every connection *and refuses to send data if verification fails*. The user *or developer* must explicitly use the SDK; direct REST skips verification. The verification is *opt-in for the integrator* but *mandatory at the SDK layer*. Same architectural pattern, different audience.

Compare to Duck.ai / Azure Confidential Inferencing / Firebase: there is no client-side attestation UX at all. Duck.ai says "Tinfoil… is processed in a Trusted Execution Environment such that Tinfoil cannot see your prompts or the model's response"; the user sees "zero provider visibility" as a label. Azure standard OpenAI says "your data is never shared with other customers or used to train our foundational models"; no client attestation at all. Firebase App Check is for *server* attestation of the *client* — the inverse direction.

### 2.3 Operator-side lesson

> **Attestation UX is a spectrum from "device-side cryptographic enforcement" (Apple) through "SDK opt-in" (Tinfoil) through "trust-us badge" (Duck.ai, Azure standard, Firebase).** The lower on the spectrum, the higher the marketing risk when a security researcher finds a problem. The higher on the spectrum, the more engineering investment required and the smaller the addressable audience (because normies don't run SDKs).

**ADR-009 implication.** Achiyon's `tee` tier should target the **"device-side cryptographic enforcement"** end of the spectrum — i.e., the client (Tauri / mobile) refuses to send `tee`-mode prompts to a CVM whose attestation does not chain to a verifier the operator maintains. This is the same architectural posture as Apple's. It is *expensive* to build — the Achiyon client needs an attestation verifier library for SEV-SNP and TDX, plus a transparency log of expected CVM measurements, plus a per-build measurement published alongside the build. But it is the *only* posture that survives a V12-style incident without becoming a press story.

The verdict above's L4.2 (multi-silicon, multi-cloud attestation diversity test) is the Achiyon-side implementation of this.

---

## 3. Duck.ai / Tinfoil — Attestation marketed to normies

### 3.1 What Tinfoil publishes (technical)

Tinfoil is a private-inference API running on AMD SEV-SNP CVMs (Ubuntu, with a Sigstore bundle from GitHub Actions that publishes enclave measurements). The Tinfoil SDKs (Python, JavaScript, Go, Rust, Swift) verify the attestation on every connection:

1. Fetch the hardware-signed attestation report from the enclave.
2. Verify the certificate chain back to AMD's root certificate.
3. Fetch the Sigstore bundle for the matching build.
4. Compare the attestation measurements to the Sigstore-published measurements.
5. Open a TLS session bound to the attested public key; refuse to send data if any check fails.

Tinfoil also commits to a cryptographic fingerprint of the model weights at build time, binds that fingerprint into the enclave's attestation, and enforces it at runtime so the enclave cannot read weights that don't match. The router enclave is attested as well — the model name → weights mapping is part of the attestation, so the router cannot silently substitute a different model. Web search (Exa) runs inside an enclave and uses a shared API key to create an anonymity set across all Tinfoil users.

### 3.2 What Duck.ai markets (normie UX)

DuckDuckGo's Duck.ai help page says:

> "Tinfoil has the added benefit of using a Trusted Execution Environment, so we are able to ensure, via technical means, that they are unable to read, retain, share, or train on your prompts, responses, or uploads."

> "Requests to Tinfoil (which hosts gpt-oss-120b and Gemma 4 31B on their servers) are anonymized and, additionally, are processed in a Trusted Execution Environment such that Tinfoil cannot see your prompts or the model's response. Chat models that support this (currently, gpt-oss-120b and Gemma 4 31B) are labeled 'zero provider visibility' in Duck.ai."

That label — "zero provider visibility" — is the entire attestation UX the user sees. No SDK download, no measurement check, no certificate chain. The user has to trust that (a) DuckDuckGo did the technical diligence and (b) Tinfoil did not lie to DuckDuckGo. There is no published evidence of *user confusion* — DuckDuckGo's documentation is careful about what "zero provider visibility" means (and what it doesn't: the third-party content-moderation provider sees images outside the encrypted channel).

### 3.3 What the operator-side lesson is

> **The normie UX for TEE is a label, not a check-mark.** Duck.ai's "zero provider visibility" is the only TEE claim the average user can act on. It is honest (DuckDuckGo publishes the limitations), it is concise, and it is the only thing the user can do anything with. A more elaborate attestation UX (per-build measurement, transparency-log check, etc.) is *only* used by the small fraction of users who would actually run an SDK — Tinfoil's developer audience.

**ADR-009 implication.** Achiyon's `tee` tier UI should ship a single label, with a tooltip that expands into the technical detail for users who want to drill in. The label must:
- Match theSHFT's "no misleading lock icon" pattern (the verdict's L2.1).
- Use the wording the precedent uses: "attested non-disclosure vs. cloud operator" or "zero provider visibility" (Duck.ai) or "verified enclave" (Tinfoil). Avoid generic "encrypted" / "secure" / "private" — those are the Kindroid/Replika failure.
- Be visible at all times the chat is open, not just on creation.

The technical attestation (multi-CVM verifier, transparency log of builds, monthly CVE digest) is engineering infrastructure that *backs up* the label — but the user sees the label, not the infrastructure. Build the infrastructure for the security researcher who finds the bug, not for the user.

---

## 4. Microsoft Azure Confidential Inferencing — enterprise vs consumer gap

### 4.1 What Microsoft shipped

Microsoft announced Azure Confidential Inferencing in 2024 and opened a gated preview in 2025. Architecture: AMD SEV-SNP + NVIDIA H100 Tensor Core GPUs in Confidential GPU VMs; Oblivious HTTP with Hybrid Public Key Encryption (HPKE) to protect user privacy; reference OHTTP proxy implementation; routed through Azure Front Door → load balancer → OHTTP gateway → Project Forge Kubernetes cluster → Confidential GPU VM.

The first model shipped was Azure OpenAI Service Whisper (speech-to-text). Microsoft's tech-community blog says:

> "Confidential inferencing is designed for enterprise and cloud native developers building AI applications that need to process sensitive or regulated data in the cloud that must remain encrypted, even while being processed. They also require the ability to remotely measure and audit the code that processes the data to ensure it only performs its expected function and nothing else."

> "Confidential inferencing is hosted in Confidential VMs with a hardened and fully attested TCB… our solution to this problem is to allow updates to the TCB at any point, as long as the update is made transparent first… every version we deploy is auditable… claims registered on the ledger will be digitally signed to ensure authenticity and accountability."

> "Confidential inferencing is a reaffirmation of Microsoft's commitment to the Secure Future Initiative and our Responsible AI principles."

### 4.2 The enterprise vs consumer gap

VoltageGPU's competitive write-up captures the gap precisely (May 2026):

> "Microsoft announced Azure Confidential Inferencing in 2024 and opened a gated preview in 2025. The architecture is right, the team is credible, and the market validation is welcome. As of May 2026 it is still preview on a narrow SKU set… The honest factual position as of May 2026 is that Azure Confidential Inferencing is still in gated preview. The feature was previewed publicly in 2025, capacity has been scarce, the application process is enterprise-gated, and the supported SKU and region footprint is narrower than the general Azure OpenAI fleet."

> "Standard Azure OpenAI Service — the product 95%+ of Azure OpenAI customers actually use today — runs on conventional Azure GPU infrastructure without TDX, without GPU CC, and without per-session attestation."

The architecture is the right answer for an RBC-style enterprise buyer: confidential VM, attested TCB, OHTTP for IP protection, auditable versions on a confidential ledger, Microsoft Azure Attestation (MAA) as the verifier. The shipping availability, however, is *enterprise-gated* — quota approval, region availability, application process. The normie Discord user is not the customer.

### 4.3 Operator-side lesson

> **Confidential-computing tiers built for enterprise buyers are a different product category from confidential-computing tiers built for consumer users.** The architecture (TEE attestation, OHTTP, transparency log) can be the same; the operational model is not. Enterprise: procurement-cycle, attestation stack as compliance artifact, audit trails per request, FedRAMP/ITAR/IRAP. Consumer: self-serve onboarding, default-flagged-on-create chat mode, attestation-UX in the client app, monthly billing.

**ADR-009 implication.** Achiyon is building a consumer product (an AI character-chat tool with a personal-vault option). The `tee` tier should be modeled on the consumer pattern (Apple PCC + Tinfoil + Duck.ai), not on the enterprise pattern (Azure). The verdict above's L2.2 / L3.1 already picks this.

If Achiyon ever wants to sell to enterprise buyers (banks, hospitals), the `tee` tier will need a separate *enterprise attestation artifact* (the Microsoft MAA / Azure Confidential Ledger equivalent) — but that is a Phase 4+ consideration, not Phase 1.

---

## 5. Firebase / Google's GenAI attestation examples — developer-facing complexity

### 5.1 What Firebase App Check for AI Logic actually requires

Firebase AI Logic is the client-side SDK for Gemini (GA at Google I/O 2026). The recommended security stack for production has **four layers** plus a fifth (Firestore Security Rules + Firebase Auth + output handling):

1. **Proxy architecture** — Gemini API key lives on Firebase's infrastructure, never transmitted to the client.
2. **Template-Only Mode** — Firebase AI Logic only executes prompts stored on the server; arbitrary prompts sent from client code are ignored. (Enforced starting I/O 2026.)
3. **Firebase App Check + Replay Protection** — device attestation (Play Integrity on Android, DeviceCheck / App Attest on iOS, reCAPTCHA Enterprise on web) generates cryptographic tokens proving a request came from a genuine, unmodified instance of the app. Single-use tokens via replay protection (shipped May 2026).
4. **Model Armor** — guardrails layer between Firebase AI Logic and Gemini API. Inspects prompt and response. GA at Cloud Next 2026.

Firebase's own docs warn:

> "When setting up App Check, consider adding replay protection, which makes App Check tokens one-time-use only. This option offers enhanced protection beyond the baseline protection and lets you set an appropriate level of protection for your app and use cases."

> "Starting in early July 2026, during the guided setup workflow in the Firebase console, Firebase automatically enforces Firebase App Check for Firebase AI Logic to help protect the Gemini API."

> "If you implement App Check in your app's codebase right away, then all your app versions can send valid App Check tokens. A request that doesn't send a valid token is considered unverified and will be blocked when App Check is enforced."

> "Implement a production attestation provider in your app as soon as possible."

> "For local development, you can set up the App Check debug provider and still keep App Check enforced for Firebase AI Logic."

The implication is clear: **the developer has to set this up correctly before they ever ship, or they will block all their users.** Firebase's docs are explicit that "it is critical to enforce App Check as early as possible."

### 5.2 What the developer-facing complexity actually looks like

A developer reading the Firebase docs has to know:
- That App Check exists (it's not in the quickstart).
- That App Attest / Play Integrity / reCAPTCHA Enterprise are the production attestation providers.
- That they need to register their apps with those providers.
- That they need to enable replay protection (a separate Firebase console toggle).
- That Template-Only Mode blocks all direct prompts from client code (so their existing prompt-in-client-code pattern must be migrated to server-stored templates).
- That Model Armor is a separate Google Cloud console configuration.

The developer is *also* the operator — for Firebase, "the developer" is the Achiyon-equivalent of "the user of our SDK." If the developer gets it wrong, the user's app stops working.

### 5.3 Operator-side lesson

> **Attestation infrastructure designed to be opt-in for the developer is opt-in for failure.** Firebase's docs are honest about this — "if you implement App Check in your app's codebase right away" — but the result is a category of app-store rejection, broken-in-production, and "users see 403 PERMISSION_DENIED" support tickets. Attestation UX must be invisible-correct in the default path.

**ADR-009 implication.** Achiyon's `tee` tier must not require the user (or the developer, if Achiyon ships an SDK) to:
- Register an app with a third-party attestation provider.
- Toggle a "production attestation" mode separately from "debug."
- Generate or store any cryptographic key for the attestation chain.

The user's Tauri / mobile client must do all of this in the default code path. The build that ships to a real user must already have the attestation verifier integrated, the CVM measurements registered, the transparency-log check wired up. The dev experience for `tee` must be one toggle (or no toggle at all — just "create a `tee` chat" and the client handles the rest).

---

## 6. Products that PROMISED TEE tiers and quietly dropped them

The promise-keeping risk is real and under-documented. The known cases:

### 6.1 Intel SGX on client PCs

Intel **deprecated SGX on consumer desktop CPUs in 2022** (withdrawn from 11th-gen Core and later; only a handful of 11th-gen chips ever shipped with SGX). Any consumer product that shipped SGX-on-client between 2015 and 2021 was forced to migrate, drop, or fold the SGX feature into something else. Examples that quietly dropped or never shipped: multiple DRM schemes, several wallet products (BitL0, before pivoting), some password-manager local-vault designs.

### 6.2 Azure DCsv2 (Intel SGX)

Microsoft **retires DCsv2-series on 30 Jun 2026**, with migration to DCdsv3 (the next-generation SGX), or to DCasv5/DCadsv5/ECasv5/ECadsv5 (SEV-SNP-backed CVMs, lift-and-shift), or to DCasv6/ECasv6 / DC/ECesv6 (currently in preview). Customers who bet on DCsv2 have 6 months to migrate. The migration is not always straightforward: DCdsv3 does not support Intel SGX Attestation Service using Intel EPID (IAS), which Intel EOL'd on **2 Apr 2025**. Any product that did EPID-based attestation on DCsv2 has to migrate to ECDSA-based attestation on DCdsv3 as part of the same migration.

### 6.3 AKS Confidential Containers (Kata-CC, AMD SEV-SNP)

Microsoft's GitHub retirement notice for `[Retirement] Confidential Containers`:

> "The Confidential Containers preview is slated to sunset in March 2026. This feature has been available in preview since 2023… After March 2026, AKS will remove the runtimeclass. In turn, customer nodepools will have the kata-cc-isolation runtime class removed from their nodepools."

> "Customers can continue to use the Kata-CC functionality if they have an existing cluster with Kata-CC functionality that persists by creating a custom runtime class that targets the kata-cc handler, but the usage of this VM SKU will be entirely unsupported."

The migration paths offered are: Confidential Containers on ACI (C-ACI), Azure RedHat OpenShift Confidential Containers (preview), or Confidential VMs on AKS (which has different isolation properties — per-VM rather than per-container). Any product that deployed Kata-CC for per-container TEE isolation has to either pivot to ACI (which is a different SKU model) or accept that their isolation granularity is now per-VM. This is a *security property* change, not just an infrastructure change.

### 6.4 Intel SGX Provisioning Certification Service (PCS) API v2/v3

Intel announced EOL of PCS API versions 2 and 3 originally for 31 Oct 2025, then extended to **30 Apr 2026**. Customers consuming the deprecated versions were required to migrate to API v4. The Intel team also updated the TCB recovery / Attestation guidance and policies in the six months leading up to EOL. The implication for any SGX-based product: your attestation stack has to migrate alongside the Intel API changes, even if you never touch your enclave code.

### 6.5 Confidential-containers `enclave-cc` sub-project (SGX-based process isolation)

The `confidential-containers/enclave-cc` project was deprecated in October 2025 (`# RFC: deprecate and archive enclave-cc`) because "the enclave-cc sub-project has not created a release for about a year now and is bit-rotten to the point that taking it back 'live' would require a lot of work." The migration path was: "users looking to run containers using process based isolation are best to use libOS 'installers' and customized containers which work with vanilla runc and containerd/cri-o." Any product that relied on `enclave-cc` for process-based SGX isolation has to migrate to a libOS approach (e.g., Gramine) or to a VM-based isolation.

### 6.6 Brave Together (E2EE video calls via TEE, sunset 2021)

Brave sunset its E2EE video-call product (Brave Together) in January 2021, citing low adoption and per-call setup friction, pivoting to Brave Leo AI chat instead. Not strictly a TEE product (Brave Together used a Double Ratchet-style protocol, not attested enclaves), but in the same family of "secure communications tier" that quietly gets dropped when adoption doesn't justify the maintenance cost.

### 6.7 Signal encrypted SMS/MMS

Signal's encrypted-SMS feature was deprecated in 2020–2022 across multiple releases, citing low adoption and migration friction. Not strictly TEE-based but in the same pattern of "shipping a secure tier; observing adoption collapse; quietly retiring it."

### 6.8 Operator-side lesson

> **TEE tiers get deprecated silently more often than they get deprecated loudly.** The Signal CDS v1 repo's `# Deprecation notice` is the rare case where deprecation is explicit in the README. The Intel SGX-on-client, AKS Kata-CC, Intel PCS, Intel IAS, and Azure DCsv2 deprecations are *announced* but easy to miss in vendor release-note noise. The Brave Together / Signal encrypted-SMS retirements are pure quiet. **A product whose `tee` tier is locked to a single silicon vendor or attestation stack will be forced to migrate or fold within 5–7 years; the migration is more work than the original build; and the deprecation is rarely announced with a banner the user will see.**

**ADR-009 implication.** The verdict's L4.1 — "the `tee` tier's long-term promise is in the *crypto envelope*, not the silicon" — is the answer to this. Specifically:

- **The TEE is a compute envelope, not a key custodian.** Per-chat content keys are wrapped under the user's vault key; the CVM holds a wrapped copy. TEE deprecation → user can still recover with the vault key.
- **Multi-substrate attestation verifier code is portable; the attestation stack itself is not.** Achiyon must keep an attestation verifier for SEV-SNP and TDX (and ideally Hopper CC / Blackwell CC) that does not depend on Azure-specific or AWS-specific primitives. This is the same architectural move Microsoft recommends ("confidential computing on multiple substrates") but at a smaller scale.
- **The `tee` mode is documented with a sunset clause.** The UI label for `tee` mode should read "attested non-disclosure vs. cloud operator while this enclave is in active vendor support" — the explicit time-bounding is what protects Achiyon from the deprecation event becoming a press story.
- **A migration path to `e2ee + hardware-roots-of-trust` is planned.** When `tee` deprecates, the migration is monotonic re-keying (not a system rewrite) because `encryption_mode` is enum-additive.

This is the *promise-keeping risk* lesson, plain: a TEE tier is a 5-year commitment, not a 5-year product.

---

## 7. Consolidated operator-side lessons (plain) → ADR-009 amendments

| Operator-side lesson | Source | ADR-009 amendment |
|---|---|---|
| TEE silicon has a 5–7 year useful lifetime; vendor deprecation is a when, not an if. | Signal CDSi 2017→2025; Azure DCsv2 retirement 30 Jun 2026; AKS Kata-CC sunset Mar 2026; Intel IAS EOL 2 Apr 2025; Intel PCS v2/v3 EOL 30 Apr 2026; Intel SGX client deprecation 2022. | **L4.1** — the `tee` tier's long-term promise is in the crypto envelope, not the silicon. Per-chat content key wrapped under user-key; TEE holds a wrapped copy. Multi-substrate attestation verifier. |
| Attestation is evidence, not a trust model. "Verification theater" vs Apple PCC's device-side cryptographic enforcement. | Oasis's coinage of "verification theater"; Apple PCC's transparency log + VRE + Apple Intelligence Report; Tinfoil's SDK-side verification; Duck.ai's "zero provider visibility" label; Firebase's multi-layer attestation stack. | **L2.1** + **L4.3** — UI label is honest (no "encrypted" / "secure" badge on `plain`); the technical attestation is built device-side and refuses to send on verification failure; CVE digest is monthly. |
| Enterprise-buyer vs consumer-user gap is real. | Microsoft Azure Confidential Inferencing preview (gated, enterprise procurement); VoltageGPU self-serve; Tinfoil SDK opt-in; Duck.ai consumer-friendly label. | **L2.2 + L3.1** — `tee` is default-flagged-on-create, not opt-in. Consumer pattern, not enterprise pattern. Phase 4+ enterprise attestation artifact is a separate workstream. |
| Attestation UX is harder than attestation engineering. | Firebase App Check: five-layer stack, four providers, replay-protection toggle, "implement in your app's codebase right away" warning. | **UX1** — the `tee` mode requires zero developer / user setup. Attestation verifier ships in the client by default; the user sees a single label, not a stack of toggles. |
| Promise-keeping risk on TEE tiers is severe and largely unpublicised. | Signal CDS v1 deprecation notice; Intel SGX client deprecation; AKS Kata-CC; Brave Together sunset 2021; Signal encrypted-SMS deprecated 2020–2022. | **L4.4** — `tee` mode is documented with a sunset clause; migration path to `e2ee + hardware-roots-of-trust` is on the roadmap. The `encryption_mode` enum is additive so re-keying is monotonic, not a system rewrite. |
| The cryptographic pivot is happening already. | Signal's 2024 Path-ORAM blog; Hetz/Schneider USENIX 2024 "DISCO" (<2 s for 1024 contacts against 2B+ database, 32× lower setup); TU Darmstadt PSI-Meets-Signal; Sonnino's Arke (database-size-independent). | **L4.4** + **L2.5** — content moderation is per-mode (not account-wide); the `tee` tier is positioned as a *current* privacy envelope while the cryptographic-only alternative matures. |

---

## 8. Single-line verdict

**Achiyon's `tee` tier is a real, shippable tier in 2026 — but its promise must be narrower than the technology supports ("attested non-disclosure vs. cloud operator while the CVM CPU family is in active vendor support and the verifier is current"), its cost is non-trivial (multi-substrate portability, attestation-stack CVE monitoring, content-key architecture independent of the TEE, time-bounded UI), and its half-life is 5–7 years.** The amendments in the verdict above (L2.3, L4.1, L4.2, L4.3, L4.4) capture the operator-side lessons from every shipped and every deprecated TEE product in 2024–2026.

---

## 9. Sources read for this study

### Primary sources (Sep 2026)

- **Signal Private Contact Discovery**: `signal.org/blog/private-contact-discovery/` (2017 SGX launch with ORAM); `signal.org/blog/building-faster-oram/` (2024 Path-ORAM upgrade, explicit phone-number-privacy framing); `github.com/signalapp/ContactDiscoveryService` (deprecation notice, CDSv2 link); `github.com/signalapp/contactdiscoveryservice-icelake` (current production CDSi, Micronaut Java + SGX C code).
- **V12 Labs**: `v12.sh/blog/signal` "Compromising Signal's Contact Discovery Enclave" (Aug 2025) — two object-lifetime vulnerabilities on Signal's Azure SGX SKUs, extracted 32-byte Noise responder private key from live attested enclave. Fix commits `df22988b` (one-worker-per-shard enforcement) and `b1c5ac44` (atomic canary+state merge).
- **Signal phone-number-pivot**: `webpronews.com/signals-quiet-push-to-break-its-phone-number-rule/` (July 2026, server-commits supporting numberless accounts; Signal Login paid option discussed at FUTO Don’t Be Evil conference March 2026 by CTO Ehren Kret).
- **Hetz / Schneider USENIX 2024 "DISCO"**: `eprint.iacr.org/2023/758.pdf` "Scaling Mobile Private Contact Discovery to Billions of Users" — two-server PSI+OPRF+PIR, <2 s online runtime for 1024 contacts against 2B+ database, 32× lower setup communication, sublinear in database size.
- **TU Darmstadt PSI Meets Signal**: `tubiblio.ulb.tu-darmstadt.de/107592` — integrates malicious-secure PSI into Signal for Android.
- **Sonnino et al. "Arke"**: `sonnino.com/papers/arke.pdf` — database-size-independent contact discovery with Byzantine-fault-tolerance.

### Apple Private Cloud Compute

- `security.apple.com/documentation/private-cloud-compute/verifiabletransparency` — five requirements, transparency log, software-image publishing.
- `security.apple.com/blog/private-cloud-compute/` — announcement blog; iBoot + sepOS in plaintext for the first time.
- `security.apple.com/documentation/private-cloud-compute/inspectingreleases` — VRE tools (`pccvre release`, `transparency-log audit`, `transparency-log verify-inclusion`).
- `security.apple.com/blog/pcc-security-research/` — Apple Security Bounty expansion to PCC; third-party auditors given early access.
- `dev.to/nagayu/i-verified-apples-private-cloud-compute-from-my-own-device-export-2hm3` — third-party `pcc-verify` tool: cross-references Apple Intelligence Report against live transparency log; verifies inclusion proof, signature, measurement binding, freshness, log consistency. Honest about what it does and does not prove.

### Tinfoil / DuckDuckGo

- `tinfoil.sh/security-and-privacy-faq` — TEE processing of prompts, completions, files; Sigstore bundle; model-weight fingerprinting; router-enclave attestation chaining; web-search enclave (Exa) anonymity set.
- `tinfoil.sh/inference` — production inference with attestation, OpenAI-API-compatible.
- `docs.tinfoil.sh/verification/attestation-architecture` — OVMF firmware, Ubuntu AMD SEV-SNP kernel, dm-verity on read-only weight volumes, TLS key binding + Encrypted HTTP Body Protocol (EHBP) for browsers.
- `docs.tinfoil.sh/verification/verification-in-tinfoil` — Sigstore integration; GitHub Actions build → immutable transparency log; certificate-transparency logs for audit-time verification; TLS+HPKE keypair bound to attestation report.
- `duckduckgo.com/duckduckgo-help-pages/duckai/ai-chat-privacy` — Tinfoil "zero provider visibility" label; anonymization via metadata-stripping before model-provider relay; image/files sent outside encrypted channel for content moderation.

### Microsoft Azure Confidential Inferencing

- `techcommunity.microsoft.com/blog/azure-ai-foundry-blog/azure-ai-confidential-inferencing-preview/4248181` — preview announcement; Whisper first; OHTTP + HPKE; Project Forge Kubernetes cluster.
- `techcommunity.microsoft.com/blog/azureconfidentialcomputingblog/azure-ai-confidential-inferencing-technical-deep-dive/4253150` — technical deep-dive; AMD SEV-SNP + NVIDIA H100 Confidential Compute; auditable claims on confidential ledger; "allow updates to the TCB at any point, as long as the update is made transparent first"; confidential ledger for accountability.
- `learn.microsoft.com/en-us/azure/confidential-computing/confidential-ai` — confidential inferencing, training, RAG use cases.
- `voltagegpu.com/compare/voltagegpu-vs-azure-openai` — competitive analysis (May 2026) of Azure Confidential Inferencing preview status, SKU/region scarcity, enterprise-gated application, vs VoltageGPU GA on open-weight models. "Standard Azure OpenAI Service — the product 95%+ of Azure OpenAI customers actually use today — runs on conventional Azure GPU infrastructure without TDX, without GPU CC, and without per-session attestation."
- `learn.microsoft.com/en-us/azure/virtual-machines/sizes/lifecycle/retirement/dcsv2-series-retirement` — DCsv2 retirement 30 Jun 2026; migration to DCdsv3 (Intel SGX) or to DCasv5/DCadsv5/ECasv5/ECadsv5 (SEV-SNP CVMs) or DCasv6/ECasv6 (preview). "Intel SGX Attestation Service Utilizing Intel EPID (IAS)… Intel announced IAS end of support on April 2, 2025."
- `learn.microsoft.com/en-us/azure/confidential-computing/virtual-machine-solutions-sgx` — Intel SGX VM SKU list; Generation 2 image requirement; Availability Sets only (no zone-redundancy).
- `learn.microsoft.com/en-us/azure/aks/confidential-containers-overview` — Confidential Containers on AKS (Kata-CC); Azure Linux 2.0 retirement Nov 2025; node images removed 31 Mar 2026.
- `github.com/Azure/AKS/issues/3781` — `[Retirement] Confidential Containers` — "After March 2026, AKS will remove the runtimeclass… customer nodepools will have the kata-cc-isolation runtime class removed."

### Firebase / Google GenAI attestation

- `firebase.google.com/docs/ai-logic/app-check` — App Check + replay protection; attestation providers (App Attest, DeviceCheck, Play Integrity, reCAPTCHA Enterprise); "implement a production attestation provider in your app as soon as possible"; "Starting in early July 2026, during the guided setup workflow in the Firebase console, Firebase automatically enforces Firebase App Check for Firebase AI Logic."
- `firebase.google.com/docs/ai-logic/security-checklist` — security checklist; layered defense-in-depth.
- `dev.to/nimra_abid_8180c39fb998b6/firebase-ai-logic-is-on-the-client-here-are-the-4-security-layers-that-keep-it-safe-b5n` — four-layer walkthrough: proxy, Template-Only Mode, App Check + replay protection, Model Armor.

### Deprecation evidence

- `github.com/confidential-containers/confidential-containers/issues/315` — `RFC: deprecate and archive enclave-cc`; bit-rotten, containerd v1.6.x POC not maintained; v0.16.0 / v0.17.0 / v0.18.0 release-notes progression; archive plan.
- `github.com/confidential-containers/enclave-cc/pull/516` — "Announce proposed deprecation" merged Oct 2025.
- `github.com/intel/confidential-computing.tee.dcap.pccs/issues/48` — Intel PCS API v2/v3 EOL originally 31 Oct 2025, extended to **30 Apr 2026**; required migration to API v4.

### Verification-theater evidence (operator-side analysis)

- `dev.to/savvysid/verification-theater-vs-real-trust-why-attestation-alone-isnt-enough-for-tee-based-systems-4l34` — coinage / framing of "verification theater"; missing dimensions (freshness, state continuity, operator identity, code provenance, future security).
- `oasisrose.garden/attestation-is-not-enough/` — Oasis's BFT-attestation-verifier-network proposal (continuous verification, slashing, on-chain policy).
- `cryptozalt.com/why-trust-in-tees-means-more-than-just-hardware-proof/` — same point: raw attestation ≠ real trust.
