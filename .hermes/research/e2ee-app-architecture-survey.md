# E2EE App Architecture Survey — How Successful Apps Solve the "Server Can't Read" Tension

**Compiled:** 2026-09-18 (for Achiyon / Achlys — self-hostable AI roleplay app, SvelteKit frontend + Rust/Axum/PostgreSQL backend, server-side LLM generation via external proxy)
**Authored by:** subagent (hermes) for parent agent
**Purpose:** Answer the question: "If we want true zero-knowledge E2EE, do successful apps conclude that all server-side features have to be rebuilt client-side? What architecture do they actually ship?"

---

## TL;DR (read this if you read nothing else)

Every successful E2EE product surveyed **does exactly the same thing**: the server is reduced to a dumb authenticated pipe (queue / blob store / relay), and **every "smart" server-side feature is either (a) moved into the client, (b) deleted, or (c) replaced with a privacy-preserving server primitive (oblivious computation in an enclave, SSE-style encrypted search index, etc.)**. The industry has *not* found a way to keep server-side prompt assembly / memory consolidation / search / contact discovery while the operator remains blind to plaintext. The architecture the builder is arriving at (encrypted-on-the-wire, server-side LLM still gets ciphertext it cannot read) is *exactly* the architecture Signal, WhatsApp, Standard Notes, Notesnook, Cryptomator, Anytype, Obsidian Sync, Matrix+Megolm, and Proton all converged on — but with one critical caveat for AI workloads, covered in §Synthesis #4.

---

## 1. Signal — "essentially all app logic runs client-side, server is a dumb encrypted message queue + auth + push"

**Verdict on the question: yes, that's the correct high-level model.**

