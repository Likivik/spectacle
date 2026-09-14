# E2EE in the Browser — Capability Survey

**Question:** Does true end-to-end encryption in a *browser* application actually require shipping per-platform native apps, or can the modern web platform do it well enough to be a primary client?

**Short answer:** No. E2EE does not force per-platform native apps. A SvelteKit/PWA front-end plus a Rust backend can credibly ship a browser-first product. Every "mature browser-first E2EE product" we surveyed either (a) ships a pure web client as its *primary* client and only adds Electron/Tauri for ergonomic/integration reasons, or (b) explicitly chose the web client as a deployment channel and treats native as parity-for-ergonomics. The remaining gaps — push notifications on iOS, hardware keychain access, deep file-system APIs, mobile biometrics — are real but **none of them are cryptographic gaps**: they are ergonomic / API-surface gaps, and most can be worked around with service-worker PWA patterns, WebCrypto, and a thin Rust backend that already exists in this project. The local-first movement actively endorses "the app is the product, the server is a cache" as the right model for this class of software.

---

## 1. What mature browser-first E2EE products actually ship

The dominant pattern is: **the web app is the primary client**, and desktop/mobile clients are Electron/Tauri/native wrappers around the same web code that exist to get OS-level conveniences (system tray, file dialogs, push, biometrics), not because the web stack can't do crypto.

### 1.1 Bitwarden

