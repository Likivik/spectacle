# E2EE-Added-to-Existing-Product Migration Lessons
*Research basis for ADR-009 per-chat `encryption_mode` field. Compiled 2026-09-18.*

**Question being answered:** When a product that was originally plaintext later adds an E2EE mode (and especially when those modes *coexist* per-unit — per-chat, per-room, per-vault, per-folder), what UX patterns have shipped, where did they break, and what should we steal or avoid for Achiyon?

Scope: seven product classes. Each section gives the mode-coexistence pattern, the documented mistakes, and the explicit "what they'd do differently" lessons. Closing synthesis maps the lessons to Achiyon's three-mode design.

---

## 1. Meta Messenger / Instagram DMs: opt-in 2016 → default 2023 (the slow-flag story)

**Timeline.**
- **2016-07-08.** Secret Conversations launched as *opt-in*, per-conversation mode in Messenger. Used the Signal Protocol but only for one-to-one chats, **single-device only** ("a unique secret key be stored on both the sender and recipient's computer, and for now, Facebook doesn't have a way to securely distribute that key among multiple phones"). No GIFs, video, or payments. Limited test rollout (Wired, July 2016).
- **2017-05.** Multi-device support for Secret Conversations; video support added later. Still opt-in.
- **2023-12-06.** Meta announced *default* end-to-end encryption for **all** personal chats and calls on Messenger. Marketed as a "years-long rebuild" — the company explicitly stated "this has taken years to deliver because we've taken time to get this right." But the rollout was staged server-side ("it will take a number of months to complete the global roll-out") (about.fb.com 2023-12-06).
- **2024-05.** Accountable Tech survey (n=80+): **67 % of users did NOT see the "End-to-end encrypted" label on their chats** six months after launch. Of the 54 users who did not see it, **39 % had received the rollout pop-up notification anyway** — the system told them encryption was enabled when it wasn't. Headlines contradicted reality.
- **2026.** Default E2EE still rolling out; group chats and Instagram DMs still in test phase (engineering.fb.com 2023-12-06).

**Mode-coexistence UX pattern.** Two distinct "threads" in one inbox (a regular Messenger conversation and a Secret Conversation were rendered as separate visible items). A black chat bubble + lock icon = Secret Conversation. Default threads had no lock. Switching modes within an existing conversation was *not* possible — to get E2EE you had to start a new thread. After 2023, the visual *default* is encrypted; the status is communicated by a chat-banner label and a per-chat "Encryption" entry in chat settings.

**Mistakes.**
1. **Opt-in for too long (2016–2023) + capability-constrained E2EE mode** (no GIFs, no payments, no multi-device) made the *secure* mode the *less useful* mode. Effect: most users never enabled it; the user base was conditioned to read "E2EE" as "downgrade." (Apple Notes and Telegram Secret Chats repeat this pattern; Zoom repeats it with E2EE meetings.)
2. **Headline-led rollout that outpaced reality.** "Default E2EE for all" was announced in December 2023 but *server-side staged* for months. By April–May 2024, two-thirds of users surveyed had the notification but no encryption. This created a documented "false sense of privacy" — users told *encryption is on* when their chat wasn't yet on the encrypted server pool. Accountable Tech called this a privacy failure for users with at-risk communications (the report cited the Nebraska abortion case).
3. **Pre-encryption chat history is not retroactively encrypted.** Help center: "If your chat wasn't previously secured with end-to-end encryption, interactions with messages sent before Messenger upgraded the chat won't be end-to-end encrypted. This includes reactions to messages." → per-chat `encryption_mode` semantics: the upgrade is a *boundary*, not a blanket; pre-existing rows are out of scope. **Confirm directly with Achiyon:** ADR-009 already says "monotonicity" but does not call out the per-message-history exception — Messenger's docs make this explicit.
4. **No public "no longer E2EE" signal.** If Meta had to roll a chat back, users had no in-chat indicator — the status silently dropped. (ADR-009 calls for monotonicity; we should be honest that *silent* downgrade is exactly what broke Element.)