### What runs on the Signal server (only)
1. **Authenticated encrypted message queue.** A per-device mailbox holds ciphertext blobs until the recipient comes online; deleted after delivery ACK. Source: Signal's Sesame spec — "The server temporarily stores the messages that devices send to each other, until the messages are fetched." (https://signal.org/docs/specifications/sesame/)
2. **Prekey bundle store.** Clients upload identity keys, signed prekeys, and one-time prekeys at registration; senders fetch a bundle to run X3DH with an offline recipient. (Signal's 2016 whitepaper pattern, still in use; see formal model https://css.csail.mit.edu/6.858/2024/readings/signal-formal.pdf)
3. **Push notifications** (via APNs/FCM) — wakes the device.
4. **Account metadata required for delivery routing** — phone number linked to ACI (account UUID), registration timestamp, last-seen timestamp. Per Signal's published transparency reports: "The only information Signal maintains that is encompassed by the subpoena for any particular user account… is the time of account creation and the date of the account's last connection to Signal servers." (security.stackexchange.com citation of Signal grand-jury subpoena response, 2016)
5. **Sealed-sender delivery token check.** A 96-bit token derived from the recipient's profile key; sender must prove knowledge to send. Sender certificate validation rate-limited for spam. (https://signal.org/blog/sealed-sender/)
6. **Private contact discovery inside an SGX enclave** — the most architecturally interesting piece. Plaintext contact lookup never happens on the host OS; the enclave matches encrypted hashed identifiers inside hardware-encrypted RAM with Path ORAM to defeat access-pattern leakage. The whole CDSi (ContactDiscoveryService-Icelake) stack is open source at github.com/signalapp/contactdiscoveryservice-icelake. (https://signal.org/blog/private-contact-discovery/, https://signal.org/blog/building-faster-oram/)

### What runs on the Signal client (essentially everything else)
- **Message composition / encryption** (X3DH + Double Ratchet). The Double Ratchet state is held in client memory; the server never sees chain keys.
- **Local message storage** — Signal Desktop uses an encrypted SQLCipher local DB (key randomly generated and stored via Electron safeStorage / OS keychain). (github.com/signalapp/Signal-Desktop/blob/main/app/main.ts, https://github.com/signalapp/Signal-Desktop/pull/6933)
- **Local search** — Signal Desktop client builds a full-text index on the device because the server has no plaintext to index. (No public docs claim otherwise; consistent with all other E2EE messengers.)
- **Profile name/avatar storage and lookup** — profile key encrypted, exchanged via the messaging channel. Server holds ciphertext profile blobs only.
- **Group state** — group master keys, membership, titles are client-side; server stores opaque group IDs and member lists. Sender-key protocol fans out a single group ciphertext that the server replicates; rotation keys are distributed client-to-client.
- **Safety number verification** — derived from public identity keys, verified by humans or via Signal's key transparency log (attestation).
- **Multi-device history transfer** — direct device-to-device encrypted sync; server never sees plaintext history. (multi-device 2021 rebuild, per WhatsApp/Ethora analysis noting the parallel)
- **Sender anonymity (sealed sender)** — the actual *cryptographic construction* (envelope encryption, ACI-only sender certificate when phone-number sharing is off) runs entirely client-side. The server just sees a delivery token + ciphertext blob addressed to a recipient. (https://signal.org/blog/sealed-sender/)
- **Contact-lookup request** — the client transmits *hashed* phone numbers to the SGX enclave; only the enclave sees the plaintext within its encrypted RAM.

### What the Signal server DOES NOT do (and the client must do instead)
- Server-side search → **client-side index**
- Server-side social graph → **SGX-enclave contact discovery with the data owner supplying plaintext**
- Server-side message archive → **client-side encrypted DB + per-device history transfer**
- Server-side content moderation → **sender certificate rate-limiting (authentication-based, not content-based)** + ephemeral delivery tokens for spam
- Server-side key generation → **all keys generated on device**
- Server-side profile → **profile keys never leave device; avatar URLs are opaque blob pointers**

### Sources
- https://signal.org/docs/specifications/sesame/ — Sesame spec, server model
- https://signal.org/blog/sealed-sender/ — sealed sender, what server knows
- https://signal.org/blog/private-contact-discovery/ — SGX enclave
- https://signal.org/blog/building-faster-oram/ — Path ORAM in enclaves
- https://github.com/signalapp/contactdiscoveryservice-icelake — contact discovery service source
- https://css.csail.mit.edu/6.858/2024/readings/signal-formal.pdf — formal Signal model
- https://github.com/signalapp/Signal-Desktop/blob/main/app/main.ts — SQLCipher key gen, init
- https://github.com/signalapp/Signal-Desktop/blob/main/DATABASE_SCHEMA.md — local schema
- https://github.com/signalapp/Signal-Desktop/pull/6933 — safeStorage integration
- Signal 2016 subpoena response (cited via security.stackexchange.com/q/272982)

---

## 2. WhatsApp E2EE — same architecture, hardened for billion-user scale

**Verdict: yes — WhatsApp's server is exactly "encrypted blob router that forgets." Meta could not comply with a court order for plaintext messages even if compelled.**

### What runs on the WhatsApp server
- **Encrypted message router / store-and-forward queue.** Per-user mailbox sharded by `recipient_id` (Cassandra + Mnesia); ciphertext blobs held until delivery ACK, then deleted (typical TTL 30 days). "The server is a temporary mailbox, not permanent storage." (https://sysdesign.wiki/systems/whatsapp/, https://hellosde.com/realtime-system-design-problems/1-chat-messaging/whatsapp-offline-delivery.html)
- **Key distribution** — prekey bundle server (identity key, signed prekey, one-time prekey). Initiator fetches bundle, performs X3DH, server never sees the resulting shared secret. (WhatsApp Security Whitepaper, 2016)
- **Multi-device fan-out** — each linked device has its own identity keys; sender encrypts once per recipient device; server routes N ciphertexts. Post-2021 multi-device architecture (Ethora analysis): each device signs up independently with its own Signal Protocol keys; server routes parallel ciphertexts.
- **Connection registry / presence** — which device is online, on which chat-server shard (Erlang/BEAM, ~1M+ concurrent WebSockets per node).
- **Delivery receipts / read receipts** — metadata only.
- **Group sender-key distribution** — sender generates one symmetric group key, distributes via per-recipient Signal sessions; sender-key rotated on join/leave. Server fans out the ciphertext.
- **Push wake-up** — APNs/FCM (the only place the server touches plaintext identifiers — phone numbers — for APNs token routing).
- **Account metadata** — phone numbers (for routing), registration time, push tokens. Meta cannot read message content but does see "who messaged whom, when, message sizes" (Ethora, hellosde).
- **Media CDN** — encrypted media blobs stored in object storage; uploaded once, downloaded on demand via encrypted pointer + key inside the message. Server sees a CDN URL, not the content. (https://ethora.com/blog/whatsapp-system-design/)

### What runs on the WhatsApp client (everything else)
- **Plaintext message composition**
- **Double Ratchet state and message-key derivation** (forward secrecy, post-compromise security)
- **Message storage** — "Every client stores messages locally in SQLite. The server is not a message archive – it's a queue that holds encrypted payloads until the recipient comes online, then delivers and discards. If you delete the app, your message history is gone unless you had cloud backup enabled." (Ethora)
- **Client-side backups** — Google Drive / iCloud backups are E2EE with a user-held 64-digit key; server holds ciphertext blob of backup, cannot read.
- **History transfer on new device link** — direct phone-to-new-device encrypted transfer, server-blind. ("A significant re-engineering of the key management layer underneath." — Ethora)
- **Group key generation, sender-key creation, key rotation on member change**
- **Search (per-message) — client-side only.** (Signal and WhatsApp are explicit that server-side content search is impossible; the Ethora system-design piece spells this out: "content search server-side becomes impossible, which is why search is a client-side feature.")
- **Encryption metadata signing** (Noise Pipes long-running transport, Curve25519 / AES-GCM / SHA256)

### What WhatsApp deliberately does NOT do on the server
- Server-side search of message content
- Server-side moderation of content (only metadata-based rate limiting)
- Server-side message archive after delivery (the server "forgets")
- Server-side key escrow
- Reading the plaintext even with a search warrant (their legal position is and has been "we cannot")

### Sources
- https://s3.documentcloud.org/documents/2786495/WhatsApp-Security-Whitepaper-April-4-2016.pdf — canonical 2016 whitepaper
- https://ethora.com/blog/whatsapp-system-design/ — detailed 2024 walkthrough
- https://sysdesign.wiki/systems/whatsapp/ — system design decomposition
- https://hellosde.com/realtime-system-design-problems/1-chat-messaging/whatsapp-offline-delivery.html — explicit "dumb encrypted mailbox" framing
- https://techinterview.coach/blog/system-design-of-whatsapp/ — billion-user architecture
- https://thecodeforge.io/system-design/design-whatsapp/ — Cassandra schema, fan-out, dedup

---

## 3. Standard Notes & Notesnook — E2EE notes; server is dumb encrypted blob store; **yes, they ship native apps per platform**

**Verdict: server reduced to "save values on demand"; all key derivation, encryption, decryption, indexing runs on device; both ship Web + Desktop + Mobile (with native elements where they matter).**

### Standard Notes

**What runs on the Standard Notes server:**
- Encrypted payload storage (UUID-keyed ciphertext blobs) — `items_key_id`, `enc_item_key`, `content`. Spec is explicit: "It treats the server as a dumb data-store that simply saves and returns values on demand." (https://github.com/standardnotes/snjs/blob/main/packages/snjs/specification.md, https://standardnotes.com/help/security/encryption)
- Account registration / password-reset using only the *second half* of the password-stretched key (the "serverPassword"); the first half (`masterKey`) never leaves the device.
- Encrypted value-storage (preferences, session tokens) — server stores ciphertext.

**What runs on the Standard Notes client:**
- **Argon2id KDF** from password → root key.
- Random **items keys** encrypted under root key, uploaded as ciphertext items (each one is itself an encrypted item).
- Per-item random **item key** → AES-256 + XChaCha20-Poly1305 encryption (current protocol 004). Each note gets its own ephemeral content key.
- **Device storage encryption (DSE)** — local SQLite DB encrypted with account keychain key (Mac/Windows/Linux keychains, iOS/Android secure enclaves). Web falls back to a user-chosen passcode that wraps the local key with PBKDF2-derived AES-256. (https://standardnotes.com/blog/enhanced-security-with-device-storage-encryption, https://standardnotes.com/help/79)
- **Search index** — client-side only (the entire local DB is already client-side after decryption).
- **Root key wrapper (passcode)** — client-only; ephemeral; user re-prompts on every launch.

**Standard Notes apps shipped:** Web (browser SPA), Desktop (Electron — macOS, Windows, Linux), iOS, Android — native per platform, sharing the `snjs` TypeScript core. (Repository: github.com/standardnotes/app, monorepo with packages for web/desktop/mobile.)

### Notesnook

**What runs on the Notesnook server:**
- Encrypted blob storage per user (Microsoft SignalR sync server, ASP.NET Core backend). (https://github.com/streetwriters/notesnook/, openapps.pro/projects/notesnook)
- Account/password auth — server gets only the Argon2 hash of the password, which is then hashed *again* server-side to mitigate password-passthrough attacks. (https://help.notesnook.com/how-is-my-data-encrypted)
- Stores encrypted SQLite blobs (`cipher`, `iv`, `salt`, `alg`, `id`) — server "performs no further operation on this data (because it can't)."

**What runs on the Notesnook client:**
- **Argon2id** password hashing; **Argon2i** PKDF.
- **Two-tier key model** — data encryption key (random, encrypts all notes) wrapped under a master key derived from password+salt.
- **XChaCha20-Poly1305-IETF** symmetric encryption per item, via libsodium wrapped in `@notesnook/sodium` + `@notesnook/crypto` (cross-platform Node.js/Browser/WebAssembly bridge). All three platforms (web, desktop, mobile) share the exact same library.
- **Encrypted SQLite database** at rest — `better-sqlite3-multiple-ciphers` encrypts the entire SQLite file. Even a stolen device backup or filesystem snapshot is unreadable without the master key. (openapps.pro)
- **Local indexes** built after decryption, also stored locally — per Notesnook's design: search runs against decrypted local index, never on server.
- **Key storage**: Web/Desktop in IndexedDB as a non-exportable `CryptoKey`; iOS/Android in OS keychain.

**Notesnook apps shipped:** Web (SPA), Desktop (Electron — macOS/Windows/Linux), Android + iOS (React Native). (github.com/streetwriters/notesnook README — monorepo with apps/web, apps/desktop, apps/mobile; shared `@notesnook/core`, `@notesnook/crypto`, `@notesnook/editor`.)
- A **Vericrypt** companion tool lets users *mathematically verify* their data is encrypted before it leaves the device — auditable proof of zero-knowledge claim.

**Notesnook also exposes a self-hosting option for the sync server** (in progress per the homepage), confirming their stance that the *app* is the source of truth and the server is just a relay.

### What these E2EE notes apps deliberately do NOT do on the server
- Server-side content search
- Server-side notes/index generation
- Server-side key generation (all keys derived on device)
- Server-side feature gating based on content
- Server-side deduplication of note content (would leak "this same text appears in multiple users' vaults")

### Sources
- https://standardnotes.com/help/security/encryption — Standard Notes encryption whitepaper
- https://standardnotes.com/help/3/how-does-standard-notes-secure-my-notes — overview
- https://standardnotes.com/help/79 — local encryption configurations
- https://standardnotes.com/blog/enhanced-security-with-device-storage-encryption — DSE details
- https://github.com/standardnotes/snjs/blob/main/packages/snjs/specification.md — protocol spec
- https://github.com/standardnotes/app — monorepo (web, desktop, mobile)
- https://help.notesnook.com/how-is-my-data-encrypted — Notesnook encryption details
- https://github.com/streetwriters/notesnook — monorepo + tech stack
- https://github.com/streetwriters/notesnook/blob/master/apps/web/at-rest-encryption.md — at-rest encryption design
- https://openapps.pro/projects/notesnook — architecture analysis
- https://notesnook.com/ — homepage + self-hosting note

---

## 4. Cryptomator / Anytype / Obsidian Sync — "server = anything that syncs, app = everything"

**Verdict: yes, these are the cleanest proof of the "server-as-dumb-storage, app-as-everything" model. Cryptomator is the strongest case — it explicitly does not even *have* its own server.**

### Cryptomator

**What runs on the Cryptomator server (i.e. any cloud sync service — Dropbox, Drive, OneDrive, MEGA, pCloud, Nextcloud, S3, etc.):**
- Literally just stores opaque files in a folder. Nothing else. No metadata about content. No user account system at all ("No accounts, no data shared with any online service"). (github.com/cryptomator/cryptomator)
- Holds `vault.cryptomator` (signed JWT pointing to the masterkey location), `masterkey.cryptomator` (wrapped keys + scrypt params), and a tree of `d/<hash>/<hash>.c9r` ciphertext files. Nothing else.

**What runs on the Cryptomator client (and only on the client):**
- **Vault master key management** — 256-bit encryption key + 256-bit MAC key, each wrapped with AES Key Wrap (RFC 3394) under a KEK derived from the user's password via scrypt (N=32768, r=8).
- **Virtual drive filesystem layer** — Cryptomator mounts a virtual drive via FUSE (Linux), macFUSE (macOS), WinFsp (Windows), with WebDAV loopback fallback. Every read/write to a virtual file is transparently en-/decrypted on-the-fly.
- **File content encryption** — AES-256-GCM, broken into 32 KiB chunks with per-chunk nonces, AAD binding the chunk number + file header nonce (prevents reordering and rebinding attacks). Per-file random content key stored in the file header (which itself is AES-GCM-encrypted with the master key).
- **Filename encryption** — AES-SIV mode encrypts filenames, binding the parent directory ID as associated data (prevents undetected file moves between directories).
- **Directory hierarchy obfuscation** — directory IDs are AES-SIV-encrypted then SHA-1-hashed then Base32-encoded, producing a flattened structure (`/d/<2chars>/<30chars>/`). From the outside, all directories look like siblings.
- **Hub mode (optional)** — adds ECDH-ES (P-384) JWE for sharing vault access among multiple users; master key never leaves any individual device unwrapped.

**Cryptomator apps shipped:** Desktop apps for macOS, Windows, Linux; iOS and Android apps. (Cryptomator explicitly lists all three desktop OSes in the README.) Plus an optional Cryptomator Hub server (Docker-deployable) for vault sharing — but even there, the server holds only wrapped keys.

**This is the clearest possible demonstration of the "server is dumb" principle.** You can take your Cryptomator vault folder and point any sync mechanism at it — iCloud, Dropbox, SFTP, rsync over SSH, USB stick — and it works. The "server" isn't part of the cryptographic protocol at all.

### Anytype (via the any-sync protocol)

**What runs on Anytype's sync/file/consensus/coordinator nodes:**
- **Sync nodes** store and process "spaces" (CRDT-based object graphs). All content is encrypted before it leaves the device; the sync node sees only ciphertext DAGs (any-sync uses encrypted DAGs as the fundamental data structure). (https://github.com/anyproto/any-sync, https://tech.anytype.io/any-sync/overview)
- **File nodes** store encrypted file blobs in a private IPFS network (flatfs dir layout).
- **Consensus nodes** monitor ACL changes and validate them.
- **Coordinator nodes** store infrastructure config — which devices, which spaces, which nodes serve which spaces.
- A **two-layer encryption model** is used: any-sync encryption layer 1 (the "space key") is *shared* with backup nodes (they need it to group changes for delivery), but layer 2 (the "data key") never leaves the device. So backup nodes can route your data but cannot read it. (https://doc.anytype.io/anytype/data/privacy-and-encryption)
- Local p2p mode via mDNS for LAN sync without touching external nodes.
- **Local-only mode** for users who want no server at all.

**What runs on the Anytype client:**
- **Local-first storage** — primary copy of every object is on the device. "All your content is stored locally on your device, and even your access keys are generated on your own hardware." (https://doc.anytype.io/anytype/data/sync-and-backup)
- **All indexes** — "Indexes stay local and unencrypted. In order to search your documents efficiently, Anytype builds local indexes from your encrypted objects, decrypting them on the fly with your keys. These indexes are stored separately from the encrypted data itself and aren't encrypted — this assumes your local device hasn't been compromised. **Indexes never sync.**"
- **CRDT merging** — conflict-free replicated data types resolved entirely on-device. No server-side merge.
- **Ed25519 signing** of every change.
- **Peer discovery and direct p2p sync** between devices on the same LAN via mDNS — the network is optional.

**Anytype apps shipped:** Desktop (macOS, Windows, Linux — Electron-based), iOS, Android (native). Multi-device sync uses any-sync protocol with optional Anytype Network backup, self-hostable sync node, or local-only.

### Obsidian Sync

**What runs on the Obsidian Sync server:**
- Encrypted vault storage — file content encrypted with AES-256-GCM under a key derived from the user's password via scrypt(N=32768, r=8, p=1) → HKDF → encryption key. (https://obsidian.md/help/sync/security)
- Metadata for sync coordination (which device uploaded/deleted, when, the *mapping* between encrypted paths and encrypted content) — explicitly NOT end-to-end encrypted so the server can route changes and maintain version history. (https://obsidian.md/help/sync/security — Limitations section)
- Deterministic file-hash encryption for dedup — encrypted hashes are deterministic so the server can detect "this file already exists, don't re-upload." Acknowledged trade-off: a compromised server could theoretically test "does user have file X" by forcing uploads. (https://obsidian.md/help/sync/security — Deterministic file-hash encryption)
- **Optional non-E2EE mode ("Standard encryption")** where Obsidian holds the key — for cases where the vault is publicly published anyway (Obsidian Publish).

**What runs on the Obsidian client:**
- **All vault parsing, indexing, search, plugin execution.** Obsidian's value proposition *is* the local app — the Sync server is a bolt-on.
- **Encryption** of every file chunk before upload.
- **scrypt key derivation** from password + per-vault salt.
- **Verification tooling** — Obsidian publishes a "how to verify Obsidian Sync's end-to-end encryption" guide that lets users capture WebSocket frames and decrypt them with their own password using Node.js, proving the server is not altering the ciphertext. (https://obsidian.md/blog/verify-obsidian-sync-encryption/)

**Important caveat — the 2025 Trail of Bits audit found significant issues** with the Sync protocol (weak randomness TOB-OBSYNC-1, missing path↔content cryptographic binding TOB-OBSYNC-10, deterministic hash collisions). (https://obsidian.md/files/security/2025-Obsidian-TrailofBits-Sync-Audit.pdf) Obsidian's E2EE model is *in the right place architecturally* (client encrypts, server stores ciphertext) but the implementation has historically been weaker than the others surveyed here. The model holds; the implementation has room to grow.

**Obsidian apps shipped:** Desktop (macOS, Windows, Linux — Electron), iOS, Android. All platforms can encrypt locally and sync via the Obsidian Sync server.

### Common pattern across all three
- The "server" (whether Sync, Dropbox, or any-sync node) holds encrypted blobs.
- All encryption, indexing, search, parsing happens client-side.
- All three ship native-quality desktop + mobile apps; none rely on a "thin browser app."
- The app is the product; the server is plumbing.

### Sources
- https://docs.cryptomator.org/security/architecture/ — Cryptomator security architecture
- https://docs.cryptomator.org/security/vault/ — vault cryptography
- https://github.com/cryptomator/cryptomator — README
- https://safe-online-documents.com/guides/client-side-encryption-with-cryptomator — walkthrough
- https://tech.anytype.io/any-sync/overview — any-sync protocol overview
- https://github.com/anyproto/any-sync — repo
- https://doc.anytype.io/anytype/data/sync-and-backup — sync + backup
- https://doc.anytype.io/anytype/data/privacy-and-encryption — encryption layers
- https://doc.anytype.io/anytype/data/storage — storage
- https://anytype.io/ — homepage
- https://obsidian.md/help/sync/security — Obsidian Sync security (incl. limitations)
- https://obsidian.md/blog/verify-obsidian-sync-encryption/ — verification guide
- https://obsidian.md/files/security/2025-Obsidian-TrailofBits-Sync-Audit.pdf — 2025 audit

---

## 5. Matrix/Megolm & Proton — the middle-ground examples

These two are the most directly relevant to Achiyon because they run a *server-side protocol* (homeserver / Proton API) with E2EE on top. They show what *cannot* be encrypted even when you try.

### Matrix + Megolm

**What runs on the Matrix homeserver (server):**
- **Stores ciphertext** for all `m.room.encrypted` events. Cannot read them. (https://matrix.org/docs/matrix-concepts/end-to-end-encryption/)
- **Stores plaintext for unencrypted rooms.** This is the entire point — E2EE is *opt-in per room*. By default, rooms are not encrypted, and the homeserver can see everything. Encrypted rooms are flagged with `m.room.encryption` state event.
- **Stores metadata for all rooms (encrypted or not):** sender UserID, room ID, event ID, timestamp, server membership. This is the metadata leak — encrypted or not, the homeserver knows who is talking to whom and when.
- **Device list management** — `/keys/query` and `/keys/claim` endpoints: clients upload device identity keys, fetch other users' device lists and one-time keys to start Olm sessions. (https://matrix.org/docs/matrix-concepts/end-to-end-encryption/)
- **Key backup** (optional) — encrypted backups stored server-side, decrypted with a recovery key that only the user holds.
- **Server-side search** — but **only works for unencrypted rooms**. The homeserver's `event_search` table is a Postgres `tsvector` index over `content.body`, `content.name`, `content.topic`. For E2EE rooms this index is empty. Synapse's own search code: `SELECT ts_rank_cd(vector, to_tsquery('english', ?)) AS rank, room_id, event_id FROM event_search WHERE vector @@ to_tsquery('english', ?)`. (https://github.com/matrix-org/synapse/blob/v1.9.1/synapse/storage/data_stores/main/search.py)
- **Account management** — registration, password, device list, push tokens, presence.

**What runs on the Matrix client (everything else for E2EE rooms):**
- **All Megolm session state** — outbound group session (never leaves device), inbound group sessions received via Olm-encrypted `m.room_key` events. (https://matrix-org.github.io/matrix-rust-sdk/matrix_sdk/encryption/index.html)
- **All Olm double-ratchet state** for 1:1 messaging and for distributing Megolm keys to other devices.
- **Encryption + decryption of every event** in encrypted rooms.
- **Local message index for search.** Seshat (https://github.com/matrix-org/seshat) was Matrix's native-client full-text indexer. Element Web (browser) could not use Seshat because it relies on native threads (Rust + tantivy); the workaround in 2024 was the Rust SDK's `matrix-sdk-search` crate with an encrypted tantivy index stored on disk under the user's session secret. (https://github.com/element-hq/element-x-android/pull/7249, https://github.com/element-hq/element-x-android/commit/e6d4472c0cef46b3f302ba45c403dd7db3bdc880)
- **Verification** — interactive emoji/SAS verification of device identity keys; cross-signing to flatten the O(n²) verification problem.
- **Key sharing requests** — `m.room_key_request` events to recover missed Megolm sessions from other devices.
- **Sharing messages with new room members** — sender must run Olm key-sharing flow for each new device; cannot read past messages (Megolm only allows future-message decryption for new members).

**Megolm's known design limits** (https://gitlab.matrix.org/matrix-org/olm/-/blob/master/docs/megolm.md):
- **No per-message forward secrecy** for group messages — one compromised session key compromises *all* past messages encrypted in that session. Mitigation: rotate sessions every 100 messages / 1 week.
- **No post-compromise security** for messages already sent.
- **Server can replay old ciphertext** to anyone it gives access to the room (no built-in replay protection beyond client-side ratchet-index tracking).
- **Unknown key-share attacks** — the Olm layer (which distributes Megolm keys) is only as strong as its authentication; vulnerabilities in Olm cascade into Megolm session forgery.

**What Matrix DOES NOT encrypt:**
- The *fact* that Alice and Bob are messaging in room R, and at what time
- The membership list of rooms
- Server-side timestamps
- Anything in unencrypted rooms (server has full plaintext)
- The existence of encrypted messages (server holds ciphertext, knows who sent to whom, even if it cannot read content)

### Proton Mail / Calendar / Drive / etc.

**What runs on Proton's servers:**
- **OpenPGP-encrypted message storage** for E2EE emails between Proton users. Server holds ciphertext, public keys, and signed-key metadata. Cannot read message bodies or attachments. (https://proton.me/blog/encrypted-email)
- **TLS + zero-access encryption at rest** for messages sent to/from non-Proton users. Server cannot decrypt bodies but CAN read subject lines, sender, recipient, timestamps (per Proton's explicit threat model). "OpenPGP encrypts the body of emails and attachments. It does not encrypt the subject line and other metadata, such as when an email was sent or who the sender is." (https://proton.me/blog/encrypted-email)
- **Email routing** — must know sender and recipient addresses to deliver; this is structurally unavoidable for email.
- **Encrypted contacts** — Proton uses a separate key pair per account for contacts; the public part is held server-side, the private part never leaves the device. (https://proton.me/blog/encrypted-contacts-manager)
- **BUT** — "The name and address fields are not encrypted (although they are digitally signed). This is so that we can actually send and receive the emails. Everything else is fully end-to-end encrypted." So email addresses themselves remain readable by Proton's server.
- **Proton Bridge** (paid feature) — a local IMAP/SMTP proxy on the user's device that holds the user's PGP private keys in memory, decrypts messages on demand for a local mail client. Critically: "Bridge never stores or shares a user's PGP keys. After the user logs in, Bridge downloads their encrypted, private PGP keys from the Proton servers and unlocks them. These keys are held in the device's memory, never on disk." (https://proton.me/blog/bridge-security-model)
- **Authentication** — Secure Remote Password (SRP) protocol so the user's plaintext password never reaches the server; access tokens are short-lived.

**What Proton CANNOT do on the server (and runs on the client instead):**
- **Message content search** — Proton's blog post "Behind the scenes of Proton Mail's message content search" is the most explicit write-up of this trade-off. They tried to design a server-side SSE-based searchable encryption scheme and rejected it. Their actual implementation: "The moment the user logs in, the cryptographic keys by which all emails are encrypted are locally available and can be used at any time. All messages are accessible; it's just a matter of sending the appropriate requests to the server." (https://proton.me/blog/engineering-message-content-search)
  - **Client-side approach:** when user enables search, fetch *every* message from server, locally decrypt, strip HTML, re-encrypt with a local AES-GCM symmetric key, store in IndexedDB. Build a forward index on the device. Search runs purely locally. Same trade-off Anytype made — "the index is created in your browser and never leaves it." (https://proton.me/support/search-message-content)
  - The local index is itself encrypted with a key derived from the user's password — even physical access to the device's IndexedDB doesn't leak content unless the attacker also has the password.
- **Server-side spam filtering of message content** — Proton filters spam *metadata* (sender reputation, URL blacklists against the encrypted attachment) but cannot read content for spam classification.
- **Server-side calendar event description parsing** — encrypted events; only subject and time are visible to server.

**What Proton explicitly does NOT encrypt:**
- **Subject lines** of emails (so server-side subject search works)
- **Sender and recipient email addresses** (so delivery works; explicit Proton choice — "we do not encrypt email addresses – doing so also does not significantly improve privacy because as an email service, we necessarily must know who you are emailing in order to deliver the message.")
- **Timestamps**
- **Folder structure**
- **Contact names and addresses** (digital signatures only)

**Bridge trade-off:** Proton Bridge exists precisely because they *couldn't* do E2EE for IMAP/SMTP clients without giving the client the keys. So they run a local proxy on the user's machine that holds the keys in memory. This is essentially "thin client on the server host" — the closest possible thing to server-side E2EE decryption without giving the server the keys.

### What both Matrix and Proton prove for the Achiyon case
- **Server-side search of E2EE content is structurally impossible without giving the server plaintext** (or accepting SSE schemes with "severe limitations," per Proton's own evaluation).
- **Server-side "smart" features that need to read the content cannot exist**; they must move to the client.
- **Routing metadata (who, when, how much) is structurally visible to the server** even with E2EE — there is no way around this for a delivery system.
- **There is a productive middle ground**: keep the server's smart features, but build them on top of metadata that the server legitimately sees. (E.g., Proton does spam filtering on metadata; Matrix does presence/notifications on metadata.) The features that *require reading content* must move client-side.

### Sources
- https://matrix.org/docs/matrix-concepts/end-to-end-encryption/ — Matrix E2EE guide
- https://gitlab.matrix.org/matrix-org/olm/-/blob/master/docs/megolm.md — Megolm spec + known limits
- https://matrix-org.github.io/matrix-rust-sdk/matrix_sdk/encryption/index.html — Rust SDK E2EE doc
- https://spec.matrix.org/v1.18/olm-megolm/olm/ — Olm specification
- https://github.com/matrix-org/synapse/blob/v1.9.1/synapse/storage/data_stores/main/search.py — server-side search only on plaintext
- https://github.com/element-hq/element-x-android/pull/7249 — local encrypted search index for Element X
- https://github.com/element-hq/element-x-android/commit/e6d4472c0cef46b3f302ba45c403dd7db3bdc880 — same
- https://github.com/BURG3R5/matrix-encrypted-search — GSoC SSE project (theoretical encrypted server-side search)
- https://github.com/vector-im/element-web/issues/16483 — Seshat threads + WASM blocker
- https://proton.me/blog/encrypted-email — Proton encryption overview
- https://proton.me/blog/engineering-message-content-search — Proton message content search design
- https://proton.me/blog/encrypted-contacts-manager — Proton Contacts encryption
- https://proton.me/support/search-message-content — Proton search docs
- https://proton.me/blog/protonmail-threat-model — threat model
- https://proton.me/blog/bridge-security-model — Proton Bridge
- https://github.com/protonmail/proton-bridge — Bridge source
- https://github.com/ProtonMail/proton-bridge/blob/138d935e/internal/bridge/bridge.go — Bridge architecture

---

## SYNTHESIS — The 4 Recurring Architectural Conclusions

### #1. The server reduces to (a) authenticated encrypted blob store + (b) routing/metadata primitive + (c) optional privacy-preserving compute (enclaves, oblivious RAM, SSE).

Across all 9 systems surveyed, the server does exactly three things:

1. **Authenticated blob storage** — Signal mailbox, WhatsApp Cassandra inbox, Standard Notes/Notesnook payload store, Cryptomator's `d/` tree, Anytype sync nodes, Obsidian Sync vault, Matrix homeserver, Proton's OpenPGP message store. The "blob" is opaque ciphertext in every case.
2. **Routing / metadata primitive** — connection registry (WhatsApp/Signal), presence, delivery ACK flow, room membership (Matrix), folder structure + timestamps (Proton), version history (Obsidian Sync), object DAG membership (Anytype). This metadata is *necessary for delivery* and cannot be removed without breaking the product.
3. **Optional privacy-preserving compute** — Signal's SGX-enclave contact discovery with Path ORAM (the only example of this in the survey); Proton's rejected-but-studied SSE scheme; Matrix's experimental `BURG3R5/matrix-encrypted-search` GSoC project. Each of these preserves a specific feature (contact lookup, content search) by paying a heavy cryptographic and engineering cost.

Note: the WhatsApp/Signal store-and-forward model is a *transient* blob store (delete after delivery). The notes apps (Standard Notes, Notesnook, Cryptomator, Anytype, Obsidian Sync) are *persistent* blob stores (the server is the archive). The deciding factor is whether the client can keep a full local copy — chat apps cannot (mobile, intermittent connectivity), so the server is a delivery buffer; note apps can (laptop/phone always holds the vault), so the server is purely redundancy.

### #2. Every "smart" server-side feature that needs to read content must move to the client.

The examples:
- **Search**: Signal, WhatsApp, Standard Notes, Notesnook, Cryptomator, Anytype, Obsidian (desktop index), Proton Mail — all client-side indexes. Proton explicitly evaluated SSE-style server-side encrypted search and rejected it. Matrix's server-side search only works for unencrypted rooms.
- **Contact discovery**: Signal uses SGX + ORAM (client supplies plaintext to an enclave the host can't see). WhatsApp uses server-side phone-number lookup at registration time but contact matching on the device. Notes apps don't have this problem. Anytype does p2p mDNS.
- **Memory consolidation / "smart" aggregation**: not applicable to any of these products (they don't have a memory-consolidation concept). But the pattern is clear — Signal's profile-fetch is client-decrypted; Matrix's tag/thread grouping happens after client decryption.
- **Spam / moderation**: metadata-based only (rate limits, sender certificates, profile-key delivery tokens, attachment URL blacklists). No content-based moderation possible.
- **History transfer on new device link**: device-to-device direct transfer (Signal, WhatsApp multi-device), never via server.

For Achiyon specifically, the implication: **anything that needs to look at the user's roleplay conversation to do "smart" things** (memory consolidation, dynamic character card generation as in the APP_SPEC, lorebook activation based on context) **must run client-side**. The server literally cannot see the plaintext. The builder's instinct is correct, and the industry has not found a workaround.

### #3. The product must ship native apps per platform to keep E2EE properties. The "thin browser app" is insufficient.

This is the under-appreciated conclusion:

- **Signal** ships iOS, Android, Desktop (Electron with encrypted SQLCipher local DB + safeStorage key wrapping), and CLI. The browser is not the primary client because: (a) no keychain → keys must be wrapped with a user-passcode; (b) WebCrypto + IndexedDB have weaker security than OS keychains; (c) native code is needed for SGX remote attestation.
- **WhatsApp** explicitly dropped their web-only client after the Signal protocol rollout because the encryption needed native hooks; today they ship iOS, Android, Desktop (Mac/Windows), and a "Web" client that requires a registered phone as the primary device.
- **Standard Notes** ships native apps on every platform; the web app is a fallback that warns about reduced security.
- **Notesnook** ships Web + Desktop (Electron) + iOS/Android (React Native) — explicitly per platform.
- **Cryptomator** ships native per-platform because the virtual drive layer requires OS-specific FUSE/macFUSE/WinFsp integration that no browser can provide.
- **Anytype** ships native apps per platform (Electron desktop + native mobile).
- **Obsidian** ships native per-platform; the web app cannot do Sync E2EE.
- **Matrix clients** ship native per platform because of the Seshat/tantivy thread requirement; only recently has the Rust SDK started shipping encrypted search indexes that work in browsers via WebAssembly (and even then, only on Firefox/Chrome with OPFS — Safari 15.1 is still unsupported).
- **Proton** ships native apps per platform, with Bridge being a separate desktop binary specifically because the browser cannot hold long-lived PGP private keys.

**For Achiyon specifically**: the Tauri 2 + native mobile approach already in APP_SPEC.md is the *right* call for E2EE. A pure SvelteKit PWA in a browser tab cannot provide the OS-keychain integration, native crypto library sandbox, or persistent background sync that E2EE requires for acceptable UX. The SvelteKit frontend is fine for the UI, but the encryption boundary should be enforced in a native shell (Tauri's Rust backend, or a native mobile shell). The fact that Notesnook uses Electron + React Native + libsodium WASM, and Standard Notes uses Electron + native + shared TypeScript core, shows the common shape.

### #4. (Caveat for AI workloads) Server-side LLM inference cannot be zero-knowledge without one of three compromises — and the industry has *not* solved this for AI yet.

The nine apps surveyed have one thing in common: their value is in *storing, routing, or displaying user data*. None of them do computation over the plaintext that the user *also wants computed over*. Signal's server doesn't read messages because it has nothing to do with them. Standard Notes' server doesn't read notes because it has nothing to do with them.

**Achiyon is fundamentally different.** The whole product *is* the server computing over the plaintext (LLM inference, character memory consolidation, lorebook activation). If the operator cannot read the plaintext, the server cannot do the LLM call. This is not a gap in the survey — it is a structural feature of AI workloads.

There are exactly three known responses to this, in increasing order of how much they sacrifice the "zero-knowledge" guarantee:

1. **Client-side LLM** — the model runs on the user's device. True E2EE; the server never sees anything. But mobile devices cannot run modern roleplay-sized models at acceptable speed; this only works on desktop/laptop with strong GPUs. (This is essentially what Obsidian's "Sync" does — the app computes, the server stores.)

2. **Trusted-compute enclave on the server** — send the encrypted prompt to an SGX/SEV/TDX enclave on the server, decrypt inside the enclave, run inference, return ciphertext. Signal does this for contact discovery. The pattern works. The trust assumption is "Intel/AMD's hardware is honest and the remote-attestation keys haven't been compromised." This is the most architecturally honest path if you want server-side LLM + privacy, but the engineering cost is enormous (Signal spent years on Path ORAM for a *far simpler* workload than LLM inference; LLM inference enclaves exist as research prototypes but no production chat roleplay service ships this).

3. **End-to-end encrypted prompt to a *trusted third-party LLM provider*** — the user encrypts the prompt to the LLM provider's public key (e.g., the OpenAI/Anthropic/MiniMax API); the Achiyon server acts as a router/relay that never sees plaintext; the LLM provider decrypts, infers, encrypts the response back to the user. This is what Proton's "outside encryption" feature approximates for email. It moves the trust from "Achiyon operator" to "LLM provider" — strictly *less* trust surface than the current Achiyon model (the Achiyon operator currently sees the plaintext at the inference call site), but it requires the LLM provider to support key-recipient encryption APIs that most don't yet ship for general chat inference. (OpenAI does for some endpoints; the pattern is not universal.)

**There is no fourth option that the surveyed apps have found.** Specifically:
- There is no "magic" server-side homomorphic encryption that runs modern LLMs without 100–10000× cost overhead.
- There is no "send the prompt through and just trust the server not to log it" that meets the zero-knowledge bar.
- There is no "scrub identifying info but keep the roleplay content" — by definition, the roleplay content IS the identifying info.

The builder's instinct that "this forces moving prompt assembly + memory consolidation into the client, leaving the server as a thin relay — which makes him question the whole hosted-product value prop" is **correct, and the industry has indeed settled on this tension by largely *not solving it for AI yet***. The most successful "AI-adjacent" E2EE products (e.g., Apple Intelligence's on-device LLM, Obsidian's plugin ecosystem with local LLM support, Notesnook's local-only mode) either run the model client-side or use a trusted cloud LLM provider with user-controlled keys.

**For Achiyon specifically**, the architectural paths forward that the survey supports:

- **Tier 1 (true E2EE, server = dumb router):** client builds the prompt locally (including memory consolidation, character cards, lorebook context), encrypts to the LLM provider's public key, sends via Achiyon server. Server does auth + queue + metering. LLM provider does inference. This is what Signal does, with the LLM provider as the "enclave" — except here the LLM provider is *outside* Achiyon's trust boundary, which is actually a stronger guarantee than the current model.
- **Tier 2 (trusted-compute server LLM, with caveats):** run inference inside an enclave on the Achiyon server. Achiyon operator cannot read plaintext even with root. Cost: enormous engineering investment; rare in the industry for LLM workloads.
- **Tier 3 (hybrid):** default to client-side LLM for desktop users (with optional small remote model for mobile), and document the trust model clearly. This is closer to Obsidian's plugin model.
- **Tier 4 (current Achiyon model, honestly labeled):** Achiyon operator can read your prompts and chats, like every SaaS LLM today. Build a real "vault" feature for users who want Tier 1–3; don't claim E2EE for the default tier.

The **hosted-product value prop question** ("does making the server dumb make the SaaS pointless?") has an industry answer: **yes, the SaaS becomes a thin infrastructure layer, and the value migrates to (a) the client app quality, (b) the LLM provider relationship, and (c) the optional non-E2EE convenience features (shared libraries, social features, multi-user rooms — where the server legitimately does see metadata, similar to Proton's metadata-visible-but-content-blind model).** Standard Notes, Notesnook, Obsidian, and Anytype all sell subscriptions against exactly this value prop: the client app, plus the convenience of "we handle your backups and cross-device sync." None of them try to be the place where the *intelligence* lives.

---

## Appendix — Quick reference table

| App | Server role | What server CANNOT do | Native apps shipped |
|---|---|---|---|
| Signal | Encrypted message queue + auth + push + SGX contact discovery | Read content, social graph, profiles | iOS, Android, Desktop (E), CLI |
| WhatsApp | Encrypted message queue + auth + push | Read content, decrypt backups | iOS, Android, Desktop (E), Web (companion) |
| Standard Notes | Encrypted blob sync server | Read notes, derive keys, search content | iOS, Android, Desktop (E), Web |
| Notesnook | Encrypted blob sync server (SignalR + ASP.NET Core) | Read notes, derive keys, search content | iOS, Android, Desktop (E), Web |
| Cryptomator | No server at all (any sync service) | Read files, see names/hierarchy, see vault contents | iOS, Android, Desktop (per OS native) |
| Anytype | Sync/file/consensus/coordinator nodes (CRDTs + DAGs) | Read content (only layer-1 space key); search content | iOS, Android, Desktop (E) |
| Obsidian Sync | Encrypted vault blob store (optional mode where server holds key) | Read file content in E2EE mode (but sees path mapping + metadata) | iOS, Android, Desktop (E), Web (no Sync E2EE) |
| Matrix/Megolm | Encrypted event store + ACL + device list + presence (unencrypted rooms readable) | Read encrypted room content; search encrypted rooms server-side | Many native clients (Element iOS/Android/Desktop) |
| Proton Mail | OpenPGP message store + routing + Bridge (local proxy) | Read message bodies, attachments, decrypt subject lines (those are plaintext by design) | iOS, Android, Desktop (Bridge), Web |

**Pattern**: every cell in "Native apps shipped" lists *at least iOS + Android + Desktop*. The "Web" tier is always either secondary or absent for full E2EE capability.

---

## Bottom line for Achiyon

The builder's question — "do successful apps conclude that all server-side features must be rebuilt client-side?" — has a clean empirical answer: **yes, for any feature that needs to see plaintext, the answer across the entire surveyed industry is "yes, the client does it."** There is no counter-example.

The follow-on question — "does this destroy the hosted-product value?" — has a nuanced answer: **the SaaS becomes infrastructure (auth, sync, LLM-relay), and the *product* becomes the client app + LLM provider relationship + value-added non-content features.** Standard Notes, Notesnook, Obsidian, and Anytype all run profitable subscriptions on exactly this architecture. None of them pretend the server is "smart."

The unique challenge for Achiyon is that *the LLM call itself is the server's main value*, and the LLM call inherently requires plaintext. The three architectural responses above (client-side LLM, trusted-compute enclaves, encrypted-to-third-party-LLM) are the only known paths. The current Achiyon model (operator sees plaintext) is structurally incompatible with "true E2EE" — but this is *not yet solved by any AI product on the market*. The honest framing is "we offer strong transport security and we do not log, but we operate the inference and could in principle see your prompts" — or pick one of the three architectural paths above and invest accordingly.