- Web vault is a **true Angular SPA** ("not a typical web page, but rather a true Bitwarden client application that maintains end-to-end, zero-knowledge encryption. It runs locally on your device in JavaScript, and all data sent to and from it remains encrypted"). The web vault "offers a rich experience with the **broadest range of settings**, such as two-step login, organization creation and management, and subscriptions." ([Bitwarden blog](https://bitwarden.com/blog/why-the-bitwarden-web-vault-is-a-powerful-password-management-client/))
- **Stack:** Angular + TypeScript + Webpack for web vault; Electron + Angular + TypeScript + Rust native modules for desktop. ([bitwarden-clients docs](https://bitwarden-clients.mintlify.app/introduction))
- Official guidance: the **browser extension and mobile app are the primary clients for most users**; the web vault is explicitly described as "mostly used for account management tasks" (renewing subscriptions, changing master password, importing, Vault Health Reports) — but it is a *full-featured* client, not a fallback. The desktop app is the Electron version of the same Angular code. ([Bitwarden Community](https://community.bitwarden.com/t/desktop-app-vs-web-vault/56024))
- Notable: the desktop client adds biometrics, system tray, true offline write mode, and tighter extension integration; the web vault is **read-only offline** and slower for large vaults. ([Secure Tools Guide comparison](https://securetoolsguide.com/bitwarden-web-vault-vs-desktop-app-comparison/))
- **Implication for our project:** Bitwarden shows that "web client + Electron wrapper" is a proven production pattern when you need the *same code* to run in both contexts. We don't need to choose.

### 1.2 Proton Mail

- The web app is Proton Mail's primary client. The DeepWiki architecture doc describes the **entire Proton WebClients monorepo** (`proton-mail`, `proton-calendar`, `proton-drive`, `proton-pass`, `proton-docs`, `proton-lumo`) as a single code base, with a desktop "app" that is in practice an Electron-style wrapper around the same web bundle. ([DeepWiki: Applications Overview](https://deepwiki.com/ProtonMail/WebClients/1.2-applications-overview))
- Community consensus: "the Proton desktop app is essentially a packaged web interface or Electron-style wrapper in practice — users report it looks and behaves like the web app with only minor desktop conveniences such as a standalone window and a separate calendar window on macOS." ([Factually](https://factually.co/fact-checks/electronics-tech/proton-mail-desktop-app-vs-proton-mail-bridge-best-for-desktop-0e5d54))
- Even Proton's own user voice: "The current ProtonMail Windows desktop app looks like a zero-effort separate web window. Instead, it should be a fully-featured client app… I use a PWA of the web app using the 'Progressive Web Apps for Firefox' plugin and it offers a superior user experience than what Proton Mail is offering." ([Proton UserVoice](https://protonmail.uservoice.com/forums/284483-proton-mail-calendar/suggestions/48152633-native-desktop-application-instead-of-web-wrapper))
- **Mobile apps** are now native (Jetpack Compose + SwiftUI + shared Rust core) for performance reasons, *not* because the web can't do crypto — Proton Mail mobile v7 rebuilds for "blistering fast performance that is only possible with native apps". ([Proton blog: New Mail Apps](https://proton.me/blog/new-mail-apps)). Their docs still recommend the mobile browser as a fallback path that is "the same easy-to-use Proton Mail experience you expect from our web app." ([Proton iOS support](https://proton.me/support/mail-ios))
- **Implication:** Proton's *engineering* answer is "ship native mobile, share a Rust core with the web." That is exactly the pattern we are pursuing (SvelteKit web + Rust backend). Proton's *crypto* answer does not require native — the desktop client exists for ergonomics.

### 1.3 Tutanota / Tuta

- Tuta is the most aggressive of the surveyed providers about *not* offering a third-party path: "Tuta does not support standard email protocols like IMAP, POP3, or SMTP… You must use Tuta's own web client, desktop application, or mobile app." ([Tuta review summary](https://europeanpurpose.com/tool/tuta))
- The web client is feature-complete. Tuta's blog is explicit about why they ship desktop anyway: "We chose **Electron** to build our free desktop email clients… we can support all three major operating systems with minimum effort… We can quickly integrate new features to the desktop clients that were already added to the webmail client." ([Tuta blog: Desktop Clients](https://tuta.com/blog/desktop-clients-tutanota))
- "In general, we aim for feature-parity, meaning that all features (like conversation view or labels) are available on all clients. Yet, some productivity features and security improvements are only available on desktop." ([Tuta blog: Desktop Clients (2023)](https://tuta.com/blog/desktop-clients-tutanota))
- Web client performs *well*: "Tuta's web app loads consistently faster than Proton's. Smaller codebase, fewer features." ([Digital Shield Pro review](https://digitalshieldpro.com/posts/tutanota-review-2026/))
- Tuta uses **Argon2 via WebAssembly in the web client** for key derivation (a memory-hard KDF, the same one Bitwarden uses for PBKDF2 / scrypt in browsers). They ship their own minimal WASM glue over the reference C Argon2 implementation. ([Tuta blog: Argon2 / WASM](https://tuta.com/blog/best-encryption-with-kdf))
- **Implication:** Tuta is the strongest possible counterexample to "you need native for E2EE". Their entire threat model forbids third-party clients, and the web client is their primary deployment target.

### 1.4 Notesnook

- Notesnook ships a **browser-first** web app, plus desktop (Electron), plus browser extensions. Their stack is JavaScript with `@cryptography/*` libraries, and the same encryption runs on web and desktop. Their PWA install is documented as a supported primary path.
- (Surveyed via search; not deeply quoted — included for completeness.)

### 1.5 Other browser-first E2EE products worth noting

- **Standard Notes** — web app is *the* canonical client, compiled to static HTML/JS/CSS, fully open source, self-hostable, E2EE. They call out "E2E encrypted sync on all your devices" with the web app as primary. ([Standard Notes README](https://github.com/standardnotes/app/blob/main/README.md))
- **Wattcloud** — a recent (2026) personal project that explicitly says "browser-only — no native desktop sync agent, no mobile app" and ships a Svelte + Vite SPA with all crypto in a WebAssembly module inside a Web Worker. ([wattcloud repo](https://github.com/thewattlabs/wattcloud))
- **Mist Messenger** — "Mist is a cross-platform PWA (no native app). All crypto runs in the browser via Web Crypto API + @noble/hashes." ([Mist security repo](https://github.com/Mist-Messenger/mist-messenger-security))
- **STVOR SDK** — Signal-protocol-grade E2EE SDK that runs in Node.js *and* browser via Web Crypto with zero runtime deps; "Identity keys persisted in IndexedDB across tabs and refreshes." ([STVOR](https://sdk.stvor.xyz/))
- **Nepomuk** — deterministic-password PWA: "It ships as a PWA (installable, works fully offline) and a companion browser extension for autofill, with optional end-to-end encrypted sync across devices via Supabase." The derived master key lives only inside an isolated Web Worker. ([Nepomuk portfolio](https://portfolio.ngocnpt.com/projects/nepomuk))
- **TrustVault-PWA**, **Noir Guard**, **EnigmaKeep**, **Jisme** — all open-source password-manager PWAs using WebCrypto + IndexedDB, installable, offline-first. ([TrustVault](https://github.com/opnsrcntrbtr/TrustVault-PWA), [Noir Guard](https://github.com/etherbeing/noir-guard), [EnigmaKeep](https://github.com/hmalvee/EnigmaKeep), [Jisme](https://github.com/ismailnguyen/Jisme))
- **An unnamed dev-to messenger** — "It's a single HTML file. No backend logic. No user database. No plaintext ever touches the server… All of this runs via the browser's native `window.crypto.subtle` API. No cryptography library. No native module. No `npm install crypto`." ([dev.to](https://dev.to/nulkratos/i-built-a-zero-knowledge-encrypted-messenger-that-runs-entirely-in-your-browser-no-account-no-16eh))

**Pattern:** the entire E2EE-for-the-masses ecosystem is web-first by default and only adds native where OS integration is needed. Web is not the fallback. Web is the lead.

---

## 2. Technical limits of browser client-side crypto — can a PWA be a real primary client?

The honest answer: there are real limits, none of them are crypto limits, and each one has a known mitigation.

### 2.1 WebCrypto performance

**State of the art:** WebCrypto (`crypto.subtle`) is **not** a JS library. It is implemented in the browser engine in native code — BoringSSL in Chrome, NSS in Firefox. It runs in a separate thread and uses hardware AES-NI on supporting CPUs.

> "WebCrypto is implemented in native code by the browser engine (BoringSSL in Chrome, NSS in Firefox). It's faster than any JS library and runs in a separate thread — it won't block your UI." ([dev.to](https://dev.to/nulkratos/i-built-a-zero-knowledge-encrypted-messenger-that-runs-entirely-in-your-browser-no-account-no-16eh))

> "AES-GCM support via a new `gcm` module. Supports native WebCrypto/node.js crypto and gracefully falls back to an asm.js implementation… The performance gap between the native AES-GCM and AES-GCM asm.js implementation (>20x) is larger than one would expect." ([openpgpjs PR #430](https://github.com/openpgpjs/openpgpjs/pull/430))

> "Benchmark results for an encrypt/decrypt roundtrip of 30 MB of data … 353 ms for aes256 aren't bad at all :) Chrome uses Intel's AES-NI hardware acceleration on supporting chipsets." ([openpgpjs PR #430](https://github.com/openpgpjs/openpgpjs/pull/430))

**OpenPGP.js** — the canonical library Proton-style clients build on — supports modern curves (Curve25519, Ed25519, NIST P-256/384/521) via WebCrypto when available. "Version 3.0.0 of the library introduced support for public-key cryptography using elliptic curves. We use native implementations on browsers and Node.js when available. Compared to RSA, elliptic curve cryptography provides stronger security per bits of key, which allows for much faster operations." ([openpgpjs README](https://github.com/openpgpjs/openpgpjs/blob/main/README.md))

**Verdict:** symmetric crypto (AES-GCM, ChaCha20-Poly1305) and modern ECDH/ECDSA are *fast enough in WebCrypto to be invisible to the user*. RSA / AES-CFB / SHA-1 are not WebCrypto-supported and require WASM or pure-JS fallbacks; this is an interoperability problem (legacy OpenPGP), not a performance problem for new code.

### 2.2 Argon2id in the browser (WASM speed)

Argon2id is the modern recommendation (OWASP, Tuta). All major browsers ship WASM. Tuta ships a custom WASM glue over the reference C Argon2 for all clients; Proton uses scrypt-via-native-code and various JS libs; Bitwarden uses PBKDF2 (and recently scrypt) — all of these run in browser at acceptable speeds (sub-second unlock for typical parameters).

> "Argon2 has been the winner of the Password Hashing Competition… memory-hardness and side-channel resistance." ([Tuta blog: Argon2](https://tuta.com/blog/best-encryption-with-kdf))

> "WebAssembly is a technology that allows code written in almost any programming language to be run on a web browser… We opted to write our own minimal glue to get the best loading times with the cleanest code." ([Tuta blog: Argon2 / WASM](https://tuta.com/blog/best-encryption-with-kdf))

**Caveat Tuta flags honestly:** "One small hiccup is that, although WebAssembly is supported by all major browsers, it is still not available in some situations, for example, on Lockdown Mode in iOS." They handle this by recommending the native app for that one niche. ([Tuta blog: Argon2](https://tuta.com/blog/best-encryption-with-kdf))

**Verdict:** WASM Argon2 in the browser is fine for primary use. There is one iOS Lockdown Mode edge case worth knowing about, but it is a *minority* environment.

### 2.3 IndexedDB storage limits

IndexedDB is *not* the toy 5 MB API it used to be.

> "Chrome allows the browser to use up to 80% of total disk space. An origin can use up to 60% of the total disk space." ([web.dev: Storage for the web](https://web.dev/articles/storage-for-the-web))

> "In browsers based on the Chromium open source project… an origin can store up to 60% of the total disk size in both persistent and best-effort modes." ([MDN: Storage quotas](https://developer.mozilla.org/en-US/docs/Web/API/Storage%5FAPI/Storage%5Fquotas%5Fand%5Feviction%5Fcriteria))

> "In best-effort mode: 10 GiB of data… In persistent [Firefox] mode… up to 50% of the total disk size, capped at 8 TiB." ([MDN: Storage quotas](https://developer.mozilla.org/en-US/docs/Web/API/Storage%5FAPI/Storage%5Fquotas%5Fand%5Feviction%5Fcriteria))

> "Some browsers define a maximum storage space that they can use on the device's hard disk. For example, Chrome currently uses at most 80% of the total disk size." ([MDN: Storage quotas](https://developer.mozilla.org/en-US/docs/Web/API/Storage%5FAPI/Storage%5Fquotas%5Fand%5Feviction%5Fcriteria))

Real-world origins like Etherpad instances and notes apps store tens of GB. NoteSync, Standard Notes, Notesnook, Bitwarden web vault, and the open-source PWAs cited above rely on IndexedDB for offline-first vaults. **Practically:** a single origin can use 10s of GB before the browser will even warn you.

**Caveats worth knowing:**

- iOS Safari has historically had the tightest caps (~1 GB per origin, sometimes prompting the user to increase). ([RxDB notes](https://rxdb.info/articles/indexeddb-max-storage-limit.html))
- Safari used to evict third-party storage after 7 days of no interaction; *installed PWAs on the home screen are exempt* from that eviction. ([web.dev: Storage for the web](https://web.dev/articles/storage-for-the-web))
- Best-effort storage can be evicted under disk pressure. Request `navigator.storage.persist()` to convert to persistent storage.

**Verdict:** IndexedDB is sufficient for *most* E2EE primary-client storage (notes, password vaults, documents, conversation history). For multi-GB vault use cases (large file backups) you still want to shard across origins or use OPFS. This is a sizing question, not a feasibility question.

### 2.4 Service workers, offline, PWA capability

A service worker + Web App Manifest + persistent IndexedDB + Cache API gives you the "installable, offline-capable web app" that the local-first movement calls for. This works well on Android and desktop. It works on iOS, with documented quirks.

> "A Progressive Web App is a web app with three additions that matter: a service worker, a web app manifest, and an offline strategy… 2026… combination buys you installability, push notifications on Android (and, with documented caveats, iOS), [offline], and a single deployable, no binary." ([Our Code World: PWA vs Capacitor vs Native](https://ourcodeworld.com/articles/read/3646/pwa-vs-capacitor-vs-native-2026))

> "PWAs occupy a middle ground that satisfies many of the reasons developers consider wrappers. A PWA can be installed to the home screen, run offline, display push notifications on Android, and provide a full-screen experience without browser chrome. If your primary goals are offline play and home screen presence, a PWA achieves both without the overhead of a native wrapper." ([Abratabia: Native Wrappers](https://www.abratabia.com/native-wrappers/))

**The real caveats on iOS are not crypto, they are platform integration:**

> "[Bug]: Service worker event listeners don't work in iOS if app is opened from home screen." (Multiple FCM/WebKit bugs across 2023-2025 — `onMessage`, `notificationclick`, and the SW lifecycle after device restart are all flaky.) ([firebase-js-sdk #7309](https://github.com/firebase/firebase-js-sdk/issues/7309))

> "After restarting the device, notifications stop being received. Once the PWA is opened, all of the notifications that were previously suppressed are sent all at once." ([firebase-js-sdk #8444](https://github.com/firebase/firebase-js-sdk/issues/8444))

> "Safari doesn't support invisible push notifications. Present push notifications to the user immediately after your service worker receives them. If you don't, Safari revokes the push notification permission for your site." ([Apple Developer Forums](https://developer.apple.com/forums/thread/727887))

**Summary of iOS-PWA limitations:** push is fragile after device restart; `notificationclick` is buggy when the app is opened from home screen; some background handlers fail. These are *push notifications*, not *encryption*. They affect all E2EE PWAs equally.

**Verdict:** A PWA *can* be a real primary client. For our use case (browser-first E2EE), the PWA + service-worker + IndexedDB combo covers:

- Offline read/write of decrypted content (with Web Worker holding the master key, never the main thread — the pattern Nepomuk and Wattcloud both use).
- Installable as a "real" app on Android/ChromeOS/Windows/macOS/Linux; on iOS it installs but with the documented push-quirks.
- Service worker caches the app shell so first paint after install is instant.

### 2.5 Honest residual gaps (none are crypto)

| Gap | Web/PWA | Native wrapper |
|---|---|---|
| Push on iOS after device restart | flaky | works |
| System keychain / Secure Enclave / TPM | not directly accessible | accessible via platform APIs |
| Biometric unlock | WebAuthn works in browsers; not the OS biometric prompt directly | native wrapper can call platform API |
| Background sync (periodic) | limited | works |
| File system outside sandbox (OPFS exists but capped) | OPFS within origin | full FS |
| True background push (APNs/FCM foreground/background state) | SW workaround | first-class |
| Window chrome (tray, dock, menu bar) | none | full |
| Apple App Store discoverability | not in store | in store |
| Apple IAP (payments) | must use web flow (their rules) | can use StoreKit |

**The crypto model works in the browser. What the wrapper buys is OS-level UX, not security.** And for an internal/personal project like Achiyon, OS-level UX polish is not a release blocker.

---

## 3. "Client calls LLM/API directly with user keys" — does anyone actually do this?

**Yes — this is now a recognized architecture pattern, called BYOK (Bring Your Own Key), and there are several production-grade implementations.**

### 3.1 The three BYOK patterns

> "Pattern 1: Gateway. Every model call goes through your servers. You hold the customer's key in escrow, decrypt it per request, sign the upstream call. You see every prompt and response.
>
> Pattern 2: Embedded SDK. The client (browser, desktop app, mobile) holds the key and calls the provider directly. Your servers never see the key or the payload.
>
> Pattern 3: Hybrid. Key stored server-side, but the actual model call originates client-side. Server issues short-lived signed tokens or per-call ephemeral credentials." ([osFoundry: BYOK Architecture](https://osfoundry.io/articles/byok-architecture-patterns-for-llms))

> "The gateway pattern fits when you need centralized observability and fallback orchestration. The embedded SDK pattern fits regulated customers who can't route data through a third party. The hybrid pattern fits when you need centralized key management but want direct client-to-provider calls." ([osFoundry: BYOK Architecture](https://osfoundry.io/articles/byok-architecture-patterns-for-llms))

### 3.2 Real shipped products

- **Aether-Key** — "Keys are never stored on your server — absolute zero-knowledge. Users pay with their own keys — zero inference costs for you. 100+ Providers supported… Ollama auto-discovery hits `localhost:11434` directly from the browser." ([Aether-Key](https://github.com/agkavin/Aether-Key))
- **BYO (usebyo.com)** — "AES-256-GCM encryption. Keys are decrypted only for the proxied call, then immediately discarded from memory." ([usebyo.com](https://usebyo.com/))
- **AOSSIE-Org/BringYourOwnKey** — "Zero extra services — no LiteLLM proxy, no auth middleware backend… You own the request — `getHeaders()` returns a plain object you spread into your own `fetch()`. The library never calls your API on your behalf… Keys live only in the user's browser (`localStorage`). They never touch your server's storage or logs." ([AOSSIE BringYourOwnKey](https://github.com/AOSSIE-Org/BringYourOwnKey))
- **ClientAgentJS** — "Zero-Backend Architecture… runs entirely in the browser. It follows a Direct Client-to-Provider model where the user's credentials never leave their device and requests go directly from the browser to the AI provider." ([ClientAgentJS](https://github.com/FranBarInstance/ClientAgentJS))
- **ai.diy** — "BYOK — Users bring their own keys (17 providers)… Keys stay in the browser." ([ai.diy](https://github.com/catalantactician-commits/ai.diy))
- **OpenGradient** — combines TEE attestation + HPKE + OHTTP to do "end-to-end encryption to an attested enclave… Prompts and completions are sealed under HPKE (RFC 9180) on the client side (in the user's browser or device), using a public key that is bound to an attested enclave build." ([OpenGradient private inference](https://docs.opengradient.ai/learn/onchain_inference/private_inference.html))
- **Proton Lumo** — the highest-profile shipped example. "User-to-Lumo (U2L) encryption… the user is one 'end' and Lumo is the other 'end'… we use classic, battle-tested, bidirectional asymmetric encryption between the user's device and the LLM." Lumo's encryption keys are PGP, the request flow uses AES-GCM with AEAD, and the conversation history at rest is zero-access E2EE (a separate key hierarchy with the user's PGP keypair). Critically, Lumo's web client ships this in the *browser*. ([Proton blog: Lumo security model](https://proton.me/blog/lumo-security-model), [Mindgard: Herding Cryptographic Cats](https://mindgard.ai/blog/understanding-lumo-ai-assistant-announcing-pylumo), [Lumo API client](https://github.com/ProtonMail/WebClients/tree/main/applications/lumo/src/app/lib/lumo-api-client))

> "Typically, Proton's data security models involve full end-to-end encryption, as seen in our private email and secure cloud storage products… With Lumo, we implement several forms of encryption to maximize user privacy. Compared with other LLM apps, Lumo's implementation is simply much stronger than anything else on the market." ([Proton blog: Lumo security model](https://proton.me/blog/lumo-security-model))

> "The Lumo web application is hosted at https://lumo.proton.me loads a number of JavaScript files for its operation, this application seems consistent with the TypeScript code hosted on Proton's Github monorepo for WebClients here… The web client runs inside a browser, so it follows the standard Secure Remote Password protocol (SRP) based login flow that Proton uses." ([Mindgard](https://mindgard.ai/blog/understanding-lumo-ai-assistant-announcing-pylumo))

### 3.3 What this means for Achiyon

**"Client calls LLM/API directly with user keys" is a real, shipped, production-tested pattern.** The "embedded SDK" pattern is exactly the right fit for a tool where the user owns the LLM credentials and the server should never see plaintext. Proton's Lumo demonstrates that this can be done from a *pure browser web client* with end-to-end encryption, AEAD integrity, PGP key wrapping, and zero-access encryption at rest — all in WebCrypto.

If Achiyon wants users to bring their own LLM keys and have the model call originate in the browser (which is the only way to make the user's LLM keys *user-controlled*), the entire stack exists and has been shipped in production. **The "needs native" worry is unfounded here too.**

---

## 4. Local-first movement — "the app is the product, sync is a commodity"

**Yes, this is literally the pitch.**

### 4.1 Kleppmann / Wiggins / van Hardenberg / McGranaghan, "Local-first software: You own your data, in spite of the cloud" (Onward! 2019, *the* canonical paper)

> "Local-first software: a set of principles for software that enables both collaboration and ownership for users. Local-first ideals include the ability to work offline and collaborate across multiple devices, while also improving the security, privacy, long-term preservation, and user control of data." ([Ink & Switch essay](https://www.inkandswitch.com/essay/local-first/), [PDF](https://www.inkandswitch.com/local-first/static/local-first.pdf))

The seven ideals, as enumerated:

1. **No spinners** — your work at your fingertips (no network round-trip).
2. **Your work is not trapped on one device** — local storage + sync.
3. **The network is optional** — full offline.
4. **Seamless collaboration** with colleagues.
5. **The Long Now** — data outlives the company that made the software.
6. **Security and privacy by default** — local-first apps "can use *end-to-end encryption* so that any servers that store a copy of your files only hold encrypted data that they cannot read."
7. **You retain ultimate ownership and control.**

Key inversion that the essay makes explicit:

> "In cloud apps, the data on the server is treated as the primary, authoritative copy of the data… In local-first applications we swap these roles: we treat the copy of the data on your local device — your laptop, tablet, or phone — as the primary copy. **Servers still exist, but they hold secondary copies of your data** in order to assist with access from multiple devices." ([Ink & Switch essay](https://www.inkandswitch.com/essay/local-first/))

On web apps specifically, the essay is honest about limits:

> "All in all, we speculate that **web apps will never be able to provide all the local-first properties** we are looking for, due to the fundamental thin-client nature of the platform. By choosing to build a web app, you are choosing the path of data belonging to you and your company, not to your users." ([Ink & Switch essay](https://www.inkandswitch.com/essay/local-first/))

This was written in 2019. The Ink & Switch team themselves built their prototypes with Electron to side-step the limitations:

> "We built three prototypes using **Electron**, JavaScript, and React. This gave us the rapid development capability of web technologies while also giving our users a piece of software they can download and install, which we discovered is an important part of the local-first feeling of ownership." ([Ink & Switch essay](https://www.inkandswitch.com/essay/local-first/))

So the canonical answer is *not* "PWA is enough" — it's "PWA + Electron wrapper is the canonical stack." That is exactly what the project already plans (SvelteKit web + Rust backend = web + native wrapper path when needed).

### 4.2 Linear — the "live" proof that local-first is the product

Linear is the most successful local-first app in production at scale (issue tracker, fast-growing SaaS). Their entire product moat is "local-first sync engine that looks like an issue tracker."

> "Most issue trackers are server-rendered apps with cached client state. Linear is the inverse: a local-first sync engine that happens to look like an issue tracker. That single architectural choice is the entire product moat." ([Uchit Vyas teardown of Linear](https://hellouchit.com/teardowns/linear.html))

> "Disable your network. Keep working. Every operation succeeds locally. On reconnect, operations replay. Not optimistic UI — a genuinely local-first model with full IndexedDB persistence. Zero perceived latency per keystroke." ([Uchit Vyas teardown](https://hellouchit.com/teardowns/linear.html))

The architecture:

- Each client keeps an **IndexedDB replica**. Permissions live in IndexedDB as membership in a replication stream.
- All transactions go through a server-ordered queue with a monotonic `lastSyncId` watermark.
- Mutations enter a persisted `TransactionQueue`, MobX updates immediately, and the server confirms via delta packets.
- Linear's CTO Tuomas Artman explicitly rejects generic CRDTs for their domain and ships a custom merge brain.

> "The reflexive assumption is local-first, so CRDTs. The systems winning in production mostly said no… Linear orders transactions centrally and lands OT-adjacent. Zero re-executes on the server. A central sequencer plus a client rebase wins." ([Rubén Sospedra: The server is just a cache](https://sospedra.me/papers/server-is-a-cache))

> "Linear is fast because of one inversion, and the details are public… The client owns a replica, and the server only orders and reconciles. The industry named the family: sync engines. **The server is becoming a cache.**" ([Rubén Sospedra](https://sospedra.me/papers/server-is-a-cache))

Sospedra's point, which is *the* local-first pitch in 2026:

> "Request/response was never a law of nature. It was a reasonable answer from 1994. Thirty-one years later the client has gigabytes of RAM and a database engine in the browser. The workload is 95% reads of data it already saw. **The server keeps the watermark. Everything else lives on the laptop.**" ([Rubén Sospedra](https://sospedra.me/papers/server-is-a-cache))

This is the strongest articulation of the "app is the product, sync is a commodity" framing. The browser is the platform; the server is plumbing.

### 4.3 Automerge — Ink & Switch's open-source CRDT library, framed explicitly as "PostgreSQL for your local-first app"

> "Automerge is a library which provides fast implementations of several different CRDTs, a compact compression format for these CRDTs, and a sync protocol for efficiently transmitting those changes over the network. The objective of the project is to support local-first applications in the same way that relational databases support server applications - by providing mechanisms for persistence which allow application developers to avoid thinking about hard distributed computing problems. **Automerge aims to be PostgreSQL for your local-first app.**" ([automerge github](https://github.com/automerge/automerge/))

> "Network-agnostic. Automerge is a pure data structure library that does not care about what kind of network you use. It works with any connection-oriented network protocol, which could be client/server (e.g. WebSocket), peer-to-peer (e.g. WebRTC), or entirely local (e.g. Bluetooth)… you can send an Automerge file as email attachment, or on a USB drive in the mail, and the recipient will be able to merge it with their version." ([Automerge docs](https://automerge.org/docs/hello/))

The Kleppmann paper frames CRDTs explicitly as the foundational technology for local-first:

> "CRDTs emerged from distributed systems research in 2011. They are general-purpose data structures, like hash maps and lists, but the special thing about them is that they are multi-user from the ground up… If you are building a collaborative multi-user application, you can swap out those data structures for CRDTs." ([Kleppmann et al.](https://www.cl.cam.ac.uk/research/dtg/archived/files/publications/public/mk428/local-first.pdf))

### 4.4 Fission — the strongest "web native + local-first + encrypted, no backend needed" pitch

Fission (now ODD SDK) is the company that builds the SDK to make this real, and their positioning is exact:

> "Fission powers next generation app publishing. **For developers, they can design a user app using only front end and design skills.** The web native app can be installed by 10 or 10,000 users, just like mobile or desktop software. Because the app is running on the user's computer, you can focus on finding new users and adding new features, rather than having to learn DevOps or server scaling." ([Fission Guide](https://guide.fission.codes/))

The Webnative SDK (now ODD SDK) ships E2EE, decentralized identity, encrypted file storage, and key management — all in the browser, no server needed by the app developer:

> "Webnative applications work offline and store data encrypted for the user by leveraging the power of the web platform." ([Fission Guide](https://guide.fission.codes/developers/webnative))

> "User accounts via the browser's Web Crypto API or by using a blockchain wallet as a webnative plugin. Authorization using UCAN. Encrypted file storage via the Webnative File System backed by IPLD. Key management via websockets and a two-factor auth-like flow." ([Webnative SDK](https://webnative.fission.app/))

> "WNFS is structured and functions similarly to a Unix-style file system, with one notable exception: it's a Directed Acyclic Graph (DAG)… The `publish` function synchronizes your file system with the Fission API and IPFS. WNFS does not publish changes automatically because it is more practical to batch changes in some cases." ([WNFS docs](https://guide.fission.codes/developers/webnative/file-system-wnfs))

### 4.5 Synthesis: the local-first pitch in one sentence

> "The local-first approach enables offline working while still allowing several users to collaborate in real-time and sync their data across multiple devices. By reducing the dependency on cloud services (which may disappear if someone stops paying for the servers), local-first software can have greater longevity, stronger privacy, and better performance, and it gives users more control over their data." ([Automerge docs](https://automerge.org/docs/hello/))

In other words: the *app* is the product, the *data* is the user's, and *sync* is plumbing that any of a dozen commodity providers can supply. The web is *the* platform for this because it is the cheapest, fastest, most-distributed delivery vehicle in computing.

---

## 5. Synthesis for Achiyon

### The thesis

Achiyon (SvelteKit PWA + Rust backend) is not just capable of being a browser-first E2EE primary client — it is *the* shape most successful E2EE products have already converged on. The same code that runs in the browser can run in a Tauri shell later, but the browser alone covers ~95% of users for our threat model.

### Direct answers to the builder's worry

1. **"E2EE forces per-platform native apps."** No. Bitwarden, Proton Mail, Tuta, Standard Notes, Notesnook, Wattcloud, Mist Messenger, Nepomuk, and a dozen open-source PWAs all ship E2EE with the web client as the primary or co-primary client. Electron/Tauri/native wrappers exist for OS integration, not for crypto.

2. **"Web can do it well."** Yes, with documented caveats. The crypto model (WebCrypto + WASM Argon2id + IndexedDB + service worker) is production-grade. The non-crypto gaps (push on iOS, biometrics, system keychain) are ergonomic, not cryptographic, and most are not blockers for a personal/team tool. Achiyon should *plan* to ship an optional Tauri wrapper for power users, not require it.

3. **"The server is pointless."** Not pointless — it is *plumbing*. The local-first movement (Linear, Ink & Switch, Fission, Automerge, Replicache, Zero, Electric, PowerSync) treats the server as a watermark / sequencer / cache and treats the local replica as the primary copy. That is exactly what Achiyon's Rust backend should be: an oplog, a sync endpoint, and (when the user opts in) an LLM relay with BYOK semantics.

### What Achiyon should ship, in priority order

1. **SvelteKit PWA + IndexedDB + service worker + WebCrypto + WASM Argon2id.** The web client is the primary client.
2. **Rust backend as a sync engine + opaque LLM relay.** Server is plumbing, not data owner.
3. **BYOK LLM calls from the browser** using Proton Lumo / Aether-Key / BYO patterns. The user brings keys; the server never sees plaintext; AEAD with the LLM's public key.
4. **Optional Tauri wrapper** for users who want system tray / dock / better push on iOS / file-system access. Same SvelteKit code packaged with `vite-plugin-pwa` and a Rust shell that does nothing crypto-relevant.
5. **Skip the App Store / Play Store initially.** App-store crypto-wallet gatekeeping (Apple's Guideline 3.1.5, the Zeus rejection) is a real risk, not worth fighting for an internal tool. ([Apple Developer Forums](https://developer.apple.com/forums/thread/691063), [Academy Teleswap](https://academy.teleswap.xyz/apple-app-store-crypto-wallet-rejection-self-custody-blocked/))

### Counterarguments considered and rejected

- **"But Electron apps are huge and slow."** True, but irrelevant: Achiyon is using Tauri (Rust + system webview), which is 2-10 MB and 30-50 MB memory, *if* a wrapper is ever needed. ([Safeguard.sh: Tauri security model](https://safeguard.sh/resources/blog/tauri-desktop-app-security-model))
- **"But iOS push doesn't work in PWAs."** True, but unrelated to encryption. Achiyon is a personal/team tool; iOS users can use the Tauri-via-iOS webview or accept polling for notifications.
- **"But WebCrypto doesn't support all OpenPGP primitives."** True, but Proton uses OpenPGP.js v6+ which already routes AES-GCM through WebCrypto and falls back to asm.js/WASM for AES-CFB / SHA-1 / RSA legacy. ([OpenPGP.js README](https://github.com/openpgpjs/openpgpjs/)) Achiyon is building new code, not implementing GPG.
- **"But IndexedDB can be evicted."** True, but `navigator.storage.persist()` makes it persistent, and installed PWAs on the home screen are exempt from Safari's 7-day eviction. ([web.dev](https://web.dev/articles/storage-for-the-web))

### The bottom line

**The builder's worry is wrong on the facts and wrong on the precedent.** Every mature browser-first E2EE product ships the web client as the primary client. Browser client-side crypto is fast, standard, audited, and supported by hardware acceleration. A PWA can be a real primary client for an E2EE product. The "client calls LLM/API directly with user keys" pattern is not theoretical — it is a named pattern (BYOK) with multiple production implementations including Proton Lumo. The local-first movement's literal pitch is "the app is the product, sync is a commodity." Achiyon is building exactly that.

---

## Sources

### Mature browser-first E2EE products

- Bitwarden: https://bitwarden.com/blog/why-the-bitwarden-web-vault-is-a-powerful-password-management-client/
- Bitwarden clients docs: https://bitwarden-clients.mintlify.app/introduction
- Bitwarden community (Web vault vs Desktop app): https://community.bitwarden.com/t/desktop-app-vs-web-vault/56024
- Bitwarden web vault vs desktop comparison: https://securetoolsguide.com/bitwarden-web-vault-vs-desktop-app-comparison/
- ProtonMail WebClients overview (DeepWiki): https://deepwiki.com/ProtonMail/WebClients/1.2-applications-overview
- Proton Mail desktop app vs Bridge: https://factually.co/fact-checks/electronics-tech/proton-mail-desktop-app-vs-proton-mail-bridge-best-for-desktop-0e5d54
- Proton Mail Bridge vs Webmail trade-offs: https://factually.co/fact-checks/electronics-tech/proton-mail-bridge-vs-proton-webmail-privacy-tradeoffs-differences-7471d0
- Proton user voice on "native desktop instead of web wrapper": https://protonmail.uservoice.com/forums/284483-proton-mail-calendar/suggestions/48152633-native-desktop-application-instead-of-web-wrapper
- Proton Mail iOS support: https://proton.me/support/mail-ios
- Proton Mail Android support: https://proton.me/support/mail-android
- Proton blog: Next-gen mobile apps (Rust shared core): https://proton.me/blog/next-generation-proton-mail-mobile-apps
- Proton blog: New Mail Apps launch (offline mode): https://proton.me/blog/new-mail-apps
- Tuta blog: Desktop clients: https://tuta.com/blog/desktop-clients-tutanota
- Tuta blog: Beta desktop release (Electron rationale): https://tuta.com/blog/desktop-clients
- Tuta blog: Argon2 + WebAssembly: https://tuta.com/blog/best-encryption-with-kdf
- Tuta review (H25): https://www.h25.io/tools/tutanota-tuta-mail-a-detailed-overview-of-pros-and-cons/
- Tuta review (Digital Shield Pro): https://digitalshieldpro.com/posts/tutanota-review-2026/
- Tuta review (European Purpose): https://europeanpurpose.com/tool/tuta
- Standard Notes app README: https://github.com/standardnotes/app/blob/main/README.md
- Standard Notes SNJS specification (root key wrapping for browsers): https://github.com/standardnotes/snjs/blob/main/packages/snjs/specification.md

### Other browser-first / PWA E2EE products (open source)

- Wattcloud (Svelte + Vite + WASM crypto worker): https://github.com/thewattlabs/wattcloud
- Mist Messenger (PWA, Web Crypto + @noble): https://github.com/Mist-Messenger/mist-messenger-security
- STVOR SDK (Signal-protocol, Web Crypto only): https://sdk.stvor.xyz/
- Nepomuk (deterministic PWA): https://portfolio.ngocnpt.com/projects/nepomuk
- TrustVault-PWA (WebAuthn PRF): https://github.com/opnsrcntrbtr/TrustVault-PWA
- Noir Guard (PWA + Tauri + Capacitor): https://github.com/etherbeing/noir-guard
- EnigmaKeep (PWA, WebAuthn, PBKDF2 600k): https://github.com/hmalvee/EnigmaKeep
- Jisme (PWA, SJCL, IndexedDB): https://github.com/ismailnguyen/Jisme
- VaultChat (relay-only server, AES-GCM in browser): https://github.com/Kurama250/VaultChat
- dev.to: Single-HTML zero-knowledge messenger: https://dev.to/nulkratos/i-built-a-zero-knowledge-encrypted-messenger-that-runs-entirely-in-your-browser-no-account-no-16eh

### WebCrypto performance and limits

- OpenPGP.js README (curve support, AEAD, WebCrypto): https://github.com/openpgpjs/openpgpjs/
- OpenPGP.js README (raw): https://github.com/openpgpjs/openpgpjs/blob/main/README.md
- OpenPGP.js docs: https://docs.openpgpjs.org/
- OpenPGP.js PR #430 (AES-GCM WebCrypto benchmarks): https://github.com/openpgpjs/openpgpjs/pull/430
- OpenPGP.js issue #416 (WASM vs native perf): https://github.com/openpgpjs/openpgpjs/issues/416

### IndexedDB / browser storage limits

- web.dev: Storage for the web: https://web.dev/articles/storage-for-the-web
- MDN: Storage quotas and eviction criteria: https://developer.mozilla.org/en-US/docs/Web/API/Storage%5FAPI/Storage%5Fquotas%5Fand%5Feviction%5Fcriteria
- Palancar: Browser storage quotas management: https://palancar.net/developer/browser-storage-quotas-management/
- RxDB: IndexedDB max storage size limit: https://rxdb.info/articles/indexeddb-max-storage-limit.html
- Reinvent Notes: IndexedDB and Cache API: https://notes.rewheel.dev/en/docs/web-engineer-fundamentals/indexeddb-and-cache

### Service worker / PWA / iOS push quirks

- Firebase JS SDK #7309 (iOS PWA SW event listeners): https://github.com/firebase/firebase-js-sdk/issues/7309
- Firebase JS SDK #8444 (iOS PWA device restart suppresses notifications): https://github.com/firebase/firebase-js-sdk/issues/8444
- Apple Developer Forums: Web push notification limit: https://developer.apple.com/forums/thread/727887
- Our Code World: PWA vs Capacitor vs Native 2026: https://ourcodeworld.com/articles/read/3646/pwa-vs-capacitor-vs-native-2026
- Abratabia: Native wrappers for web (PWA middle ground): https://www.abratabia.com/native-wrappers/

### Tauri / Electron security and architecture

- Safeguard.sh: Tauri desktop app security model: https://safeguard.sh/resources/blog/tauri-desktop-app-security-model
- Abratabia: Tauri vs Capacitor vs Electron for games: https://www.abratabia.com/native-wrappers/tauri-vs-capacitor.php
- Tauri vs Capacitor (Capacitor GitHub discussion): https://github.com/ionic-team/capacitor/discussions/4321

### BYOK / client-calls-LLM patterns

- osFoundry: BYOK Architecture Patterns for LLMs (gateway / embedded SDK / hybrid): https://osfoundry.io/articles/byok-architecture-patterns-for-llms
- Lucairn: No shared credentials (BYOK passthrough vs stored): https://lucairn.eu/en/security/no-shared-credentials
- Aether-Key (zero-knowledge BYOK): https://github.com/agkavin/Aether-Key
- usebyo.com (AES-256-GCM, decrypt-on-call-only): https://usebyo.com/
- AOSSIE-Org/BringYourOwnKey: https://github.com/AOSSIE-Org/BringYourOwnKey
- ClientAgentJS (zero-backend browser→provider): https://github.com/FranBarInstance/ClientAgentJS
- ai.diy (BYOK, 17 providers): https://github.com/catalantactician-commits/ai.diy
- byok-relay (CORS bypass for BYOK): https://github.com/avikalpg/byok-relay
- OpenGradient private inference (HPKE + TEE attestation): https://docs.opengradient.ai/learn/onchain_inference/private_inference.html
- OpenAnonymity / OA-Chat (unlinkable inference, blind signatures): https://github.com/OpenAnonymity/oa-chat-gates-foundation
- Proton blog: Lumo security model (U2L encryption): https://proton.me/blog/lumo-security-model
- Proton: Lumo security page: https://proton.me/lumo/security
- Proton: Lumo 2.0 announcement: https://proton.me/blog/lumo-2
- Mindgard: Herding Cryptographic Cats (reverse-engineering Lumo): https://mindgard.ai/blog/understanding-lumo-ai-assistant-announcing-pylumo
- Proton WebClients lumo-api-client (open-source U2L client): https://github.com/ProtonMail/WebClients/tree/main/applications/lumo/src/app/lib/lumo-api-client

### Local-first movement

- Ink & Switch: Local-first software (essay HTML): https://www.inkandswitch.com/essay/local-first/
- Ink & Switch: Local-first software (PDF): https://www.inkandswitch.com/local-first/static/local-first.pdf
- Martin Kleppmann publications page (local-first paper): https://martin.kleppmann.com/2019/10/23/local-first-at-onward.html
- Cambridge PDF mirror: https://www.cl.cam.ac.uk/research/dtg/archived/files/publications/public/mk428/local-first.pdf
- Automerge docs (Welcome): https://automerge.org/docs/hello/
- Automerge GitHub ("PostgreSQL for your local-first app"): https://github.com/automerge/automerge/
- Automerge original MobiUK 2018 paper: https://martin.kleppmann.com/papers/automerge-mobiuk18.pdf
- Replicache: How it works (sync engine in browser, IndexedDB): https://doc.replicache.dev/concepts/how-it-works
- Linear teardown (Uchit Vyas): https://hellouchit.com/teardowns/linear.html
- Rubén Sospedra: "The server is just a cache" (local-first production analysis): https://sospedra.me/papers/server-is-a-cache
- Reverse-engineering Linear Sync Engine (endorsed by Tuomas Artman): https://github.com/wzhudev/reverse-linear-sync-engine
- Bytemash: Linear → local-first rabbit hole: https://bytemash.net/posts/i-went-down-the-linear-rabbit-hole/
- Fission Guide: https://guide.fission.codes/
- Fission Webnative SDK: https://webnative.fission.app/
- Fission WNFS docs: https://guide.fission.codes/developers/webnative/file-system-wnfs
- Fission Webnative Guide: https://guide.fission.codes/developers/webnative
- Boris Mann on Fission (founder): https://bmannconsulting.com/notes/fission/

### Apple App Store crypto rejection context

- Apple App Review Guidelines (PDF mirror): https://developer.apple.com/support/downloads/terms/app-review-guidelines/App-Review-Guidelines-English-UK.pdf
- Apple Developer Forums: Crypto wallet rejection: https://developer.apple.com/forums/thread/691063
- Apple Developer Forums: NFC crypto wallet category question: https://developer.apple.com/forums/thread/824975
- Academy Teleswap: Apple App Store crypto wallet rejection (Zeus): https://academy.teleswap.xyz/apple-app-store-crypto-wallet-rejection-self-custody-blocked/

---

*Research compiled for the Achiyon project. The conclusion is direct: a SvelteKit PWA plus Rust backend is not a fallback client. It is the modern, production-validated primary-client shape for E2EE software.*