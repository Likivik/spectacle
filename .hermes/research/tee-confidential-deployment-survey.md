# TEE Deployment Survey — Running Rust/Axum + SurrealDB Inside AMD SEV-SNP / Intel TDX Confidential VMs (2025/2026)

**Compiled:** 2026-09-18 (for Achiyon — self-hostable AI roleplay app, Rust/Axum + SurrealDB backend, NixOS)
**Purpose:** Concrete feasibility, SKUs, pricing, attestation choices, side-channel caveats, OHTTP+HPKE prompt-relay pattern, and a monthly cost model for 100–1000 users.
**Builds on:** `e2ee-app-architecture-survey.md`, `e2ee-business-model-survey.md`.

---

## TL;DR

1. **TEE deployment is operationally mature in 2025/2026** on all three clouds. SEV-SNP is on Azure, GCP, and AWS (m6a/c6a/r6a); TDX is on Azure (DCesv6) and GCP (C3); H100 confidential compute (Hopper CC) is GA only on Azure (NCCadsH100v5) — AWS does *not* enable SEV-SNP on P5, GCP does not yet have a H100 confidential VM SKU.
2. **A TEE does not change SurrealDB or Axum compatibility at all.** SurrealDB is plain Linux/x86-64; runs unchanged inside a CVM. Axum runs unchanged. The only "TEE-aware" code is the attestation verifier — typically 100–500 lines of Rust.
3. **No CPU-TEE side channel is closed.** Coherency / cache / ciphertext side channels (Heracles, CacheWarp, Cohere+Reload, Reload+Reload) on SEV-SNP, and analogous issues on TDX, are *active research areas*. These are the cost of running on untrusted cloud infrastructure — TEE does not give you "as good as a rack in your office," it gives you "dramatically better than a non-confidential VM."
4. **The honest architectural choice for Achiyon** is to treat the TEE as a *stronger envelope* around the existing operator-trusted model (Tier 4 in the earlier survey), not as a path to Signal-grade E2EE for prompts. The OHTTP+HPKE relay pattern is a real, IETF-standard, production-deployed (Apple Private Cloud Compute, Cloudflare Privacy Gateway) way to *additionally* hide client IP from the inference endpoint; this composes with the TEE to hide plaintext from the cloud operator.
5. **Cost for 100–1000 users: ~$420–$1,200/month on Azure SEV-SNP, ~$310–$1,000/month on AWS c6a, ~$600–$1,300/month on GCP TDX, plus GPU inference if local models are wanted: ~$2,500–$6,500/month on Azure NCC H100.** Detailed breakdown in §10.

---

## 1. Why even run in a TEE? Honest framing for Achiyon

The earlier `e2ee-app-architecture-survey.md` concluded that **Signal-grade E2EE for prompts is structurally incompatible with operator-side LLM inference**. The honest options were Tier 1–4. A TEE **does not change that conclusion**, but it changes the *content* of Tier 4 (and partially Tier 2):

- **Tier 4 (current Achiyon model, honestly labeled) + TEE:** "We run inside a hardware-attested TEE. The cloud operator cannot read plaintext — even with root on the host. We cannot claim E2EE on the prompts themselves (the TEE still has to read them to do inference), but we can claim *attested non-disclosure* — you can verify what code is running inside the CVM, and the cloud operator cannot bypass it." This is materially stronger than "we pinky-promise we don't log." It is the same envelope Signal uses for private contact discovery, and DuckDuckGo uses for Tinfoil-backed models.
- **Tier 1 (encrypted-to-third-party-LLM) + TEE:** user encrypts to LLM-provider key; Achiyon CVM is a routing/relay that cannot read the prompt. Trust moves to LLM provider. TEE makes this composable: even if the Achiyon operator wanted to MITM, they can't.
- **Tier 2 (in-TEE local LLM) + TEE:** the LLM runs inside a SEV-SNP + Hopper CC H100 CVM. Both prompt and inference are confidential to the operator and to AMD/NVIDIA as far as the published threat model extends. This is the OxiHub/veil + Signal-bot-tee pattern, raised to GA cloud primitives.

The key consumer-facing claim a TEE unlocks: **"the cloud operator can prove to a third-party auditor that they cannot see your prompts"** — not "we encrypted your prompts with a key only you hold" (Signal-grade E2EE is impossible without local-only inference or trusted third-party LLM).

---

## 2. Cloud SKU matrix and exact pricing (2025/2026, USD, pay-as-you-go, Linux)

### 2.1 Azure — most SKUs, most mature confidential-GPU story

| Family | TEE | Generation | vCPU | Mem | $/hr East US (PAYG) | $/mo (730h) | Notes |
|---|---|---|---|---|---|---|---|
| **DCasv5** (Milan) | SEV-SNP | 3rd-gen EPYC | 2–96 | 8–384 GiB | $0.086 → $4.128 | $63 → $3,013 | No local temp disk; "no local" variant = `DCasv5`, with local = `DCadsv5`. |
| **DC8as_v5** | SEV-SNP | Milan | 8 | 32 GiB | **$0.3440** | **$251.12** | Sweet spot for small Axum API + SurrealDB. |
| **DC16as_v5** | SEV-SNP | Milan | 16 | 64 GiB | **~$0.688** | **~$502** | Doubles memory, fine for modest SurrealDB. |
| **DCasv6** (Genoa) | SEV-SNP | 4th-gen EPYC 9004 | 2–96 | 8–384 GiB | TBD (~5–10% above v5 in most regions) | — | Genoa, Intel-AMX; slightly newer. |
| **DCesv5** (older TDX gen) | Intel TDX | older Sapphire | 2–96 | 8–384 GiB | comparable to DCasv5 | — | Older TDX; superseded by DCesv6. |
| **DCesv6** | Intel TDX | 5th-gen Xeon (Emerald Rapids) | 2–128 | 8–512 GiB | $0.101 → $2.064 | $74 → $1,507 | **Linux pay-as-you-go East US: DC2es_v6 $0.101/hr, DC8es_v6 $0.403/hr, DC32es_v6 $1.613/hr**. Intel AMX. |
| **DC8es_v6** | Intel TDX | Emerald Rapids | 8 | 32 GiB | **$0.4030** | **$294.19** | Sweet-spot TDX SKU. |
| **ECasv5 / ECesv6** | SNP / TDX | as above | 2–128 | memory-optimized | — | — | For SurrealDB-heavy workloads. |
| **NCC40ads_H100_v5** | **SEV-SNP + NVIDIA H100 (94 GB)** | Genoa + Hopper | 40 | 320 GiB | **$8.82/hr East US 2** | **~$6,439** | Confidential GPU. Only generally-available cloud SKU pairing TEE with H100 in 2026. |