**What they'd do differently (per their own retros).**
- Not launch E2EE as opt-in for 7 years — every year they delayed *conditioned* users to associate "lock icon" with "no GIFs" and "single device." Switching from opt-in to default was always going to be a migration problem.
- Have built recovery/PIN setup into the *default-on* deploy (the "prompted to set up a recovery method" notice only appears once E2EE is actually on for a user's account — so users who got the pop-up but not the upgrade could neither encrypt nor set up recovery).
- Use a single in-chat indicator per chat, not just a hidden "Encryption" submenu entry.

**Direct lessons for Achiyon.**
- **Don't ship an E2EE mode that is less capable than plaintext** for years. ADR-009's vault mode already plans TEE-or-BYOK generation, but **the per-chat vault upgrade must support every feature the plaintext chat supports** on day one (attachments, dreaming, image generations, voice), or users will treat "vault" as a downgrade. This is what Messenger's Secret Conversations got wrong for 7 years.
- **Phase-0 schema scaffolding (the `encryption_mode` column) must land *before* the E2EE feature** so we never have a moment where some chats "are E2EE" and others "are not" without the schema knowing — exactly Meta's problem. ADR-009 already nails this ("Phase-0 scaffolding lands before any feature work").
- **Per-chat mode transition is *monotonic by user action only***, never silent. The user action is the upgrade. No silent server-side flips, no implicit "this is encrypted now" without an in-app cue. Meta's 2023-2024 rollout is the canonical "how not to do this" case.
- **Pre-existing content is in-scope-when-user-acts.** For an "upgrade this chat to vault" prompt, the chat upgrade must be a single deliberate user action that *also* names the cost (old messages stay as-is in the prior mode; new messages are vault-mode). Messenger documented this rule clearly; we should mirror the wording.
- **Recovery/PIN UI must be ready when the first chat upgrades**, not months later. The recovery flow design in ADR-009 needs to ship as part of vault-mode, not as a P3 follow-up.

---

## 2. Google Messages RCS E2EE (default-on-for-RCS, not for SMS) — the mixed-mode coexistence reference

**Timeline.**
- **2020-11.** Google Messages rolls out Signal-Protocol E2EE for RCS one-to-one, "automatic in eligible conversations." SMS/MMS explicitly excluded.
- **2024 onward.** Apple and Google jointly announce cross-platform E2EE RCS, rolling out May 2026 to iPhone (iOS 26.5 beta) and Android. Same lock icon on both sides. Default-on for RCS only.

**Mode-coexistence UX pattern.** Two-state color system: **dark-blue bubble = RCS state** (i.e. data-based, can be E2EE); **light-blue bubble = SMS/MMS state** (carrier SMS, never E2EE). On top of the *transport* state, an *encryption* state: a **lock icon on the send button + next to the message timestamp** when E2EE is active. The compose bar's text changes from "Text message" to "RCS message" depending on transport. Color = transport; lock = encryption. **Two orthogonal axes, two orthogonal indicators.**

When a recipient is offline or loses RCS, the conversation can downgrade to SMS; the lock icon disappears. When RCS comes back, "the conversation will automatically switch back to end-to-end encrypted RCS" (Google support doc). **The mode is allowed to change mid-thread based on capability**, and the indicator follows the current state.

**Mistakes.**
1. **Per-message confusion when a recipient client is mid-migration.** The Google white paper (gstatic.com/messages_e2ee.pdf) describes a known failure mode: "in rare situations where the conversation starts as E2EE, then one of the clients migrates to a different RCS client or an older Messages client that does not support E2EE, Messages might be unable to detect the change immediately. If the Messages user sends a new message, it's still E2EE, however the recipient client may render the encrypted base64 payload directly as message content." They patched by appending "Encrypted message..." prefix to the encrypted payload with a link to docs. This is a *downgrade-attack-friendly* failure mode: the receiver sees garbage or wrong UX.
2. **Cross-platform inconsistency for years.** Until 2026, Android (Google Messages) could E2EE-RCS to Android but not to iPhone. iPhone RCS (since iOS 18) had no E2EE. Result: a lock icon on Android meant one thing, the same conversation on iPhone meant nothing — for the same user, same contact, same content. This is *the* mode-visibility problem (see §3). The 2026 cross-Apple/Google rollout fixes this; it took 2 years of public friction (the Forbes piece calls out the user confusion directly).
3. **Color-collision with iMessage.** Android users who message iPhone users had *iMessage-blue-bubble-with-E2EE* vs *Google-Messages-blue-bubble-with-E2EE-vs-SMS* — three blues across two apps with different semantics. The general public could not tell them apart.
4. **Backup behavior ambiguity.** RCS E2EE messages are written into Android's local messages DB and *included* in Android system backup (which is E2EE under lock-screen-derived key from Android P+). But apps with SMS permissions can read the local DB. Google acknowledges this in the white paper: "we will work across the ecosystem to improve security of E2EE storage and access by other apps." → backup/sync is a known soft spot.

**What they'd do differently.**
- Ship cross-platform E2EE RCS *simultaneously* on both Apple and Android, not staggered. They got there eventually (2026) but lost 2 years of user trust in the lock icon's meaning.
- Move from "color-coded transport" to "explicit lock + label" earlier. Color is too overloaded (Apple blue-bubble, carrier blue, RCS blue, Facebook blue).
- Resolve the "encrypted message rendered as base64" case with a *client-side downgrade*, not a "render the garbage with a label" workaround. Better: when a message is detected as undecryptable by the recipient, *don't send the next one as E2EE* — auto-downgrade the conversation and notify both users.

**Direct lessons for Achiyon.**
- **Two orthogonal axes (transport/visibility vs. encryption) need two orthogonal indicators.** If we ever ship per-chat TEE-vs-E2EE for transport as well as generation, the indicator system needs *two* icons, not one. Google's "color = transport, lock = encryption" is the cleanest version of this in the wild. Don't merge them.
- **Live mode-flip is acceptable when the cap drops.** If an Achiyon vault chat's user loses their vault key mid-session, the conversation should *gracefully fall back* (with explicit notice) rather than dead-end the user. Google's "lock disappears when RCS drops, comes back when RCS returns" is the model — but the user's mental model needs an *explanatory banner*, not just a silent color shift.
- **The "encrypted base64 rendered as garbage" failure is the worst case for per-chat E2EE.** If a chat was vault, then the user disabled vault on the other end, the next message sent as vault ciphertext would render as base64 to the receiver. This is the equivalent of a downgrade attack. We need client-side detection (a "I can't decrypt" error type) and an auto-downgrade-to-plain for that chat with explicit in-chat notice — never silent.
- **Backup/sync semantics for vault chats must be designed up front.** Google Messages puts E2EE-RCS messages into the local DB and lets SMS-permission apps read them. ADR-009 says dreaming runs client-side on phones for vault chats; the analog problem is "what does `dreams` indexing do with vault content?" — and the answer "decrypted on the fly, never written plaintext to disk" must be enforced in code, not policy. Anytype has the right pattern here (§7).

---

## 3. iMessage vs SMS "green bubbles" — the mode-visibility problem

**Timeline.**
- **2011-06-06.** iOS 5 / iMessage launch. iPhone-to-iPhone messages use iMessage (blue bubble), iPhone-to-other use SMS/MMS (green bubble). Encrypted vs not, by color.
- **2014-2024.** Apple faces DOJ scrutiny (2024), public pressure (DOJ called out the green bubbles specifically: "Apple's anticompetitive conduct ... making it more difficult for iPhone users to message with users of non-Apple products"). WCAG accessibility analysis: the green Apple picked scores 2.18 (very poor contrast vs. white text), while the darker blue scores much better.
- **2024.** Apple announces RCS support (no E2EE initially). Blue bubble no longer = secure.
- **2026-05.** Cross-platform E2EE RCS ships (Apple + Google), iOS 26.5. The Forbes piece ("After 15 Years — Apple Changes Green Bubbles On Your iPhone") captures the failure: "**any green bubble might be fully secured. Or it might not. You need to check**." Apple Insider quoted: "sending media to Android is better, but everything else is more confusing and frustrating than ever."

**Mode-coexistence UX pattern.** One indicator (color of bubble) used to encode *both* protocol family and security status. After 2026, color = transport (iMessage blue, RCS blue, SMS green); security status moves to an in-chat lock icon — but the lock is small, sometimes ephemeral, and inconsistent across OS versions and conversation partners.

**Mistakes (the mode-visibility failures).**
1. **One cue overload.** Color was used to encode two things simultaneously for 15 years (iMessage vs not, secure vs not). When RCS blurred the line, the cue became ambiguous. Forbes explicitly called this out as a security risk: "And that's a major security risk."
2. **The green-bubble-as-downgrade effect.** iOS users have been culturally trained to read green as "worse." When some green is now encrypted (cross-platform E2EE RCS) and some green is not (SMS), the trained reflex produces false negatives — users downgrade their trust in actually-secure green messages because of their pattern-match for "green = bad."
3. **Color-contrast choice (UX/Design analysis).** Apple's green has poor WCAG contrast (2.18). For users with visual disabilities, the green is unreadable. The design choice *also* happens to make green messages look "worse," which reads as intentional friction. Whether intentional or not, the takeaway for accessibility is clear: a security cue must be *legible*, not decorative.
4. **Carrier-dependent behavior invisible to the user.** RCS availability depends on carrier, OS version, account. The user can't tell from the bubble alone *why* it's not blue. They have no diagnostic.

**What they'd do differently (per the Forbes / Apple Insider analysis).**
- Apple's *own* pre-RCS design *relied on* the green/blue encoding to create social friction. Removing the encryption=blue link is the right call long-term; the immediate cost is the 2024-2026 "which color means what" confusion period.
- A dedicated security indicator (lock icon in the chat header) should have existed *alongside* the bubble color for the entire period, not been added when RCS complicated things.

**Direct lessons for Achiyon.**
- **Never let one visual encoding mean two things.** In Achiyon's case: chat-list item dot, chat header, chat title — these are three different surfaces. If we use color for "vault" on any one of them, we must use the same color *everywhere*, and we must not also use color for "unread" or "favorite" or "AI-suggested."
- **The mode cue must be permanent, not ephemeral.** WhatsApp's "end-to-end encrypted" banner that disappears after a few seconds is a usability bug; users who didn't see it in the first 2 seconds don't see it at all. Achiyon's per-chat mode badge must be persistent and unambiguous.
- **Accessibility matters for security cues.** A small gray padlock at 2:1 contrast fails WCAG and fails low-vision users. The lock icon must be high-contrast, or there must be a textual alternative ("Vault" in the chat header) for screen readers.
- **Plan the "the cue used to mean X, now means Y" moment.** Achiyon will have chats that started as plain and were upgraded to vault. The user might recall that the lock on this chat was *not* there yesterday. Make the upgrade an *explicit* in-chat event ("This chat was upgraded to Vault on Sept 18. Older messages are not encrypted.") — never silent, never ambiguous.
- **Don't inherit Apple's mistake.** Specifically: do not let the chat list use one color for "vault" and the chat header use a different color or icon. Pick one canonical representation per state (plain, TEE, vault) and use it on every surface.

---

## 4. Matrix rooms with mixed encryption state — the room-flag precedent closest to Achiyon's per-chat field

This is the most directly relevant section. Matrix has had `m.room.encryption` as a per-room flag since 2018, and Element has spent seven years discovering the failure modes.

**Timeline (selected).**
- **2018.** E2EE by default for new DMs in Riot (later Element); rooms can be created unencrypted (public rooms don't usually need it). The `m.room.encryption` state event in the room is the flag.
- **2022-2023.** Element Android bug 5068: a user's phone "decided" a DM room was unencrypted and *started sending unencrypted messages* without any warning. The web/desktop version correctly refused to send unencrypted messages in a once-encrypted room ("a room that was once encrypted cannot be downgraded"). The mobile version did not. capocasa's bug report: "Suddenly, I started getting warnings about unencrypted outgoing messages in the browser, but not incoming ones. I got no warnings at all on the phone."
- **2023.** Element-meta issue #147 ("Clear, reliable indication of whether a composed message will be sent encrypted, or unencrypted"): capocasa's spec-level proposal. Cited bug 5068 and asked for a spec-level guarantee.
- **2024-2025.** Matrix-ios-sdk advisory GHSA-fxvm-7vhj-wj98: "Sending blank `m.room.encryption` on iOS will disable encryption … can be forced to send unencrypted messages in an end-to-end encrypted room, without warning the user." Patched in 0.20.14 / Element-iOS 0.6.10. → confirmed downgrade attack via state-event spoofing, with no client-side warning. WhatsApp's downgrade-attack rule (don't go back) exists for exactly this reason.
- **2024.** Element-meta #2746 ("Show room encryption state in the composer"): design proposal. Element's official stance: "as we are overall optimizing for E2EE encryption, we would like to avoid explicit decorations when the room is encrypted (as this is the nominal state). However, this means that the decorations in case the room is not encrypted need to be stronger."
- **2025-08-27.** Element Web 1.11.110 ships the "blue broken padlock" + "Send unencrypted message..." placeholder. Backlash from self-hosters running *intentionally* unencrypted public rooms. PR #30440 ("Show a blue lock for unencrypted rooms and hide the grey shield for encrypted rooms") implements this; subsequent issue #30691 ("private server with disabled e2ee element has 'send an unencrypted message' on text input on all channels") reports that the new warning is now invasive for self-hosted instances that *choose* plaintext rooms.
- **2026-07-31.** Matrix-spec issue #2302: "Immutable encryption and history visibility." Proposal: room encryption settings and history visibility should be *immutable by future spec*, stored in `m.room.create`. Quote: "for the other state, like the room's encryption settings or history visibility … it can be devastating because it provides the homeserver with a potential mechanism to also impact the confidentiality of messages." → the spec is now moving toward making encryption setting monotonic at the spec level.

**Mode-coexistence UX pattern.**
- `m.room.encryption` event is the source of truth. Empty / missing = plain. Non-empty = E2EE (with algorithm in the event).
- **Element design philosophy (post-2024):** "invisible crypto" — encrypted rooms get *no decoration* (no icon, plain "Send message..." placeholder). Unencrypted rooms get a *strong* decoration: blue broken padlock icon next to the composer, "Send unencrypted message..." placeholder text, and a blue "Not encrypted" pill in room info. Public rooms additionally get a blue globe icon.
- Cross-client inconsistency: Element Web/Desktop refuses to send unencrypted in a once-encrypted room (monotonicity enforced); Element Android historically did not, leading to the 2022 silent-downgrade bug.
- The "blue lock" specifically signals "warning / not the nominal state," not "secure" — a deliberate inversion from the WhatsApp/Telegram green-lock-for-secure norm.

**Mistakes.**
1. **Silent client-side state divergence (Element Android 2022).** A client got the room state wrong and started sending unencrypted messages with no indicator. Web/desktop caught it; phone didn't. Result: user thinks they're in an encrypted room; only by checking on another device do they find out. **This is the exact failure mode our per-chat field could have.**
2. **Server-side state-event manipulation = downgrade attack.** Matrix-ios-sdk 2024 advisory: an attacker with room admin (or a malicious homeserver) can send a blank `m.room.encryption` state event. Old iOS clients read this as "no encryption" and start sending plain. The room appears "downgraded" to anyone on the old client. **Server-side state is not trustworthy for a confidentiality decision** — clients must remember their own state.
3. **Cross-client inconsistent enforcement.** "Once a room is encrypted, it must stay encrypted" is enforced on Web/Desktop but historically *not* on Android/iOS. Element-meta #147 asks for spec-level enforcement: "Element-branded clients MUST confirm from three different information sources that an unencrypted message was indeed intended to be sent unencrypted."
4. **"Invisible crypto" = dangerous when the system fails.** Element's design philosophy is "encrypted is normal, so don't decorate it." When the system *does* fail (downgrade attack, sync lag, server event spoofing), there is no positive indicator to tell the user "this is encrypted" — only the absence of the broken-padlock warning. capocasa: "It's important that people don't mistake SMS messages sent or received via the Signal interface as secure and private when in fact they are not." Same logic for Matrix: a missing warning is not the same as a present confirmation.
5. **The "blue broken padlock" looks like "secure" to many users.** Despite Element's intent, the *color* (blue) and the *symbol* (lock) read as "secure" — the opposite of intent. Comment from a user: "I think an open lock is also misleading, as e.g. on website that means total lack of encryption. Perhaps a yellow/orange lock instead to show that there is encryption, but it's not as 'encrypted' as it could be?" Element community could not agree on the right color, and several iOS/Android versions had to be patched to match.
6. **Mandatory E2EE would have prevented this, but isn't possible for Matrix.** Many commenters argued "E2EE should not be optional … all chats should be end-to-end encrypted by default, even if they have not verified the other user's keys." Element's response: "Forcing E2EE in all rooms at this point is unrealistic." This is exactly Achiyon's position (ADR-009: three modes, default plain, vault optional).
7. **Multi-client state sync is unreliable.** Bug 5068 went away after logout-login. State had to be re-synced. Element-meta #147's prescription: "must be synced with server *at least* every time the user enters the application after having closed it — and certainly not at login time."

**What they'd do differently.**
- **Immutable `m.room.encryption` in `m.room.create`** (MSC4268, in flight 2026). Once a room is created, its encryption setting is locked into the create event — no later admin can downgrade it. This is the architectural answer to the silent-downgrade problem.
- **Element-branded clients would refuse to send unencrypted messages in *any* room that has ever had encryption** (the Web/Desktop behavior, generalized). The mobile clients' permissive behavior was a bug.
- **They would not have called it "unencrypted."** The wording "unencrypted message" in the placeholder caused years of complaints (Riot/Element-web #3628, #2961) because users interpreted it as "no encryption at all" — not "transport-encrypted only." Proposed alternatives: "Send a message (SSL encryption: on, E2E encryption: off)…" — or simply a positive "Send an encrypted message" for the encrypted case so the user can see the contrast.
- **Spec-level, not client-level, monotonicity.** ADR-009 already calls for monotonicity per chat; this lesson reinforces it and says *spec it*, don't just enforce it in the client.

**Direct lessons for Achiyon.**
- **Monotonicity is non-negotiable, and it must be enforced client-side.** Per-chat `encryption_mode` can only transition forward (plain→TEE→vault); never backward. But the *client* must enforce this; trusting the server to enforce it (or trusting the server's state event) is the iOS 2024 bug. **The per-chat `encryption_mode` should be stored in the local client DB, validated against the server's view on every sync, and the client's view should win on conflict.**
- **Server-side state for mode is hostile by default.** Don't read `encryption_mode` from the server row alone. Maintain a *trusted* local record (signed by client at time of user action) and require the server record to match the local record. (Analog to Matrix's move to put `m.room.encryption` in `m.room.create`.)
- **Two-source confirmation for "sending plain."** Element-meta #147: "MUST confirm from three different information sources." For Achiyon: before any plaintext message leaves a chat that has *ever* been upgraded to vault, the client must confirm (a) chat metadata says mode=vault, (b) vault key is unavailable on this client *and* recoverable from recovery token, and (c) the user explicitly clicked "send in plain mode" on a per-message basis. If any of those three fail, the message doesn't send.
- **Don't call it "unencrypted."** ADR-009 calls modes "plain / TEE / vault" — a deliberate neutral naming. Don't introduce UI strings like "Send unencrypted message." Use "Send without vault" or "Send in plain mode" — and pair with a *positive* "Encrypted (vault)" indicator for the secure case.
- **A lock icon alone is ambiguous; the iOS design lesson applies here too.** If we use a lock icon for "vault," users on different OSes will read it as "secure" regardless of state. Use a labeled badge ("Vault") plus an icon, or use a *non-lock* symbol (Proton Mail's blue lock + checkmark combo, Anytype's "🔒" with a "Local-only" badge). The pattern from Proton Mail is worth following: a *lock color* (black = zero-access, blue = E2EE Proton-to-Proton, green = PGP, gray = open) plus an *icon-inside-lock* (checkmark, warning). State is the combination.
- **Multi-device sync for vault key state must be reliable.** Element Android's 2022 bug: state stale, sync didn't fix it. Achiyon: when a user upgrades a chat to vault on device A, device B must reflect this within the same sync window, *and the local "is this chat vault?" state must be re-derived on every app foregrounding*, not cached from login. Matrix-spec #147 is right: cache freshness is part of the security model.

---

## 5. Tresorit / Proton Drive / Box KeySafe / BooleBox — encrypted folder coexistence in storage products

This is the closest analog to "some folders are vault, some are not, in one account."

**Pattern (Tresorit, Proton Drive, BooleBox).** All three are *zero-knowledge from launch*. They don't have a "migrate from plaintext to encrypted" problem — the whole account is encrypted by default. Encrypted folders ("tresors" in Tresorit, "encrypted folders" in Proton, "Personal Key folders" in BooleBox) are containers that hold encrypted content; the user's key hierarchy wraps per-folder symmetric keys.

**Box KeySafe (the actually-comparable case).** Box is a *plaintext-by-default* cloud storage platform that *added* an enterprise add-on called **KeySafe** for customer-managed encryption keys (BYOK). KeySafe encrypts file content uploaded to Box with customer-held keys (AWS KMS or GCP KMS); Box cannot read the file content. **KeySafe is not zero-knowledge in the strict sense** — Box holds the customer's *key identifier* and uses short-lived credentials to fetch decrypt operations on behalf of the customer (per Box support article on keyless authentication). The customer controls the CMK in their own AWS/GCP account.

**BooleBox (the smallest-scale but most-illuminating case).** Per-file "Personal Key" feature: a user selects a file or folder, chooses a Personal Key, and the file/folder is encrypted with that key. The file is marked with a key icon. To open, you enter the key. **Lost key = data lost forever** ("it will no longer be possible to access it without the key set"). This is the per-item encryption-mode field *as a UX*.

**Mode-coexistence UX patterns.**
- *Box KeySafe.* File content is E2EE-with-customer-key; metadata (file names, comments, descriptions, Metadata templates) is encrypted with **Box-managed** keys, not customer keys. Full-text search indexes are Box-managed-key encrypted. **The split is per-attribute, not per-folder.** Customer-managed file content + provider-managed metadata + provider-managed search. User-visible result: search results don't break, but a search-warrant against Box returns metadata but not content.
- *Tresorit.* Folder-level key: every file in a "tresor" gets its own symmetric key; the tresor's group key file holds all member-encrypted keys. ACL changes → new folder key generated → "lazy re-encryption" of future content (old content still under old key, but ACL denies the removed user). User-visible result: revocation is *fast* and the per-user view is immediate.
- *Proton Drive.* Per-node key (file and folder each have their own key); tree structure wraps keys by parent. Sharing requires changing the ACL on a parent, which re-wraps child keys. Two-layer encryption: inner content + outer ACL wrapper.
- *BooleBox.* Per-file-or-folder Personal Key. Decryption requires the key; key recovery is impossible.

**Mistakes.**
1. **Box: metadata was a side-channel.** Search indexes, comments, and metadata were *not* under the customer key. A user enabling KeySafe for "compliance" got file-content protection but not metadata protection. Box was transparent about this in the support article ("Comments, descriptions, and Metadata are encrypted with Box-managed keys") but the marketing message "encrypted content with your keys" can mislead on the metadata. → lesson: in a per-mode product, every byte of the row needs to be classified, not just the body.
2. **BooleBox: lost key = lost data.** Hard lesson from per-item password protection: users *will* lose the password. Apple Notes locked notes (§7) repeat this — when you reset the notes password, *old locked notes stay locked with the old password*. Users who don't understand this lose data.
3. **Tresorit: key rotation is a separate operation.** Key rotation happens "automatically by the user device within reasonable intervals, or when a given cryptographic event (such as a device revocation) necessitates it." For an enterprise customer, "reasonable intervals" is not enough — they need explicit rotation policy. Tresorit's posture is "we rotate for you" — fine for consumers, friction for enterprises.
4. **Box: KMS credential management was a UX wall.** Pre-keyless auth, Box customers had to manage long-lived IAM credentials or cross-account roles with Box — credential rotation was a "coordinated multi-party change," not self-service. The 2025 keyless-auth refactor was effectively Box admitting their original UX was untenable. *Migration from old auth to new auth is a managed-services operation*, not a user-facing one.
5. **Proton Drive: search is server-blind.** Search works on local index only (Proton's model is zero-knowledge; server can't search encrypted blobs). Users on devices without the full local index (web, second device) get degraded search. For an enterprise with 100k files, this is a real UX cost.

**What they'd do differently (per Box's own support docs and Proton's blog).**
- Box: ship metadata encryption under customer key from the start of KeySafe (instead of "full-text search encrypted with Box-managed keys, customers can disable"). The fact that this is a documented limitation, not a feature, is Box admitting the gap.
- BooleBox: add a *recovery* mechanism for Personal Keys (e.g., escrowed in the user's account with a secondary passphrase, or a key-derivation from the user's account password). Without it, the feature is a data-loss vector.
- Tresorit: surface rotation events to enterprise admins. "Auto-rotation on revocation" is invisible; admins need to know.
- Proton Drive: ship server-assisted search (with a usage policy the user accepts) or clearly label which devices have full search.

**Direct lessons for Achiyon.**
- **Every attribute of a chat row needs a mode classification, not just the body.** A `ciphertext` blob plus `ciphertext_meta` blob in the schema (ADR-009 §e2ee scaffolding) is correct — but the *mode* needs to be recorded for *both* columns, and any new column added later (e.g., dreaming memory index, attachments index) must inherit the chat's mode. Box's "file content E2EE, metadata provider-encrypted" is the side-channel to avoid.
- **Lost recovery token = lost vault.** Same as BooleBox. ADR-009's recovery token flow (random 256-bit + SHA-256 hash server-side, shown once) is correct, but the *UI* for "I lost my recovery token" needs to be explicit: not "you can recover" but "you can migrate this chat to plain mode *only by losing the old history*, do you want that?" — same pattern as Apple Notes reset.
- **Per-chat mode-flip UX must surface feature loss.** Box's "full-text search and AI features are disabled" disclaimer is the right pattern for any Achiyon feature that can't operate in vault mode (dreaming, AI recall, cross-chat search). The user must see the feature-loss list *before* they upgrade, not after.
- **Keyless / per-row key derivation is the right pattern.** Tresorit's "per-file key + ACL-wrapped parent key" is the model. ADR-009 already does this (vault key wraps per-chat content keys). The Tresorit "lazy re-encryption" pattern (rotate on ACL change, re-encrypt forward only) is the migration-cost minimization pattern.
- **Credential/key UX must be zero-config by default.** Box's 2025 keyless-auth refactor is a lesson in *what happens when your key-management UX is too operationally heavy* — enterprise customers manage it; consumers never enable the feature. Achiyon's vault must be one-tap to enable, with the recovery token as the only user-managed secret. No KMS, no IAM, no customer-managed keys for v1.

---

## 6. Zoom E2EE meetings opt-in — the feature-loss-in-secure-mode lesson

**Timeline.**
- **2020-05.** Zoom acquires Keybase; commits to E2EE for paid meetings.
- **2020-10.** Zoom E2EE launches as **opt-in** technical preview. Per-meeting toggle. Account-level setting "Allow use of end-to-end encryption." 1,000-participant cap.
- **2020-12.** Zoom enables E2EE for *all* free and paid users (still opt-in per meeting).
- **2026.** Zoom ships post-quantum E2EE (PQ E2EE) for Zoom Workplace — Meetings, Phone, Rooms. First UCaaS to do so. Still opt-in per meeting.

**Mode-coexistence UX pattern.** Per-meeting toggle at scheduling time. Account admin can set default encryption type ("Enhanced" vs "E2EE") at the account/group/user level; individual meetings override the default. **Cannot switch mid-meeting.** Once a meeting starts as standard, you can't upgrade to E2EE; once it starts as E2EE, you can't downgrade.

**Feature loss in E2EE mode (the documented list).** When E2EE is on, Zoom disables:
- Cloud recording
- Live transcription / closed captions
- Live streaming
- AI Companion features
- Breakout Rooms (in original launch; later versions recovered some support)
- Polling and Surveys
- Zoom Whiteboard, Zoom Notes, Zoom Apps
- Join-before-host
- 1:1 private chat in-meeting
- Meeting reactions
- Telephone dial-in, SIP/H.323 endpoints, on-premise configurations (Phase 1)
- Zoom Web App and Web SDK (later versions partially recovered)

**Why opt-in only.** Zoom's own reasoning (blog, support docs):
- "Because end-to-end encryption disables several meeting features, we recommend using E2EE only for meetings where additional protection is needed."
- E2EE requires all participants on the desktop client, mobile app, or Zoom Rooms. Browser/SIP/PSTN can't decrypt.
- Key management: when E2EE is on, Zoom doesn't hold the keys, so cloud recording, transcription, etc. are impossible by definition.

**Mistakes.**
1. **Opt-in forever = "E2EE = worse."** Same mistake as Messenger Secret Conversations. Users who tried E2EE once found: no dial-in for their colleague, no cloud recording, no transcription. They reverted. The "lock icon" came to mean "inconvenient meeting," not "secure meeting." Zoom's blog *says* E2EE is "an extra layer to mitigate risk and protect sensitive meeting content" — i.e., explicitly frames it as the inconvenience option.
2. **Cloud recording users discovered the loss the hard way.** The docs warn: "Enabling this version of Zoom's E2EE in your meetings disables certain features, including ... cloud recording." The toggle is at meeting creation, not mid-meeting. Users who toggle E2EE on by accident lose their recording silently.
3. **Browser/SIP users are second-class citizens in E2EE mode.** The docs: "Users will not be able to join by telephone, SIP/H.323 devices, or on-premise configurations." If a meeting is scheduled as E2EE and someone tries to dial in, they fail. The discoverability of this failure (i.e., does the dialer know *before* they try?) is weak.
4. **No mid-meeting switching.** "You cannot upgrade a meeting to end-to-end encryption during the meeting." A user who realizes mid-call that the call needs more protection can't add it. They have to schedule a new meeting. (Compare: WhatsApp, which switched to default-E2EE because opt-in forever didn't work.)
5. **The meeting-scheduling UX doesn't surface feature loss clearly enough.** Zoom shows the list, but it's in the KB article, not in the meeting-create dialog. Users discover the loss when they try to use a feature in the meeting.

**What they'd do differently.**
- Surface the feature-loss list *in the meeting-creation dialog*, not just the support article. A summary like "E2EE will disable: cloud recording, live transcription, AI Companion, telephone dial-in" with a checkbox confirmation.
- Make the mode-flip more discoverable. A scheduled meeting's mode should be editable up to start time, with explicit warnings if the change disables features currently enabled.
- For Browser/SIP users: either support them in E2EE mode (with reduced functionality) or fail the dial-in attempt *with a clear message* before the meeting.

**Direct lessons for Achiyon.**
- **Every vault-mode chat must surface its feature-loss list at upgrade time.** ADR-009 already calls out that vault mode means generation moves to BYOK-browser-direct or TEE worker, and dreaming is client-side. The upgrade prompt should explicitly enumerate: "Dreaming will run client-side on your phone" (performance note), "AI generation will use your API key" (cost note), "Cross-chat memory recall may be slower" (performance note). One tap, explicit list, confirm.
- **The "secure = inconvenient" brand must be avoided.** Zoom and Messenger both conditioned users to read "E2EE" as "downgrade." Achiyon's vault mode cannot be the *less featured* mode for years. The ADR's plan to have vault mode generation via TEE worker (so server still generates, just inside attested TEE) keeps feature parity — the user doesn't notice feature loss. **This is the most important architectural decision in the ADR for vault-mode adoption.** Don't replace it with a BYOK-only model that caps adoption.
- **Per-chat mode must be editable, not fixed at create time.** Zoom doesn't let you flip mid-meeting; that's a bug, not a feature. Achiyon: "upgrade this chat to vault" must be a per-user action, with explicit confirmation and a feature-loss list. Once vault, monotonicity prevents downgrade.
- **Multi-modal users (phone, desktop, web) need a coherent vault experience.** Zoom's "browser/SIP can't join E2EE" is the kind of "your less-capable device is locked out" problem we must avoid. ADR-009's vault key on Tauri/keychain (desktop) and WASM Argon2id (mobile) means every device class can hold the vault key. The escalation path (recovery token for lost devices) must work on every class.
- **Surface feature-loss *before* commitment, not after.** Zoom's UX lesson: don't make users discover feature loss by trying to use the feature. Achiyon's chat-upgrade modal should be a checklist, not a one-tap confirm.

---

## 7. Squirrel (Apple Notes locked notes) / Anytype / Obsidian Sync — per-vault or per-item encryption modes

**Apple Notes locked notes (iOS 16+, macOS 13+, 2022).**
- Per-note encryption toggle. Each note can be locked individually; locked notes are E2EE in iCloud.
- Locking uses either device passcode (FastSync w/ iCloud Keychain) or a custom notes-only password.
- **Locked notes cannot have video, audio, PDF, or document attachments.** Only tables, images, drawings, scanned documents, maps, or web attachments.
- Apple community thread 256088704: a user changed their notes password and discovered old locked notes *retained the old password*. New content added after the password change went missing — the app showed only the version tied to the old password. **Critical UX bug: per-item key material tied to global password, change cascades lose history.**
- Apple Notes reset docs: "Resetting the password doesn't give you access to previously locked notes. If you reset then create a new notes password, that only allows you to lock other notes." → password change is a forward-only operation on *new* locks; old locks are stuck on the old password.

**Obsidian Sync (2021+).**
- Per-vault encryption mode: **End-to-end (default) or Standard encryption**. Set at vault-creation time; choice only affects the *remote* vault, not the local vault.
- Standard encryption: Obsidian holds the key, can search, can serve web access. Standard is the *convenient* option; E2EE is the *paranoid* option.
- Password recovery: "if you forget your encryption password, your data remains encrypted and unusable forever. We're not able to recover your password, or any encrypted data for you." → the default-on-E2EE + zero-recovery story is the same data-loss vector as BooleBox.

**Anytype (2021+).**
- Account model: every user has a Vault (encrypted container, 12-word BIP-39 phrase). Spaces inside the vault are *also* encrypted. Two-layer encryption model (object-identity layer + content layer).
- Per-space *sharing*: personal spaces (E2EE, only the user) vs shared spaces (E2EE-with-members). The encryption mode is the same (E2EE); the *sharing scope* changes.
- Per-object ACL: "You cannot set permissions on a per-Object basis. All Space Members can view everything inside a Space. If you require more separation, use a different space and import only the content you are happy to share with everyone." → coarse-grained E2EE; no per-object downgrade.
- Vault key = recovery phrase; lost phrase = lost vault. "If you lose your Key and are logged out on all devices, there is no way to recover your Vault."

**Pattern across these three.**
- **Per-item key material + global password = catastrophic UX failure mode.** Apple Notes is the canonical example: change the global password, old items become inaccessible with the new password, and the UI doesn't make this clear until you're locked out.
- **Per-vault encryption mode at creation time is the simplest UX.** Obsidian's choice at remote-vault creation works because vaults are heavy-weight units; the user is already in setup mode.
- **Default = secure** for Anytype and Obsidian Sync (anytype: everything is encrypted by default; obsidian sync: E2EE is the default for new remote vaults, "we recommend end-to-end encryption for all users"). User *opts down* to standard encryption.

**Mistakes.**
1. **Apple Notes: per-note password history is invisible.** When a user changes their notes password, old locked notes keep the old password. The UI shows them in the locked list but with no visible "this one uses your old password" indicator. The user discovers the discrepancy only by trying to unlock and failing. Multiple Apple community threads on this. (Apple's docs do mention it, but only if you read the docs.)
2. **Obsidian: "no recovery" is the price of E2EE.** "We're not able to recover your password, or any encrypted data for you." This is honest, but it means a user who sets E2EE then forgets the password *loses all their remote vault* — even though they have all the local copies. The local data is not at risk, but the sync state is. Standard encryption (provider-held key) gives recovery; E2EE doesn't. Users who don't realize this pay the price.
3. **Anytype: shared-space UX can leak via member changes.** Each member added widens the attack surface ("Each additional member you add to a space widens its potential attack surface"). And the granularity is wrong: "You cannot set permissions on a per-Object basis. All Space Members can view everything inside a Space." → a single bad invite exposes everything in the space. Coarse-grained E2EE means coarse-grained leak.
4. **Anytype: recovery phrase is shown once at account creation, never again.** Lost phrase + lost devices = permanent loss. BIP-39 phrase is the only mechanism.

**What they'd do differently.**
- Apple Notes: keep per-note password history *visible* in the note metadata (e.g., "locked with password v1, last changed 2023-04-12"). Make "update all locked notes to current password" an explicit action, not a hidden behavior.
- Obsidian: add *escrowed recovery* as an optional second factor for the E2EE password (HSM, time-locked recovery, or a printable recovery kit). The "no recovery" stance is too hard for general users.
- Anytype: per-object ACL or per-subspace granularity. A space is too coarse for real collaboration.

**Direct lessons for Achiyon.**
- **Per-chat key material must be self-describing.** A vault chat's `ciphertext` blob needs metadata indicating which vault key version wraps it (analog to Apple's per-note password history). ADR-009's `ciphertext_meta` column should record `vault_key_version`, `vault_key_derivation` (Argon2id params), and `wrap_alg`. Then "upgrade this chat to vault" or "rotate vault key" can be deterministic operations that don't lose data.
- **Recovery must be designed for the user who loses their phone.** ADR-009's recovery token (random 256-bit, shown once) + Argon2id passphrase is right. But the *failure mode* of "user lost phone + forgot recovery token + forgot passphrase" is total data loss. Obsidian accepts this; Achiyon should at least surface the risk in the vault-enrollment flow ("If you lose all three — your phone, your recovery token, and your passphrase — your vault chats cannot be recovered. Period. There is no admin reset.")
- **Default should be the *secure* mode for new accounts, the convenient mode for migration.** ADR-009 calls the default "plain" — that's the right *migration* default (don't break existing users), but for *brand-new* accounts on day-one, vault could be default with a one-tap "I don't need this, give me the convenient mode" downgrade. This is Anytype's model. For Achiyon's hosted product, default-plain is the right choice; for vault to be the default for new users who *specifically come for privacy*, the per-chat field needs to be visibly offered at chat creation.
- **Coarse-grained vault granularity is wrong for roleplay use cases.** Anytype's "all members of a space see everything" is wrong for Achiyon: a user wants to share *one* roleplay world with a friend without sharing their entire history. Per-chat `encryption_mode` is the right granularity — and *per-shared-world encryption mode* should be a feature for shared worlds (ADR-009 calls this out: "Private world sharing = later feature (share-links)"). Per-world mode is a v1.5 extension.
- **Multi-device vault key escrow must be default.** Tauri OS keychain (desktop) and TEE-derived keys (mobile) make sense. But the *enrollment* moment — "this is your recovery token, write it down" — needs to be friction-light and unambiguous. Apple Notes' "Apple can't help you" warning is the right tone.

