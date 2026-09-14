# Achiyon — Threat Model & Adversary × Option Matrix

**Compiled:** 2026-09-18 — for the Achiyon / Achlys project (SvelteKit PWA + Rust/Axum + SurrealDB AI roleplay app).
**Question:** For each architectural option (A client-side, B TEE-hosted, C escrow status quo), precisely who can read the user's roleplay content — operator (Kirill), cloud provider, DB-dump attacker, subpoena, compromised server admin, malicious browser extension, rogue employee? Does TDX/SEV-SNP deliver "operator cannot read" or only "cloud admin cannot read"? Who runs the attestation service for a hosted product, and what does that imply?
**Method:** Synthesize the prior research in this directory (especially `.hermes/research/tee-confidential-deployment-survey.md`, `e2ee-app-architecture-survey.md`, `e2ee-byok-relay-ux-survey.md`) plus targeted web research on the actual SEV-SNP / TDX threat model, attested-literature side-channel attacks, attestation-trust chains, and end-to-end trust models (Microsoft Azure Attestation, Intel DCAP/QVS, AMD KDS/VCEK, Apple Private Cloud Compute).
**Output contract:** the report file plus a JSON verdict block — no prose around the JSON.

---

## TL;DR

The headline answer: **the literature is unambiguous that TDX/SEV-SNP gives you "cloud admin cannot read VM memory," not "operator cannot read."** Every published TEE threat model — including the Linux kernel's own CoCo threat model — names the hypervisor as a stronger-than-network adversary, not as a removed adversary. The attestation service is a separate trust anchor operated by someone (AMD, Intel, Microsoft, Apple, or Achiyon itself), and whoever runs it becomes a new high-value compromise target. The honest answer to "can Achiyon deploy TEE-hosted inference so the operator cannot read?" is **no** — the operator still sees plaintext at the application layer unless they delegate key release to a third party (and even then only if that third party is genuinely independent). Options A and B both have adversary x option tables that differ sharply from what marketing implies.

---

## 1. The threat-model framing that the literature actually uses

### 1.1 The Linux kernel's CoCo VM threat model (the canonical reference)

The Linux kernel documentation explicitly defines the TEE/CVM threat model as **adding a new class of adversary, not removing any existing one**:

