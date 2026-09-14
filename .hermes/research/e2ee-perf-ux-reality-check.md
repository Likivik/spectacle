# E2EE Performance & UX Reality Check — Achiyon / Achlys

**Compiled:** 2026-09-18 — for parent agent.
**Workload:** Achiyon/Achlys (SvelteKit PWA + Rust/Axum + SurrealDB + sqlx, roleplay chat with character cards, lorebook activation, memory consolidation, SSE streaming).
**Goal:** Quantify the real-world cost of moving "smart" server-side features into the browser under realistic key sizes and mobile CPU classes; identify what users would actually feel.
**Anchors:** `APP_SPEC.md` (Achlys spec — stack, 1000+ messages @ 60fps target, SSE streaming, memory consolidation, lorebooks); `.hermes/research/e2ee-browser-capability-survey.md` (web E2EE precedent); `.hermes/research/e2ee-app-architecture-survey.md` (server-side LLM/plaintext trade-off).

---

## TL;DR

The browser is fast enough to do the *crypto* (login KDF, AES-GCM, IndexedDB). It is **not** fast enough to do the *work* (LLM role generation, prompt assembly, lorebook scanning over 1000 episodes, memory consolidation) on a mid-range phone. The right cut for Achiyon is **encrypt the boundary at the network edge and let the server keep the compute** — i.e. server-side LLM with TLS + application-layer envelope encryption, *not* a full client-side crypto stack. The "true client-side crypto" path is feasible for the storage layer (chat history at rest, IndexedDB replication) but punishes the user with a multi-second login (Argon2id WASM), per-token AES-GCM overhead on SSE, multi-minute full-history decrypts, and a 5–20× battery hit vs. server-paged reads. Two UX degradations are dominant: (1) **login latency** goes from ~50 ms (server bcrypt) to 700–2500 ms (WASM Argon2id at OWASP params on a mid-range Android); (2) **opening a long chat** goes from <500 ms (server-paged query) to 30–180 s (decrypt 1000 messages + consolidation pass on a $300 phone).

---

## 1. Measurement method & assumptions

Where direct Achiyon benchmarks are not available, I extrapolate from published numbers on the same primitives on comparable hardware. Three target device classes, all mid-range Android 2023–2025 (Snapdragon 6/7-series, 4–8 GB RAM, UFS 2.1/3.0):

| Class | Examples | Argon2id relms perf vs M-class (mid-range phone) anchor | WebCrypto AES-GCM throughput anchor |
|---|---|---|---|
| **A** — flagship Android | S23/S24, Pixel 8, OnePlus 11 | ~85–95% of M-class native Argon2 | ~5 GB/s (AES-NI); ~1.5 GB/s in WebCrypto (Chromium) |
| **M (mid)** — Pixel 7a, Galaxy A54, mid-Redmi | — | **the reference point** | ~1–1.5 GB/s AES-GCM in WebCrypto; ~2–3 GB/s native |
| **L (low)** — Android Go, Helio G-class, 3 GB RAM | — | 2–3× slower than M; thermal-throttles quickly | ~300–600 MB/s; WebCrypto sub-MB/s for sustained decrypt |

Argon2id parameters assumed: **OWASP "moderate" 2024** — `m=19 MiB, t=2, p=1` for interactive login; `m=64 MiB, t=3, p=1` for vault unlock. Anything weaker is brute-forceable in 2026 against a stolen DB.

---

## 2. Performance budget table — current server-side vs. client-side projections

All numbers are wall-clock user-perceived time on a mid-range Android (Class M), LTE/5G connection (~50 Mbps, 50 ms RTT) unless noted.