---

## Cross-cutting synthesis: lessons for Achiyon's per-chat `encryption_mode` field

These seven products converge on a set of principles that ADR-009's per-chat `encryption_mode` field must encode:

### A. The schema (Phase-0) is the right first move
Every product that shipped E2EE without a per-unit flag (Messenger, Apple Notes pre-2022, Zoom E2EE meetings) ended up adding one later — or struggling because they didn't have one. The Matrix `m.room.encryption` flag is the closest analog and the highest-value lesson. ADR-009's Phase-0 plan (`encryption_mode ∈ {plain, tee, e2ee}` as a nullable column + `ciphertext` / `ciphertext_meta` + `X-Achlys-Protocol-Version` header) is correct. The schema must land *before* any user-visible feature.

### B. Monotonicity is non-negotiable, enforced client-side
- WhatsApp: chat encryption state can only change visibly.
- Element: room encryption can be re-spoofed via state event (iOS 2024 bug, Matrix-spec #2302 moving to immutable).
- Achiyon: `encryption_mode` for a given chat can only transition forward (plain → TEE → vault), never backward. **Client-side enforcement**, not server-side. The client must cache its own view, validate on every sync, and the client's view wins on conflict. (Matrix-spec #147 "three information sources" rule.)

### C. Pre-existing content is *not* auto-encrypted
- Messenger: "If your chat wasn't previously secured ... interactions with messages sent before Messenger upgraded the chat won't be end-to-end encrypted."
- Apple Notes: password change is forward-only; old notes retain old password.
- Achiyon: "upgrade this chat to vault" must be a user action that explicitly scopes the upgrade to *new* content. Old messages stay plain. The UI should say so plainly.

### D. Two orthogonal indicators for two orthogonal state axes
- Google Messages: color = transport, lock = encryption. Two axes, two indicators.
- Proton Mail: lock color (black/blue/green) + lock icon (closed/open) + checkmark/warning inside. State = combination.
- iMessage: one indicator for two things → ambiguity when RCS came.
- Achiyon: chat list / chat header / chat composer are three places. Mode (plain/TEE/vault) and *something else* (e.g., AI presence, dreaming state, sharing state) must each have their own indicator. Don't overload color or icon.

### E. "Unencrypted" is a bad word
- Element: "Send unencrypted message" was misread as "no TLS." Years of complaints.
- Riot/Element #3628: proposed "SSL encryption: on, E2E encryption: off" or simply "Send a message" + "Send an encrypted message" as positive pair.
- Achiyon: use the ADR's neutral labels — plain, TEE, vault — in *every* UI string. Don't say "unencrypted," "insecure," "no encryption." Pair the secure state with a positive label ("Encrypted (vault)") and the plain state with a positive label ("Standard") if needed.

### F. Mode cue is permanent, not ephemeral
- WhatsApp "End-to-End Encrypted" banner disappears after a few seconds → users miss it.
- Element "invisible crypto" → users don't see encryption at all unless they look for absence of warning.
- Achiyon: per-chat mode indicator must be persistent in the chat header and visible in the chat list. Not a banner that fades. Not "invisible crypto." A label, with icon, always present.

### G. Feature-loss-in-secure-mode is the killer pattern
- Zoom E2EE meetings: "secure = inconvenient." Opt-in = niche.
- Messenger Secret Conversations: "secure = single device, no GIFs." Opt-in = niche.
- Anytype / Obsidian: default-secure works because the secure mode has *all* the features of the plain mode (with some tradeoffs, not deletions).
- Achiyon's vault mode must keep feature parity with plain mode. ADR-009's "generation in vault = BYOK browser-direct OR TEE worker" is the architectural answer: the server still generates, just inside an attested TEE. The user doesn't lose features; the operator loses visibility. *Do not* pivot vault-mode to "BYOK-only, power users" — that caps adoption at 5-15 % per ADR-009. The TEE worker path is the one that makes vault-mode non-downgrade.

### H. Lost key = lost data, and the user must know
- Apple Notes: per-note password history is invisible; password change cascades lose access to old notes.
- Obsidian Sync: "no recovery" is the price of E2EE.
- BooleBox: per-file Personal Key; lost key = lost data.
- Achiyon: the recovery token + Argon2id passphrase is the right shape, but the *enrollment UX* must be explicit about the three-factor recovery model (device, recovery token, passphrase) and the consequence of losing all three. "This chat cannot be recovered. Period." needs to be a sentence in the enrollment dialog, not a footnote in the docs.

### I. Cross-client state sync must be reliable and re-derived
- Element Android 2022: state stale, didn't re-sync until logout/login.
- Google Messages cross-platform 2024-2026: years of "lock means one thing on Android, nothing on iPhone."
- Achiyon: when a chat is upgraded to vault on device A, device B must reflect within one sync window. The local "is this chat vault?" state must be re-derived on every app foregrounding, not cached from login.

### J. Cross-mode (per-mode within one account) visibility must be coherent
- Box KeySafe: file content E2EE, metadata provider-encrypted → side-channel.
- Tresorit: folder-level keys with member re-wrap.
- iMessage: one color, two meanings → confusion.
- Achiyon: every byte of a chat row must be classified by mode. ADR-009's `ciphertext` + `ciphertext_meta` is the start; dreaming memory index, attachment indices, and any future columns must inherit the chat's `encryption_mode`. A future schema PR that adds a new column without mode-classification is a security regression.

### K. Per-item upgrade UX must surface the cost
- Messenger: "this chat will become E2EE from this point forward; reactions to old messages won't be E2EE."
- Zoom: "this meeting will lose cloud recording, AI Companion, dial-in."
- Apple Notes: "this note will lose PDF/audio/video attachments."
- Achiyon's "upgrade this chat to vault" modal should list, in plain language: which features change, which history is in scope, what recovery options exist, and what happens if recovery fails.

### L. Default-on is the only way to make "secure" the *normal* mode
- WhatsApp (2016 default) → 1B users secured in 6 months.
- Messenger (2016 opt-in → 2023 default) → 7 years to migrate, partial.
- Signal (drop SMS rather than keep plaintext alongside) → simple, principled, lost user share.
- Achiyon's hosted default is plain (correct — most users don't need vault; the hosted product must stay affordable). But *for privacy-sensitive cohorts* (the roleplay-user-with-sensitive-content persona), vault should be the default-on offer at account creation, with plain as the one-tap downgrade. This is the Anytype / Obsidian model and is the only way to avoid the "secure = inconvenient" brand.