> "Confidential Computing adds a new type of attacker to the above list: a potentially misbehaving host (which can also include some part of a traditional VMM or all of it), which is typically placed outside of the CoCo VM TCB due to its large SW attack surface. It is important to note that this doesn't imply that the host or VMM are intentionally malicious, but that there exists a security value in having a small CoCo VM TCB. This new type of adversary may be viewed as a more powerful type of external attacker, as it resides locally on the same physical machine (in contrast to a remote network attacker) and has control over the guest kernel communication with most of the HW." (https://www.kernel.org/doc/Documentation/security/snp-tdx-threat-model.rst, kernel.org)

This is the canonical statement of what TEE delivers: **the host (including any operator with root on the hypervisor) is treated as a more powerful local attacker, not as a removed party.** The threat model assumes the host may misbehave and designs defenses assuming that. It does **not** claim the host operator has been removed from the trust boundary.

### 1.2 The AMD SEV-SNP threat model (private memory, not private I/O)

AMD's own SEV-SNP architecture documentation and the academic survey (https://doi.org/10.1145/3623392, "Hardware VM Isolation in the Cloud") describe the protections as:

> "SEV-SNP is designed to protect a VM from all outside entities, including the bare-metal hypervisor, BIOS, other VMs, and even external I/O devices... The RMP enforces access control to memory pages in the system... the HV no longer can write that memory page. If it attempts to do so, the CPU will issue a page fault."

This means: **the HV cannot directly read VM-private memory or silently modify guest code/data**. But the same documentation is explicit about what the HV still controls:

- **VM creation, scheduling, and lifecycle** — "The host retains full control of the CoCo guest resources, and can deny access to them at any time. Examples include CPU time, memory that the guest can consume, network bandwidth, etc."
- **The guest's I/O data** — "A misbehaving host retains full control of the CoCo guest's data in-transit between the guest and the host-managed physical or virtual devices. This allows any attack against confidentiality, integrity or freshness of such data." (kernel CoCo docs)
- **The guest's firmware, bootloader, and kernel** at launch time — "The host in a CoCo system typically controls the process of creating a CoCo guest: it has a method to load into a guest the firmware and bootloader images, the kernel image together with the kernel command line. All of this data should also be considered untrusted until its integrity and authenticity is established via attestation."

In other words, "memory confidentiality" ≠ "operator cannot read application plaintext." The operator can still (a) control what code runs inside the VM (by feeding firmware/OVMF/kernel/images), (b) control when/how the VM runs (DoS, scheduling-based side channels), (c) inspect every byte of plaintext flowing in or out of the VM via I/O, and (d) read ciphertext during transit through device DMA, MMIO, virtual NICs, vsock channels.

### 1.3 The Intel TDX threat model — same posture

The Intel TDX module offers the same protections with the same caveats. Per the academic overview (https://sys.cs.fau.de/extern/lehre/ws22/akss/material/amd-sev-intel-tdx.pdf): "every component which would previously be considered to be trusted due to its ability to write into VM memory (e.g. Hypervisor, Direct Memory Access (DMA) capable PCI devices) can now safely be assumed to be untrusted" for **memory confidentiality/integrity** only. TDX additionally uses MAC-protected cache lines (or logical-integrity mode without MAC). TDX does not address the broader host attack surface and explicitly does not prevent the host from seeing inbound/outbound traffic or from controlling when the TD runs.

### 1.4 Side-channel attacks have moved the goalposts repeatedly

Even within the "memory confidentiality" guarantee that TEE does offer, the published attacks in 2024–2026 show that **what looks like "memory confidentiality" in the spec is not the same thing as "no information leakage" in practice**:

- **CipherLeaks (USENIX Security 2021, https://yinqian.org/papers/sec21b.pdf)**: VMSA ciphertext is deterministic in plaintext-per-address space, allowing dictionary attacks to recover register values and steal RSA/ECDSA keys from "constant-time" OpenSSL running inside an SEV/SEV-ES/SEV-SNP VM. The attack works against SEV-SNP because AMD allows the hypervisor to read ciphertext. AMD shipped a microcode patch (MilanPI-SP3 1.0.0.5) adding nonce-based freshness to the VMSA — but only for the VMSA page; the underlying XEX determinism remains.
- **A Systematic Look at Ciphertext Side Channels on AMD SEV-SNP (https://radu.teodorescu.us/assets/pdf/mengyuan_sp2022.pdf)**: generalizes CipherLeaks to any memory location (kernel data structures, stacks, heaps), not just VMSA. Confirms AMD's firmware patch is insufficient because the root cause — deterministic, unauthenticated, stateless memory encryption — is unchanged.
- **CacheWarp (USENIX Security 2024, https://www.usenix.org/system/files/usenixsecurity24-zhang-ruiyi.pdf)**: a software-based fault-injection attack on SEV-ES **and** SEV-SNP that uses the `invd` instruction to drop modified cache lines, achieving Bellcore attacks on RSA (recover full private key in 6 seconds, 90% success without single-stepping), SSH authentication bypass, and privilege escalation via sudo. The authors note: "unlike previous attacks on the integrity, CacheWarp is not mitigated on the newest SEV-SNP implementation, and it does not rely on specifics of the guest VM... Mitigating CacheWarp purely in software is difficult as it exploits a memory-coherence problem that a malicious hypervisor can create." This is an integrity violation — the SEV-SNP "integrity" guarantee has a known unfixed breach.
- **Heracles (https://doi.org/10.1145/3719027.3765209, 2025)**: turns the XEX tweak + the hypervisor's page-move primitive into a chosen-plaintext oracle, enabling leak of "kernel memory, crypto keys, and user passwords, as well as... web session hijacking" at byte granularity in SEV-SNP. Crucially: "Neither SGX nor TDX allows the untrusted privileged software to observe the victim enclave/CVM ciphertext, rendering Heracles or even prior ciphertext attacks impossible." So SEV-SNP has a class of attacks that TDX/SGX do not, because AMD's design intentionally lets the HV read ciphertext.

Each of these is a published, peer-reviewed demonstration that the hypervisor/operator is *not* read-only with respect to guest state. The hypervisor cannot grab a plaintext page dump, but it can recover secrets through deterministic-encryption leakage, fault injection, and chosen-plaintext oracles — all without breaking the spec.

### 1.5 The firmware / supply-chain TCB has been broken multiple times

Even setting side channels aside, the attestation root of trust itself has been compromised in published research:

- **BadRAM / RMPocalypse / CipherLeaks and other chain**: documented memory aliasing attacks that break SEV-SNP's integrity guarantees at boot (referenced in https://www.usenix.org/system/files/usenixsecurity26-shen.pdf, "Jailbreaking the AMD Secure Processor").
- **BadFuse / MilanLaunchy (arxiv 2605.12990, 2025)**: "a software-only exploit" extracting the VCEK root seed on EPYC Milan, enabling "an adversary to forge valid attestation reports for any firmware version, thereby effectively undermining the security model of SEV-SNP." AMD issued MilanPI-1.0.0.3 to mitigate; the underlying architectural oversight in the fuse controller is not fixable in shipped silicon.
- **Google's microcode signature vulnerability (https://github.com/google/security-research/security/advisories/GHSA-4xq7-4mgh-gp6w, Feb 2025)**: "an adversary with local administrator privileges (ring 0 from outside a VM)" can load malicious microcode on Zen 1 through Zen 4, "to compromise confidential computing workloads protected by the newest version of AMD Secure Encrypted Virtualization, SEV-SNP." Ring 0 from outside the VM is exactly the threat model. Fixed in microcode update, but the disclosure makes clear that the TCB extends beyond just the silicon.
- **AMD's own response to ATT&CK-style analyses** acknowledges that the TCB includes firmware, microcode, the ASP bootloader, and the chip's fuses — and the security literature has shown each of those layers can be attacked.

### 1.6 The attestation-trust wrinkle — who runs the attestation service?

This is the part that marketing copy skips. Remote attestation is a chain of signed claims. For it to mean anything, the verifier needs to trust:

1. **The hardware root key** (AMD ARK, Intel root keys) — burned into silicon at fab time. Trust requires trusting AMD/Intel's foundry supply chain (TSMC, packaging, key injection).
2. **The chip endorsement key** (VCEK / PCK Cert) — derived from the chip's unique secret + TCB version. Signed by AMD/Intel via the **Key Distribution Service / Provisioning Certification Service** (https://kdsintf.amd.com, https://api.trustedservices.intel.com).
3. **The attestation token issuer** — for cloud deployments, this is typically the cloud provider's attestation service:
   - **Microsoft Azure Attestation (MAA)** — closed-source, runs inside an SGX enclave. Microsoft's own page: "One of the core operational guarantees of the Azure Attestation Service is that the service operates 'operationally out of the TCB'. In other words, there is no way that a Microsoft operator could tamper with the operation of the service, or corrupt data sent from the client." This is a *claim*, not a proof — and the user must trust Microsoft's claim, Microsoft's code, and Microsoft's SGX. (https://github.com/Azure/azure-sdk-for-js/blob/main/sdk/attestation/attestation/README.md)
   - **Microsoft's own recommendation** is direct: "If you use MAA, you need to implicitly trust that MAA is correctly validating the SNP report and is free from malicious intentions. While MAA follows industry-standards and Microsoft leads the CCC Attestation SIG, MAA remains closed-source." (https://github.com/Azure/confidential-computing-cvm-guest-attestation/blob/main/cvm-guest-attestation.md)
   - **Intel DCAP Quote Verification Service (QVS)** — open source (https://github.com/intel/SGX-TDX-DCAP-QuoteVerificationService), but explicitly: "QVS is purely software component, and it doesn't require SGX capable platform to work. Although it can be additionally protected by running inside an enclave (for example by using Gramine)." The verifier can choose to self-host it or use Intel's hosted PCS.
   - **Apple's Private Cloud Compute** is the strongest published model: every production PCC build is published to a public, append-only, cryptographically tamper-proof transparency log; users' devices wrap payload keys only to public keys of PCC nodes whose attested measurements appear in the log. (https://security.apple.com/documentation/private-cloud-compute/verifiabletransparency) The model requires (a) Apple publishes the binaries, (b) researchers verify, (c) the device checks at runtime, (d) the transparency log is operated by Apple.
   - **An attestation-bypass CVE** is not hypothetical: CVE-2026-45642 (https://www.sentinelone.com/vulnerability-database/cve-2026-45642/) describes an authentication bypass in MAA via improper input validation, allowing an attacker with physical access to spoof attestation results. CVSS 3.1 = 3.9 (constrained by physical-access requirement), but the integrity impact is high. **Attestation services have CVEs too.**

**Implication for Achiyon:** if Achiyon goes TEE-hosted, *someone* must operate the attestation verifier. Three options:

- **Use a cloud provider's attestation service** (MAA on Azure, Nitro Attestation on AWS, GCE Confidential VM attestation on Google). The cloud provider becomes a new trust anchor. The cloud provider's closed-source attestation service is what stands between an attacker that controls the hypervisor and your inference workload. Your "operator cannot read" claim now depends on Microsoft's or Amazon's claim that they operate the attestation service honestly.
- **Self-host the attestation verifier** (Intel QVS open-sourced, AMD's KDS is reachable via TLS for cert retrieval but the verifier can be self-hosted). The Achiyon operator runs both the inference VM *and* the verifier that says "the inference VM is genuine and unmodified." This is structurally incoherent if the goal is "the operator cannot read" — the operator is the one running the attestation infrastructure.
- **Delegate attestation to an independent third party** (e.g., a dedicated confidential-compute auditor). Adds latency, cost, and another trust anchor. Not a standard option.

Apple's PCC works because Apple publishes every build to a public log and the user's device verifies. That requires Apple to ship devices whose trust root is Apple silicon's hardware keys (rooted at the Secure Enclave, manufactured by Apple under Apple's control). Achiyon cannot replicate this model — Achiyon does not control a hardware root, does not control user devices, and has no transparency-log infrastructure that researchers audit.

---

## 2. The three options, restated for the threat-model analysis

This section restates each option precisely so the adversary table is unambiguous.

### Option A — Client-side (RisuAI-style BYOK, server as encrypted relay)

- The user's device derives the master key locally (Argon2id from passphrase, or WebAuthn PRF).
- All roleplay content is encrypted before leaving the device. The server stores opaque ciphertext blobs indexed by user/character/conversation id.
- The server's "smart" features (prompt assembly, lorebook activation, memory consolidation, character emergence) run client-side via WASM.
- LLM inference happens either (i) on the user's device (local model), (ii) browser-direct to a third-party LLM using the user's own API key (BYOK), or (iii) via the Proton Lumo "encrypt-to-LLM-provider" pattern (client encrypts prompt to the LLM provider's public key; the Achiyon server never sees plaintext).
- See `.hermes/research/e2ee-app-architecture-survey.md` (Signal/Standard Notes/Notesnook/Cryptomator patterns) and `.hermes/research/e2ee-byok-relay-ux-survey.md` (Lumo U2L pattern) for the canonical implementations.

### Option B — TEE-hosted (SEV-SNP / TDX with remote attestation)

- The Achiyon operator's inference workload runs inside an attested confidential VM (Azure CVM, GCP Confidential Space, AWS Nitro Enclaves, or self-hosted bare-metal with SEV-SNP/TDX).
- The CVM's attestation report is verified before secrets (LLM API keys, user conversation keys, model weights) are released to it.
- Achiyon's inference code is the workload inside the VM; the rest of the Achiyon stack (auth, billing, key management, orchestration) runs on operator-controlled infrastructure.
- See `.hermes/research/tee-confidential-deployment-survey.md` for the architecture detail.

### Option C — Escrow (status quo, server reads plaintext)

- The Achiyon Axum server holds all prompts and responses in plaintext in SurrealDB / PostgreSQL.
- The operator (Kirill) and any employee with DB access, any compromised server admin, and any attacker with a DB dump can read everything.
- This is the current state per `APP_SPEC.md`. Every mainstream AI chat product runs this model today.

---

## 3. The Adversary × Option table

The table cells use three values:
- **YES** = adversary can read plaintext roleplay content (current or historical) at will.
- **NO** = adversary cannot read plaintext content; would require breaking a meaningful cryptographic or hardware guarantee.
- **PARTIAL** = adversary can read content under specific conditions (e.g., during one session, with insider access to specific keys, or via side channel that is hard to scale).

| Adversary | A — Client-side E2EE | B — TEE-hosted | C — Escrow (status quo) |
|---|---|---|---|
| **Operator (Kirill)** | NO. The server stores only ciphertext. Cannot decrypt without the user's master key, which never leaves the user's device. (Same threat model as Signal: "we cannot.") | **PARTIAL**. Operator cannot read VM-private memory directly while the workload is attested-running inside the CVM. But the operator still controls (a) the workload binary that runs inside the VM, (b) the orchestration layer around the VM, (c) every byte flowing into and out of the VM via I/O (the VM is a black box for memory but not for network/device traffic), and (d) the attestation policy. The operator can ship a modified workload that exfiltrates plaintext before encryption, can read plaintext in transit on the host-side NIC, and can replay or substitute the model. Honest framing: the operator cannot read *while the CVM is running unmodified Achiyon code with attested secrets released only inside the CVM*, but the operator *can* substitute that code at any time and is the party running the attestation verifier. | YES. Full plaintext access. |
| **Cloud provider (Azure/GCP/AWS infra layer)** | NO. Cloud provider sees only ciphertext blobs in object storage / DB. No way to decrypt. | **PARTIAL**. Cloud provider cannot read attested CVM-private memory (that's the entire point of CVM). But the cloud provider controls the hypervisor and (a) sees all I/O traffic to/from the CVM in cleartext (unless the application-layer TLS terminates outside the CVM, which is not how most confidential-LLM deployments work — the LLM API call to OpenAI/etc. typically exits the CVM and returns, or the model is hosted inside the CVM, in which case the access pattern is exposed), (b) controls attestation policy and can present stale or false attestation reports (subject to the cloud provider's attestation service not catching it), (c) controls firmware/OVMF/kernel the CVM boots from at launch (so a determined cloud provider can in principle backdoor the CVM image), and (d) can deny service. The "memory confidentiality" guarantee holds against the cloud provider; the broader "operator cannot read" guarantee does not. | YES. |
| **DB-dump attacker** (steals the database or storage) | NO. The DB contains ciphertext blobs only. Without master keys, useless. | NO, with a caveat. A DB dump of the *external* Achiyon DB is ciphertext for any encrypted rows. But a DB dump of the *attestation database, policy store, or in-flight plaintext rows* (e.g., conversation metadata before encryption) can leak. If the application architecture is clean (encrypt-then-store, keys held inside CVM), the dump yields ciphertext. If the architecture shortcuts (logging plaintext for debugging), the dump yields plaintext. | YES. |
| **Subpoena / court order to operator** | NO. The operator cannot comply with a court order for plaintext content. Can be compelled to hand over ciphertext, but it is by definition unreadable. The legal posture is the same as Signal's: "we cannot." (Signal's transparency reports: only registration date and last-seen are produced; no content.) | **PARTIAL**. The operator can be compelled to (a) hand over the attestation policy and CVM image, (b) testify about the deployment, (c) **operate the system in a specific way** — e.g., ship a modified CVM workload that logs plaintext, or present a stale attestation report. The CVM memory is confidential *while it runs*, but the operator is in the loop on what runs. The court can compel the operator to deploy malicious code in the same way it can compel a phone company to perform a wiretap. | YES. |
| **Compromised server admin** (rogue SSH/root on Achiyon host or orchestration layer) | NO. Server admin sees only ciphertext blobs. Same threat model as the DB-dump attacker — full filesystem access yields ciphertext. The only thing the admin can do is denial-of-service. | **PARTIAL**. Server admin cannot directly read attested CVM memory. But the server admin is the same person who controls the workload deployment, the orchestration, the attestation policy, the logs, the network, and everything *outside* the CVM. They can (a) substitute the workload at deploy time, (b) tap plaintext on the host-side NIC, (c) replay stale attestation reports, (d) feed malicious firmware/OVMF at CVM launch, (e) corrupt the attestation verifier. The CVM provides defense in depth, not isolation from anyone with admin on the orchestration layer. | YES. |
| **Malicious browser extension** | YES. A browser extension with content-script access to the Achiyon origin can read plaintext before the app encrypts it (the user is typing in the unencrypted input box, the extension sees the DOM), and can read the decrypted plaintext after decryption for display. This is well-documented: extensions with `<all_urls>` or specific host permissions have full DOM/storage access. (Neplox's published wallet-extension research and aegis-vault's threat model both note: "A malicious browser extension with content-script access to the origin can read localStorage directly via window.localStorage... The extension can still observe vault operations while the user is unlocked but cannot recover state from before extension installation, and cannot persist stolen state past a page reload.") Mitigation: Tauri 2 desktop/mobile shell isolates the webview from other extensions, and WebAuthn PRF keeps the master key in the OS keychain. In a pure browser, this is the dominant residual threat. | YES, same as A. The browser extension runs in the user's browser, not on the server, so the TEE does not protect against it. If Achiyon ships the unlock UI in a browser tab, the extension has the same access. Mitigation: same Tauri shell. | YES. |
| **Rogue employee** (Achiyon staff with DB or admin access) | NO. Same as compromised server admin: only sees ciphertext. Insider cannot decrypt user content. | **PARTIAL**. Same as compromised server admin. A rogue employee with admin on the orchestration layer cannot read attested CVM memory directly but can substitute code, tamper with attestation, tap I/O. Same caveats. | YES. |
| **(Bonus) Intel / AMD / hardware vendor** | NO. Hardware vendor has no special access to encrypted user content. | **PARTIAL**. The hardware vendor's root keys (AMD ARK, Intel root) are the root of the attestation chain. A vendor compromise (key extraction, supply-chain attack, government compulsion) lets an attacker forge attestation reports — see BadFuse / MilanLaunchy paper for a published demonstration of VCEK root-seed extraction on EPYC Milan. A vendor that issues a false certificate chain or breaks the silicon (e.g., enables a backdoor in microcode) can attest a malicious CVM as genuine. | NO. Not a relevant party. |
| **(Bonus) Compromise of attestation service operator** (e.g., MAA, Intel PCS, Apple transparency log) | NO. Attestation is not on the trust path for option A. | **YES**. Whoever runs the attestation verifier can present forged results. Microsoft's own advisory on MAA (CVE-2026-45642) demonstrates that this is a real attack surface, not theoretical. If Achiyon uses MAA on Azure, a Microsoft compromise or insider with sufficient access (or a successful phishing of attestation admin credentials, per Microsoft's "PIM + MFA + approval on activation" guidance) can validate forged CVM images. | NO. |
| **(Bonus) Coerced update / supply-chain attack on Achiyon's workload binary** | NO. An attacker who ships a malicious client update can read user content (because the client has the master key). But this is a per-user compromise: the attacker gets *that user*'s key, not all users. Detection is via signed builds (Apple/Google/Sigstore). | **YES / PARTIAL**. An attacker who compromises the Achiyon CI/CD pipeline can ship a modified CVM workload that exfiltrates plaintext before/at encryption. This is a fleet-wide compromise affecting every user. The attestation only attests to *some* workload — it does not by itself enforce that the workload is privacy-preserving. Apple's PCC addresses this with the public transparency log + researcher inspection, but Achiyon has neither. | YES. |

---

## 4. Reading the table — what each option actually delivers

### Option A — Client-side E2EE (proper Signal / Standard Notes / Cryptomator / Lumo U2L)

**Real adversary reading:**
- The operator, the cloud provider, the DB-dump attacker, the subpoena, the rogue admin, the rogue employee, the hardware vendor, and the attestation service are all **structurally incapable of reading user content**, because the master key never leaves the user's device and the server only stores ciphertext. This is the same posture as Signal, WhatsApp, Notesnook, Standard Notes, Cryptomator.
- The **one residual threat is the malicious browser extension** in the pure-browser case. This is mitigated by shipping the app in a Tauri 2 desktop/mobile shell (per APP_SPEC.md), where the webview is isolated from other extensions, and by using the OS keychain / WebAuthn PRF for key storage. The `.hermes/research/e2ee-engineering-cost-realism.md` and `e2ee-app-architecture-survey.md` documents both call this out.
- Even in the pure-browser case, a malicious extension can only access *active session* plaintext — it cannot recover state from before it was installed, and cannot persist stolen state past a page reload. (See aegis-vault's threat model: "the extension can only read encrypted IDB blobs — useless without the passphrase. The extension can still observe vault operations while the user is unlocked but cannot recover state from before extension installation.")
- **The honest cost:** Achiyon must rebuild the prompt/lorebook/memory pipeline as client-side WASM (per `e2ee-engineering-cost-realism.md` Path A: 26–38 engineer-weeks). The LLM inference problem has its own answer (encrypt-to-LLM-provider / local model / BYOK), covered in `e2ee-byok-relay-ux-survey.md`.

### Option B — TEE-hosted

**Real adversary reading:**
- TDX / SEV-SNP deliver "memory confidentiality against the host." They do **not** deliver "operator cannot read user content" as the marketing framing suggests.
- The hypervisor / cloud operator can still (a) ship a modified workload, (b) feed malicious firmware/OVMF at boot, (c) tap plaintext I/O, (d) replay stale attestation, (e) deny service, (f) launch published side-channel attacks (CipherLeaks, CacheWarp, Heracles, BadFuse). Each of these is a published, peer-reviewed demonstration that "memory confidentiality" is not "operator blindness."
- The **attestation service** is a new high-value compromise target. If Achiyon uses MAA / Azure's closed-source service, the cloud provider becomes the trust anchor for "the workload is genuine" — exactly the party the user is trying to avoid trusting. If Achiyon self-hosts the verifier, the operator runs both the inference workload and the thing that says the workload is unmodified, which is structurally incoherent for an "operator-blind" claim.
- The hardware vendor (AMD/Intel) is in the trust path via the ARK/root key, and the published attacks (BadFuse, microcode signature CVE) show this is not theoretical.
- **Frankly**: option B gives "cloud admin cannot directly read CVM memory while the attested workload is running" — which is a meaningful upgrade over option C but a far weaker claim than option A. The threat-model literature (kernel CoCo docs, AMD/Intel specs, every academic survey) is consistent on this.
- **Subpoena posture**: weaker than option A. The ability to compel the operator to ship a modified workload means a court can order Achiyon to read user content, even if it cannot read it on its own initiative. Option A is structurally immune (no one can be compelled to do the cryptographically impossible).
- **Engineering cost** per `e2ee-engineering-cost-realism.md` Path B: 28–44 engineer-weeks + $80–150K external CC audit + 25–40% higher cloud bill. Same prompt/lorebook engineering as A because the LLM call still requires plaintext somewhere.

### Option C — Escrow (status quo)

**Real adversary reading:**
- Every adversary except the malicious browser extension can read plaintext. The malicious browser extension is also a threat, but it has competition from a much wider field.
- This is the same model as every SaaS LLM today (ChatGPT, Claude.ai, Perplexity, ai.diy's hosted tier). The privacy story is "we promise not to log" rather than "we cannot."
- This is what `e2ee-app-architecture-survey.md` calls "Tier 4 (current Achiyon model, honestly labeled)" and what `e2ee-byok-relay-ux-survey.md` calls "Option C from the table... most commercial privacy-aware AI assistants run this mode."

---

## 5. The attestation-trust wrinkle, made explicit

The published attestation service architectures make the trust claim more concrete:

- **Microsoft Azure Attestation (MAA)**: "operationally out of the TCB" by running in SGX, but Microsoft's own documentation says "If you use MAA, you need to implicitly trust that MAA is correctly validating the SNP report and is free from malicious intentions... MAA remains closed-source." Microsoft recommends (a) using MAA, (b) using signed attestation policies, (c) Azure RBAC + PIM + MFA + JIT approval for the Attestation Contributor role, (d) audit logging and alerting. (https://learn.microsoft.com/en-us/azure/attestation/secure-attestation). **The attestation service operator's security controls become a primary attack surface.**
- **Intel DCAP / Quote Verification Service (QVS)**: open-source, "purely software component, and it doesn't require SGX capable platform to work. Although it can be additionally protected by running inside an enclave (for example by using Gramine)." Self-hostable, but the certificates and TCB info come from Intel's Provisioning Certification Service. (https://github.com/intel/SGX-TDX-DCAP-QuoteVerificationService, https://cc-enabling.trustedservices.intel.com/intel-sgx-tdx-pccs/02/overview/)
- **AMD KDS / VCEK**: VCEK certificates are signed by the AMD Root Key (ARK) via the AMD SEV Key (ASK), per the published specification (https://www.amd.com/content/dam/amd/en/documents/epyc-technical-docs/specifications/57230.pdf). VCEKs are derived from a chip-unique secret + TCB version. KDS is reachable over TLS at kdsintf.amd.com. Anyone can verify a quote; the trust is rooted in AMD's key and silicon.
- **Apple Private Cloud Compute (PCC)**: the most rigorous published model. Every production build is published to an append-only transparency log; the user's device checks that the workload matches a logged measurement; "user devices will be willing to send data only to PCC nodes that can cryptographically attest to running publicly listed software." The model is **only enforceable because Apple controls both the silicon and the device trust root.** PCC on Google Cloud (2025 expansion) adds NVIDIA H100 confidential compute, Intel TDX, and Google Titan root of trust, with "at least two separate roots of trust from independent vendors" for high-risk components. (https://security.apple.com/blog/expanding-pcc/) Apple's model also explicitly disclaims "side-channel attacks" being mitigated solely by CVM tech: "We do not rely solely on confidential computing technologies to mitigate attacks that leverage privileged access outside of a confidential VM, including side-channel attacks. We consider every component — from firmware through the host and guest OS stacks to application code — to be part of our trusted computing base, subject to our verifiable transparency and no-privileged-access guarantees."

**For Achiyon**: the realistic attestation posture is "use a cloud provider's MAA-like service and trust them" or "self-host the verifier, in which case the operator is the verifier, which defeats the purpose for an operator-blind claim." There is no third option that delivers "operator cannot read" — Apple's PCC only works because Apple operates the device trust root, which an independent SaaS cannot replicate.

**Concrete CVE that landed in this layer**: CVE-2026-45642 (June 2026) is an input-validation flaw in MAA allowing attestation spoofing with physical access. CVSS 3.1 = 3.9, integrity impact high. (https://www.sentinelone.com/vulnerability-database/cve-2026-45642/) Attestation services have CVEs.

---

## 6. The hard truth about TEE threat-model marketing

The published TEE threat model is "add a more powerful local adversary" (the host/hypervisor), not "remove the operator from the trust boundary." Every vendor whitepaper is consistent on this if you read carefully. The marketing phrase "confidential VMs protect data from the cloud operator" means "the cloud operator cannot directly read VM-private memory." It does **not** mean:

- The cloud operator cannot ship a malicious VM that exfiltrates the data it processes.
- The cloud operator cannot read VM I/O traffic (network and device data are not memory).
- The cloud operator cannot deny service to the VM.
- The cloud operator cannot present a stale attestation report.
- The cloud operator cannot backdoor the firmware/OVMF that the VM boots.
- A determined cloud operator with physical access cannot mount the published side-channel attacks (CipherLeaks, Heracles) or supply-chain attacks (BadFuse, microcode CVE).

When the Achiyon spec says "TEE-hosted with SEV-SNP — operator cannot read," this is the same category of overclaim that the AMD/Intel academic surveys and the kernel CoCo docs push back against. The honest claim is "the operator cannot read VM-private memory while the attested workload is running unmodified" — which is meaningfully different from "operator cannot read user content."

---

## 7. Synthesis — the recommendation that the threat-model data supports

The data in sections 1–6 supports the conclusion that the prior research files already converged on:

- **Option A** delivers the structural property the user actually wants ("operator, cloud provider, DB-dump attacker, subpoena, rogue employee, hardware vendor, attestation service — none of them can read my content"). Cost: rebuild prompt/lorebook/memory pipeline client-side; LLM call becomes BYOK or encrypt-to-provider.
- **Option B** delivers a meaningful but weaker property: "the cloud provider cannot directly read CVM memory while the attested workload runs." The operator, the workload-binary supply chain, the attestation service, the firmware, and the side-channel research all remain exploitable. Cost: comparable to A in engineering weeks + audit cost + higher cloud bill. Honest claim is "memory confidentiality against the host," not "operator blindness."
- **Option C** delivers the standard SaaS-LLM property: "operator and cloud provider can read," mitigated by policy ("we promise not to log") and access controls.

The product spec's framing of option B as "TEE-hosted — operator cannot read" oversells what TEE delivers. The accurate statement is "TEE-hosted — cloud provider's hypervisor cannot read VM memory directly while the attested workload is running; the operator and the workload-binary supply chain are still in the trust boundary."

For a true "operator cannot read my roleplay" guarantee — the property the user is asking for — **the threat-model data only supports option A.**

---

## 8. Sources

### TEE threat-model primary sources
- Linux kernel CoCo VM threat model: https://www.kernel.org/doc/Documentation/security/snp-tdx-threat-model.rst
- "Hardware VM Isolation in the Cloud" (ACM Queue / doi 10.1145/3623392): https://doi.org/10.1145/3623392
- "General overview of AMD SEV-SNP and Intel TDX" (FAU Erlangen): https://sys.cs.fau.de/extern/lehre/ws22/akss/material/amd-sev-intel-tdx.pdf
- "VIA: Analyzing Device Interfaces of Protected Virtual Machines" — explicit threat model section on malicious hypervisor: https://ar5iv.labs.arxiv.org/html/2109.10660
- "Confidential VMs Explained" (doi 10.1145/3700418): https://dl.acm.org/doi/10.1145/3700418
- VCEK / KDS spec: https://www.amd.com/content/dam/amd/en/documents/epyc-technical-docs/specifications/57230.pdf
- Intel TDX DCAP QVS: https://github.com/intel/SGX-TDX-DCAP-QuoteVerificationService
- Intel TDX Enabling Guide — Infrastructure Setup: https://cc-enabling.trustedservices.intel.com/intel-tdx-enabling-guide/02/infrastructure_setup/
- Intel SGX/TDX PCCS Overview: https://cc-enabling.trustedservices.intel.com/intel-sgx-tdx-pccs/02/overview/
- Microsoft Azure Attestation README: https://github.com/Azure/azure-sdk-for-js/blob/main/sdk/attestation/attestation/README.md
- Microsoft CVM Guest Attestation docs: https://github.com/Azure/confidential-computing-cvm-guest-attestation/blob/main/cvm-guest-attestation.md
- Microsoft Azure Attestation security recommendations: https://learn.microsoft.com/en-us/azure/attestation/secure-attestation
- Azure Attestation product page: https://azure.microsoft.com/en-us/products/azure-attestation
- Apple Private Cloud Compute (security blog): https://security.apple.com/blog/private-cloud-compute/
- Apple PCC Verifiable Transparency: https://security.apple.com/documentation/private-cloud-compute/verifiabletransparency
- Apple PCC Inspecting Releases: https://security.apple.com/documentation/private-cloud-compute/inspectingreleases
- Apple Expanding PCC (Google Cloud + NVIDIA + multi-vendor): https://security.apple.com/blog/expanding-pcc/

### Published attacks on SEV-SNP / TDX (the threat model in practice)
- CipherLeaks (USENIX Security 2021): https://yinqian.org/papers/sec21b.pdf
- "A Systematic Look at Ciphertext Side Channels on AMD SEV-SNP" (USENIX): https://radu.teodorescu.us/assets/pdf/mengyuan_sp2022.pdf
- CacheWarp (USENIX Security 2024): https://www.usenix.org/system/files/usenixsecurity24-zhang-ruiyi.pdf
- Heracles (CCS 2025, doi 10.1145/3719027.3765209): https://doi.org/10.1145/3719027.3765209
- Jailbreaking the AMD Secure Processor (USENIX Security 2026): https://www.usenix.org/system/files/usenixsecurity26-shen.pdf
- BadFuse / MilanLaunchy (arxiv 2605.12990, 2025): https://arxiv.org/html/2605.12990
- Google AMD microcode signature vulnerability: https://github.com/google/security-research/security/advisories/GHSA-4xq7-4mgh-gp6w

### Attestation service CVE
- CVE-2026-45642 (MAA authentication bypass): https://www.sentinelone.com/vulnerability-database/cve-2026-45642/

### Prior research in this directory (referenced throughout)
- `.hermes/research/tee-confidential-deployment-survey.md`
- `.hermes/research/e2ee-app-architecture-survey.md`
- `.hermes/research/e2ee-byok-relay-ux-survey.md`
- `.hermes/research/e2ee-business-model-survey.md`
- `.hermes/research/e2ee-engineering-cost-realism.md`

### Browser extension threat model references
- aegis-vault THREATMODEL.md: https://github.com/cyberdione/aegis-vault/blob/main/THREATMODEL.md
- Neplox "Attacking Crypto Wallets: Modern Browser Extension Security": https://neplox.security/research/attacking-crypto-wallets
- VALKYRI wallet pentesting guide: https://blog.valkyri.xyz/posts/wallet-extension-pentesting/
- RxDB IndexedDB encryption: https://rxdb.info/articles/indexeddb/indexeddb-encryption.html
- Signal Sealed Sender (NDSS 2021): https://www.ndss-symposium.org/wp-content/uploads/ndss2021_1C-4_24180_paper.pdf

---

## 9. One-paragraph verdict (for the parent agent)

The TEE threat-model literature is unambiguous: TDX and SEV-SNP deliver "memory confidentiality against the host / cloud hypervisor," not "operator cannot read user content." Every published academic survey and the Linux kernel's own CoCo threat-model documentation treats the host as a more-powerful local attacker, not a removed party. Published attacks in 2021–2026 (CipherLeaks, CacheWarp, Heracles, BadFuse, AMD microcode signature CVE) repeatedly demonstrate that "memory confidentiality" in TEE marketing is not the same as "operator blindness." The attestation service is a separate trust anchor — typically a closed-source cloud-provider service (MAA, Intel PCS) or a self-hosted verifier — and whichever party runs it becomes a new high-value compromise target (CVE-2026-45642 is a real example that landed in MAA). For Achiyon's three options: **option A (client-side E2EE) is the only one that delivers "operator cannot read user content" in the structural sense the user is asking for; option B delivers "cloud hypervisor cannot read CVM memory while the attested workload runs," which is a meaningful upgrade over option C but a much weaker claim than option A; option C delivers "operator can read," which is the current state.** The product spec's framing of option B as "operator cannot read" oversells the guarantee; the honest framing is "cloud-provider hypervisor cannot directly read CVM memory during attested execution."