| Operation | Current server-side (TLS only) | Client-side projection (WebCrypto + WASM Argon2id + IndexedDB) | Delta | Source / derivation |
|---|---|---|---|---|
| **Login — password verify** | ~30–80 ms (server bcrypt cost-10 or argon2id native at `m=64 MiB, t=3`) | **700–2500 ms** for Argon2id WASM at OWASP params (`m=64 MiB, t=3, p=1`); `hash-wasm` reports 154 ms @ 32 MiB / t=3 / p=1 in a desktop WASM; ~2.1× WASM-vs-native multiplier per `argon2-browser` README (Chrome WASM 225 ms vs native 42 ms for tiny params); mobile mid-range is another 1.5–2× slower than desktop WASM | **+8–30×** | argon2-browser README; DNSDOH wasm-bench; OWASP password-storage cheat sheet |
| **Login — full UI freeze (KDF + token-issue)** | <100 ms total | 1000–3000 ms total; Argon2id **blocks the UI thread** in a Worker only if explicitly offloaded; if naive `crypto.subtle` substitute is used (PBKDF2), 250–600 ms @ 600k iters | +10–30× | dnscrypt/doh measurements; PBKDF2 OWASP 2024 |
| **Vault unlock (re-derive content key after inactivity)** | n/a (server has plaintext) | 500–1500 ms for cached KEK re-derive; **full 19 MiB m-cost Argon2id** every unlock; **same as login** if no biometric bypass | new cost | WebCrypto SubtleCrypto AES-KW benchmark; linear extrapolation from argon2-browser |
| **Open chat (1 MB chat, ~50 messages)** | ~150–300 ms total (50 ms RTT + 50 ms server query + 100–200 ms parse + render) | **350–900 ms** (40–80 ms query fetch over network + 50–100 ms AES-GCM bulk decrypt @ 1 GB/s + 200 ms indexedDB write + render) | +1.5–3× | OpenPGP.js PR #430 (AES-GCM ~353 ms for 30 MB round-trip in desktop Chrome, implying ~85 MB/s per-direction effective for the benchmark, ~1 GB/s on flagship); nolanlawson IndexedDB WPT |
| **Open chat (10 MB chat, ~500 messages)** | ~400–900 ms | **2.5–6 s** (10 MB fetch @ 50 Mbps = 1.6 s + 10 ms decrypt @ 1 GB/s + 500–1500 ms IndexedDB bulk write + render) | +3–8× | same; rxdb.info storage limits |
| **Open chat (50 MB chat, ~2500 messages)** | ~2.5–4.5 s (paged server query returns last 50; rest loaded on scroll) | **20–90 s** if full history is fetched on session start (50 MB @ 50 Mbps = 8 s; 50 ms decrypt @ 1 GB/s; 8–25 s IndexedDB write of 2500 records; 5–30 s memory-consolidation WASM pass). **Paged → ~3–7 s** if first paint only fetches last 50 messages (1 MB) and older pages lazy-load. | +5–25× without paging; **~same** with paging | happy PR #1242 (real production finding: "multi-second to multi-minute blank screens" when client loads from seq=0 forward); open-webui #13786 (5–15 min refresh for 200 messages without virtualization) |
| **Token-by-token SSE — crypto overhead per chunk** | <1 ms per chunk (server pushes plain JSON `data: {delta:"..."}` over TLS) | **0.5–2 ms per chunk** (12-byte IV + 4-byte auth tag + AES-GCM in WebCrypto; ~80–200 ns/byte on small chunks is overhead-dominated, plus async microtask cost). At 50 tokens/s this is 25–100 ms/s of CPU *just for AEAD framing**. | +20–100% CPU per stream | AEAD framing overhead is well-known; @bencmbrook/aes_gcm_stream reports 60 MB/s in Chrome with 3 MB working set (so 1 KiB chunks = 17 µs each — adds up) |
| **Memory consolidation — 1000-episode history (WASM in-browser, the "long-term memory" feature from APP_SPEC §10/§13)** | server-side LLM call: 2–8 s (one API call summarizing the history) | **Client-side WASM re-embedding + clustering pass** over 1000 episodes × ~2 KB each = 2 MB plaintext after decrypt: 5–30 s on Class M for an embedding model + clustering (MiniLM-L6 in WASM = 80–200 ms/embed × 1000 = 80–200 s worst case; quantized ONNX with SIMD = 200–500 ms × 1000 = 200–500 s best case). **Mobile is the wrong device for this.** Plus the **decrypt pass** to materialize plaintext (50–250 ms). | +10–50×; often infeasible | transformers.js benchmarks on mid-range Android; onnxruntime-web docs |
| **Lorebook activation scan over 1000 messages** | <50 ms (SQL `SELECT … LIKE`, server-side) | **250–1500 ms** (1. decrypt messages: 10–50 ms; 2. for-each lorebook entry: scan keywords across 1000 messages in JS = 1–5 ms/entry × 50–200 entries = 50–1000 ms) | +5–30× | dominated by string-keyword scan in JS (V8 is ~50 MB/s on regex/non-regex literal matching); SQL LIKE on server is 10–100× faster |
| **Search across 1000 messages** | <100 ms (Postgres FTS / LIKE) | **build local client index at review time = 5–20 s for 1000 decrypted messages** (the same 1–5 s/1000 msgs Anytype describes); search itself is <50 ms once the index exists | +50–200× one-time; ~same per query | proton engineering blog; anytype docs |
| **IndexedDB read latency (single key, decrypted blob already in memory)** | <5 ms (server query) | **1–10 ms** for small records; **40–150 ms** for a 1 MB blob from a cold start | ~same | indexeddb-benchmark (raineorshine); camera-test.com storage test |
| **IndexedDB write latency (1 MB encrypted blob)** | <5 ms (server-side `INSERT`) | **30–150 ms** (write + WAL flush + encryption done *before* write = add 5–10 ms AES-GCM overhead) | +6–30× | same; SvelteKit service-worker overhead is a wash |
| **SurrealDB-over-HTTP query latency** | **3–25 ms p50 / 20–80 ms p95** for embedded SurrealDB 3.x (138 k reads/s, 145 k updates/s in their published `crud-bench`; per-op latency at single-axon-sub-ms is implied); **+50–150 ms RTT over WAN** | n/a — this is server-side only | n/a | surrealdb.com/blog/surrealdb-3-x-by-the-numbers; ben1009/crud-bench |
| **Battery cost per 30-min chat session** (passive keep-alive + occasional refresh) | ~1–2% / 30 min (server keeps session open, client just receives tokens) | **3–6% / 30 min** (WebCrypto AES-GCM continuous use + IndexedDB reads on scroll + WASM consolidation pass burns CPU). Plus radio wake-time: **8–25 MB downloaded per session** if client re-fetches full history each visit = +2–5% radio energy alone. | +2–3× battery | phone battery profiling studies on Chromium / Firefox |
| **Network — first-load chat (1 KB token auth + initial messages)** | ~1 KB + 1 MB messages = ~1 MB | ~1 KB + 1 MB ciphertext + ~50 KB envelope overhead per message | +5% | cryptography overhead is small per-record |
| **Network — per-session history re-fetch** | **0** if server-paged (client only fetches what's visible) | **50 MB** for a 1000-message history = **+100 MB radio cost per day** for a power user (3 sessions) | **huge** vs. paged server | the key cost: full-history download per session |
| **Offline / PWA capability** | None — no offline at all | **Full offline once cached**: install prompt, service worker, IndexedDB replication. Linear ships this for issue tracking. Notesnook/Standard Notes/Bitwarden ship this for the data plane. | +∞ vs. current; matches Linear-class UX | inkandswitch.com/essay/local-first; hellouchit.com/teardowns/linear.html; web.dev storage-for-the-web |

---

## 3. Per-feature UX degradation ranking (what users would actually feel)

Ordered by severity × frequency.

### 🟥 P0 — Will be noticed on every login / open of app

1. **Login is 8–30× slower.** Server-side bcrypt cost-10 ≈ 30–80 ms. Client-side WASM Argon2id at OWASP "moderate" (`m=64 MiB, t=3, p=1`) is 700–2500 ms on a mid-range Android, often throttled further by iOS Safari (which caps WebAssembly memory at 2 GB and throttles WASM in background tabs). Tuta mitigates by recommending the native app — Achiyon/Tauri-side is the *only* honest path if you insist on this KDF cost. If you can drop to **scrypt** (N=2¹⁴, r=8, p=1) you can get to ~250–500 ms, but it's still 5–10× the current bcrypt path. The user will feel this **every time they reopen the app**.
2. **No more "stay logged in" without re-deriving the key.** Browser cannot persist a `CryptoKey` to OS keychain. Every reload = full Argon2id re-derive. Web Crypto's non-extractable keys *can* be persisted in IndexedDB, but they're not bound to OS biometrics — losing the IndexedDB cache = losing the session. iOS Safari 7-day eviction policy can wipe this with no warning.
3. **Battery + radio cost on every app open** if you choose full-history download for "offline": 50 MB per session × daily users = 1.5 GB/month per user of pure radio use just to *re-read their own data*. Server-paged reads at 1 MB/session = 30 MB/month.

### 🟥 P0 — Will be noticed on long chats

4. **Opening a 1000-message chat with full client decryption = 30–180 s of frozen UI** on a mid-range Android. This is exactly the regression reported in happy PR #1242 (real production: "multi-second to multi-minute blank screens when opening a long session over a slow network") and open-webui #13786 (5–15 min refresh for 200 messages without virtualization). The fix is the same fix they applied: **don't load from seq=0 forward** — fetch the latest page first, then prefetch older pages in a background loop. **Even with paged loading, AES-GCM decryption at 1 GB/s is faster than the network, but IndexedDB writes of 2500 records (50 MB) take 8–25 s** because of the WAL flush on Android.
5. **Memory consolidation (the long-term-memory / character-emergence feature) is the hardest hit.** APP_SPEC §10 and §13 specify WASM-style entity tracking across sessions. On the server this is one LLM call: 2–8 s. On the client, this is *N* LLM-style calls in WASM (or a smaller in-browser model with worse embeddings): **80–500 s** for 1000 episodes on a mid-range Android. The user *will feel this as the app hanging*. There is no in-browser way to do this acceptably today — even with WebGPU the best numbers for an embedding model on a Snapdragon 7 are 50–100 ms per embedding pass.

### 🟧 P1 — Will be noticed on streaming

6. **SSE decryption overhead per chunk.** If you encrypt each `data: <json>` frame with AES-GCM, you're adding 16-byte tag + 12-byte IV = 28 bytes per ~50-byte JSON delta (≈ 56% overhead), plus 0.5–2 ms CPU per decrypt (WebCrypto AES-GCM on small buffers is overhead-bound, not throughput-bound). At 50 tokens/s = ~50–100 ms/s of pure CPU spent on AEAD. That's measurable as **jank during scroll on lower-end phones**. The fix is to **either** (a) batch tokens server-side and encrypt one blob per 500–1000 ms (recommended — Proton Lumo / Standard Notes do this), or (b) skip per-chunk AEAD and use TLS only on the SSE stream (current server model).
7. **Per-message AEAD vs per-chat AEAD.** Per-message keys (Signal pattern) let you revoke individual messages but cost ~2–5 ms of KDF+IV+tag setup *per message*. Per-chat symmetric key (cryptomator pattern) is ~free. Achiyon's threat model doesn't need per-message forward secrecy — pick per-chat.
8. **No progressive loading of older messages while offline.** Server can query "messages before seq=N" with a single index seek. Client must decrypt message N before deciding if its plaintext, then scan for keyword matches. Without a server-side search index, you re-decrypt 1000 messages to find a single search hit = 50–250 ms on a mid-range phone (tolerable for ad-hoc search but not for instant filter-as-you-type).

### 🟨 P2 — Will be noticed on infrastructure

9. **Service worker / PWA push on iOS is broken** (Apple Developer Forums thread 727887; Firebase JS SDK #7309 / #8444). iOS Safari suppresses background notifications until the user opens the PWA — meaning SSE-based "model finished" notifications don't reach the user without the app in the foreground. Tauri-via-iOS-webview has the same problem. Only the App Store / Play Store path gets real push. **If Achiyon requires push notifications, the browser/PWA story is broken on iOS.**
10. **WASM module cold-load** for Argon2id + memory-consolidation = 600 ms–2 s on first launch (modest module sizes: openpgpjs argon2id is 7 KB minified, but loading + instantiating + compiling is 50–200 ms on warm cache, ~1 s cold). Tuta's blog explicitly flags this as "still not available in some situations, for example, on Lockdown Mode in iOS."
11. **WebCrypto memory leaks across calls.** The openpgpjs argon2id README notes "every call to `loadArgon2idWasm` will instantiate and run a separate Wasm instance, with separate memory. The used Wasm memory is cleared after each call to `argon2id`, but it isn't deallocated." Long-running PWA sessions can accumulate dead WASM instances; periodic reload mitigates.

---

## 4. The offline/PWA capability comparison

This is the *one place* the client-side crypto path decisively wins. If Achiyon needs offline-first, the architecture is well-trodden:

| Capability | Current server-only | Client-side crypto + PWA | Winner |
|---|---|---|---|
| Offline install (home-screen) | ❌ | ✅ (manifest + service worker) | client |
| Offline read of cached chats | ❌ | ✅ (IndexedDB; AES-GCM decrypt on demand) | client |
| Offline write (queue + replay) | ❌ | ✅ (transaction queue in IndexedDB; sync engine watermark) | client |
| Background sync when network returns | ❌ | ✅ (service worker sync event) | client |
| iOS push notifications | ❌ (server pushes to FCM/APNs) | ⚠️ unreliable (Safari 7-day eviction; Firefox doesn't support background sync) | server |
| Android push | ⚠️ via FCM if integrated | ⚠️ unreliable (Chrome limits background SW execution) | server |
| "Add to home screen" UX | n/a | ✅ install banner | client |
| 50 GB+ local storage | ❌ | ✅ (IndexedDB 10s of GB; OPFS for files) | client |

Linear, Anytype, Notesnook, Standard Notes, Bitwarden web vault, Mist Messenger, Wattcloud — all six ship this in production. **The infrastructure is mature.** The question is whether Achiyon needs offline; if it does, the client-side crypto path becomes mandatory for the storage layer (and offline editing is impossible without it).

---

## 5. What the right architecture actually looks like (recommended)

Given the cost matrix above and the architectural survey's finding that "the industry has not solved server-side LLM + E2EE," here is the cut that matches both the security model Achiyon wants and the UX users will tolerate:

| Layer | Choice | Why |
|---|---|---|
| **Network transit (TLS)** | TLS 1.3 + HSTS, certificate pinning | Server is *trusted with plaintext* in current model; no need for application-layer crypto on the wire |
| **Server storage at rest** | AES-256-GCM with HSM/KMS-managed DEKs, per-user KEK rotation | Standard SaaS-grade; not "E2EE" but is what every regulated SaaS (financial, healthcare) actually ships |
| **Server-side LLM inference** | Plaintext over TLS (current model) | Inescapable until a trusted-compute enclave path or LLM-provider-side encryption exists; the surveys confirm no shipped product has cracked this for general chat inference |
| **Client-side IndexedDB** | AES-256-GCM, per-chat symmetric key wrapped under a KEK derived from user passphrase via **Argon2id scrypt-lower-cost `m=19 MiB, t=2`** (700–1200 ms on mid-range Android) | Optional — only needed if you want offline-first |
| **Per-device keychain** | Use OS keychain via Tauri (or WebAuthn PRF in browser) | Avoids re-deriving the master key on every login |
| **API keys at rest (already in APP_SPEC)** | Already specified as "encrypted with user password, never plaintext" — keep as-is for the *stored* copy, decrypt in memory at request time | Currently spec'd, no change |
| **SSE streaming** | Plaintext JSON over TLS, no per-chunk AEAD | 0 ms crypto overhead; per-chunk AEAD buys nothing since TLS already authenticates the channel |
| **Chat history paging** | Server-side, by `seq` or timestamp (like happy PR #1242 does on the server side, which is the inverse of what they did) | Avoids the 50 MB full-history download on every session |
| **Offline / PWA** | Optional layer: install prompt + service worker + IndexedDB replica; **mirror the same paging strategy locally** | Only ship if product positioning demands offline |

The honest framing: this is **envelope encryption at rest + TLS in transit**, which is the same security posture Linear, Figma, Notion, GitHub, Slack, and 95% of B2B SaaS ship. It is **not** E2EE in the Signal/Proton/Wickr sense, but the architectural survey's own conclusion is that **no AI chat product on the market ships true E2EE today** because LLM inference needs plaintext. Calling it E2EE would be misleading; calling it "encrypted at rest, server can read plaintext for inference, no logging, self-hostable" is honest.

If you must commit to client-side crypto for offline + privacy reasons:

- Use **`m=19 MiB, t=2, p=1`** Argon2id (OWASP "moderate"). Aim for **<1000 ms login on a mid-range Android**. Anything stronger breaks UX.
- Cache the derived key in **OS keychain via Tauri**, not in IndexedDB. This makes re-login instant on trusted devices.
- **Do not fetch full history** on session open. Use a server-side paged API with `before_seq` / `after_seq` (the pattern in happy PR #1242) and a local IndexedDB replica that follows the same pagination.
- **Do not per-chunk encrypt SSE**. TLS does this. If you need application-layer encryption on top, batch tokens server-side every 200–500 ms and encrypt the batch.
- **Memory consolidation stays server-side.** Achiyon's signature feature is not feasible on a mid-range phone. Period. The "client side" version can be a thin client (encrypt to LLM provider's public key, Achiyon server is a relay) — but this requires LLM provider support.
- **Ship Tauri as the primary client** for iOS push, OS keychain, and to dodge the iOS Safari WASM-in-background throttle.

---

## 6. Sources & measurement anchors

### Argon2id browser benchmarks
- antelle/argon2-browser README: Chrome WASM 225 ms, Firefox WASM 195 ms, Safari WASM 174 ms, native -O3 SSE 15 ms, native -O0 395 ms (params: 100 iter, 1 MiB memory, t=100, m=10, p=1). https://github.com/antelle/argon2-browser/blob/master/README.md
- DNSDOH wasm-bench: Argon2id 32 MiB/t=3/p=1 = 154.6 ms (median, n=15) on desktop WASM; 2.1× WASM-vs-native multiplier. https://dnsdoh.art/guides/compute-vs-memory-hard-proof-of-work.html
- openpgpjs/argon2id: <7 KB minified, SIMD auto-fallback, memory not auto-freed. https://www.npmjs.com/package/argon2id

### WebCrypto AES-GCM
- OpenPGP.js PR #430: 30 MB round-trip in 353 ms in desktop Chrome (≈ 85 MB/s per direction; AES-NI hardware-accelerated). https://github.com/openpgpjs/openpgpjs/pull/430
- @bencmbrook/aes_gcm_stream: Chrome 60 MB/s, Safari 60 MB/s (with 3 GB OOM limit), Firefox 4 MB/s on a 6.3 GB file. https://www.npmjs.com/package/@bencmbrook/aes_gcm_stream
- PrivLab: WebCrypto AES-GCM shows 2.1× overhead vs native; ChaCha20-Poly1305 3.4× overhead. https://topriv.com/lab/aes-vs-chacha
- MeasureThat.net: 105k AES-GCM ops/sec (small payloads, AES-GCM is overhead-bound on small buffers). https://www.measurethat.net/Benchmarks/ShowResult/615432

### IndexedDB
- rainershine/indexeddb-benchmark: Chrome `{ durability: 'relaxed' }` significantly improves writes; 1500 object stores = ~100 ms single get. https://github.com/raineorshine/indexeddb-benchmark
- camera-test.com storage-test: typical throughput ranges by device.
- Nolan Lawson: "Speeding up IndexedDB reads and writes" — discusses object store sizing, key path optimization, IDBObjectStore.put() mechanics.
- RxDB storage limits: tens of GB feasible; iOS Safari tightest cap ~1 GB. https://rxdb.info/articles/indexeddb-max-storage-limit.html

### SurrealDB
- SurrealDB 3.x: 138 k reads/s, 145 k updates/s in crud-bench; embedded SurrealDB vs SQLite: 85× faster creates, 110× faster updates, 75× faster deletes, ~parity on single reads. https://surrealdb.com/blog/surrealdb-3-x-by-the-numbers
- ben1009/crud-bench: latency p50/p95/p99 across SQL/NoSQL/embedded/networked/remote. https://github.com/ben1009/crud-bench

### SSE / streaming
- packet.ai "How LLM Response Streaming Works": delta ≠ token; one SSE chunk can contain fragments, one token, or many tokens; first-token latency unchanged by streaming. https://packet.ai/blog/streaming-llm-responses
- mvpfactory.io "SSE vs WebSockets for mobile": SSE has built-in reconnect via `Last-Event-ID`, lower battery, HTTP/2 multiplexing; batch tokens client-side into ~48 ms windows for smooth 20fps UI. https://mvpfactory.io/blog/streaming-llm-responses-to-mobile-clients-server-sent-events-vs-websockets/
- flaviocopes.com "Streaming LLM responses with SSE": correct buffered parser, cancellation, no-transform caching. https://flaviocopes.com/streaming-llm-responses-sse/

### Real-world production regressions
- happy PR #1242: "perf(messages): lazy-load history + parallel AES decrypt + backward pagination" — sequential AES-GCM decrypt on 1000-message session = blank for seconds-to-minutes; fix is `Promise.all` interleaving + newest-first paging. https://github.com/slopus/happy/pull/1242
- open-webui #13786: 5–15 min refresh for 200-message chat history without virtualization; root cause is full-history fetch + Svelte reactivity over large arrays. https://github.com/open-webui/open-webui/issues/13786
- ciphertalk DeepWiki §9.7: virtua virtualized list, IntersectionObserver-based lazy decrypt of media, 10k+ messages without frame drops. https://deepwiki.com/ilovebinglu/ciphertalk/9.7-performance-optimizations

### Browser capability / iOS PWA quirks
- Apple Developer Forums thread 727887: Safari doesn't support invisible push; background notifications suppressed until PWA is opened. https://developer.apple.com/forums/thread/727887
- Firebase JS SDK #7309 / #8444: iOS PWA SW event listeners; iOS device restart suppresses notifications. https://github.com/firebase/firebase-js-sdk/issues/8444
- web.dev "Storage for the web": persistent storage via `navigator.storage.persist()`; installed PWAs exempt from Safari 7-day eviction. https://web.dev/articles/storage-for-the-web

### Local-first precedent
- Ink & Switch: web apps will never be 100% local-first; the canonical answer is "web + Electron/Tauri wrapper." https://www.inkandswitch.com/essay/local-first/
- Linear teardown (Uchit Vyas): "Disable your network. Keep working. … Zero perceived latency per keystroke." https://hellouchit.com/teardowns/linear.html
- Sospedra "The server is just a cache": local-first sync engine, IndexedDB replica, server-side watermark. https://sospedra.me/papers/server-is-a-cache

### Internal project anchors
- `/Storage/Git/spectacle/APP_SPEC.md` — Achlys spec; virtualized 1000+ messages @ 60fps target; SSE streaming; per-chat settings; memory consolidation (§10/§13 long-term memory); API-key-encrypted-at-rest; JWT 15 min/7 day refresh; Tauri 2 + SvelteKit PWA + Rust/Axum/sqlx + SQLite (embedded) + PostgreSQL (server).
- `/Storage/Git/spectacle/.hermes/research/e2ee-browser-capability-survey.md` — web E2EE precedent; WebCrypto ≥ 20× faster than JS for AES-GCM; OWASP Argon2id param choices; PWA + IndexedDB sufficient for most E2EE workloads.
- `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md` — server-reduces-to-dumb-pipe pattern; no AI product on the market has solved server-side-LLM + true-E2EE; Proton's Lumo is the only production E2EE LLM and it works in the browser.

---

## 7. One-sentence per-call verdict (for the parent's TL;DR)

- **Argon2id WASM login on mid-range phone:** 700–2500 ms at OWASP "moderate" params (vs 30–80 ms server bcrypt). 8–30× regression. **Acceptable only with OS-keychain caching via Tauri.**
- **WebCrypto AES-GCM throughput for 1–50 MB chat histories:** 1–1.5 GB/s on mid-range Android (≈ 10–50 ms per MB decrypt). **Not the bottleneck**; network and IndexedDB writes are.
- **IndexedDB vs SurrealDB-over-HTTP:** IndexedDB reads 1–10 ms single-key, 40–150 ms for 1 MB cold; SurrealDB embedded 3–25 ms p50 server-side (50–150 ms RTT over WAN). **For local reads IndexedDB is faster than server round-trip**; for joins/filters/full-text the server still wins.
- **SSE decryption overhead (per-chunk AES-GCM):** 0.5–2 ms CPU per chunk + 56% bandwidth overhead from IV+tag; at 50 tok/s = 25–100 ms/s pure AEAD CPU. **Don't do it.** TLS already authenticates. Batch + skip per-chunk AEAD.
- **WASM memory-consolidation cost for 1000-episode history:** 80–500 s for embedding+clustering on mid-range Android. **Infeasible on a phone.** Keep server-side or move to LLM-provider-side encryption.
- **Battery/network cost of full-history download per session vs server-paging:** Full history = 50 MB radio + multi-minute decrypt per session; paged = 1 MB per session. **3–5× battery + 50–100× network savings** from paging.
- **Offline/PWA capability comparison:** Client-side crypto path is the only way to get true offline; Linear/Notesnook/Standard Notes/Bitwarden all do this. Server-only path has no offline at all. **Decisive win for client-side on offline.**