---

## What we should explicitly do (and not do) in Achiyon

**Do.**
- Land Phase-0 schema (ADR-009 §Phase-0) before any user-visible feature. `encryption_mode`, `ciphertext`, `ciphertext_meta`, protocol-version header. The schema must support *every* row's mode being changed independently.
- Per-chat mode badge in chat list *and* chat header, permanent, label-plus-icon (not color alone).
- Per-chat mode-cue in the composer: not "Send unencrypted" but "Send in standard mode" with a paired "Encrypted (vault)" indicator for vault chats.
- Per-chat upgrade modal that lists feature changes, history scope, recovery options, and recovery failure consequence. Two confirmations (Matrix #147: three-source confirmation for plain sends).
- Recovery token enrollment at first vault chat, explicit three-factor warning. Argon2id params + recovery token + device-held key.
- Client-side monotonicity enforcement: client's view of `encryption_mode` is trusted; server's view is validated against it; on conflict, client wins and user is notified.
- Sync freshness: re-derive `encryption_mode` from the network on every app foreground, not cached from login.
- TEE worker path for vault generation (not BYOK-only), to keep vault-mode feature-parity with plain-mode.
- Dreaming in vault = client-side WASM on phones, opt-out toggle, never server-side. Indexed search over decrypted local cache (Proton Drive model), never server-side search over vault ciphertext.

**Don't.**
- Don't ship an E2EE/opt-in mode that's less capable than the default for years (Messenger Secret Conversations mistake).
- Don't use color as the sole encryption indicator (iMessage mistake; also WhatsApp's red-key-change banner).
- Don't let the encryption cue be ephemeral (WhatsApp "End-to-End Encrypted" banner that fades).
- Don't use the word "unencrypted" in any user-facing string (Element #3628 mistake).
- Don't trust server-side state for the encryption decision (Matrix iOS 2024 downgrade-attack bug).
- Don't allow silent downgrades (WhatsApp rule; Element-meta #147).
- Don't auto-encrypt existing chat history on upgrade (Messenger rule; user action is the boundary).
- Don't lose feature parity between modes (Zoom / Messenger mistake). Vault mode must support generation, dreaming, attachments, voice, image — everything plain does.
- Don't make recovery a footnote. Make it an enrollment moment.
- Don't ship per-item encryption without per-item key-version metadata (Apple Notes per-note password history mistake).
- Don't split encryption modes at the attribute level (Box KeySafe metadata side-channel).
- Don't allow a chat to be vault-mode but the dream index for that chat to be plain-mode on the server (mode inheritance for every column).