**Azure extras worth knowing:**
- The first-party attestation service (**Microsoft Azure Attestation / MAA**) is **free** as of 2025/2026 — it is part of the Azure substrate, billed at $0.
- Confidential VMs incur a small "VMGS disk" (virtual machine guest state, a few MB) which has a minor monthly storage fee.
- Full-disk encryption with **Azure Key Vault Managed HSM** is a separate billable resource (FIPS 140-2 Level 3) — typically ~$1/hour HSM pool + per-key $1/month.
- Reserved Instances: 1-year ~20% off; 3-year ~40% off; Spot ~75–80% off for DCasv5 (interruption-prone — only for stateless tiers).

### 2.2 AWS — cheapest confidential VMs; GPU path is *not* confidential

| Family | TEE | Generation | vCPU | Mem | $/hr us-east-1 (PAYG, Linux) | $/mo | Notes |
|---|---|---|---|---|---|---|---|
| **m6a.large** | SEV-SNP | Milan | 2 | 8 GiB | **$0.0765** | **$55.85** | Base m6a + 10% SNP surcharge already baked into AWS's listed on-demand. |
| **m6a.xlarge** | SEV-SNP | Milan | 4 | 16 GiB | **$0.1530** | **$111.69** | |
| **m6a.2xlarge** | SEV-SNP | Milan | 8 | 32 GiB | **$0.3060** | **$223.38** | Sweet spot for small Axum + SurrealDB. |
| **c6a.large** | SEV-SNP | Milan | 2 | 4 GiB | **$0.0765** | **$55.85** | |
| **c6a.xlarge** | SEV-SNP | Milan | 4 | 8 GiB | **$0.1530** | **$111.69** | Compute-optimized. |
| **c6a.2xlarge** | SEV-SNP | Milan | 8 | 16 GiB | **$0.3060** | **$223.38** | |
| **r6a.large** | SEV-SNP | Milan | 2 | 16 GiB | **$0.1008** | **$73.58** | Memory-optimized. |

**The AWS SEV-SNP surcharge is +10% on the on-demand rate** — already applied in the prices above. Reserved Instances and Savings Plans apply to the base rate; the +10% SNP surcharge is *not* discount-eligible in some interpretations (verify per region).

**AWS — no confidential GPU.** `p5.48xlarge` (H100) and `p5e.48xlarge` (H200) **do not** enable SEV-SNP. Confirmed in nvtrust Issue #65 (NVIDIA maintainer): *"AWS doesn't enable the AMD SEV-SNP feature for [P5], which means P5 instance is not a CVM."* AWS's GPU confidential story is therefore: **Nitro Enclaves (CPU-only, no GPU passthrough) + TPM-based Instance Attestation (CPU-only, attestation only, no hardware memory encryption)**. Achiyon should **not** plan on AWS for confidential-GPU local inference.

**AWS Nitro Enclaves pricing:** **$0** — there are no additional charges for using Nitro Enclaves. You pay standard EC2 + standard KMS/ACM. (Confirmed in Nitro Enclaves FAQ and user guide.) The attestation PKI root cert is published; you verify attestation documents yourself or have AWS KMS verify them via PCR-bound policies.

### 2.3 GCP — cleanest pricing model; N2D SNP or C3 TDX, no GPU confidential yet

GCP charges Confidential VM as a **flat per-vCPU + per-GB surcharge on top of Compute Engine** — not as a separate SKU with embedded markup. This makes cost forecasting clean.

| Tech | Machine series | vCPU ($/hr) | Mem ($/GiB/hr) | Notes |
|---|---|---|---|---|
| **AMD SEV** (legacy, weaker) | N2D, C2D, C3D, C4D | $0.005479 | $0.0007342 | Live migration supported. |
| **AMD SEV-SNP** | **N2D** (Milan) | **$0.0027502** | **$0.0003686** | True SEV-SNP. Live migration *not* supported on SNP. |
| **Intel TDX** | **C3** (Sapphire Rapids) | **$0.0033982** | **$0.0004555** | Released GA in 2024–2025. |

**Computed examples (on-demand, Linux, us-central1, 730h/month):**

| SKU | vCPU | Mem | Compute hr | CVM surcharge | Monthly total |
|---|---|---|---|---|---|
| n2d-standard-4 + SNP | 4 | 16 GiB | $0.1923/hr | $0.0168/hr | ~$152/mo |
| n2d-standard-8 + SNP | 8 | 32 GiB | $0.3845/hr | $0.0336/hr | ~$305/mo |
| c3-standard-8 + TDX | 8 | 32 GiB | ~$0.42/hr | $0.0417/hr | ~$337/mo |
| n2d-highmem-16 + SNP | 16 | 128 GiB | ~$0.97/hr | $0.091/hr | ~$774/mo |

**GCP — confidential GPU: not yet.** `a3-highgpu-1g` (1×H100) supports Intel TDX on the host as of GA, but **GPU CC mode is not enabled by default on GCP H100 SKUs** (NVIDIA Hopper CC requires host CPU TEE + BIOS-CC-mode + SPDM attestation; GCP does not currently expose a "confidential H100" SKU). GCP's Confidential Spaces (preview, 2025) integrates with Intel Trust Authority for TDX-only attestation, no GPU TEE.

### 2.4 Side-by-side for the same shape: 8 vCPU / 32 GiB, pay-as-you-go, Linux, lowest-cost region

| Cloud | SKU | TEE | $/hr | $/mo |
|---|---|---|---|---|
| AWS | m6a.2xlarge | SEV-SNP (Milan) | $0.3060 | **$223.38** |
| Azure | DC8as_v5 | SEV-SNP (Milan) | $0.3440 | **$251.12** |
| GCP | n2d-standard-8 + SNP surcharge | SEV-SNP (Milan) | $0.4181 | **$305.22** |
| Azure | DC8es_v6 | TDX (Emerald Rapids) | $0.4030 | **$294.19** |
| GCP | c3-standard-8 + TDX surcharge | TDX (Sapphire Rapids) | $0.4617 | **$337.04** |

**Conclusion:** **AWS SEV-SNP is the cheapest by ~10–25%**. Azure is in the middle with the broadest SKU selection (especially the only GA confidential-H100 path). GCP charges cleanly per resource but is the most expensive of the three.

---

## 3. Attestation services (free on every cloud, important practical differences)

