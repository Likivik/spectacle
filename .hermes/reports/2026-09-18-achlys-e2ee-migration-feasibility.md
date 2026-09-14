# Achlys: v1 escrow → later E2EE migration feasibility

**Compiled:** 2026-09-18 — for the Achlys project (per `APP_SPEC.md`, self-hostable
SvelteKit + Rust/Axum roleplay chat; SQLite via sqlx for embedded, PostgreSQL via
sqlx for server, dual-DB via `DB_URL`). Note: the spec calls the project "Achlys";
earlier research files call it "Achiyon" interchangeably — same codebase.

**Question:** Is there a staged path where Achlys ships v1 with server-side
escrow (operator can read plaintext, as every SaaS LLM does today) and migrates
to E2EE later without re-plumbing everything — or does the choice lock the data
model forever (encrypted blobs vs queryable rows, re-encrypt-and-replace, what
happens to existing users, schema implications, API versioning)?

**Method:** Synthesize existing research (`.hermes/research/e2ee-app-architecture-survey.md`,
`e2ee-business-model-survey.md`, `e2ee-browser-capability-survey.md`) plus targeted
web research on (a) the WhatsApp Signal Protocol rollout (2014–2016) — the only
public reference migration of a billion-user plaintext product to default E2EE,
(b) the Proton Mail OpenPGP rollout (2015 onward), (c) the Signal/TextSecure
encrypted-SMS retirement, (d) Wire's `/api-version` negotiation pattern,
(e) SurrealDB expand/contract rollouts (SurrealKit), (f) the hybrid-E2EE-plus-plaintext
pattern now shipping in Discord DAVE, theSHFT, Voidcom, Zentachain, and Briar.

