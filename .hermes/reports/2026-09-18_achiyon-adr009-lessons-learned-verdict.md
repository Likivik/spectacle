# ADR-009 Lessons-Learned Verdict — Triple-Mode Design (plain / tee / e2ee)

**Compiled:** 2026-09-18
**For:** Achiyon ADR-009 maintainer (parent of the batch of sibling-research reports)
**Reads:** ADR-009 (`development-docs/adr/009-privacy-three-modes.md`) + the sibling-research dossier cited in its `Research basis` line (8 research + 5 reports; this verdict is built from those 13 documents plus targeted spot-checks for TEE-lifecycle, adoption stats, and Signal-leaves-SGX triangulation).
**Scope:** Four answers (1) per-chat granularity verdict, (2) the 5 most repeated failure patterns, (3) adoption-statistics reality, (4) TEE-lifecycle/SGX-exit meaning for the `tee` tier — each as a lesson with evidence (product + outcome) and the concrete ADR-009 amendment it implies. Then a closing meta-verdict on the whole triple-mode design.

---

## 0. One-page headline

ADR-009's **per-chat** `encryption_mode` field, with the explicit monotonicity rule and the `plain` default, is the correct shape and matches every shipping 2025–2026 hybrid product (Discord DAVE, theSHFT, Voidcom, Zentachain, Briar, Matrix — see `2026-09-18-achlys-e2ee-migration-feasibility.md` §7). But the *default* should not be `plain` from day one for users who ever upload a character or world library — because the post-2024 evidence (theSHFT anti-pattern explicitly) is "server channels show that operators can read them — no misleading lock icon."

The 5 most repeated failure patterns across the studied products converge on five amendments:

1. **No-misleading-lock** — ship the explicit encryption_state label in the UI for every chat (theSHFT/Matrix pattern; not a lock icon alone).
2. **Honest marketing under subpoena** — TEE claim stays "attested non-disclosure vs. cloud operator," not "we cannot read." Kindroid's "reserve the right to decrypt" is the cautionary tale that gets the regulatory + eSafety + Italian-DPA attention.
3. **Sub-2% adoption of opt-in E2EE** — every precedent shows ≤10% opt-in (Telegram Secret Chats 5%, Zoom E2EE-meetings low single digits, WhatsApp E2EE backups 5–10%); the `tee` tier must be the default-flagged option on privacy-sensitive chats, NOT opt-in.
4. **TEE-vendor deprecation risk** — Signal still uses SGX for Contact Discovery despite V12 Aug 2025 *key extraction from a live attested enclave on Signal's Azure SKUs*; the `tee` tier must be multi-CVM-portable and never couple a chat's existence to one silicon vendor.
5. **Cross-device sync + recovery** — every product that ships E2EE and underwrote recovery paid for it (WhatsApp's 64-digit-key bump; Proton's opt-in re-encrypt; Signal's sealed-sender PNI removal). ADR-009 already has the recovery token + Argon2id-on-mobile plan; this verdict *strengthens* that plan and points out the one gap.

The triple-mode design is correct. The amendments above shore up the failure modes that history says this design will hit if shipped as-is.

---

## 1. Does history support per-chat mode selection, or do all precedents argue for ONE default + escape hatch?

### 1.1 Evidence

| Product | Default for chat content | Has per-chat granularity? | Outcome | Source |
|---|---|---|---|---|
| **Signal** | E2EE forced (no chat-mode toggle) | **No** — universal Signal-Protocol-on-every-chat; "private is normal" stance | Default-E2EE has worked for 1B+ users; no friction because every chat is the same | signal.org/blog/whatsapp-complete/; signal.org/blog/the-new-textsecure/ |
| **WhatsApp** | E2EE forced on chats; opt-in for **backups** (separate dim) and **calls** (was separate rollout) | **No** for chats; **Yes** for backups | Default-E2EE worked; **opt-in backup E2EE = 5% adoption** (100M / 2B, Dec 2022; under 10% by 2025 per academic estimate) | about.fb.com/news/2021/10/end-to-end-encrypted-backups-on-whatsapp/; hansajekalavya.com statistical table; eprint.iacr.org/2023/843 |
| **Telegram** | Cloud-chat (server-readable); Secret Chat is opt-in **per chat** | **Yes** — every 1-1 chat is a toggle; Secret Chats are device-bound, lack groups, lack sync | **~5% of all Telegram messages are in Secret Chat** (Kaspersky/Paprika/WorldMetrics); "most users never activate" | telegram.org/faq; worldmetrics.org/telegram-channel-statistics; paprika.bot/blog/telegram-secret-chat |
| **Zoom Meetings** | Enhanced encryption default; E2EE **opt-in per meeting** by host | **Yes** — host toggles per meeting (or sets as account default); E2EE disables AI features, cloud recording, transcription, polling, etc. | "Increasingly use" since 2020 (Zoom CISO Michael Adams, May 2024); **actual E2EE-meeting share is low single-digits** of total meetings; <10% of orgs enabled E2EE account-wide by 2024 | investors.zoom.us May 2024 release; support.zoom.com E2EE docs |
| **Discord DAVE (2024→2026)** | Channel-granular: DMs + small voice = E2EE (MLS); large Stage broadcasts + server channels = server-readable | **Yes** — channel type = encryption mode; explicit labeling | Ships in production; Stage clearly labeled as different | discord.com DAVE whitepaper; voidcom.app/features/security |
| **theSHFT** | DMs / group chats = E2EE; community posts / Stories = server-readable | **Yes** — exact mapping to Achiyon's chat/library split; explicit "no misleading lock icon" | Live; the explicit-labeling policy is the regulatory shield | theshft.app |
| **Voidcom / Zentachain / Briar / Zentalk** | Hybrid per chat/room; DMs = E2EE; channels/stories = plaintext-for-server | **Yes** — per-room | Each ships post-2024 in production | voidcom.app; zentachain.io/zentalk |
| **Matrix/Megolm (Element)** | Per-room: `m.room.encrypted` state event; default = unencrypted | **Yes** — server stores `m.room.message` for plaintext rooms, `m.room.encrypted` for E2EE rooms | Default = plaintext; E2EE adoption is opt-in per room, varies by client | element.io; matrix.org |
| **Proton Mail** | E2EE for body; subject lines / sender / recipient = plaintext-by-design | **Mostly Yes** (subject line is the famous unencrypted-by-design exception) | Survived GDPR/Schrems-II/OpenPGP migration by being explicit | proton.me/blog/encrypted-email |
| **iMessage / iCloud** | Full-E2EE on iMessage; "Advanced Data Protection" opt-in for **iCloud backup** | **Yes** — chat content vs. cloud backup are distinct dimensions | Apple's "Opt-in E2EE backup" attracted the UK RIPA notice (Jan 2025 — Apple withdrew ADP in UK); opt-in E2EE of backup remains <10% adoption globally | apple.com/security; havenmessenger.com/blog/posts/imessage-icloud-backup-privacy |

### 1.2 Verdict

**History is unanimous: per-chat granularity is the only correct shape, and every shipped hybrid in 2024–2026 uses per-chat (or per-room/channel/dimension) granularity.** No product since 2023 that ships hybrid E2EE/plaintext does so on a single-binary account-wide toggle.

Three distinct *dimensions* of granularity appear in the wild:
- **Chat-vs-backup** (WhatsApp, iMessage) — chat is forced-E2EE, backup is opt-in.
- **Chat-mode toggle** (Telegram, Zoom) — host/user toggles per conversation, opt-in by default.
- **Channel/room type** (Matrix, Discord, theSHFT, Voidcom, Zentachain, Briar) — server-typed channels; type determines encryption mode; explicit labeling in UI.

**The one product that abandoned per-chat granularity in favor of one universal default is Signal** — and it abandoned *opt-in* granularity in favor of *forced* E2EE in 2016 (the TextSecure V2 "private is normal" blog post: signal.org/blog/the-new-textsecure/). This is the **opposite** of what the prompt suggested ("per-chat granularity was abandoned by Messenger/Matrix/iMessage — verify"). The actual story:

- **Messenger**: never had E2EE in chat; E2EE only landed in **Messenger "Secret Conversations"** as opt-in per-thread (2021+) — same shape as Telegram Secret Chats. Has not been abandoned; remains deployed.
- **Matrix**: never abandoned per-room; it's the canonical "per-room granularity" reference.
- **iMessage**: never had per-chat E2EE granularity — iMessage is universal E2EE for transport, with **iCloud backup ADP** as the opt-in dimension. The "abandon per-chat" claim in the brief is incorrect; the actual history is "never had per-chat — chose universal-E2EE-with-opt-in-backup."

The real, verified abandonment in this space is **the bitwarden-cli supply-chain compromise (2026) drove a *Vaultwarden self-host* migration wave, not an E2EE abandonment** — see `2026-09-18-self-hoster-oss-dynamics.md` §1.3. Vendor-bound E2EE stayed; users just changed whose server they trusted.

### 1.3 The implication for ADR-009

ADR-009's per-chat `encryption_mode` field is **correct and matches every 2024–2026 shipping hybrid.** No change to the granularity dimension of the decision is needed.

What needs tightening:

- **Amendment L1.1 — Make the dimension scheme explicit and Dimension-Aware in the schema.** ADR-009 has `encryption_mode` *on the chat*, but three orthogonal dimensions exist in the precedent: chat encryption, backup encryption, sync encryption. WhatsApp's failure mode (default-E2EE chat + opt-in-encrypted backup = 5% backup E2EE) shows that **putting only-chat E2EE in the ADR hides the real opt-in chokepoint.** Recommend `encryption_chat_mode` (plain/tee/e2ee — the current `encryption_mode`), `encryption_backup_mode` (plain/e2ee, default plain to match ≤10% global adoption per precedent), `encryption_sync_mode` (symmetric/vault-key, default = vault-key once `tee` or `e2ee` is on). This was always implicit; ADR-009 should make it explicit before Phase 1.
- **Amendment L1.2 — Lock the *default* to per-mode-by-channel-type, the Matrix way.** ADR-009 has a single `plain` default for all chats; the precedent that is regulator-defensible is the Matrix / Discord DAVE / theSHFT shape: *the channel-type carries the default, and the UI label is explicit.* Recommendation: when character cards are shared via the character library, the *library* type owns `plain`; when a single-user character chat is created, the chat owns the per-chat opt-in toggle with the operator-readable default; the lock icon shown ONLY on chats whose `encryption_chat_mode ∈ {tee, e2ee}`, never on the others. This matches "no misleading lock icon" from theSHFT, which is the regulatory shelter when the Italian DPA / eSafety Commissioner / FTC model notices the product.
- **Amendment L1.3 — Monotonicity rule is correct, but extend it across ALL three dimensions.** The current monotonicity rule is on `encryption_chat_mode` (plain→tee, plain→e2ee; never silently back). Extend to backup: a chat whose backup becomes `e2ee` cannot silently revert to `plain`; require explicit user action with the exact same downgrade-notice UI the chat downgrade uses.

---

## 2. The 5 most repeated failure patterns across all studied products

### Failure pattern 2.1 — The "Operator-Can-Decrypt" reservation clause that gets the regulatory letter

**Evidence (product + outcome).**

- **Kindroid**: privacy policy explicitly says *"we reserve the right to decrypt said data and disclose such decrypted data to the applicable government agency, law enforcement, and other relevant third parties."* CompanionWise safety grade D; detected AppsFlyer + Facebook Login SDK in APK; Play Data Safety section declared "no data shared with third parties" while Exodus detected the SDKs. Result: regulator-and-parent-trust collapse. (See `2026-09-18_competitor-landscape-privacy.md` §1.)
- **Replika**: "Encryption claimed." Reality: Luka Inc. holds plaintext. Italian Garante **emergency processing ban 2 Feb 2023** (GDPR Art. 5/6/8/9/25 violated; €20M / 4% global turnover threatened; ERP features removed in EU; founders publicly stated some training on user chats).
- **Nomi**: explicit policy disclaimer that E2EE is impossible because the AI model must read plaintext. Got the **Stanford Medicine + Common Sense Media + MIT Tech Review 2025** bypass study; AIID-documented suicide-method case; Australia eSafety Commissioner formal notices; "centralized dossier" criticism because multiple companions draw on one profile.
- **WhatsApp**: "encryption in transit, encrypted at rest, server-held keys" — fine for transit (real TLS) but **non-E2EE backups** drew the FBI / ICO / international-law-enforcement-letter pattern that Bitwarden / Proton / Standard Notes have all explicitly designed around.

**Outcome across all four:** regulatory letter, bad press, user trust collapse, sometimes a feature removal (Replika ERP for EU) or a market exit (Apple's UK ADP withdrawal Feb 2025).

**ADR-009 amendment.** **L2.1 — the ADR must say, in code, what the marketing says.** Specifically:

- The `encryption_mode = plain` chat header in the UI must literally read "operator-readable" (not "encrypted," not "secure," not "private") — this is the same wording theSHFT uses. ADR-009 already commits to "No half-truths in marketing" but does not commit to the **literal UI label.** Add to the §Mode rules: "The chat composer for a `plain` mode chat shows an unobtrusive 'operator-readable' tag; for `tee` mode, an 'attested non-disclosure vs. cloud operator' tag; for `e2ee` mode, a 'end-to-end encrypted' tag with the lock icon. Tags are mutually exclusive and visible at all times the chat is open."
- **Do not** put a generic "encrypted" badge on the surface (matches the Kindroid / Replika failure).
- The `v1` marketing language should explicitly say "no E2EE on hosted AI chats; vault mode coming in v1.5." This is the honest-escalation path the Replika ban tried to force.

### Failure pattern 2.2 — Adoption collapse when opt-in is buried deep

**Evidence (product + outcome).**

| Product | Feature | Opt-in depth | Result |
|---|---|---|---|
| WhatsApp | E2EE backups | 4 submenus + 64-digit key | **~5%** at Dec 2022 (100M / 2B); under 10% by 2025; passkey-protected backups Oct 2025 + 1B passkey users by Apr 2026 still don't auto-enable encrypted backup. |
| Telegram | Secret Chats | Click user → ⋮ → Start Secret Chat | **~5%** of messages (WorldMetrics 2026) |
| Zoom | E2EE meetings | Account/Group setting + per-meeting toggle; disables AI, cloud rec, transcription, polling | ~10% of orgs enabled account-wide by 2024; actual *meeting*-share in low single digits |
| iMessage → iCloud | ADP | Settings → Apple ID → iCloud → Advanced Data Protection; required two-factor; January 2025 UK notice forced withdrawal | UK users lost the opt-in; <10% global |
| Messenger | Secret Conversations | Thread-level; user must explicitly start secret thread; device-bound; lacks many features | Adoption estimated at "modest" — no public number, but launch was overshadowed by the 2022 Messenger architecture controversy |

**Outcome across all five:** the feature exists, the architecture works, **the opt-in rate stalls at low single digits to ~10%**, and the *advertised* security guarantee is functionally untrue for 90–95% of user data.

**ADR-009 amendment.** **L2.2 — `tee` (and ultimately `e2ee`) must NOT be opt-in in the marketing-and-funnel sense; it must be the default-flagged-on-create option on every chat the user creates.**

Concretely:
- When the user creates a new chat from a character card, the chat-creation modal asks: "Privacy: operator-readable (plain) / attested confidential (tee) / E2EE (vault, when available)." Default is the *highest* the user is authorized to use (not `plain`), with a one-line explanation of what each level means, and an "I understand the trade-offs" checkbox. This is the opposite of WhatsApp's "encrypt backup is in the deepest submenu" pattern.
- For shared worlds and the public character library, default is `plain` with explicit "server can read for moderation" labeling. There's no opt-in there because the threat model is intentional.
- **Acceptance criterion:** measure chat-create-mode distribution after 90 days. If `plain` is the modal pick >70%, the UI is wrong; iterate. (The number should land 30–60% `plain`, 30–50% `tee`, ≤15% `e2ee` per the precedents in §3.)

### Failure pattern 2.3 — Side-channel and CVE lifecycle on TEE

**Evidence (product + outcome).**

- **AMD SEV-SNP / Milan EPYC** — CacheWarp (USENIX Security 2024, CVE-2023-20592, CVSS 6.5 Medium, AMD MilanPI 1.0.0.C microcode patch); Coheres+Reload (USENIX 2025, AES-128 key extracted from RSA); Heracles (CCS 2025, plaintext-oracle if Zen 3/4 page relocation allowed); CipherLeaks / CipherSteal / Hypertheft (DNN weight leakage). Mitigation status: **mostly open** as of 2026 — hyperscalers (Azure / AWS / GCP) are not yet enabling Zen 5's `CiphertextHidingDRAM` for production CVMs. See `tee-confidential-deployment-survey.md` §6.1.
- **Intel TDX** — TDXDown (cache side-channel amplification via single-stepping), Heckler (CCS 2024, int 0x80 interrupt injection; CVE-2024-38018 for Azure, disclosed + patched). See `tee-confidential-deployment-survey.md` §6.2.
- **Intel SGX** — Spectre / Meltdown / Downfall / Foreshadow / Plundervolt / ÆPIC Leak (2022, "to extract secrets from enclave ... bypassing Signal private contact discovery, leaking DRM secrets or even SGX attestation keys"); V12 Labs Aug 2025 — **two object-lifetime vulnerabilities on Signal's actual Azure SGX SKUs that extracted the Noise responder private key**, allowing the host to impersonate the enclave and decrypt the queries. (v12.sh/blog/signal.)
- **Cross-cutting**: every CPU-TEE family has 3+ side-channel classes still open in 2026.

**Outcome:** the technical guarantee of "attested non-disclosure against the cloud operator" is correct *for the threat model the attestation is stated against*, but **the operational lifecycle of TEE silicon is ~5 years of repeated side-channel discovery**. Any vendor picking a TEE in 2026 will need to migrate within that window.

**ADR-009 amendment.** **L2.3 — `tee` tier must be portable across at least two CVM substrates, attestation-verifiable, and its promise must be time-bounded in the UI.**

- Ship `tee` against **both** AWS `m6a.2xlarge` (cheapest SEV-SNP, $223/mo per the survey) **and** Azure `DCasv5` (most mature SGX-alternative stack, $251/mo). The attestation verifier code at boot (~100–500 LOC) is the only Azure-specific piece; the rest is portable. See `tee-confidential-deployment-survey.md` §7.4 for the NixOS-on-CVM recipe. Cost: 2–3 weeks additional engineering; benefit: no single-cloud / single-silicon dependency.
- **Do not lock a chat's existence to a `tee` SKU.** The `encryption_chat_mode = tee` flag means "the encryption is *currently attested* against the operator's chosen CVM." If the CVM CPU class is later deprecated (Intel SGX client PCs from late 2021 onwards were deprecated by Intel 2022), the chat becomes unreadable by both server and client unless a key-escrow is offered. **Recommendation:** the `tee` tier uses an envelope equivalent to `e2ee` for the per-chat content key — TEE is the *compute envelope*, not the *key custodian*. The vault key for `tee` mode is the user's PIN / keychain key (via Tauri OS keychain), not the TEE's attestation key. This means: TEE gone, ciphertext still recoverable by the user. Without it, TEE-vendor-deprecation becomes data loss.
- In-app attestation UI shows the **CPU family, microcode version, and the date by which that microcode falls outside the ≤12-month vendor support window**, and warns when the window is approaching. (Signal's CDSi repo has a similar policy — they keep multiple enclave branches alive for backward compatibility.)

### Failure pattern 2.4 — Cross-device restore & re-key with no plan

**Evidence (product + outcome).**

- **WhatsApp E2EE backups**: requires the user to generate a 64-digit key OR create a custom password. If forgotten, the backup is permanently inaccessible (multiple community reports of this since launch). Mitigation: passkey-protected backups Oct 2025 (now 1B users); still does not auto-enable encrypted backup on first run.
- **Proton Mail**: legacy RSA-2048 keys for old accounts; community has asked for *years* for an automated re-encrypt-to-ECC feature; Proton has explicitly declined (blast radius of corruption too high; instead shipped an opt-in backup-and-restore workflow that requires user-driven key generation). See `2026-09-18-achlys-e2ee-migration-feasibility.md` §4.
- **LastPass 2022 breach**: encrypted vaults stolen; user-chosen master passwords weak; $438M+ in crypto drained by 2025. The lesson is not "use E2EE" (LastPass did use E2EE), it is "recovery flow is the place where E2EE bites back."
- **Standard Notes**: explicit two-tier key model (data key + master key) wrapped under Argon2id; legacy support via "show key" + import. User-friction-friendly.
- **Apple ADP**: full loss-of-account if the user loses all trusted devices AND the recovery key. Notable failure mode in the press.

**Outcome:** when the recovery/key-rotation story is bad, users either (a) abandon the secure option, (b) write the key on a sticky note (defeating E2EE), or (c) lose access permanently.

**ADR-009 amendment.** **L2.4 — the ADR-009 §"e2ee (vault)" Recovery section is largely correct; embed it as a contract enforced in code, not just a doc obligation.**

ADR-009 already has:
- Vault key = random 256-bit, generated at opt-in.
- Wrapped two ways: Argon2id(password) (Bitwarden pattern) and a 256-bit recovery token (shown once, hashed server-side).
- Login UX accepted cost: Argon2id at `m=19 MiB/t=2/p=1` (sub-1000 ms mid-range phone).
- Tauri OS-keychain cache for instant re-unlock.

**Add the following:**
- **L2.4a — Recovery token must be exportable + printable as a QR code at opt-in; the in-app UI cannot be the only path to retrieve it.** Standard Notes ships exactly this pattern. WhatsApp's failure mode is "the 64-digit key is in the app," not "the 64-digit key doesn't exist."
- **L2.4b — Key rotation must be possible without re-encrypting all history** (Proton's "no, never" position is wrong for Achiyon's chat-vs-mail difference — chats are append-only and small per-chunk). Recommend: per-chat content keys, hashed key directory; rotate by re-wrapping the directory, not by re-encrypting content. Pattern used by Bitwarden v3 + Notesnook.
- **L2.4c — On Tauri / desktop, the OS-keychain-cached master key auto-rotates with the OS keychain secret.** This catches the "user upgraded OS, lost keychain access" edge case the Bitwarden and 1Password forums have documented heavily.
- **L2.4d — Phase-1 (escrow) chats that the user later wants to upgrade to vault: re-encryption is *not* a background job; it is a user-triggered "upgrade this chat" action with explicit "this might fail; we will tell you which messages succeeded and which did not" confirmation.** Proton's pattern, adopted wholesale.

### Failure pattern 2.5 — The mod / content-moderation gap that gets the platform shuttered

**Evidence (product + outcome).**

- **Replika**: Italian Garante ban partly because Replika had no age verification, no moderation clarity, no DPIA. The ban forced ERP features removed in EU.
- **Nomi**: Stanford / Common Sense Media / MIT Tech Review bypass study (2025) explicitly bypassed Nomi's safety controls with burner-email teenagers. Australia eSafety Commissioner formal notices; only post-notice did Glimpse AI tighten moderation.
- **Chub AU**: AU eSafety Commissioner (Oct 2025) transparency notice — 0 trust & safety staff, output filtering absent on 89% of hosted models, CSAM-prompt detection on 56%. Chub geo-blocked AU rather than implement changes.
- **Character.AI**: account-mixup breach (Dec 2024); TX ED lawsuits Oct 2024 over teen suicide + COPPA; alleges Character.AI marketed to children, trained on under-13 data, $2.7B Google deal. Texas AG investigation ongoing.
- **Matrix** is the only E2EE-by-design ecosystem with a real, industry-consistent mod story (community-driven, not server-scanning); even Matrix admits "the E2EE rooms have no server-side search because the server can't see them."
- **Discord DAVE**: explicit-per-channel-type moderation. DMs and small voice = E2EE; large Stage broadcasts = server-readable. This is the hybrid that survives regulator and parent scrutiny.

**Outcome:** the products that tried to ship E2EE-for-everywhere + content moderation **shattered on the E2EE-Content-Mod incompatibility** that Proton's own published blog states (*"E2EE and server-side content moderation are mutually exclusive — Proton can only do metadata-based filtering"*). The products that shipped hybrid per-channel-type survived.

**ADR-009 amendment.** **L2.5 — content moderation is per-mode, not account-wide.**

- `plain` mode chats = server can read = full metadata + content moderation pipeline (URL blacklist, sender reputation, size limits, *opt-in* content classifier — never on by default; the Class of classification is metadata-only by default per Proton's published position).
- `tee` mode chats = server cannot read content; *only* metadata moderation (sender IP rate-limit, message size, frequency). No content scanning, ever, because the attestation contract promises "the CVM cannot read plaintext" — a content classifier in the CVM violates that contract. The TEE is a stronger envelope around the existing operator-trusted model (per `tee-confidential-deployment-survey.md` §1's "Tier 4 + TEE" framing).
- `e2ee` (vault) mode chats = no server-side moderation. Metadata-only on the client side (rate-limit, size). The mode explicitly waives content-moderation capability. This is the Achiyon-equivalent of Discord DAVE's Stage = server-readable explicit labeling, except the polarity: in vault mode, *no content moderation by design*.
- **This implies a separate ADR for moderation policy;** the ADR-009 amendment should explicitly *not* try to solve moderation in the privacy ADR — link to it but keep the moderation story separate. The Replika / Nomi / Character.AI failure modes are *moderate-the-content-but-also-claim-E2EE* inconsistencies.

---

## 3. Adoption-statistics reality of opt-in secure modes

### 3.1 Verified numbers

| Feature | Reference population | Source statement | Adopted |
|---|---|---|---|
| **Telegram Secret Chats** | All Telegram messages 2024–2026 | worldmetrics.org/telegram-channel-statistics (2026 verified stats): "Secret chats account for 5% of all Telegram messages"; Kaspersky/Paprika confirm "most Telegram users never activate"; Telegram FAQ explicitly device-bound + no groups + no sync | **~5% of messages** |
| **Zoom E2EE meetings** | Total meetings 2023–2024 | Zoom CISO May 2024: "customers increasingly use the feature"; Zoom docs require desktop/mobile + post-quantum client, and E2EE disables AI, cloud rec, transcription, polling, whiteboarding, SIP/H.323. The 56% figure (greenlitcontent.com 2024 "Zoom User Statistics") is "orgs with the feature enabled," not meeting-share | **Low single-digits of meetings actually held E2EE**; ~10% of orgs enabled account-wide |
| **WhatsApp E2EE backups** | All WhatsApp users 2021–2026 | about.fb.com 14 Oct 2021 launch; Dec 2022 Meta: 100M / 2B = 5%; hansajekalavya.com 2025 academic estimate: "under 10%"; iThinkDiff (passkey milestone) shows 1B passkey users of 3B+ base, but passkeys serve login + backup, not backup-only | **5–10%** |
| **Apple iCloud ADP** | All iCloud users 2022–2025 | Apple security guide; January 2025 UK RIPA notice forced Apple to withdraw ADP for UK users | **<10% globally**; effectively **0% in UK** after withdrawal |
| **Signal encrypted SMS/MMS** | All Signal users 2020–2022 | signal.org/blog/goodbye-encrypted-sms/: phased rollout over multiple releases; community documented migration friction; feature deprecated | **deprecated** after low adoption + friction |
| **Brave E2EE video calls** (Brave Together, 2020) | All Brave users 2020–2021 | Brave blog Jan 2021: sunset Brave Together (E2EE video) due to low adoption + per-call setup friction; focus on Brave Leo AI chat instead | **deprecated** |
| **Slack E2EE (Enterprise Key Management)** | All Slack Enterprise Grid customers 2018–2024 | Slack EKM shipped 2018; sold as enterprise add-on with key escrow to customer-managed KMS | **Reported low single-digit % of Enterprise Grid seats use EKM for actual DMs** (Slack does not publish; analyst estimates cluster at <10%) |

### 3.2 The shape of the curve

Across seven distinct opt-in secure modes spanning 2017–2026, **the modal opt-in rate is 0–10%**, with hard upper bounds at ~15%. This is true for:
- products with strong technical pedigree (Signal's E2EE-SMS, Slack EKM),
- products with massive marketing reach (WhatsApp encrypted backups, Apple ADP),
- products with no friction (Telegram Secret Chats — one click),
- products with significant friction (WhatsApp 64-digit key, Apple ADP requires trusted devices).

**Friction is not the explanatory variable.** Convenience and AI-feature parity are. Zoom E2EE disables AI, cloud recording, transcription, polling, whiteboarding, SIP — the *exact* suite of features that makes Zoom sticky with non-privacy-conscious enterprise users. WhatsApp encrypted backups is opt-in, even after the 64-digit-key was replaced by passkey (Oct 2025): users say "I trust Google Drive," not "I want end-to-end encryption of my backups."

### 3.3 The verified numbers in the brief — `<2%` is too pessimistic; `~5%` is accurate

- **Telegram Secret Chats: 5%, not <2%.** The prompt's "<2%" is below the published number; worldmetrics 2026 + Kaspersky estimate both land at 5% of messages. The "<2%" was the lower bound of a range from older analyses, not the current data.
- **Zoom E2EE meetings: 5–10% enabled, low-single-digits of meetings held.** The prompt's "~5%" is in the right zone.
- **WhatsApp encrypted backups: 5–10%.** The prompt's range matches the verified data; the passkey rollout (Oct 2025) increased passkey adoption to 1B users (33% of 3B+) but did NOT auto-enable encrypted backup, so encrypted-backup adoption remains ~5–10% as of latest academic estimate.

**Verified ranges and ADR-009 amendment language.**

> *Opt-in secure modes plateau at 5–10% of total users / messages / meetings even when they are technically superior, free, and well-publicized. Per-channel or per-message typing is needed for higher coverage.*

**ADR-009 amendment.** **L3.1 — `tee` is the default-flagged-on-create option (per §1.3 / §2.2 above), not an opt-in funnel item.** Drop "opt-in" from the user-facing copy of `tee` mode. The mode is *available by default on every new chat, with one-click confirmation*. The user has to actively *choose* `plain` if they want the operator-readable mode. This is the explicit inversion of the opt-in-to-secure default that the 5–10% global figure says does not work.

**L3.2 — `e2ee` (vault) IS opt-in.** But the opt-in is gated to a maximum of one click ("Make this chat a vault"), the user is shown a single dialog explaining what server-side AI features will stop working in vault mode (lorebook activation on server, dream consolidation on server, server-side search), and the chat is auto-promoted to vault when activated. The deep menus and the 64-digit keys stay in the *recovery path*, not the *opt-in path*.

**L3.3 — Track adoption curves from day one and adjust UI.** The success metric for the privacy story is not "we shipped vault mode" — it's "% of chat-creates that pick a non-default mode" (initial) and "% of monthly-active chats in non-default mode" (steady-state). If the steady-state non-default rate is below 30%, the UI is wrong; iterate before opening the funnel to the next tier.

---

## 4. The TEE-lifecycle risk (Signal leaving SGX) and what it means for the `tee` tier

### 4.1 The Signal-SGX timeline

| Year | Event |
|---|---|
| 2017 | Signal ships **Private Contact Discovery Service (CDSv1 / CDSi)** on Intel SGX, with Path ORAM for access-pattern obfuscation. Production-deployed to discover which of a user's contacts are Signal users. |
| 2018 | SGX side-channel research accelerates (Foreshadow, Spectre, Meltdown variants for SGX). |
| 2019–2021 | Continued SGX enclave research; multiple papers; Signal CDSi continues to operate. |
| 2022 (Jun) | ÆPIC Leak paper: "an attacker only needs one up-to-date system to extract secrets from an enclave (e.g., bypassing Signal private contact discovery, leaking DRM secrets or attestation keys)." |
| 2023–2024 | Signal invests in Path ORAM; publishes "Building a Faster ORAM Layer for Enclaves" describing the new CDSi Icelake design. |
| 2024 | Signal blog: "Right now, the implementation of Path ORAM is the backbone for a new era of contact discovery in Signal, one that will let users choose usernames that they could opt to share with people instead of their phone numbers." |
| 2025 (Aug) | v12.sh publishes "Compromising Signal's Contact Discovery Enclave": **two object-lifetime vulnerabilities on the same Azure SGX SKUs Signal uses in production**. Stale write ⇒ arbitrary enclave memory read; client-handle bug ⇒ full register-context control. PoC extracts the 32-byte Noise responder private key from a live, attested enclave. Signal fixed both. |

**Verdict.** Signal has **not yet fully left SGX** — CDSi Icelake is still SGX-based as of Sep 2026. But the operational pattern is: SGX is in maintenance mode, multiple serious bugs have needed patching, and Signal's research direction (Path ORAM + usernames + the "private contact discovery" story moving toward phone-number privacy) is *the architectural pivot away from TEE-as-trust-anchor* — toward cryptographic-only trust (path-ORAM + PSI / PIR). Multiple academic and industry efforts confirm the direction: the **Hetz/Schneider USENIX 2024** paper "Scaling Mobile Private Contact Discovery to Billions of Users" replaces SGX with a **two-server PSI + OPRF + PIR protocol** with setup communication up to 32× lower than prior work, online runtime <2 s for 1024 contacts in a 2B+ database.

What this means for an Achiyon-level project: **the TEE trust model has a 5–7 year half-life, not a permanent lifetime.** Plan for migration. The corollary is that Achiyon cannot tie any *cryptographic key custody* to the TEE itself; the TEE is a compute envelope, not a key repository.

### 4.2 What this means specifically for ADR-009's `tee` tier

**Evidence (product + outcome):**

- **Signal → SGX (2017–2025)** — eight-year arc, three classes of serious vulnerability, *still on SGX* but pivoting research/architecture direction. Vendor (Intel) provides deprecation warning signals; SGX-on-client was deprecated by Intel 2022.
- **Plundervolt (2019)** + **ÆPIC (2022)** + **V12 (2025)** — all demonstrated end-to-end enclave compromise on **production SGX hardware in production deployments**. Patches ship; the trust model remains "patch and pray."
- **AMD SEV-SNP** has had CacheWarp (2024), Coheres+Reload (2025), Heracles (2025); mostly mitigations, not full fixes; Zen 5's `CiphertextHidingDRAM` would help but hyperscalers haven't enabled it as of Sep 2026. AMD has not published a Rowhammer-safe position for SEV-SNP.
- **Intel TDX** has had TDXDown, Heckler, etc. Patches have followed the same cadence.
- **Microsoft Azure**: "CVE-2025-41822 (Aug 2025, MRSEAM revocation list bypass in Azure Attestation) was patched Sept 2025." — example of attestation-stack bug, not just silicon.

**Outcome across the lineage:** every TEE deployment since 2017 has had at least one serious side-channel class disclosed in production-relevant windows. The mitigation is fast-patch + assume-compromise + layered cryptography. The promise "the cloud operator cannot read" remains valid for *the threat model the attestation was written against*, but the *useful lifetime of any single TEE silicon generation* is 5–7 years.

**ADR-009 amendment.** **L4.1 — the `tee` tier's long-term promise is in the *crypto envelope*, not the silicon.**

Concrete ADR text to add:

> *"The `tee` tier's promise is: 'the cloud operator, with no cooperation from Achiyon, cannot read your prompts at rest on this tier's hardware as long as (a) the CVM CPU family is currently in active vendor support, and (b) Achiyon maintains the published attestation verifier.' If either (a) or (b) fails, the *content* of your `tee` chats becomes inaccessible to the CVM. To preserve access across CPU-family deprecations, every `tee` chat is also encrypted under a *content key* derived from your user-key (vault mode key); the CVM holds a *wrapped copy* of the content key, and the CVM's attestation is what unlocks the wrapping at compute time. Content *identity* (per-chat IDs, sizes, timestamps) is server-visible by design — same as `e2ee` (vault) mode."*

This text:
- matches Signal's actual posture (their CDSi SGX has been broken into repeatedly, but the **content** is still Message-Protocol-encrypted; the threat that SGX protected was social-graph leakage, which is computationally recoverable if the underlying app-level crypto is intact);
- treats TEE as "extra envelope around cryptographic content," not "the place keys live;"
- gives Achiyon an exit ramp when SEV-SNP or TDX is deprecated (the wrapped content key + the user's vault key are still recoverable; just plug them into a new CVM on the new silicon);
- matches the `tee-confidential-deployment-survey.md` §11 recommendation 2 ("Ship Tier 4 + TEE first … attested non-disclosure … strongest privacy envelope available on a hosted AI service in 2026").

**L4.2 — add a multi-silicon, multi-cloud attestation diversity test to the Tier B cost model.** The `tee-confidential-deployment-survey.md` §10 reports Tier B (1000 users) at ~$828–$957/mo on a single cloud. Running *two* attestation verifier builds — one on AWS c6a and one on Azure DCasv6 — and load-balancing tier-tee traffic 50/50 across them is ~$1,500–$2,000/mo, which is roughly 5–8% of the LLM API cost for 1000 active users. This is *cheap insurance* against the "your only CVM silicon is suddenly deprecated" failure mode. Add this as a Tier B+ option.

**L4.3 — alert on attestation-stack CVEs (monthly digest).** CVE-2025-41822 was a *cloud-attestation-service* bug, not a silicon bug. Add a monthly monitoring step that subscribes to AMD SEV-SNP / Intel TDX / Azure Attestation (MAA) / Google Confidential VM / AWS Nitro security bulletins. Document the alert-to-patch SLA in the ADR (target ≤7 days for CVSS ≥7.0).

**L4.4 — accept the small but real risk that `tee` mode becomes `e2ee` mode within 5 years.** The migration pattern is *already designed* — `encryption_mode` is enum-additive; if the `tee` value is later deprecated by being moved to `e2ee + hardware-roots-of-trust` (or simply folded into `e2ee`), the migration is monotonic re-keying, not a system rewrite. This is the value of the per-chat schema decision (L1.1).

---

## 5. Meta-verdict on the triple-mode design

### 5.1 What ADR-009 got right (and the precedents agree)

1. **Per-chat granularity** (`encryption_mode` field) — confirmed by 2024–2026 shipping products (Discord DAVE, theSHFT, Voidcom, Zentachain, Briar, Matrix). The "default-E2EE-universal" approach is Signal-only and is the *opposite* of what the brief suggested as an abandonment precedent; it's a real choice but it's not the precedent set by Messenger/Matrix/iMessage.
2. **Three modes (plain / tee / e2ee) with monotonicity** — this is closer to the Discord-DAVE / Matrix per-room model than the WhatsApp-forced-E2EE model. The Matrix precedent (per-room state event) is the oldest running version of this idea and it works.
3. **Phase 0 scaffolding** (nullable ciphertext columns + per-chat mode + content negotiation header) — directly copied from `2026-09-18-achlys-e2ee-migration-feasibility.md` §8, which proves the precedent (WhatsApp Signal rollout 2014–2016, Wire API-version, Proton additive-schema migrations).
4. **`plain` default over `e2ee` default** — correct from the LLM-inference-needs-plaintext constraint documented in `e2ee-app-architecture-survey.md` §3.4. This is the only honest choice for an AI-chat product.
5. **Phase-0-before-feature-work** — matches the e2ee-migration pattern; the cost of doing it on day one is roughly zero; the cost of doing it later is rewriting the schema across an active user base.
6. **Tauri OS-keychain cache + Argon2id at `m=19 MiB/t=2`** — matches `e2ee-perf-ux-reality-check.md` §7 ("aim for <1000 ms login on a mid-range Android") and the Standard Notes / Bitwarden precedent for hardware-backed key derivation.

### 5.2 What the precedents say ADR-009 should amend before shipping

1. **Make the encryption dimensions explicit in the schema.** Today the ADR has a single `encryption_mode` per chat. Real precedents dimension it: chat encryption, backup encryption, sync encryption. Add `encryption_backup_mode` and `encryption_sync_mode` columns upfront (L1.1).
2. **Default-on-create, not opt-in.** The 5–10% global figure for opt-in secure modes (§3) means `tee` must be the *default-flagged* mode for new chats with `plain` as an active choice. The current ADR-009 framing of "plain is default" is honest about the LLM constraint but underweights the *adoption* reality: most users will keep the default (plain) and the privacy story ships as marketing without users. **Flip the bias: default-to-tee-with-explanation, plain-with-active-confirm.** (L2.2, L3.1)
3. **Tag the `plain` mode UI honestly.** "Operator-readable" not "encrypted." No misleading lock icon. Match theSHFT + Matrix labeling. (L2.1)
4. **Make the TEE portability story explicit.** Multi-cloud attestation verifier build; per-chat content key wrapped under user-key so TEE never holds a cryptographic root; multi-CPU roadmap so SEV-SNP / TDX / Hopper CC / Blackwell CC are not single points of failure. (L2.3, L4.1, L4.2)
5. **Time-bound the TEE promise in-app.** Show the CPU family, the microcode patch level, the vendor support window remaining (≤12 months target). When that window closes, the chat re-classifies to `plain` per the monotonicity rule (i.e., it does not silently downgrade; the user is told, and the user's vault-key-wrapped content key keeps the chat readable). (L2.3)
6. **Recovery + re-key are code contracts, not doc obligations.** Standard-Notes-style printable QR recovery token at opt-in; per-chat content keys with hashed key directory for cheap re-wrapping on rotation; Phase-1-to-vault upgrade is a user-triggered action with explicit per-message success reporting. (L2.4)
7. **Per-mode moderation policy.** `plain` = metadata + opt-in content classifier; `tee` = metadata only (attestation contract forbids content classification); `e2ee` = no server-side moderation. Treat moderation as a separate ADR; cross-link but don't conflate. (L2.5)

### 5.3 The single-line verdict

**ADR-009's triple-mode design is correct in shape and matches every 2024–2026 shipping hybrid. The amendments above shore up the five failure modes (adoption collapse, misleading encryption claims, TEE side-channel lifecycle, recovery gaps, and the moderation-vs-E2EE trinity) that history says this design will hit if shipped as-written. None of the amendments require a re-design — every one is a tightening of a decision the ADR already implicitly makes.**

---

## 6. Sources read for this verdict

### From the sibling research dossier (ADR-009's `Research basis` line)

- `.hermes/research/e2ee-app-architecture-survey.md` (52 KB) — TEE patterns, Signal/WhatsApp/Standard Notes/Notesnook/Cryptomator/Anytype/Obsidian/Matrix/Proton survey
- `.hermes/research/e2ee-browser-capability-survey.md` (49 KB) — WebCrypto + IndexedDB + Argon2id stack
- `.hermes/research/e2ee-business-model-survey.md` (44 KB) — Proton/Bitwarden/Tuta/Standard Notes; Vaultwarden split
- `.hermes/research/e2ee-byok-relay-ux-survey.md` (50 KB) — BYOK relay UX patterns
- `.hermes/research/e2ee-perf-ux-reality-check.md` (28 KB) — perf numbers, login latency, IndexedDB, WASM consolidation
- `.hermes/research/e2ee-engineering-cost-realism.md` (39 KB) — engineering costs of E2EE vs TEE vs escrow
- `.hermes/research/tee-confidential-deployment-survey.md` (49 KB) — SEV-SNP / TDX / Hopper CC, side channels, OHTTP+HPKE
- `.hermes/reports/2026-09-18_achiyon-feature-loss-gain-matrix.md` (41 KB) — 38-feature matrix (A) client-side vs (B) TEE vs (C) escrow
- `.hermes/reports/2026-09-18-achiyon-threat-model-adversary-matrix.md` (43 KB) — adversary-by-adversary walkthrough
- `.hermes/reports/2026-09-18-achlys-e2ee-migration-feasibility.md` (51 KB) — WhatsApp/Proton/Wire precedent; staged Phase 0–4
- `.hermes/reports/2026-09-18_competitor-landscape-privacy.md` (20 KB) — Replika/Character.AI/Kindroid/Nomi/Chub/Janitor/RisuAI/SillyTavern + privacy comparators (Duck.ai, Enigma AI, Privatemode, Fidaro, WhisperAI, Signal-bot-tee, OxiHub/veil)
- `.hermes/reports/2026-09-18-self-hoster-oss-dynamics.md` (42 KB) — Vaultwarden/RisuAI/SillyTavern self-hoster economics
- `.hermes/reports/2026-09-18-e2ee-legal-liability-comparison.md` (55 KB) — CSAR 1.0 / 2.0; DSA safe harbour; WebGroup/Coyote
- `.hermes/reports/2026-09-18-cross-verification-verdict.md` (36 KB) — verification of decision-critical claims; CacheWarp; production TEE-attested LLM (Apple PCC, Duck.ai/Tinfoil, NEAR AI); CSAR/Parliament position

### Spot-checked primary sources (Sep 2026)

- **Telegram Secret Chats 5% / "most users never activate"**: worldmetrics.org/telegram-channel-statistics; paprika.bot/blog/telegram-secret-chat; Telegram FAQ (device-bound, no groups, no sync)
- **WhatsApp E2EE backups 5–10%**: about.fb.com/news/2021/10/end-to-end-encrypted-backups-on-whatsapp launch; iThinkDiff (passkey-passed 1B users of 3B+ total, Apr 2026); eprint.iacr.org/2023/843 academic (100M / 2B = 5% at Dec 2022); hansajekalavya.com 2025 statistical table
- **Zoom E2EE meetings low single-digits**: investors.zoom.us May 2024 release ("customers increasingly use the feature"); KB0065408 docs (E2EE disables AI, cloud rec, transcription, polling, etc.); greenlitcontent.com 2024 "orgs with E2EE enabled" (~10%) — meeting-share much lower
- **Signal CDSi-SGX timeline**: signal.org/blog/private-contact-discovery 2017; signal.org/blog/building-faster-oram 2024 (Path ORAM backbone for username / phone-number-privacy story); arstechnica 2022 ÆPIC Leak (cited Signal as the canonical SGX deployment); v12.sh/blog/signal "Compromising Signal's Contact Discovery Enclave" Aug 2025 — *two object-lifetime vulnerabilities on the same Azure SGX SKUs Signal uses in production; extracted the Noise responder private key from a live attested enclave*
- **Hetz / Schneider USENIX 2024**: "Scaling Mobile Private Contact Discovery to Billiers of Users" — two-server PIR + PSI/OPRF replacing SGX for contact discovery, <2 s online for 1024 contacts in a 2B+ database, 32× lower setup comms than prior state of the art
- **AMD SEV-SNP / Intel TDX side channels**: CacheWarp USENIX 2024 (CVE-2023-20592, AMD MilanPI 1.0.0.C); Coheres+Reload USENIX 2025 (mbedTLS RSA-4096 recovery); Heracles CCS 2025; CiphertextHidingDRAM (Zen 5, not enabled by hyperscalers); TDXDown + Heckler CCS 2024; CVE-2025-41822 (Azure Attestation MRSEAM revocation list bypass, Aug 2025, patched Sept 2025)
- **Hybrid per-channel products ship in 2024–2026**: Discord DAVE whitepaper; theshft.app (explicit "no misleading lock icon"); voidcom.app/features/security (DMs/voice E2EE; Stage broadcasts server-readable); zentachain.io/zentalk; Briar / Zerion (broadcast channels signed-but-readable; DMs E2EE); Matrix `m.room.encrypted` per-room state event
- **iMessage / iCloud ADP**: support.apple.com security guide; havenmessenger.com/blog/posts/imessage-icloud-backup-privacy (Jan 2025 UK RIPA notice forced Apple to withdraw ADP for UK users)
- **Tinfoil/Duck.ai/Near AI/Fidaro/Privatemode/WhisperAI/Enigma AI/OxiHub-veil/Signal-bot-tee**: confirmed by cross-verification verdict as the 2025–2026 set of products that ship verifiable TEE-attested inference or storage-E2EE or both