### 3.1 Azure — Microsoft Azure Attestation (MAA)
- **Free.** Billed at $0 — it is a substrate service.
- Validates SEV-SNP and TDX attestation reports; issues JWTs with claims the verifier checks.
- For SEV-SNP, attestation is *opaque-to-the-user* during boot — Azure's host fabric performs it. For deeper attestation, Azure Confidential VM Guest Attestation is available for in-guest, post-boot verification.
- For Intel TDX, full in-guest attestation similar to AMD is "coming soon" per docs; Intel Trust Authority is supported as the operator-independent verifier today.
- Integrates with Azure Key Vault / Managed HSM for release-of-secrets-after-attestation (you tell AKV "only release the key if the CVM has measurements X, Y, Z").

### 3.2 AWS Nitro Enclaves attestation
- **Free.** Nitro Enclaves itself has no surcharge; KMS calls are billed per standard KMS pricing ($0.03 per 10k requests for KMS cryptographic operations; attestation-document verification is free because the PCR check happens inside KMS via policies).
- Two flows:
  - **Nitro Enclaves attestation document** (CBOR+COSE-signed by Nitro Hypervisor; root cert published). Enclave can prove PCRs + parent instance ID + attached IAM role ARN.
  - **NitroTPM / EC2 Instance Attestation** (newer, 2025): TPM-based attested instance boot, including GPU instances. Doesn't give you CVM memory encryption but does give you a hardware-rooted signed-boot chain.
- For SEV-SNP on m6a/c6a/r6a, attestation reports come from the AMD PSP directly (`/dev/sev-guest`); AWS doesn't provide a managed "SEV-SNP attestation service" comparable to MAA. You verify the ARK→ASK→VCEK chain yourself using the AMD KDS.

### 3.3 Intel Trust Authority (ITA, formerly Project Amber)
- **Free for Azure/GCP/IBM Cloud customers.** General availability as of 2024. Optional paid support tier.
- Operator-independent attestation for Intel TDX + Intel GPU TEE. Issues OIDC-compliant attestation tokens usable for key-release decisions. Supports GCP Confidential Spaces (private preview).
- "Faithful Verification" feature: lets you audit every attestation token ITA issues for transparency.

### 3.4 AMD KDS + self-hosted verifier (for SEV-SNP)
- The AMD Key Distribution Service (`kdsintf.amd.com`) serves the ARK/ASK/VCEK certificate chain. It's free.
- You can run your own verifier: the `sev` / `VirTEE/sev` Rust crate provides SEV-SNP report parsing + verification; the `tenzro_tee::amd_sev_snp` crate provides both real hardware and simulation modes; AMD's docs include sample code using `openssl` + VirTEE/sev.
- This is the only attestation verifier that needs no cloud trust assumption — but it does trust the AMD root keys.

### 3.5 Recommended pattern for Achiyon
**Defense in depth: MAA / ITA + AMD KDS verifier.** The first-party cloud attestation service tells you "this is genuine AMD/Intel hardware running in this Azure/AWS/GCP region." The AMD/Intel root-of-trust verification tells you "this is genuine AMD/Intel hardware, period." Combining both lets you detect a compromised or malicious cloud control plane.

---

## 4. OHTTP + HPKE prompt-relay pattern (the production-deployed "hide-from-Achiyon" piece)