**Note on SurrealDB:** the task brief mentions SurrealDB, but the Achlys stack
is **SQLite + PostgreSQL via sqlx** (`APP_SPEC.md` line 20, decision logged as
"✅ Decided — schema as proposed, dual SQLite (embedded) + PostgreSQL (server)
via sqlx"). The SurrealDB section below translates the same expand/contract
principles to sqlx migrations because that is what the project actually runs;
the SurrealDB notes are kept where the principles are database-engine-agnostic.

---

## TL;DR (verdict)

**Migration is feasible and there is a clear staged path — but the choice
does *not* lock the data model, it locks the *trust story*.** The data
model can be migrated cleanly. What cannot be retroactively undone is the
public trust message: once Achlys has been promoted as "zero-knowledge, can't
read your chats," it cannot go back. The right staging is **v1 = honest
escrow + privacy-respecting defaults + zero-logging + reversible schema**
and **v2 = E2EE as opt-in per-chat/per-character, advertised separately from
the default tier**. This matches the only known successful migrations
(WhatsApp, Proton Mail) and matches what every modern hybrid product
(Discord DAVE, theSHFT, Voidcom, Zentachain, Briar, Matrix) ships in 2026.

The WhatsApp Signal Protocol rollout (April 2016) is the single best
precedent in the industry: **18 months of progressive rollout, default-on
once the other party's client was e2e-capable, never plaintext-with-same-contact-after-rollout,**
notification in the conversation screen when chats became encrypted,
expiry of old non-e2e clients. That rollout took a billion-user plaintext
product to default E2EE *without losing messages* (old plaintext stayed
plaintext, new messages after the handshake were encrypted) and *without
breaking backwards compatibility* during the transition window.

**Achlys can do the same. The shape:**

- v1 (ship now): escrow with `transport_security + zero_logging` (the
  current model). Schema designed *as if* the field will eventually be
  encrypted — nullable ciphertext columns + plaintext columns coexisting.
- v1.5 (3–6 months in): introduce `encryption_mode` per-chat / per-user
  (`server_escrow | client_e2ee`) with no breaking changes.
- v2 (12+ months in): promote `client_e2ee` to default for new chats;
  legacy escrow chats migrate lazily on next write (re-encrypt-and-replace,
  per Proton's `old_key → new_key` workflow). Public message changes
  from "we cannot read your chats" to "we can read your chats unless you
  opt into E2EE mode." This is the *opposite* of the WhatsApp narrative,
  which is the harder problem.

The "what happens to existing users' data" question is the same as Proton
Mail's `RSA-2048 → ECC` key-rotation problem and LastPass/Bitwarden's
encrypted-vault migration pattern: **legacy plaintext stays as-is, opt-in
upgrade on next write, no silent re-encryption that could corrupt data**.
That is the safe, boring, correct answer.

---

## 1. The question reframed

Two distinct locks:

1. **Data model lock** (technical): does choosing escrow v1 force every
   future E2EE path to be a rewrite?
2. **Trust story lock** (product/marketing/legal): does Achlys's promise
   of "we cannot read your chats" survive once E2EE lands?

The data model lock is **false**. The trust story lock is **real** but
manageable. Conflating them causes the wrong answer (either "ship E2EE
on day one because the data model locks" or "ship escrow forever because
the trust story locks"). The right answer is: **separate the two locks,
plan for both, and choose your marketing carefully**.

---

## 2. What "does not lock" actually means

### 2.1 The data model is not locked

The Achlys sqlx schema (sqlite + postgres) currently models chats as rows
with plaintext text columns. E2EE does not require "encrypt the column";
it requires "the server cannot read the content." There are three well-trodden
migrations from "server-readable plaintext rows" to "server-opaque blob rows":

| Migration shape | What changes | Source |
|---|---|---|
| **Add nullable `ciphertext` column alongside `text`; per-row flag** | Plaintext rows stay plaintext; new writes can be encrypted. Server ignores `ciphertext` for plaintext rows; client decrypts on read for encrypted rows. | Standard pattern; e.g. Obsidian Sync's "encrypted vs. legacy" record format. |
| **Enveloped `blob` column with embedded header** (`{version, alg, iv, ciphertext, tag}`) | One column holds any payload type. Old plaintext rows get wrapped in `{version:0, plaintext}` envelopes on first read; new E2EE writes use `{version:1, e2ee}`. | Used by WhatsApp protobuf evolution and by Matrix's `m.room.encrypted` state event marker. |
| **Whole-table rewrite to opaque blobs + metadata side table** | The chat row becomes `(id, metadata, blob_ref)`. Metadata (sender_id, timestamp, char_id) stays queryable; content moves to blob storage. | Pattern used by every "post-E2EE" notes app (Standard Notes, Notesnook, Anytype, Obsidian Sync). |

**All three preserve the chat ID, the message order, the metadata (sender,
recipient, timestamp), and the foreign keys** that the server needs for
querying. Only the *content body* moves from plaintext to opaque. From the
server's point of view, what changes is one column; from the client's point
of view, what changes is "I now encrypt before POST."

This is exactly the migration that **WhatsApp performed between 2014 and 2016
on a billion users without losing a single chat** and **that Proton Mail
performed in 2015** when it introduced OpenPGP for stored mail:

> **WhatsApp (2014 → 2016):** "Over the past year, we've been progressively
> rolling out Signal Protocol support for all WhatsApp communication across
> all WhatsApp clients. This includes chats, group chats, attachments, voice
> notes, and voice calls across Android, iPhone, Windows Phone, Nokia S40,
> Nokia S60, Blackberry, and BB10. As of today, the integration is fully
> complete. Users running the most recent versions of WhatsApp on any platform
> now get full end to end encryption for every message they send."
> — Open Whisper Systems blog, April 2016.
> (https://signal.org/blog/whatsapp-complete/)

What WhatsApp did:

- Each client generates an identity key pair on first run after the update
  and uploads the public bundle to the server.
- Server stores the public bundle per user (no plaintext content change).
- New messages after the client-to-client handshake are encrypted before
  reaching the server. Old messages stored in plaintext stay in plaintext —
  they are *not* retroactively re-encrypted.
- A notice appears in the conversation screen when the chat becomes
  end-to-end encrypted.
- A user can verify the security code (Signal fingerprint) with the other party.
- After a contact is recognized as e2e-capable, the client **never sends
  plaintext to that contact again, even if the contact downgrades** (downgrade
  attack prevention).

The crucial sentence: *"Each client generates an identity key pair on first
run after the update."* Existing plaintext history is left untouched. There
is no re-encryption job over a billion users' data — that would have been
operationally catastrophic (Proton Mail's later re-encryption effort, which
is opt-in and rare, was the subject of multiple user-facing complaints and
data-corruption tickets).

### 2.2 The trust story IS locked — in the wrong direction

The hard part is not the schema. The hard part is the public promise.

- If v1 ships as "zero-knowledge E2EE" and v2 turns out to be escrow because
  the LLM call genuinely needs plaintext (which is true for Achlys — see
  `e2ee-app-architecture-survey.md` §4), that is a **public trust failure**.
  This is the trap that catches products that ship "E2EE" marketing without
  understanding what their server actually needs.
- If v1 ships as "honest escrow, transport encryption, zero logging" and
  v2 introduces an opt-in E2EE mode, that is **a feature addition, not a
  reversal**. The trust story strengthens, not breaks.

The current research base already concluded that the Achlys server must
read plaintext for LLM inference (character card generation, lorebook
activation, memory consolidation). See
`e2ee-app-architecture-survey.md` §3.4 ("the LLM call itself is the
server's main value") and §4 ("Achiyon is fundamentally different…
there are exactly three known responses: client-side LLM, trusted-compute
enclave, end-to-end encrypted prompt to a third-party LLM provider").
This means **v1 cannot honestly be marketed as E2EE** without picking one
of those three architectural paths, each of which is a 12+ month build.

The pragmatic staging is therefore:

- **v1**: escrow, honestly labeled, with the data model designed for later
  E2EE addition.
- **v1.5**: opt-in E2EE tier (e.g. "vault chat" mode) for users who want
  true E2EE and accept the feature loss (no server-side lorebook activation,
  no dynamic character emergence on server side, etc.).
- **v2**: promote E2EE-vault to default for new chats, keep escrow tier
  for AI-feature-enabled chats, label the difference clearly.

---

## 3. The WhatsApp precedent — what the rollout actually required

The WhatsApp rollout is the single largest plaintext-to-E2EE migration in
the history of consumer software. The mechanics, lifted from the Open
Whisper Systems blog and the April 2016 WhatsApp whitepaper:

### 3.1 What stayed plaintext

- **Pre-rollout message history.** Anything stored before the client
  upgrade. The server's Cassandra `messages` table continued to hold
  pre-rollout messages as plaintext rows. No re-encryption job ran.
- **Backup history.** WhatsApp Google Drive / iCloud backups for pre-rollout
  messages remained in the same plaintext-key-in-backup format they had
  before. (E2EE backups arrived separately in November 2021, 5 years
  after the E2EE rollout. That itself was a multi-month migration with
  its own data-loss edge cases — users who enabled E2EE backups could
  not restore from non-E2EE ones.)
- **Group membership metadata.** The server always saw who was in which
  group, who sent what to whom, when, and how much. Even post-rollout.

### 3.2 What became encrypted

- **New message bodies** after both endpoints had updated and completed
  the Signal handshake.
- **Attachments** (images, video, voice notes, files) after the rollout.
- **Voice calls** (after a separate, later rollout in 2016–2017).

### 3.3 What schema changes were required

The server schema did *not* require a "rebuild." What it required:

1. **A new per-user `identity_keys` + `pre_keys` table** (the Signal
   protocol needs public identity keys, signed pre-keys, and one-time
   pre-keys published server-side so other clients can initiate sessions).
2. **A new per-message ciphertext envelope** — the existing message row
   gained a `{signal_message, ephemeral_key, counter}` blob alongside
   the existing plaintext fields. New writes populated the envelope; old
   rows left the plaintext fields untouched.
3. **A `device_id` column on the user** for multi-device fan-out (which
   came later in the rollout, again additive — never a rewrite).

That is exactly the expand/contract pattern that SurrealKit calls
"rollouts" and that sqlx migrations can replicate trivially. See §5 for
the Achlys-shaped schema work.

### 3.4 What broke

Per the EFF write-up and the contemporaneous InfoWorld coverage:

- **Downgrade attacks were blocked, not allowed.** Once a client saw
  another client as e2e-capable, it refused plaintext. This meant a
  downgrade (someone re-installing an old version to intercept) was
  impossible *between e2e-upgraded clients*.
- **Old plaintext stayed old plaintext.** Users expecting their entire
  history to "become encrypted" did not get that. WhatsApp and Open
  Whisper were explicit in their messaging: only new messages from this
  point forward.
- **Encryption status was visible in the UI** — a notice in the
  conversation screen, and a preference screen showing which chats were
  encrypted. This is the trust-amplification loop that made the rollout
  a feature, not a regression.

### 3.5 The single biggest lesson

> *"Once a client recognizes a contact as being fully e2e capable, it
> will not permit transmitting plaintext to that contact, even if that
> contact were to downgrade to a version of the software that is not
> fully e2e capable. This prevents the server or a network attacker
> from being able to perform a downgrade attack."*
> — Open Whisper Systems blog.

Achlys can adopt the same posture: once a chat is in `client_e2ee` mode,
neither endpoint (nor any future downgrade) can revert it to plaintext
without an explicit user action. That makes the migration **monotonic** —
no accidental loss of E2EE coverage, only deliberate re-grants.

---

## 4. The Proton Mail precedent — the re-encryption question

Proton Mail is the closest reference for "what if we want to migrate
existing encrypted data to a new key/algorithm?" because Proton's
own customer base has been pushing for a "re-encrypt all my old mail with
my new ECC key" feature for years and Proton has only partially shipped it.

### 4.1 Proton's "we can re-encrypt your mailbox" feature is opt-in

Proton's official position (from their public UserVoice and support docs):

> *"Old accounts have as per old standards GPG 2048 keys, which are not
> as secure as current ECC ones… We can create a new key but it only works
> for new emails, existing ones cannot be re-encrypted with the new key."*
> — Proton UserVoice thread "How can we improve Proton Mail?"

And from the same thread, a user-documented workaround using Proton's
own backup-and-restore flow:

> 1. Perform a backup of the entire mailbox using Proton tool for it.
> 2. Create a new key for the account and for the mailbox, marking them as PRIMARY.
> 3. Mark the old key as obsolete, so it is not used to encrypt anything.
> 4. Restore the backup done at step 1 using Proton tool. All the mails
>    are stored in the same folders they were before with a tag, but you
>    can remove the tag and they are exactly as they were earlier.
> 5. Remove the old key. I had to contact Proton support for this, as it
>    was being blocked because of the Proton Drive…

The community-commented risks (verbatim):

> *"For implementation this imposes great risk. What if anything goes wrong
> during the decryption and reencryption? This could corrupt any number of
> emails."*

This is the canonical "re-encrypt-and-replace is dangerous" case. Proton
chose **never** to ship an automatic re-encrypt job over the entire
mailbox because the blast radius of a corrupt-ciphertext bug is the entire
user history. Instead, Proton shipped an opt-in export/restore workaround
that requires the user to back up first, restore to the new key, and accept
that some edge cases need support intervention.

**Achlys must follow the same posture:** legacy escrow content stays escrow
content; the moment an E2EE-mode chat gets a new write, that write is
encrypted; a separate, opt-in "re-encrypt legacy chat history" tool exists
and is documented as risky.

### 4.2 What Proton did ship that Achlys should copy

- **Address Verification + full PGP support** (Proton blog, May 2023):
  Proton added full PGP *import* so users could bring their existing keys
  with them. The schema learned a `key_type` and a `key_status` field.
  Old key types continued to work; new key types were additive. This is
  the exact "new envelope version alongside old" pattern.
- **Encrypted contacts** (separate key per account): same additive pattern.
- **Bridge** (local IMAP/SMTP proxy): a separate runtime process that
  holds decrypted keys in memory on the user's machine, so a non-Bridge
  user can still use a stock IMAP client. Bridge is the architectural
  acknowledgment that "the protocol is non-standard" — Proton gave up
  SMTP compatibility rather than weaken encryption. (Compare Tuta, which
  has no IMAP at all for the same reason.)

For Achlys, the **Bridge analogue** is interesting: if v2 E2EE mode is
non-standard (e.g. requires the Tauri desktop or mobile shell to hold
keys, see `e2ee-browser-capability-survey.md` §3.3), Achlys will need
to decide whether to ship an "E2EE proxy" — a local process that holds
the keys and exposes a localhost-only API — or accept that E2EE mode is
desktop-only.

---

## 5. SurrealDB and sqlx schema implications

### 5.1 General principle: expand/contract

Both SurrealDB (via SurrealKit's `rollout start` / `rollout complete`
two-phase model) and sqlx (via numbered, additive migrations) have
first-class support for **expand-then-contract** migrations: in the
expand phase, add new tables/columns/indexes; let the old code keep
reading the old shape; in the contract phase (after the new code is
deployed and old data has been migrated), remove the old shape.

The relevant SurrealDB doc quote (verbatim from
https://surrealdb.com/docs/manage/schema-migration/rollouts):

> *"Rollouts are SurrealKit's migration system for shared and production
> databases. Rather than immediately pushing all changes (as Sync does),
> Rollouts generate a reviewed manifest and apply it in two phases: an
> expand phase that adds new definitions without breaking existing
> consumers, and a contract phase that removes old ones after your
> application has been updated. Deploying schema and application changes
> separately means no downtime."*
>
> *"1. Start: applies non-destructive changes: adding tables, fields,
> indexes, and access methods that new application code will use. The
> old application code continues to work alongside the new definitions."*
>
> *"2. App cutover: you deploy the new version of your application. Both
> old and new application code remain compatible with the database during
> this window."*
>
> *"3. Complete: applies destructive changes: removing legacy tables,
> fields, or indexes that are no longer needed."*

And the schema-evolution doc adds the **widen-then-narrow** pattern
for fields:

> *"If you are able to modify a field to be more than one possible type
> then you can avoid updating the data at all. For example, if the `num`
> field on `person` defined as an `int` also needs to accept numeric
> strings, you can alter it to `TYPE string | int`, along with an
> assertion that checks every character is numeric when the value is a
> string."*
>
> *"You can use events to gradually migrate data if a full move from one
> data type to another doesn't need to happen immediately… first widen
> the schema to accept either type… And then use an event to normalise
> the data every time the user logs in… Once no more changes come in,
> you can remove the event and tighten up the field to only accept
> datetimes."*

### 5.2 Translating to sqlx for Achlys

Achlys uses sqlx (per APP_SPEC.md). The same principles apply, expressed
in sqlx migration files:

**Migration 0001 (v1, escrow only — already in the repo):**
```sql
CREATE TABLE chat_message (
    id BIGSERIAL PRIMARY KEY,
    chat_id UUID NOT NULL REFERENCES chat(id),
    sender_user_id UUID NOT NULL REFERENCES "user"(id),
    -- ...
    content_text TEXT NOT NULL,           -- plaintext, escrow mode
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX chat_message_chat_id_idx ON chat_message(chat_id);
CREATE INDEX chat_message_sender_idx ON chat_message(sender_user_id);
```

**Migration 0002 (v1.5, E2EE optional — additive):**
```sql
ALTER TABLE chat ADD COLUMN encryption_mode TEXT NOT NULL DEFAULT 'server_escrow';
--   'server_escrow' | 'client_e2ee' (add new values, never rename/remove)
ALTER TABLE chat_message ADD COLUMN ciphertext BYTEA;
ALTER TABLE chat_message ADD COLUMN ciphertext_meta JSONB;
--   { "version": 1, "alg": "xchacha20poly1305", "recipients": [{user_id, wrapped_key}] }
ALTER TABLE chat_message ADD COLUMN content_text_plain_legacy TEXT;
--   renamed from content_text; old plaintext rows stay under this name
--   new e2ee rows leave it NULL; content_text becomes nullable
ALTER TABLE chat_message ALTER COLUMN content_text DROP NOT NULL;
--   or: rename content_text -> content_text_plain_legacy, default to NULL
```

At this point, the server treats `content_text_plain_legacy` as the
content for `encryption_mode = 'server_escrow'` rows and `ciphertext` as
the content for `encryption_mode = 'client_e2ee'` rows. **No existing
row has its data changed. No existing query breaks.** New rows are
shaped according to the chat's mode.

**Migration 0003 (v2, promote E2EE for new chats — additive):**
```sql
ALTER TABLE chat_message ALTER COLUMN encryption_mode SET DEFAULT 'client_e2ee';
--   Only fires on inserts that omit the column. Existing rows unchanged.
--   (SurrealDB equivalent: ALTER FIELD encryption_mode ON chat DEFAULT 'client_e2ee'.)
-- Server-side index for query planning:
CREATE INDEX chat_message_ciphertext_presence_idx
    ON chat_message(chat_id) WHERE ciphertext IS NOT NULL;
-- Server-side check constraint: a row is in one mode OR the other, never both wrong:
ALTER TABLE chat_message ADD CONSTRAINT content_mode_consistency CHECK (
    (encryption_mode = 'server_escrow' AND content_text_plain_legacy IS NOT NULL
        AND ciphertext IS NULL)
    OR
    (encryption_mode = 'client_e2ee' AND ciphertext IS NOT NULL
        AND content_text_plain_legacy IS NULL)
);
```

**Migration 0004 (v3+, optional, lazy re-encrypt — never default-on):**
This is the migration Proton avoided. It would be a per-user opt-in
"re-encrypt legacy history" job that:
1. Reads each `content_text_plain_legacy` row for the user.
2. Decrypts on the server (still in escrow mode, so the server has the
   plaintext — this is fine, because the user opted in).
3. Encrypts to the user's new public key (e2ee mode).
4. Writes the new `ciphertext` row.
5. Marks the legacy row as "shadowed" via a `superseded_by` pointer.
6. Only after the user confirms ("yes, all my legacy history is now in
   e2ee mode"), a separate contract migration drops
   `content_text_plain_legacy`.

**Achlys should NOT ship migration 0004 by default.** It should exist as
an opt-in "upgrade vault" button that the user has to click and confirm,
modeled exactly on Proton's manual backup-and-restore flow. The blast
radius of a corrupt re-encryption over a user's entire chat history is
catastrophic and the value is purely cosmetic (it lets the user claim
"all my chats are e2ee"). Proton decided the risk was not worth the
benefit. Achlys should make the same call.

### 5.3 SurrealDB-specific note (in case any team member confuses the brief)

The task brief mentions SurrealDB; the project actually runs sqlx.
SurrealDB's `DEFINE TABLE ... SCHEMAFULL` and `DEFINE FIELD ... ASSERT`
plus `ALTER TABLE ... IF EXISTS` give you exactly the same additive-
then-narrow pattern. The expand/contract sequence translates:

| SurrealDB | sqlx equivalent |
|---|---|
| `DEFINE FIELD ciphertext ON chat_message TYPE bytes` | `ALTER TABLE chat_message ADD COLUMN ciphertext BYTEA` |
| `ALTER FIELD content_text ON chat_message TYPE option<string>` | `ALTER TABLE chat_message ALTER COLUMN content_text DROP NOT NULL` |
| `DEFINE INDEX ... ON chat_message COLUMNS chat_id` | `CREATE INDEX ... ON chat_message(chat_id)` |
| `DEFINE EVENT normalise_legacy ON TABLE chat_message WHEN ... THEN { UPDATE ... SET ciphertext = ... }` | Triggers in Postgres (sqlite has limited support — use app-level background job) |
| SurrealKit `rollout start` then `rollout complete` | sqlx migration files numbered; never destructive in the same migration that adds new shape |

The principles are identical. The only SurrealDB-specific gotcha worth
noting is `DEFINE EVENT` for the lazy-normalise-on-write pattern — in
sqlite + sqlx, this requires an explicit background job (no in-DB event
support). Achlys should plan for that job in the v1.5 timeline.

---

## 6. Does the API need versioning from day one?

### 6.1 The argument for day-one versioning

Wire's API versioning doc (`https://docs.wire.com/latest/developer/developer/api-versioning.html`)
is the canonical industry reference. The model:

- Backend advertises supported versions at `GET /api-version`.
- Client negotiates the highest mutually-supported version before
  sending requests.
- Endpoints are path-versioned (`/v3/conversations`).
- Wire's contract: "backwards- and forwards-compatible" endpoints do
  not need version bumps; only *breaking* changes do.

WhatsApp did not version its REST API in the traditional sense because
its protocol is binary protobuf over a single socket; version negotiation
happens inside the protobuf envelope (the Axolotl/Signal handshake itself
includes a protocol version field). That is not available to Achlys over
HTTP+JSON.

### 6.2 The pragmatic answer for Achlys

Achlys does **not** need full path-versioning on day one. What it needs
on day one:

1. **An explicit `Content-Type` or `X-Achlys-Protocol-Version` header
   on every authenticated endpoint** — Wire-style content-negotiation,
   not URL-versioning. Default is `v1`. The server returns
   `426 Upgrade Required` if the client sends a higher version than the
   server supports, or `299 Warnings` if the server is older.
2. **An additive field policy.** New fields can be added to request and
   response bodies without bumping the protocol version, as long as old
   clients ignore unknown fields. Wire's documented rule: *"Clients might
   need to be written in such a way as to handle the scenario in which
   the server ignores the extra field or parameter."*
3. **A `/api-version` endpoint** (mirroring Wire) at v1.5, returning
   `{ supported: ["v1", "v2"], development: ["v3"], current: "v2" }`.
4. **Per-feature version flags in response bodies**, so the client can
   know whether the server supports `encryption_mode = client_e2ee`
   without doing a separate round-trip.

This is the minimum that makes the E2EE migration not require a
flag-day client update. **It is cheap to add now and impossible to add
later without breaking old clients.** That is the one piece of plumbing
worth doing on day one.

What Achlys does **not** need on day one:

- Path-versioned URLs (`/v1/api/chat`). This is a legacy convention from
  when API providers wanted their docs to look like they had versions.
  In 2026 the consensus is content-negotiation or header versioning,
  not URL versioning. Wire, GitHub (Accept header), and most major
  SaaS APIs all agree on this.
- A separate "v2 binary." The whole point of the expand/contract
  pattern is that v1 and v2 endpoints live side by side in the same
  binary, gated by the negotiated version.

### 6.3 What happens when E2EE lands

The single breaking change E2EE introduces is the **request body for
"send a message"**:

- v1: `POST /api/chat/{id}/messages { sender, content_text }`
- v2: `POST /api/chat/{id}/messages { sender, content: { kind: "e2ee", ciphertext, ciphertext_meta } | { kind: "escrow", content_text } }`

Both bodies deserialize cleanly if v2 clients know the discriminated
union and v1 clients ignore the `kind` discriminator. The server's
content-negotiated handler dispatches on `kind`. Old clients continue
to send `content_text` and get the v1 code path. New clients send
`content: { kind: "e2ee", ... }` and get the v2 code path. The schema
sees both shapes because the migration 0002 added nullable columns for
both.

**There is no flag day. There is no API rewrite. There is no "the v1
client stops working."** Wire, Stripe, GitHub, and the WhatsApp binary
protocol all prove this pattern works at scale.

---

## 7. The hybrid end-state — what modern products actually ship

The hybrid pattern (E2EE for intimate content, plaintext-for-operator for
social content) is now the **dominant** 2026 product shape. The examples:

### 7.1 Discord DAVE (2024 → 2026)

Discord's DAVE protocol (Decentralized Authentication, Verifiable
End-to-end encryption) is the highest-profile hybrid-E2EE launch of the
cycle. Per Discord's published protocol papers and the Voidcom docs that
study it: DAVE covers **DMs and small voice channels** with end-to-end
encryption (MLS / RFC 9420 family); **large Stage broadcasts** (≥100
participants) and **server channels** stay plaintext for the server so
Discord can moderate, search, and serve content. Discord explicitly
labels which channel types are E2EE and which are not. Per Voidcom
(`https://voidcom.app/features/security/`): *"Regular voice channels and
DMs stay fully end to end encrypted; only large Stage broadcasts are
moderated like a livestream… Stage rooms are clearly distinguished from
regular voice channels… Server-mediated encryption — the server can read
Stage audio, like any broadcast platform."*

### 7.2 theSHFT (2025)

Per theSHFT's published security page (`https://theshft.app/`): *"Our
servers only store encrypted blobs for direct messages, group chats, and
calls. We cannot read your direct messages, group chats, or call media.
Community posts and Stories use server-readable encryption, so they can
be served to other community members and viewers."* theSHFT ships an
explicit **^encryption-talk community** that is plaintext, and DMs that
are E2EE, in the same product, with the lock icon shown only on E2EE
chats. *"Server channels show that operators can read them — no
misleading lock icon."* This is the model that maps directly onto Achlys:

| Achlys feature | Encryption mode | Mapping |
|---|---|---|
| Single-user chat with an AI character (the default) | server_escrow | Server reads content for LLM inference, lorebook activation, character emergence |
| Persona-to-persona chat (rare; future feature) | client_e2ee | Same as theSHFT DMs |
| World library / public lorebooks | server_escrow (plaintext) | Same as theSHFT communities |
| Shared-character library (Phase 3 feature in APP_SPEC) | server_escrow (plaintext) | Public catalog; metadata visible to server; content signed by uploader |
| "Vault" mode for a single chat (opt-in) | client_e2ee | User explicitly opts in; accepts that server-side AI features are disabled for that chat |
| Group chat (Phase 2) | client_e2ee | Same as Matrix `m.room.encrypted` |

### 7.3 Voidcom (2026)

Direct messages and voice are E2EE with X25519 + ML-KEM-768 + MLS;
**server channels are explicitly transport-encryption only, with the
server operator able to moderate**. Stage broadcasts are not E2EE.
Per Voidcom: *"Server channels are protected by transport encryption"*
vs *"Direct messages and voice are end-to-end encrypted with
post-quantum cryptography — the server never sees your DM content and
can't listen on your calls."*

### 7.4 Zentachain / Zentalk (2025–2026)

Hybrid model: encrypted DMs and group chats (Signal Protocol), with
broadcast channels and stories in plaintext for server-side serving. Per
zentachain.io: *"Messaging, voice and video calls, groups and channels,
stories and media, polls and location… Text, voice messages, reactions,
replies, forwarding, editing, and disappearing messages. Pin favorites,
star important ones. The server cannot read any of it."* — for DMs. But
for channels and stories the server is explicitly the reader.

### 7.5 Briar / Zerion

Briar and Zerion both default to E2EE for all messages; their "broadcast
channel" feature (which exists to support public subscription feeds) is
signed-but-readable-by-server. The signature scheme is post-quantum
hybrid (ML-DSA-65 + Ed25519). Per the Zerion docs: *"Broadcast
Channels… designed so that subscribers remain anonymous to each other,
and the owner controls the content flow… Hybrid Signatures: Every post,
comment, and reaction is signed using a hybrid Ed25519 + ML-DSA-65
signature to ensure post-quantum integrity."*

### 7.6 Matrix

Matrix is the longest-running hybrid reference. The Matrix spec makes
E2EE **per-room, opt-in, default-off for new rooms**. The server stores
plaintext for unencrypted rooms and ciphertext for encrypted rooms,
under the same homeserver code, with the same API. Per the Matrix
homeserver docs (referenced in `e2ee-app-architecture-survey.md` §5):
*"By default, rooms are not encrypted, and the homeserver can see
everything. Encrypted rooms are flagged with `m.room.encryption` state
event."* The schema is `m.room.message` for plaintext rooms and
`m.room.encrypted` for E2EE rooms — additive, per-room, server-blind
for the latter.

### 7.7 What this means for Achlys

The hybrid end-state is not a compromise or a fallback. It is the
industry-consensus shape for 2026. Every product that has launched E2EE
in the last 24 months has shipped a hybrid model: DMs / intimate / vault
content is E2EE, social / public / server-mediated content is plaintext-
to-the-server with explicit labeling. Achlys's natural fit is:

- **Per-chat `encryption_mode`** ∈ {`server_escrow`, `client_e2ee`}.
- **Default for AI-character chats = `server_escrow`** (because the LLM
  call needs plaintext — see §2.2 and the architectural survey).
- **Per-character-card `encryption_mode` default** — opt-in at character
  creation; the user can mark a character "private / vault" and any
  chat spawned from that character defaults to `client_e2ee`.
- **World library / shared-character library** explicitly plaintext with
  a "server reads this for moderation / cataloging" disclosure. Same
  as Matrix's `m.room.message` vs `m.room.encrypted` distinction.
- **No lock icon shown on plaintext-for-server features.** Per theSHFT's
  explicit anti-pattern: *"Server channels show that operators can read
  them — no misleading lock icon."*

This is exactly the Achlys APP_SPEC §4 "Dynamic Character Emergence"
and §3 "Chat / Session Management" architecture: character cards and
world libraries are server-readable; private chat with an AI character
is server-escrow; vault chats (opt-in) are client_e2ee.

---

## 8. The staged plan

### Phase 0 (now, before any user data exists): schema + protocol scaffolding

- Add `encryption_mode` column on `chat` (default `'server_escrow'`).
- Add nullable `ciphertext BYTEA` and `ciphertext_meta JSONB` columns
  on `chat_message`. Keep `content_text` (or `content_text_plain_legacy`
  if renaming for clarity).
- Add `X-Achlys-Protocol-Version: 1` header requirement on all
  authenticated endpoints.
- Add `GET /api-version` endpoint returning
  `{ supported: ["v1"], development: [], current: "v1" }`.
- Add per-feature version flag in `/api/auth/me` response:
  `features: { client_e2ee: false, vault_chat: false }`.
- Document in CONTRIBUTING.md that `encryption_mode` is reserved and
  additive-only — never rename, never remove, only append new values.

**Effort: ~1 week of work, single PR.** No breaking changes. The
protocol-version header is a *soft* requirement on day one (server
warns but accepts missing header) and a *hard* requirement by v2.

### Phase 1 (ship v1, escrow mode)

- The default product. All AI-character chats are server_escrow.
- No marketing claim of E2EE. Honest label: "encrypted in transit, not
  end-to-end; we operate the AI inference and could in principle see
  your prompts. We do not log them. Use vault mode (Phase 2) for
  true E2EE."
- Build the world library / shared-character catalog as plaintext-for-
  server with explicit "this content is publicly readable" disclosure
  (matches APP_SPEC §6 and §15 multi-user sharing).

### Phase 2 (v1.5, ~3–6 months in): opt-in client_e2ee tier

- New `vault` chat type. User creates a chat from a character card,
  toggles "vault mode," confirms the warning that server-side AI
  features (lorebook activation, dynamic character emergence, AI
  summarization) are disabled for that chat, accepts.
- All chat messages in that chat are encrypted client-side using
  X25519 + XChaCha20-Poly1305 (or ML-KEM-768 + X25519 hybrid for
  post-quantum; see `e2ee-browser-capability-survey.md` §3 for why
  WebCrypto + WASM is enough).
- Server stores only `ciphertext` + `ciphertext_meta`. Server never
  sees plaintext. Server cannot run LLM inference on these chats
  (matches Matrix's "encrypted rooms have no server-side search"
  trade-off).
- Protocol-version negotiation upgraded to `v2`. Server returns
  `features: { client_e2ee: true, vault_chat: true }`.
- Old `v1` clients continue to work on all server_escrow chats; they
  simply don't see vault chats as anything other than opaque blobs
  (which is correct — they can't decrypt them anyway).
- UI: lock icon on vault chats; plaintext-for-escrow indicator on
  default chats. Per theSHFT: no misleading locks.

### Phase 3 (v2, ~12–18 months in): promote client_e2ee for new chats

- New chat default becomes "ask the user: vault mode or normal mode."
- Default selection is configurable in `/settings` (user's choice;
  if they don't choose, default to vault mode for new private chats
  and normal mode for chats spawned from a shared character library).
- Server-side lazy re-encrypt job (the opt-in migration 0004 from §5.2)
  is exposed as a user-triggered "upgrade my legacy history" button
  that requires explicit double-confirmation, mirrors Proton's backup-
  and-restore flow, and documents the data-corruption risk.
- Protocol-version negotiation upgraded to `v3` with `features` updated
  to reflect the new defaults. `v2` clients still work; `v1` clients
  still work on all server_escrow chats; nothing is removed.

### Phase 4 (v3+, optional, never default): full history re-encryption

- Only after the lazy migration has been stable for 12+ months and the
  user-triggered flow has been validated, consider a contract-phase
  migration that drops `content_text_plain_legacy` for users who have
  completed the upgrade. **This is the migration Proton declined to ship
  as automatic; Achlys should not ship it either unless there is a
  product reason to.** The "lock the data model forever" worry is
  really "what if we want to delete the plaintext column," and the
  answer is "don't, until every user has migrated or opted out."

### Backwards compatibility guarantee

- The server continues to support `v1`, `v2`, and `v3` clients in the
  same binary indefinitely, matching the Wire / Stripe pattern.
- New `encryption_mode` values are additive; old values are never
  removed; the server must always handle every value it has ever
  advertised.
- Once a chat is `client_e2ee`, neither client nor server can revert
  it to `server_escrow` without an explicit user action (matches
  WhatsApp's "once recognized as e2e-capable, never plaintext" rule).

---

## 9. What the brief asks, restated as answers

| Question | Answer | Source |
|---|---|---|
| Is there a staged path? | **Yes.** Expand/contract in three phases (escrow → opt-in E2EE → default-promote). | This doc §8. |
| Or does the choice lock the data model forever? | **No** for the data model; **yes** for the public trust story. The right move is honest v1 marketing. | This doc §2. |
| Encrypted blobs vs queryable rows — can E2EE migration be re-encrypt-and-replace? | **Yes** as an opt-in user action; **no** as an automatic background job. Proton Mail precedent: blast radius of corruption is too large. | This doc §4. |
| What happens to existing users' data? | **Legacy plaintext stays plaintext.** New writes are E2EE if the chat is in vault mode. Migration is monotonic (WhatsApp precedent). | This doc §3. |
| SurrealDB schema implications | **None blocking.** Expand/contract pattern is identical in SurrealDB (SurrealKit rollouts) and sqlx (numbered additive migrations). The project actually runs sqlx, so sqlx is the operative answer. | This doc §5. |
| Does the API need versioning from day one? | **A protocol-version header, yes.** Full path-versioning (`/v1/`, `/v2/`), no. Content-negotiation matches Wire, Stripe, GitHub. Cost on day one is ~1 week; cost later is "flag day for every client." | This doc §6. |
| How did WhatsApp handle the rollout? | 18 months progressive, default-on once both parties were e2e-capable, never plaintext-after-rollout-to-same-contact, notification in UI, expiry of old non-e2e clients. The single best industry precedent. | This doc §3. |
| How did Proton handle legacy encrypted mail? | Never auto-re-encrypted. Shipped a user-driven backup-and-restore workaround. Community has been requesting auto-re-encrypt for years and Proton has declined. | This doc §4. |
| Hybrid end-state (E2EE chats + plaintext-for-operator social features)? | **This is now the industry default.** Discord DAVE, theSHFT, Voidcom, Zentachain, Briar, Matrix all ship it in 2025–2026. Achlys's natural fit: per-chat `encryption_mode`, default escrow for AI chats, opt-in vault for private, plaintext-for-server for shared libraries with explicit labeling. | This doc §7. |

---

## 10. Sources

### Achlys project
- `/Storage/Git/spectacle/APP_SPEC.md` — Achlys product spec (lines 1–298).
- `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md`
  — survey of 9 E2EE products (Signal, WhatsApp, Standard Notes, Notesnook,
  Cryptomator, Anytype, Obsidian Sync, Matrix/Megolm, Proton).
- `/Storage/Git/spectacle/.hermes/research/e2ee-business-model-survey.md`
  — hosted-tier vs self-host E2EE economics.
- `/Storage/Git/spectacle/.hermes/research/e2ee-browser-capability-survey.md`
  — WebCrypto + WASM + service worker E2EE stack viability.

### WhatsApp / Signal
- https://signal.org/blog/whatsapp-complete/ — Open Whisper Systems
  announcement of the WhatsApp Signal Protocol rollout completion
  (April 2016).
- https://s3.documentcloud.org/documents/2786495/WhatsApp-Security-Whitepaper-April-4-2016.pdf
  — WhatsApp encryption whitepaper (April 2016), describes the
  identity-key / pre-key / one-time pre-key infrastructure.
- https://www.infoworld.com/article/2249092/whatsapp-turns-on-end-to-end-encryption-for-all.html
  — InfoWorld coverage of the rollout; quotes Moxie on the
  "eventually all pre-e2e capable clients will expire" posture.
- https://techcrunch.com/2016/04/05/whatsapp-completes-end-to-end-encryption-rollout/
  — TechCrunch coverage.
- https://www.eff.org/deeplinks/2016/04/whatsapp-rolls-out-end-end-encryption-its-1bn-users
  — EFF coverage, including downgrade-attack prevention details.
- https://signal.org/blog/the-new-textsecure/ — TextSecure V2 transition
  (2014): "private is normal," no distinction between encrypted and
  unencrypted chats from the user perspective.
- https://signal.org/blog/a-whisper/ — Whisper unification post,
  describing the migration of TextSecure + RedPhone users to a single
  app, "with overlapping code base, code audits, user interface design,
  and migration of existing users."
- https://signal.org/blog/goodbye-encrypted-sms/ — TextSecure 2.7.0
  retirement of encrypted SMS/MMS support; the last release to support
  it was 2.6.0; phased rollout over multiple releases.
- https://signal.org/blog/cyanogen-integration/ — CyanogenMod 10M+ users
  integration, federated TextSecure servers.

### Proton Mail
- https://proton.me/blog/encrypted-email — Proton's encryption overview
  (body encrypted with OpenPGP, subject lines / sender / recipient
  visible to server by design).
- https://proton.me/blog/engineering-message-content-search — Proton's
  decision to abandon SSE-style server-side encrypted search; message
  content search is client-side only.
- https://proton.me/blog/address-verification-pgp-support — full PGP
  support launch (2023); the schema learned `key_type` and `key_status`
  fields, additive migration.
- https://proton.me/support/pgp-key-management — Proton key import
  workflow for users coming from other PGP clients.
- https://proton.me/support/importing-openpgp-private-key — Proton
  private key import; documents the constraints (must have encryption
  subkey, AES-256, no expiry, etc.).
- https://protonmail.uservoice.com/forums/284483-proton-mail/suggestions/48200333-update-encryption-key-on-any-all-past-emails
  — community discussion of "re-encrypt all my old mail with my new
  ECC key" feature; Proton's official position is that this is opt-in
  manual backup-and-restore, not automatic.

### API versioning
- https://docs.wire.com/latest/developer/developer/api-versioning.html
  — Wire's API versioning pattern (`GET /api-version` + path-versioned
  endpoints + content-negotiation).
- https://developers.facebook.com/docs/whatsapp/flows/reference/versioning/
  — WhatsApp Flows versioning (semver-like major.minor).
- https://www.api-patterns.org/patterns/evolution/VersionIdentifier —
  Version Identifier pattern (URL, header, payload variants).
- https://github.com/ProtonMail/WebClients/blob/b03477cb/packages/shared/lib/api/calendars.ts
  — Proton calendar API versions (`calendar/v1`, `calendar/v2`).
- https://github.com/ProtonMail/WebClients/blob/b03477cb/packages/activation/src/api/api.ts
  — Proton importer API (`importer/v1/...`) — same additive pattern.

### Database schema migration
- https://surrealdb.com/docs/manage/schema-migration/rollouts — SurrealKit
  expand/contract rollout model.
- https://surrealdb.com/docs/learn/schema-management/schema-design/schema-evolution
  — SurrealDB schema evolution: `ALTER FIELD ... TYPE A | B` widening
  pattern, `DEFINE EVENT` for lazy data normalization, `IF EXISTS`
  pattern for safe re-application.
- https://surrealdb.com/docs/reference/query-language/statements/define/field
  — `DEFINE FIELD` semantics, including `OVERWRITE` and `IF NOT EXISTS`.
- https://surrealdb.com/docs/reference/query-language/statements/define/table
  — `DEFINE TABLE SCHEMALESS` / `SCHEMAFULL` and field-vs-table
  permissions defaults.
- https://docs.cloud.google.com/kms/docs/envelope-encryption — envelope
  encryption (DEK + KEK) pattern that Achlys's `ciphertext` column +
  per-user wrapped key slot maps onto.
- https://havenmessenger.com/blog/posts/imessage-icloud-backup-privacy/
  — Haven's analysis of why "encrypted in transit ≠ encrypted at rest,"
  including the iCloud backup gap. The general principle is the same
  one Achlys has to internalize: an E2EE mode means the server has the
  ciphertext AND ONLY the ciphertext, including in backups.

### Hybrid E2EE+plaintext products (2024–2026)
- https://voidcom.app/features/security/ — Voidcom's hybrid model
  (E2EE DMs and ≤99-participant voice, plaintext Stage broadcasts,
  explicit labeling, MLS 1.0 / RFC 9420 with post-quantum hybrid
  X25519 + ML-KEM-768).
- https://theshft.app/ — theSHFT's E2EE DMs + plaintext communities /
  Stories; "no misleading lock icon" policy.
- https://deepwiki.com/zerionproject/Zerion/4-messaging-features —
  Zerion/Briar hybrid: E2EE DMs and group chats, signed-but-readable
  broadcast channels, post-quantum Ed25519 + ML-DSA-65 hybrid
  signatures.
- https://zentachain.io/zentalk — Zentachain hybrid: E2EE DMs and
  group chats, plaintext channels and stories.
- https://docs.rs/crate/aloo/latest — aloo (terminal chat app) hybrid
  E2EE model: server-coordinated channels but content E2EE; explicit
  PWD / PQH / PLAIN identity type tags visible to the user.

### iCloud / iMessage ADP migration
- https://support.apple.com/guide/security/security-of-icloud-backup-sec2c21e7f49/1/web/1
  — Apple's iCloud Backup security docs; describes the iCloud Backup
  keybag model and the Advanced Data Protection (ADP) launch.
- https://github.com/ChatExport/ChatExportKnowledge — third-party
  documentation of the iMessage SQLite schema and how `attributedBody`
  blobs changed between iOS 16 and 17. Cited here as evidence that
  schema evolution in a high-stakes encrypted messaging product is
  always additive (new blob columns, new indexes, never rewrites).

---

## 11. One-paragraph verdict (for the parent agent)

**Migration from escrow v1 to E2EE later is feasible without re-plumbing
the data model, as long as v1 ships with additive nullable columns and a
protocol-version header from day one.** The WhatsApp Signal rollout
(April 2016, 18-month progressive rollout over a billion users,
legacy plaintext left untouched, monotonic "never plaintext after
recognized-as-e2e-capable" rule) and the Proton Mail pattern
(legacy RSA-2048 mail stays RSA-2048-encrypted under the old key,
new key only encrypts new mail, re-encryption over legacy history
is opt-in user-driven and Proton has declined to automate it)
together prove the pattern works at scale. The data model does NOT
lock — the right sqlx migrations in phase 0 make the v1 → v2 transition
additive. What CAN lock is the public trust story: if v1 markets itself
as E2EE and v2 has to walk that back because the LLM call needs
plaintext, that's a public failure. The right framing is honest v1
("encrypted in transit, zero logging, vault mode coming in v1.5"),
opt-in v1.5 E2EE tier for true private chats, default-promote v2.
The hybrid end-state (E2EE private chats + plaintext-for-server world
libraries + explicit labeling) is now the industry default — Discord
DAVE, theSHFT, Voidcom, Zentachain, Briar, Matrix all ship this in
2025–2026. Achlys's natural fit is per-chat `encryption_mode` ∈
{server_escrow, client_e2ee}, default escrow for AI-character chats
(because the LLM call needs plaintext), opt-in vault for private chats,
plaintext-with-explicit-labeling for shared character / world libraries.
The "data model lock forever" worry is unfounded; the right schema
scaffolding costs ~1 week of work on day one and unlocks a three-phase
staged rollout that follows industry-validated precedent.