---

## Citations and primary sources

- Messenger Secret Conversations launch (2016-07): https://about.fb.com/news/2016/07/messenger-starts-testing-end-to-end-encryption-with-secret-conversations/
- Messenger Secret Conversations technical whitepaper (2017-05): https://about.fb.com/wp-content/uploads/2016/07/messenger-secret-conversations-technical-whitepaper.pdf
- Default E2EE for Messenger (2023-12-06): https://about.fb.com/news/2023/12/default-end-to-end-encryption-on-messenger/
- E2EE on Messenger explained (2024-03): https://about.fb.com/news/2024/03/end-to-end-encryption-on-messenger-explained/
- Accountable Tech survey (2024-05): https://accountabletech.org/research/metas-e2e-survey/
- Engineering at Meta (2023-12-06): https://engineering.fb.com/2023/12/06/security/building-end-to-end-security-for-messenger/
- Google Messages E2EE overview (white paper): https://www.gstatic.com/messages/papers/messages_e2ee.pdf
- Google Messages E2EE support: https://support.google.com/messages/answer/10262381
- Google RCS security: https://support.google.com/messages/answer/9592174
- E2EE RCS rolls out for Android+iPhone (2026-05): https://blog.google/products-and-platforms/platforms/android/android-ios-end-to-end-encrypted-rcs-messaging/
- Apple E2EE RCS newsroom (2026-05): https://www.apple.com/newsroom/2026/05/end-to-end-encrypted-rcs-messaging-begins-rolling-out-today-in-beta/
- Forbes "After 15 Years — Apple Changes Green Bubbles" (2026-05-15): https://www.forbes.com/sites/zakdoffman/2026/05/15/confusing-apple-changes-iphone-green-bubbles-after-15-years/
- DOJ antitrust lawsuit (2024-03): https://arstechnica.com/tech-policy/2024/03/apples-green-bubbles-targeted-by-doj-in-lawsuit-over-iphone-monopoly/
- UX design critique of green bubble contrast: https://uxdesign.cc/how-apple-makes-you-think-green-bubbles-gross-e03b52b12fed
- Matrix-ios-sdk downgrade advisory (2024): https://github.com/matrix-org/matrix-ios-sdk/security/advisories/GHSA-fxvm-7vhj-wj98
- Matrix-spec #2302 immutable encryption: https://github.com/matrix-org/matrix-spec/issues/2302
- Matrix-spec #535 (encryption event handling): https://github.com/matrix-org/matrix-spec/issues/535
- Element-meta #2746 (composer encryption state): https://github.com/element-hq/element-meta/issues/2746
- Element-meta #2961 (blue broken padlock confusion): https://github.com/element-hq/element-meta/issues/2961
- Element-web #3628 ("unencrypted" wording complaint): https://github.com/element-hq/element-web/issues/3628
- Element-web #20865 (silent E2EE disable on Android): https://github.com/vector-im/element-web/issues/20865
- Element-meta #147 (clear encryption indicator): https://github.com/element-hq/element-meta/issues/147
- Element-meta #69 (misconfigured encryption handling): https://github.com/vector-im/element-meta/issues/69
- Element-web PR #30440 (blue lock for unencrypted): https://github.com/element-hq/element-web/pull/30440
- Tresorit folder sharing architecture: https://support.tresorit.com/hc/en-us/articles/216114387-Folder-sharing-architecture-in-Tresorit
- Tresorit encryption whitepaper: https://prodfrontendcdn.azureedge.net/202208011608/tresorit-encryption-whitepaper.pdf
- Proton Drive security model: https://proton.me/blog/protondrive-security
- Box KeySafe: https://support.box.com/hc/en-us/articles/31479910481811-About-KeySafe
- Box KeySafe keyless auth: https://support.box.com/hc/en-us/articles/52499402534291-KeySafe-Keyless-Authentication
- BooleBox Personal Key: https://www.guideboolebox.com/en/documentation/android-en_1410/android-en_141005/
- Zoom E2EE for meetings: https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0075502
- Zoom E2EE using: https://support.zoom.com/hc/en/article?id=zm_kb&sysparm_article=KB0065408
- Zoom E2EE rollout blog (2020): https://www.zoom.com/en/blog/zoom-rolling-out-end-to-end-encryption-offering/
- Zoom PQ E2EE sovereign controls: https://library.zoom.com/advanced-enterprise-services/public-sector-sovereignty-controls/european-union-public-sector-sovereignty-controls-explainer.md
- Apple Notes locked notes security: https://support.apple.com/guide/security-pdf/secure-features-in-the-notes-app-sec1782bcab1/web
- Apple Notes lock note on Mac: https://support.apple.com/guide/notes/lock-your-notes-not28c5f5468/mac
- Apple community thread (lost locked note content): https://discussions.apple.com/thread/256088704
- Obsidian Sync security: https://obsidian.md/help/sync/security
- Anytype docs — Vault: https://doc.anytype.io/anytype/basics/vault
- Anytype docs — Privacy & Encryption: https://doc.anytype.io/anytype/data/privacy-and-encryption
- Anytype deepwiki — Vault & Key Mgmt: https://deepwiki.com/anyproto/docs/2.2-vault-and-key-management
- Anytype deepwiki — Encryption Model: https://deepwiki.com/anyproto/docs/7.1-encryption-model
- any-sync access control and encryption: https://sync.any.org/access-control/
- Apple ADP iCloud overview: https://support.apple.com/en-euro/102651
- Apple ADP announcement (2022-12): https://www.macrumors.com/2022/12/07/apple-advanced-data-protection/
- Apple ADP global expansion (2023-01): https://www.macrumors.com/2023/01/18/ios-16-3-advanced-data-protection-global/
- Apple ADP UK withdrawal (2025-02): https://www.macrumors.com/2025/02/26/advanced-data-protection-uk-need-to-know/
- WhatsApp complete E2EE (2016-04): https://blog.whatsapp.com/end-to-end-encryption
- WhatsApp E2EE backups (2021-09): https://engineering.fb.com/2021/09/10/security/whatsapp-e2ee-backups/
- WhatsApp E2EE backups announcement: https://about.fb.com/news/2021/10/end-to-end-encrypted-backups-on-whatsapp/
- WhatsApp E2EE backup explainer (Wired): https://www.wired.com/story/whatsapp-end-to-end-encrypted-backups/
- WhatsApp security code change FAQ: https://faq.whatsapp.com/820124435853543/
- WhatsApp E2EE chat label (WABetaInfo 2.24.6.11): https://wabetainfo.com/whatsapp-beta-for-android-2-24-6-11-whats-new/
- WhatsApp E2EE chat label (Indian Express, 2024-03-12): https://indianexpress.com/article/technology/tech-news-technology/whatsapp-end-to-end-encrypted-badge-9209975/
- Telegram FAQ — Secret Chats: https://telegram.org/faq?setln=en%23secret-chats
- Telegram Secret Chats protocol: https://core.telegram.org/api/end-to-end
- Telegram BB secret chats: https://core.telegram.org/blackberry/secretchats
- Signal SMS removal (2022-10): https://signal.org/blog/sms-removal-android/
- Signal-Android #945 (color confusion): https://github.com/signalapp/Signal-Android/issues/945
- Signal-Android #12517 (SMS removal backlash): https://github.com/signalapp/Signal-Android/issues/12517
- Proton Mail lock icons meaning: https://proton.me/support/encryption-lock-meaning
- Proton Mail encryption overview: https://proton.me/blog/encrypted-email