### 4.1 What the pattern actually does
OHTTP (RFC 9458, Jan 2024) + HPKE (RFC 9180) is the IETF-standardized split of trust between a **relay** (sees client IP, sees only ciphertext) and a **gateway** (sees request content, sees only the relay's IP). The protocol is:
1. Client fetches `application/ohttp-keys` from the gateway (HPKE public key + supported algorithms).
2. Client generates an ephemeral HPKE context, encapsulates the binary HTTP request, sends `message/ohttp-req` to the relay.
3. Relay forwards the opaque body to the gateway, stripping client IP / cookies / auth headers.
4. Gateway decapsulates, processes the inner request, encapsulates the response with the same HPKE context, returns `message/ohttp-res`.
5. Relay forwards; client decapsulates with the original context.

### 4.2 Production deployments that exist today
- **Apple Private Cloud Compute (PCC)**: OHTTP relays operated by an independent third party; AI requests from Apple Intelligence flow through them. Apple processes the AI request without knowing which device sent it.
- **Meta**: WhatsApp message summarization uses OHTTP to a third-party relay, hiding requester IP from Meta's AI infrastructure.
- **Cloudflare Privacy Gateway** (closed beta): Cloudflare operates the relay; you operate the gateway.

### 4.3 Open-source implementations for self-hosting
- **`cloudflare/privacy-gateway-server-go`** — Go reference gateway (production-ready enough for low traffic; closed beta on relay side).
- **`thibmeu/ohttp-gateway` + `thibmeu/ohttp-relay`** — Edge-platform OHTTP gateway + relay (Cloudflare Workers, Vercel Edge, Netlify Edge, Railway Node).
- **`cloudflare/privacy-gateway-relay`** — Cloudflare Worker OHTTP relay reference.

The whole stack is small (~hundreds of lines). The harder engineering is:
- Choosing a relay operator *independent* of the gateway operator (if Achiyon runs the gateway, the relay must be Cloudflare or another party).
- Handling request chunking for large prompts (draft `chunked-ohttp` adds per-chunk AEAD, draft-ietf-ohai-chunked-ohttp-08).

### 4.4 Composes with TEE
- **OHTP gateway inside a TEE**: even if the OHTTP relay sees that Achiyon is the destination, the prompt is only readable inside the CVM, which the cloud operator cannot introspect.
- **OHTTP relay hosted on a third party** (Cloudflare / another OHTTP relay operator): the cloud operator doesn't even see "this IP sent Achiyon a prompt at this time."
- **End result**: the strongest realistic privacy you can ship to a non-self-hosting user in 2026 is *client encrypts to LLM provider's public key* → *OHTTP relay strips IP* → *OHTTP gateway inside SEV-SNP CVM* → *prompt decrypted, inference done, ciphertext response returned*. Three-party trust split (user / Achiyon CVM / LLM provider), with no single party holding all the metadata.

### 4.5 For Achiyon specifically
The cheapest deployable pattern:
1. **Client** (Tauri desktop + native mobile): HPKE encrypts to Achiyon's CVM-published public key, fetched from `/.well-known/ohttp-gateway`.
2. **Relay**: `cloudflare/privacy-gateway-relay` on Cloudflare Workers, configured to forward to Achiyon's gateway. (Or Achiyon runs its own relay on a different cloud — e.g., AWS — and the gateway on GCP TDX, so no single operator sees both halves.)
3. **Gateway**: an Axum endpoint inside the SEV-SNP CVM, with HPKE-decapsulation middleware. Inner request is then a normal HTTPS request to the Axum app.

This is a meaningful engineering project but not exotic — RFCs are stable, reference implementations exist, and it composes with everything else in this report.

---

## 5. Confidential GPU H100 / Blackwell — local-model inference in a TEE

### 5.1 What "confidential GPU" actually means (Hopper CC)
- The H100 has an on-die hardware root-of-trust (the first NVIDIA GPU to have one).
- "CC-On" mode (configurable via host): command buffers and CUDA kernels are encrypted+authenticated before crossing PCIe; data staging happens via encrypted bounce buffers; GPU performance counters are disabled (preventing many side channels); HBM encryption via per-GPU keys fused into the die.
- **CC requires a host CPU TEE**: AMD SEV-SNP (Milan / Genoa / Turin) or Intel TDX (Sapphire / Emerald Rapids, in early access on Intel).
- **CC requires attestation**: GPU device identity certificate signed by NVIDIA CA, plus a GPU attestation report verifiable via NVIDIA Remote Attestation Service (NRAS) — or local verifier for air-gapped.
- Performance overhead: published numbers show ~1.4% for TensorRT-LLM on Llama 70B float8 (15,200 → 14,980 tokens/sec). Compute-bound workloads near-zero; I/O-bound workloads higher.

### 5.2 Cloud availability (only Azure has it as a managed SKU)

| Cloud | GPU SKU | CC mode | Status |
|---|---|---|---|
| **Azure** | NCC40ads_H100_v5 (40 vCPU Genoa + 1× H100 94 GB) | **Yes** (AMD SEV-SNP host + Hopper CC) | **GA**. $8.82/hr East US 2. Only generally-available cloud SKU pairing TEE with H100 in 2026. |
| AWS | p5.48xlarge (8×H100), p5e.48xlarge (8×H200) | **No.** SEV-SNP not enabled. Nitro Enclaves don't support GPU passthrough. | Use NitroTPM Instance Attestation (CPU attestation only) if you want boot-integrity for GPU nodes. |
| GCP | a3-highgpu-1g (1×H100), a3-highgpu-8g (8×H100) | **No.** Intel TDX host supported but GPU CC mode not exposed. | Confidential Spaces (preview) is TDX-only. |
| VoltageGPU / Lambda / smaller GPU clouds | H100, H200 | Some (VoltageGPU TDX @ $2.77/hr; Lambda Labs bare-metal; varies) | Verify per provider. Not subject to BAA from hyperscaler. |

### 5.3 Blackwell status (early 2026)
- **Blackwell B200 / GB200**: NVIDIA's deployment guide explicitly lists Blackwell as supported in CC mode ("Confidential Compute (single or multi-GPU) mode"). It needs the same CPU TEE host (Genoa/Turin or Granite Rapids). At GA time of this report (Sep 2026), no hyperscaler has shipped a Blackwell confidential SKU; expect this to land at Azure first as a follow-on NCC series.

### 5.4 Practical for Achiyon
- **For 100–1000 users on a hosted roleplay product**, local inference in a TEE at $6,400/mo for one Azure H100 is *not cost-competitive* with calling OpenAI/Anthropic/MiniMax APIs (≈ $0.50–$3 per 1M tokens). The TEE inference makes sense only if: (a) user data is so sensitive that the regulatory/compliance story requires it (HIPAA, EU AI Act tier-1), or (b) the product is selling privacy as a premium feature, or (c) you are building the proof-of-concept for "Tier 1 with our own model" that the e2ee-app-architecture survey flagged as open.
- **For pure tier-2/3/4 deployments (operator trusted, no TEE inference)**, the TEE's job is to **protect user data at rest and in transit while the API runs** — which is what `DCasv5`/`m6a.2xlarge` give you for $223–$251/mo.

---

## 6. Side-channel classes still open on CPU TEEs

This is the part cloud vendors don't put on the front page. **No CPU TEE is a fortress.** The published academic literature as of 2025/2026 shows ongoing, often unauthenticated-or-patch-deferred attacks on both AMD SEV-SNP and Intel TDX. Naming them concretely:

### 6.1 AMD SEV-SNP — open attack classes

| Attack | Class | Effect | Mitigation status (2026) |
|---|---|---|---|
| **Heracles** (CCS 2025) | Chosen-plaintext via page relocation + AES-XEX tweak | Build plaintext oracle from VM; recover arbitrary VM plaintext if attacker can move pages (which the hypervisor can on Zen 3/4). | AMD Zen 5 introduces `CiphertextHidingDRAM` feature (kernel patch v9 — already merged) that returns `0xff` instead of ciphertext on disallowed reads. **Not enabled by default**, requires `kvm-amd.ciphertext_hiding_asids=` boot param. Hyperscalers (Azure, AWS, GCP) on Milan/Genoa do not yet enable this for production CVMs. |
| **CacheWarp** (USENIX Security 2024) | Software fault injection via INVD | Drop modified cache lines; escalate to RSA private-key recovery in Intel IPP, root via sudo, OpenSSH auth bypass on **up-to-date SEV-SNP on EPYC 7313P (Zen 3)**. | CVE-2023-20592. No hardware fix; only software mitigations (process-level). AMD's microcode cannot fully prevent it. |
| **Cohere+Reload** (USENIX Security 2025) | Coherence conflict timing | 2 KB granularity control-flow leak; 256 B within that; full mbedTLS RSA-4096 key recovery in single trace (99.7% bits correct); OpenSSL AES T-table attack with 100% accuracy in 1500 encryptions. | Disable coherence for sensitive pages (requires VM-side modification); or hide ciphertext (same Zen 5 path). |
| **Reload+Reload: RRFS + RRMB** (ASPLOS 2025) | Cache-flush + memory contention | 64 B granularity memory-access pattern leak; AES-128 secret key extraction. | Architectural fix proposed (allow cross-ASID cache access without flush); not yet shipped. |
| **CipherLeaks / CipherSteal / Hypertheft** | Ciphertext side-channel (AES-XEX tweak reuse) | Neural-network weight + input leakage for DNNs; register page leaks for crypto keys. | Application-level. Software fix is workload-specific. |
| **BadRam** | Unauthenticated DRAM module sizes | Memory aliasing → SEV-SNP bypass. | BIOS-level; vendor mitigations shipped. |
| **RMPocalypse** | RMP corruption during init | SEV-SNP bypass. | Patched. |
| **Heckler / WeSee / CounterSEVeillance** | Interrupt injection + perf counters | Single-stepping + branch/div leakage. | Software mitigation in newer kernels. |

### 6.2 Intel TDX — open attack classes

| Attack | Class | Effect | Mitigation |
|---|---|---|---|
| **TDXDown** | Cache side-channel amplification via single-stepping | Cache-line granularity leak from TDX CVMs. | Software-side constant-time, kernel hardening. |
| **Heckler** (CCS 2024) | int 0x80 interrupt injection | TDX CVM integrity compromise. | Patched in TDX module updates; Azure CVE-2024-38018 disclosed + patched. |
| **AEPIC Leak** (SGX, but in same family) | Architectural bug | SGX enclave compromise. | Hardware-revised CPUs needed; SGX-only on most current silicon. |
| **Google pre-release analysis** (2023) | Multiple architectural issues | Various. | Mitigated over time. |

### 6.3 What this means practically for Achiyon
- The threat model that **matters** for Achiyon's user is "the cloud operator tries to read my prompts." SEV-SNP and TDX meaningfully raise the bar against that — the operator needs a SEV-SNP/TDX 0-day or insider-level host access, not just "shell on the hypervisor."
- The threat model that **does not matter** for Achiyon's user is "a nation-state with physical access to the server DRAM tries cold-boot." That threat requires physical access to the host; on a multi-tenant cloud it's the cloud operator's problem, and they defend against it via memory encryption (which SEV-SNP and TDX both implement).
- **Rowhammer specifically on SEV-SNP**: AMD has not published a comprehensive rowhammer-resistance position. SEV-SNP inherits DDR5's on-die ECC plus Target Row Refresh (TRR) on most server DIMMs, which raises the bar but does not eliminate Rowhammer (the 2022 BlackSmith and 2024 PRResident papers show TRR bypass on ECC DIMMs in some configurations). **There is no AMD-published "SEV-SNP is Rowhammer-safe" guarantee.** For Achiyon: store sensitive things encrypted, treat the TEE as protection against *logical* host compromise (operator & insider) and not against *physical* DRAM attacks.

### 6.4 What hyperscalers actually do
- **Azure**: runs SEV-SNP with the standard SNP firmware + their own attestation. As of mid-2025, did *not* broadly enable Zen 5 ciphertext hiding (Milan/Genoa hardware lacks it; Azure's DCasv6 is Genoa). Microsoft publishes CVEs and patches for Azure-Confidential-VM issues; CVE-2025-41822 (Aug 2025, MRSEAM revocation list bypass in Azure Attestation) was patched Sept 2025.
- **AWS**: enables SEV-SNP on c6a/m6a/r6a with AWS Nitro System underneath; supports TDX on newer Nitro-based instance types but **does not advertise them broadly for SEV-SNP / TDX yet**; NitroTPM Instance Attestation (2025) provides signed-boot on GPU instances.
- **GCP**: runs SEV-SNP on N2D (Milan) and TDX on C3 (Sapphire Rapids). N2D live migration supported *only for legacy SEV, not SEV-SNP* (per GCP release notes). Caveat: from Aug 2026 GCP is migrating guest kernels and SEV-SNP VMs may see longer boot times + perf changes through Nov 2026.

### 6.5 Net recommendation for Achiyon's threat model
**Treat the TEE as strong protection against cloud-operator/insider read, not as a fortress.** If a user trusts the cloud provider's *hardware supply chain* (AMD / Intel), the TEE does what they need. If a user doesn't trust the hardware vendor's root keys, no cloud TEE helps them — they need local-only inference.

---

## 7. Does running in a TEE change anything for SurrealDB / Axum compatibility?

**No, with two footnotes.**

### 7.1 SurrealDB
- SurrealDB runs as a Linux/x86-64 binary. CVMs are full Linux VMs with UEFI + kernel + userspace unmodified. SurrealDB will start and run.
- **Disk encryption**: SurrealDB recommends LUKS / cloud-provider disk encryption at rest. On Azure CVMs, OS disks can be encrypted with **confidential disk encryption** (customer-managed keys held in Azure Key Vault / Managed HSM, sealed to the CVM's attestation measurement). AWS SEV-SNP volumes are EBS-encrypted by default; KMS-backed envelope encryption works the same as non-confidential VMs. GCP CVM disks support customer-managed encryption keys similarly.
- **`SURREAL_KEY` env var**: documented in SurrealDB env-vars table as "Encryption key to use for on-disk encryption. **Not currently in use**." SurrealDB does not currently do application-layer on-disk encryption — it relies on the storage layer for at-rest. So the encryption-at-rest story for SurrealDB in a TEE is *the same as a non-TEE VM*: LUKS / EBS / DiskEncryption / cloud-provider. TEE protects *in-memory* while the process is running, not the disk format.
- **SurrealKV (file)** vs **TiKV (cluster)** vs **RocksDB (file)**: all run unchanged.

### 7.2 Axum
- Pure userspace. Unmodified. The only TEE-aware code you write is the attestation-verifier on startup, which the `VirTEE/sev` crate (SEV-SNP), the Microsoft Azure `azure-attestation` crate (Azure), or the AWS Nitro Enclaves SDK handle. ~100–500 lines.

### 7.3 Footnotes
1. **Some CVM features are disabled** that your normal VM had:
   - **No live migration** on SEV-SNP / TDX (Azure, GCP, AWS). Means your blue-green deploy strategy has to handle VM recreation explicitly.
   - **No accelerated networking** on DCasv5 (older), DC8es_v6 does support. DCesv6 series does support accelerated networking per the spec sheet.
   - **No Site Recovery** on Azure Confidential VMs (per Microsoft docs).
   - **No disks >128 GB** with confidential disk encryption on Azure.
   - **No hibernation, no nested virtualization, no accelerated networking on DCasv5-series** (per spec).
   - **Nitro Enclaves**: no GPU passthrough; no persistent storage; max 4 enclaves per parent; no interactive access; enclave-to-enclave only via vsock or parent-process socket.
2. **OS image selection matters.** Ubuntu 22.04 LTS for Azure CVMs (Azure-recommended for SEV-SNP); Ubuntu 22.04+ for GCP Confidential VMs; latest Amazon Linux 2023 or Ubuntu 22.04 LTS for AWS c6a/m6a/r6a with SEV-SNP. Host firmware enabling SEV-SNP/TDX is automatic on these SKUs.

### 7.4 NixOS compatibility
- **NixOS runs inside CVMs.** Ubuntu is the default recommended image on all three clouds for CVMs, but NixOS-Azure images exist in the marketplace and NixOS-on-EC2 community AMIs are stable. Build a NixOS AMI/image with `kernelPackages = pkgs.linuxPackages_latest` (≥ 6.2 for Azure SEV-SNP guest module support, ≥ 5.19 for `sev-guest` character device) and the existing CVM image flow works.
- The NitroTPM / Azure vTPM modules both work inside CVMs; they're how in-guest attestation flows into your application.

---

## 8. Concrete deployment architecture for Achiyon (recommended)

### 8.1 Architecture diagram (text)

```
┌────────────────┐                      ┌──────────────────────┐
│  Tauri/mobile  │ ──── mTLS (TLS 1.3) ───►│  Cloudflare OHTTP   │
│  client app    │                       │  relay (3rd-party)  │
└────────────────┘                       └──────────┬───────────┘
                                                    │ opaque bytes
                                                    ▼
                          ┌───────────────────────────────────────┐
                          │  Axum OHTTP gateway (inside CVM)     │
                          │  ┌─────────────────────────────────┐  │
                          │  │ DCasv5 / m6a.2xlarge / n2d-8    │  │
                          │  │ AMD SEV-SNP                     │  │
                          │  │ NixOS 23.11                       │  │
                          │  │                                  │  │
                          │  │  ┌──────────┐   ┌─────────────┐  │  │
                          │  │  │  Axum    │──►│  SurrealDB  │  │  │
                          │  │  │  (Rust)  │   │  (SurrealKV │  │  │
                          │  │  │          │   │   on local  │  │  │
                          │  │  │          │   │   NVMe)     │  │  │
                          │  │  └──────────┘   └─────────────┘  │  │
                          │  │                                  │  │
                          │  │  HPKE ctx + attestation daemon   │  │
                          │  └─────────────────────────────────┘  │
                          └──────────────────────┬───────────────┘
                                                 │
                                                 ▼
                          ┌───────────────────────────────────────┐
                          │  External LLM API (OpenAI / Anthropic │──── prompt (encrypted in TLS to provider)
                          │  / MiniMax)                          │──── response
                          │  Tier 1 variant: encrypt prompt to    │
                          │  provider's HPKE public key          │
                          └───────────────────────────────────────┘
```

### 8.2 Component choices

| Component | Choice | Reason |
|---|---|---|
| **Cloud** | **Azure** for primary (only GA confidential H100 if local models); **AWS c6a** for cheapest cost; **GCP N2D+CVM** for cleanest billing. | Each has a niche. Azure = GPU + broadest SKU. AWS = cheapest. GCP = cleanest. |
| **CVM SKU (MVP)** | `DCasv5` 8 vCPU/32 GiB or `m6a.2xlarge` or `n2d-standard-8`. | Sweet spot for Axum + SurrealDB at 100 users. |
| **CVM SKU (1k users)** | `DCasv5` 16 vCPU/64 GiB or `m6a.4xlarge` or `n2d-standard-16`. | SurrealDB working set fits in 64 GiB. |
| **OS** | NixOS 23.11+ with `linuxPackages_latest` (≥ 6.2 for `sev-guest`). | Achiyon's existing NixOS stack works unchanged. |
| **OHTTP relay** | Cloudflare Privacy Gateway OR self-hosted on a different cloud (e.g., Achiyon runs gateway on AWS c6a, relay on GCP C3 TDX — different operators, no single party sees both halves). | Split trust between operators. |
| **OHTTP gateway** | In-CVM Axum endpoint with HPKE middleware. Use the `ohttp` Rust crate (Cloudflare reference) or build on `hpke` crate (RustCrypto). | RFC 9458 compliant. |
| **Attestation verifier** | At boot, the CVM: (1) fetches its SEV-SNP attestation report from `/dev/sev-guest`; (2) verifies VCEK against AMD KDS; (3) optionally cross-checks via Microsoft Azure Attestation (Azure) or self-hosted verifier (AWS). The verifier publishes its measurement (PCR-equivalent) for clients. | Defense-in-depth: cloud attestation + AMD hardware root. |
| **LLM API** | OpenAI / Anthropic / MiniMax with zero-retention + no-training contracts. Tier-1 variant: encrypt prompt to provider's HPKE public key (if supported — currently experimental). | Operator-trusted LLM with audit + minimal-data contracts. |
| **Database** | SurrealDB with SurrealKV on a local encrypted NVMe (Azure Disk Encryption w/ customer-managed key sealed to CVM attestation; AWS EBS encryption w/ KMS; GCP disk encryption w/ CMEK). | Standard cloud-disk encryption + TEE attestation-bound key release. |
| **Backups** | Encrypted snapshots (age / restic / SurrealDB export) to S3/Blob Storage with customer-managed keys. Daily; 30-day retention. | Same pattern as non-TEE; keys held in cloud KMS. |

### 8.3 What runs where
- **Client**: Tauri 2 desktop + native mobile, builds prompts locally (memory consolidation, lorebook activation), encrypts to LLM-provider pubkey + Achiyon gateway pubkey (Tier 1 variant), sends via OHTTP relay.
- **CVM**: HPKE gateway terminates OHTTP; Axum does auth + rate-limit + session-orchestration + relay-to-LLM + log-stripping; SurrealDB for account state + non-prompt metadata (timestamps, character IDs, payment state); no plaintext chat content reaches disk.
- **External**: LLM provider does inference under its own privacy contract (zero-retention).
- **Independent**: OHTTP relay operator (different party from Achiyon & cloud) sees only encrypted bytes + client IP. Without colluding with both Achiyon and the LLM provider, the relay learns nothing.

### 8.4 Honest marketing
"**Attested E2EE-against-cloud-operator**: Achiyon runs inside an attested hardware TEE (AMD SEV-SNP) on Microsoft Azure, verified against AMD's hardware root of trust and Microsoft's attestation service. The cloud operator cannot read your prompts. Your prompts are also encrypted in transit to our LLM provider (OpenAI / Anthropic / MiniMax) under their zero-retention contract. Client traffic is routed via an independent OHTTP relay (Cloudflare) so the LLM provider does not see your IP. This is **not** Signal-grade E2EE — the LLM still has to read your prompt to generate a reply — but it is the strongest privacy envelope available on a hosted AI service in 2026."

---

## 9. Operational considerations

### 9.1 Boot & attestation
- Every CVM boots in ~30–60s (Azure DCasv5: ~40s reported in community blogs). SEV-SNP attestation report fetched at first `/dev/sev-guest` read; VCEK fetch from AMD KDS adds ~200ms.
- NixOS builds into a custom Azure Gallery Image / AWS AMI with the application, the OHTTP gateway code, the attestation verifier, and the systemd units to start them in order.

### 9.2 Live migration & updates
- **No live migration** on SEV-SNP / TDX. Rolling deploys require: launch new CVM → attest → cut traffic → drain old CVM → decommission. ~5 min per instance.
- **OS patches**: kernel + SEV firmware updates require VM restart. AMD SEV firmware 1.55:21 (Aug 2025) added VCEK improvements; CVE-2023-20592 (CacheWarp) is patched in current microcode.

### 9.3 Observability
- **Logs are plaintext from your CVM's perspective but ciphertext to the cloud operator** — unless you export them. Recommendation: keep logs in-CVM (journald → Loki/Vector inside the CVM); only export aggregated counters (request counts, latency p50/p95/p99, error rates) to your telemetry backend. **Never export prompt content**; that's the privacy claim.
- Prometheus exporter runs fine inside the CVM; standard Linux/x86-64.

### 9.4 Disaster recovery
- SurrealDB backup encrypted snapshot to cold storage hourly; RPO 1h, RTO 30 min (rebuild CVM + restore snapshot).
- Multi-region: replicate encrypted snapshots cross-region; spin up standby CVM in secondary region.
- **Confidential disk encryption caps Azure disks at 128 GB per disk** — if SurrealDB grows past that, use multiple disks or split data.

---

## 10. Monthly cost estimate for ~100 and ~1000 users

Assumptions:
- ~10 messages/user/day average.
- ~2 KB prompt + ~4 KB response = 6 KB/message.
- 100 users × 10 msg × 30 days = 30,000 msg/month → ~180 MB outbound.
- 1000 users × 10 msg × 30 days = 300,000 msg/month → ~1.8 GB outbound.
- LLM cost excluded (depends on model + provider; ~$50–$500/mo for 100 users, ~$500–$5,000/mo for 1000 users on hosted APIs).
- 1-year reserved discount (~20% off) on Azure / AWS.
- Spot / preemptible for stateless tiers.

### 10.1 Tier A — MVP, 100 users, cheapest acceptable

| Component | Azure DC8as_v5 (SEV-SNP) | AWS m6a.2xlarge (SEV-SNP) | GCP n2d-standard-8 + SNP |
|---|---|---|---|
| Compute (1y RI) | $251 × 0.8 = **$201** | $223 × 0.8 = **$179** | $305 × 0.8 = **$244** |
| OS disk (Premium SSD 64 GB) | $10 | $6 (gp3) | $10 |
| Snapshots / backups | $5 | $5 | $5 |
| Data egress (~180 MB) | $16 | $16 | $16 |
| MAA / Nitro / CVM surcharge | $0 | +$22 (10% of base for SNP on shared tenancy) | included |
| Azure Disk Encryption key (Key Vault) | $1 | $0.30 | $1 |
| Cloudflare OHTTP relay (Workers paid) | $5 | $5 | $5 |
| Misc (DNS, monitoring, error tracking) | $20 | $20 | $20 |
| **Total** | **$258/mo** | **$253/mo** | **$301/mo** |
| **Plus margin (×1.3)** | **~$335** | **~$330** | **~$390** |

### 10.2 Tier B — 1000 users, SurrealDB workload

| Component | Azure DC16as_v5 | AWS m6a.4xlarge | GCP n2d-standard-16 + SNP |
|---|---|---|---|
| Compute (1y RI) | $502 × 0.8 = **$402** | $447 × 0.8 = **$358** | $609 × 0.8 = **$487** |
| OS + data disk (256 GB P30) | $40 | $26 | $40 |
| Snapshots / backups (250 GB) | $12 | $12 | $12 |
| Data egress (~1.8 GB) | $160 | $160 | $160 |
| SNP surcharge on AWS | — | +$45 | included |
| Key Vault / KMS / CMEK | $2 | $1 | $2 |
| OHTTP relay | $5 | $5 | $5 |
| Misc | $30 | $30 | $30 |
| **Total** | **$651/mo** | **$637/mo** | **$736/mo** |
| **Plus margin (×1.3)** | **~$846** | **~$828** | **~$957** |

### 10.3 Tier C — 1000 users + confidential-GPU local inference (Azure NCC H100)

- SurrealDB/API tier as in Tier B: $651/mo (Azure DC16as_v5).
- NCC40ads_H100_v5 at $8.82/hr East US 2 (1y RI: ~$5.24/hr → ~$3,825/mo) — only run as needed; auto-shut-down nightly for 12h saves ~$1,900/mo.
- If run 24/7: **~$4,500/mo GPU + $650/mo data = $5,150/mo** total.
- If run 12h/day: **~$2,350/mo GPU + $650/mo data = $3,000/mo** total.

### 10.4 Summary
| Scale | Cheapest (AWS) | Azure (mid) | Most expensive (GCP) |
|---|---|---|---|
| 100 users | **~$330** | ~$335 | ~$390 |
| 1000 users | **~$828** | ~$846 | ~$957 |
| 1000 users + local LLM (12h/day) | n/a (no AWS CC GPU) | **~$3,000** | n/a |

**Bottom line:** for 100–1000 users, the TEE envelope costs **~$0–$10/month more than a non-confidential equivalent** on the same cloud. The architecture premium is essentially free; the engineering cost (attestation verifier, OHTTP gateway, NixOS CVM image) is the real investment.

---

## 11. Concrete recommendations for Achiyon

1. **Pick Azure** as primary if any feature beyond the data-plane protection is on the roadmap (confidential GPU, managed attestation with MAA, broadest SKU coverage). Pick **AWS c6a/m6a** if pure cost-optimization is the only criterion. Pick **GCP** if you want cleanest cost forecasting.
2. **Ship Tier 4 + TEE first**: the existing operator-trusted model, with attestation-verifiable CVM deployment. This is the minimum engineering investment and gives you the "attested non-disclosure" marketing claim.
3. **Add OHTTP+HPKE as a v1.5 feature**: independent relay (Cloudflare or self-hosted), HPKE gateway inside the CVM. ~2–4 weeks of engineering. This gives you client-IP unlinkability from the LLM provider.
4. **Add Tier 1 (encrypted-to-LLM-provider) as v2**: requires LLM-provider cooperation for HPKE key recipients. Currently experimental on a few providers; plan for 2026/2027.
5. **Defer Tier 2 (in-TEE local LLM) until either (a) regulatory pressure demands it or (b) the Azure NCC H100 price drops 3×**: at $6,400/mo GPU it's not viable for the target price point.
6. **Be honest in marketing**: "attested E2EE against cloud operator" is a meaningful, verifiable claim. Signal-grade E2EE for prompts is *not* achievable in this product and won't be until local-only inference or trusted-third-party-LM becomes the norm. The earlier `e2ee-app-architecture-survey.md` Tier 4 framing holds.

---

## Sources

### Azure pricing and SKU specs
- DCasv5 series: https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dcasv5-series
- DCesv6 series: https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dcesv6-series
- DC family overview: https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/general-purpose/dc-family
- Confidential VM overview: https://learn.microsoft.com/en-us/azure/confidential-computing/virtual-machine-options
- Confidential VM FAQ: https://learn.microsoft.com/en-us/azure/confidential-computing/confidential-vm-faq
- NCCads H100 v5 series: https://learn.microsoft.com/en-us/azure/virtual-machines/sizes/gpu-accelerated/nccadsh100v5-series
- Confidential GPU options: https://learn.microsoft.com/en-us/azure/confidential-computing/gpu-options
- Pricing (DC8as v5): https://www.economize.cloud/resources/azure/pricing/virtual-machine/dc8asv5/
- Pricing (DC8es v6): https://www.azurespeed.com/AzureVmPricing/Series/DCesv6
- Microsoft Azure Attestation (free): https://azure.microsoft.com/en-us/products/azure-attestation

### AWS pricing and SKU specs
- c6a: https://aws.amazon.com/ec2/instance-types/c6a/
- m6a: https://aws.amazon.com/ec2/instance-types/m6a/
- SEV-SNP enablement docs: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/sev-snp.html
- SEV-SNP launch guide: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/snp-work-launch.html
- Nitro Enclaves (free): https://docs.aws.amazon.com/enclaves/latest/user/nitro-enclave.html
- Nitro Enclaves FAQ: https://aws.amazon.com/ec2/nitro/nitro-enclaves/faqs/
- Nitro Enclaves attestation: https://docs.aws.amazon.com/enclaves/latest/user/set-up-attestation.html
- NitroTPM attestation (GPU instances): https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/nitrotpm.html
- Pricing (c6a.large): https://aws-pricing.com/c6a.large.html

### GCP pricing and SKU specs
- Confidential VM pricing: https://cloud.google.com/confidential-computing/confidential-vm/pricing
- Confidential VM overview: https://cloud.google.com/confidential-computing/confidential-vm/docs/confidential-vm-overview
- Supported configurations: https://cloud.google.com/confidential-computing/confidential-vm/docs/supported-configurations
- Release notes (2025–2026): https://cloud.google.com/confidential-computing/confidential-vm/docs/release-notes

### Attestation
- Microsoft Azure Attestation: https://azure.microsoft.com/en-us/products/azure-attestation
- Intel Trust Authority (free for CSP customers): https://www.intel.com/content/www/us/en/security/trust-authority.html
- Intel Trust Authority docs: https://docs.trustauthority.intel.com/
- Intel Trust Authority what's new (2025): https://docs.trustauthority.intel.com/main/articles/whats-new.html
- AWS Nitro Enclaves attestation PKI: https://docs.aws.amazon.com/enclaves/latest/user/verify-root.html
- AMD SEV-SNP KDS / Rust verifier (VirTEE/sev): https://docs.amd.com/api/khub/documents/Fs8c5rfhxC4nlZfXaZal0Q/content
- Rust SEV-SNP crate (sev): https://docs.rs/sev/latest/sev/
- tenzro_tee amd_sev_snp module: https://docs.rs/tenzro-tee/latest/tenzro_tee/amd_sev_snp/index.html

### OHTTP / HPKE
- RFC 9458 Oblivious HTTP: https://www.rfc-editor.org/rfc/rfc9458.txt
- RFC 9180 HPKE: https://www.rfc-editor.org/info/rfc9180/
- Chunked OHTTP: https://datatracker.ietf.org/doc/draft-ietf-ohai-chunked-ohttp/
- Cloudflare Privacy Gateway server (Go): https://github.com/cloudflare/privacy-gateway-server-go
- Cloudflare Privacy Gateway relay: https://github.com/cloudflare/privacy-gateway-relay
- thibmeu/ohttp-gateway: https://github.com/thibmeu/ohttp-gateway
- thibmeu/ohttp-relay: https://github.com/thibmeu/ohttp-relay
- OHTTP overview: https://http.dev/ohttp

### Confidential GPU
- NVIDIA Confidential Compute on Hopper H100 whitepaper: https://images.nvidia.com/aem-dam/en-zz/Solutions/data-center/HCC-Whitepaper-v1.0.pdf
- NVIDIA CC deployment guide (Hopper + Blackwell): https://docs.nvidia.com/cc-deployment-guide-tdx-snp.pdf
- NVIDIA "Creating the First Confidential GPUs" (CACM): https://cacm.acm.org/practice/creating-the-first-confidential-gpus/
- NVIDIA Hopper CC developer blog: https://developer.nvidia.com/blog/confidential-computing-on-h100-gpus-for-secure-and-trustworthy-ai/

### Side-channel research (2024–2026)
- Heracles — CCS 2025: https://doi.org/10.1145/3676641.3716017
- CacheWarp — USENIX Security 2024: https://www.usenix.org/system/files/usenixsecurity24-zhang-ruiyi.pdf
- Cohere+Reload — USENIX Security 2025: https://gruss.cc/files/cohere.pdf
- Reload+Reload — ASPLOS 2025: https://doi.org/10.1145/3676641.3716017
- AMD-SB-3021 (ciphertext side-channel response): https://www.amd.com/en/resources/product-security/bulletin/amd-sb-3021.html
- CiphertextHidingDRAM kernel patch series: https://lore-kernel.gnuweeb.org/lkml/7eed1970-4e7d-4b3a-a3c1-198b0a6521d5@amd.com/T/
- BeyondScale CISO guide (2026 perf overhead): https://beyondscale.tech/blog/confidential-computing-ai-inference-enterprise-ciso-guide
- Decryption Digest AWS/Azure/NVIDIA comparison: https://www.decryptiondigest.com/blog/confidential-computing-ai-model-protection-nitro-azure-nvidia

### SurrealDB
- Security best practices: https://surrealdb.com/docs/learn/security/best-practices/security-best-practices
- Environment variables (SURREAL_KEY): https://surrealdb.com/docs/reference/cli/surrealdb-cli/environment-variables
- File-backed (SurrealKV): https://surrealdb.com/docs/running/file-backed
- AKS deployment: https://surrealdb.com/docs/build/deployment/self-hosted/azure-aks
- EKS deployment: https://surrealdb.com/docs/build/deployment/self-hosted/amazon-eks

### Ubuntu SEV-SNP host/guest support
- Ubuntu SEV-SNP host/guest docs: https://ubuntu.com/server/docs/how-to/virtualisation/sev-snp/

### Open-source implementation refs
- `VirTEE/sev` (Rust, Linux Foundation): https://github.com/virtee/sev (community fork of `tylerfanelli/sev`)
- `aws/aws-nitro-enclaves-nsm-api`: https://github.com/aws/aws-nitro-enclaves-nsm-api/blob/main/docs/attestation_process.md
- nvtrust (NVIDIA GPU attestation): https://github.com/NVIDIA/nvtrust