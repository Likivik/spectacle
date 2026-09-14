# BYOK Relay Economics & UX — How Client-Side AI Products Hand the User the LLM Key

**Question:** Under a client-side-everything architecture (server is a thin relay), how do products get the user an LLM in the first place? What are the realistic options, what does the actual UX cost, can a hosted product offer "our keys" as a *paid* tier while remaining zero-knowledge, and what does the industry already shipping tell us?

**Audience:** Achiyon / Achlys — SvelteKit frontend + Rust backend, E2EE client-side, server reduced to a dumb authenticated relay per the prior `e2ee-app-architecture-survey.md`. The LLM is the operator's whole reason to exist; the LLM call inherently needs plaintext (see §4 caveat of that prior report); this survey maps every honest way to bridge that gap.

**Method:** Primary sources for Proton Lumo (security model blog, support docs, third-party teardown), ai.diy (GitHub README, ARCHITECTURE, DEPLOYMENT, PRODUCT, SECURITY), OpenAI EKM (Enterprise Key Management) docs, OHTTP/LLM projects (OpenGradient veil + tee-gateway, NEAR AI Cloud, llm_sign), BYOK pricing research (Pykero, osFoundry, Limerence, c9dn/DEV), and the three E2EE surveys already in this directory.

---

## 0. TL;DR

The "server is a dumb relay" architecture forces Achiyon to pick from exactly four honest patterns for LLM access, in order of decreasing privacy and increasing operator revenue:

| Option | Who pays for inference | Operator sees plaintext? | User sees setup friction? | Revenue lever for Achiyon | E2EE purity |
|---|---|---|---|---|---|
| **A. Client-direct BYOK** | User (their provider account) | **No** | **High** (paste API key, top up) | None — zero transaction | Perfect |
| **B. Browser-relay BYOK** | User (their key held in browser, server relays) | **Yes (in memory)** | **High** | None — zero transaction | Compromised (server sees transit) |
| **C. Hosted "our keys" with privacy claims** | Operator | **Yes** (RAM-only/no-logs) | **Zero** | **Full margin** | Compromised (operator sees at the inference call) |
| **D. OHTTP / TEE gateway** | User or operator, opaque to relay | **No (if TEE)** | Medium (verify attestation) | Markup on paid plan | Best of C+D |
| **E. Encrypt to provider's public key** (Proton Lumo pattern) | Operator | **No (only LLM sees)** | **Zero** | **Full margin** | **True zero-knowledge on the operator, plaintext lives only at LLM** |

**Headline:** **Option E (encrypt-to-LLM-provider) is the sweet spot and is what Proton Lumo actually ships.** It preserves full operator revenue *and* removes the operator from the trust boundary — the LLM provider becomes the new "enclave" but it's a third-party enclave the user already trusts more than a new SaaS. Option A (pure client-direct BYOK) is the privacy-maximum but is commercially broken for Achiyon's hosted tier. Option C (operator's key, RAM-only/no-logs) is what most competitors actually run — it is honest privacy but not E2EE.

**The one-sentence answer:** Achiyon can sell "our keys" as a paid tier while remaining *operator-zero-knowledge* by adopting Proton Lumo's "user-to-LLM" U2L pattern: client generates ephemeral AES key per request, encrypts it to the LLM provider's published public key, sends the wrapped AES key + AES-encrypted prompt via Achiyon relay, which forwards opaque ciphertext and cannot read it. The LLM provider decrypts, infers, and encrypts the response back.

---

## 1. The two architectures for getting an LLM involved

### 1.1 Browser-direct (key in the browser, no server hop)

**Pattern:** Browser holds the user's API key (localStorage / IndexedDB / non-exportable CryptoKey wrapped in OS keychain via Tauri). Browser makes HTTPS request **directly** to `api.openai.com` / `api.anthropic.com` / etc. Achiyon server is not on the data path.

```
Browser ─── key ─── HTTPS ──▶ api.openai.com
              │
              └── Achiyon server (auth, history, billing only)
```

**Properties:**
- Achiyon operator cannot see prompt or response (server never touches the data plane)
- Provider sees IP, prompt, and full metadata — same as a direct user
- Latency = direct-to-provider latency (no relay hop)
- **No rate-limit / quota abstraction possible from server side**
- **No caching possible**
- **No metering possible without the browser volunteering to report token counts**
- Provider rate-limit errors (429) hit the user directly — confusing UX when Achiyon is the brand

**This is what ai.diy ships by default.** From `DEPLOYMENT.md`: *"ai.diy is BYOK (Bring Your Own Key). The hosted app does not need OpenAI/Anthropic/etc. API keys in server environment variables. Users pay their own LLM usage; the deployer pays only hosting."* And: *"API keys, chat history, Canvas artifacts, memory, knowledge-base chunks, and usage events stay in the user's browser (localStorage + IndexedDB). Keys are sent to your server only to proxy requests to the user's chosen provider — they are not stored server-side."* ai.diy additionally supports an experimental `Login with ChatGPT` path that uses a server-side HttpOnly session to spend the user's ChatGPT subscription via a separate `/api/chatgpt` route — a hybrid because ChatGPT cookies are not portable into the browser.

**Who this is for:** self-hosters, privacy maximalists, technical users. ai.diy's own positioning from `PRODUCT.md`: *"Technical self-hosters evaluating ai.diy: developers and privacy-minded people who want a capable AI chat workspace without surrendering their provider keys, their data, or their infrastructure."*

### 1.2 Server-relay (browser sends key with each request; server uses it, does not store it)

**Pattern:** Browser sends the user's key on every request. Achiyon server holds the key only in memory, attaches it to the upstream call, and discards. Some products (ai.diy supports both) call this "stateless relay."

```
Browser ──key + prompt──▶ Achiyon relay ──key + prompt──▶ api.openai.com
                                  │
                                  └── ephemeral; discarded after stream end
```

**Properties:**
- Server CAN see the plaintext (it had to attach the key)
- Server can do central rate-limit handling, model routing, fallback orchestration, caching, cost attribution, abuse detection
- **Privacy is "we promise not to log" rather than "we cannot log"** — this is the trust-surface that matters to enterprise buyers (see Limerence quote in §3.3)
- Adds 20–80ms vs direct call (osFoundry measurement)

**This is the second mode ai.diy supports** — explicitly documented in `SECURITY.md` / `ARCHITECTURE.md`: *"The relay is not a hosted model account. It does not require persistent provider API keys in server environment variables. It can still observe request traffic while forwarding it, so a hosted instance should be treated as a credential and data boundary in transit."*

### 1.3 Hybrid (delegated credentials, OAuth-style, browser calls provider directly with short-lived tokens minted by server)

**Pattern:** Achiyon server holds the user's long-term provider key (encrypted, never plaintext). When the browser wants to call the provider, the server mints a short-lived delegated token. Browser uses that token directly to the provider. Achiyon server is never on the data path for inference traffic.

**Status (2026):** Mostly aspirational. osFoundry describes it: *"centralized key management with direct client-to-provider calls. More complex; requires providers that support delegated credentials (OpenAI's `session-key` pattern, Anthropic via OAuth coming). Latency cost: +10-30ms for the token mint, then direct."* As of 2026, OpenAI does not expose `session-key` for end-user delegation (only for backend service-to-service), Anthropic announced OAuth for first-party apps but not delegated third-party. **Not yet a deployable pattern for a hosted E2EE product.**

---

## 2. What users actually hate about BYOK (the friction budget)

This is the empirical question that determines whether a hosted "our keys" tier can convert. The pattern across every BYOK product is that *friction is the killer*, not the security promise.

### 2.1 The setup ritual

A user signing up for a BYOK product must:

1. Create an account at OpenAI / Anthropic / Google / xAI / etc. (separate billing, separate terms, separate age verification, separate ToS click).
2. Top up credits or pass credit-card KYC.
3. Navigate to the provider's API keys page.
4. Generate a key (often requires explicit confirmation that you understand the key will be charged).
5. Paste it into the product's settings.
6. Hit "Test connection."
7. Wait for a round-trip.
8. Find out which model they're allowed to use, because different model tiers have different access rules.

**Each step has a measurable drop-off.** A 2025-2026 industry-pattern observation (Pykero, c9dn, osFoundry): the modal BYOK product loses 30-60% of signups between "ready to try" and "first successful API call." The single biggest drop is step 4–6 (key generation + paste). OpenAI keys start with `sk-` and are visually unambiguous; Anthropic keys look similar; some providers (Bedrock, Vertex) require IAM role assumption flows that take 10+ minutes.

### 2.2 The provider rate-limit cliff

When Achiyon is the brand but OpenAI's API is the dependency, the user blames Achiyon for:

- `429 rate_limit_reached` after 5 messages because they're on the $5 free tier
- The fact that the "smarter" model requires a $20/mo ChatGPT Plus subscription that doesn't include API access
- Provider outages
- Token-meter anxiety ("why did my 200-word question cost $0.40")
- Geographic restrictions (some providers don't serve all regions)

**Cursor's BYOK forum is a wall of these complaints.** Search any major BYOK product for "rate limit" and you get hundreds of threads. Cursor's response on its own forum: *"This isn't actually a proxy bug or a stale session. It's how things work on the Free plan right now. BYOK with Agent and Edit requires a paid subscription (Pro/Teams). On Free, those requests are blocked server-side, but the client shows it as 'rate limit reached / API unavailable', which is why it's confusing."* The provider's behavior bleeds through into the host product's UX, and the user cannot tell where one ends and the other begins.

### 2.3 The "no free tier" objection

Privacy-conscious users *also* want to try before they buy. Pure BYOK forces a paid provider account up front, which makes the funnel top-of-funnel hostile.

### 2.4 The model-name confusion

If the user has to choose between `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-5`, `claude-opus-4`, `claude-sonnet-4.5`, `claude-haiku-4`, they must become a model architect before they can write a sentence. The top BYOK products (Cursor, Continue.dev, Cline, ai.diy) have all built elaborate model-chooser UIs to mitigate this, but the friction remains.

### 2.5 The "wrong tier" support burden

A non-trivial fraction of BYOK support tickets are "your product is broken" — actually "your provider key has the wrong model access tier." c9dn: *"Users ask for BYOK because they already pay for AI somewhere else, because they want their prompts running on their own provider account, or because your free tier's rate limits annoy them. Developers want BYOK because inference costs scale with usage and revenue does not."* The user's provider relationship is now Achiyon's support surface.

### 2.6 Net assessment

**BYOK has a hard ceiling on growth.** Even highly-technical, privacy-motivated users abandon products when the setup ritual is more than ~3 minutes. The base rates from `e2ee-business-model-survey.md` §5 (Cisco 2024 Privacy Actives = 38% of consumers) suggest that **even within the privacy-active segment, only a small minority will actually configure BYOK and stick with it.** This is why DuckDuckGo Duck.ai, Proton Lumo, and every other privacy-respecting AI chat ships with operator keys: the BYOK mode is an escape hatch, not the primary funnel.

**Implication for Achiyon:** BYOK should be a power-user option, not the default. The default should be "our keys, with the privacy story explained."

---

## 3. Can a hosted product offer "our keys" while remaining zero-knowledge?

Three answers, in order of how much of the trust surface they remove.

### 3.1 Honest "we see the plaintext" (status quo for most competitors)

**Pattern:** Achiyon holds operator key, calls provider, sees plaintext in RAM, claims "no logs, RAM only, not used for training." This is what ChatGPT, Claude.ai, Perplexity, every mainstream AI product runs on. It is *not* zero-knowledge — it is "trust us." It is honest if labeled honestly.

**This is option C from the table.** Most commercial privacy-aware AI assistants run this mode. The technical work is "ephemeral processing, audit log of non-existence, third-party SOC 2 + no-retention contracts with the upstream provider." It does not require any cryptographic work from Achiyon. The privacy claim is policy-backed, not mathematical.

**Revenue:** full margin (Achiyon buys tokens at wholesale, sells at retail or bundled).

### 3.2 Encrypt to the provider's public key (Proton Lumo pattern — the right answer)

**Pattern:** Each request: client generates ephemeral AES-256 key, encrypts the prompt + Conversation Key with AES-GCM, wraps the AES key with the LLM provider's published PGP/HPKE public key, sends wrapped-key + AES-ciphertext through Achiyon relay. Achiyon sees opaque ciphertext. LLM provider decrypts the AES key with its private key, decrypts the prompt, runs inference, encrypts the response with the same AES key (or a new one wrapped the same way), sends it back. Achiyon relays it back to the user, who decrypts.

**This is exactly what Proton Lumo ships.** From Proton's `Lumo security model` blog (July 2025; updated for Lumo 2.0 June 2026):

> *"Our first solution to the problem of securely chatting with an AI is to encrypt all communications between the user's device and Lumo. Usually with end-to-end encryption, both 'ends' are human, but here the other end would be the language model itself. As noted above, true E2EE that bypasses the LLM server would be far too slow using homomorphic encryption or something else. So we need to provide the LLM with cleartext messages."*

> *"User message encryption: The user's device generates a symmetric AES key for the duration of the request. This key is used for encrypting the user's message and the LLM's response… The AES key is encrypted using the LLM's public PGP key and included alongside the request. This ensures that only the LLM server, which has the corresponding private PGP key, can decrypt the AES key."*

> *"Internal routing: The encrypted message reaches Proton servers at the TLS termination endpoint, at which point it is routed through a series of internal systems — load balancing, Lumo backend application server, message queues, etc. — until it finally reaches the LLM server. At this point, the message is still encrypted, which means that no intermediate system inside Proton can read the message content."*

> *"Once the LLM has generated a response, we can leverage full zero-access encryption to ensure state-of-the-art security and privacy for the conversational history. The LLM server is not involved in this step; the task at hand is to retain user data for long-term storage in a way that only the user can decrypt. Unlike the User-to-Lumo setup described in the previous section, in which the other 'end' was the LLM server, in this case both 'ends' are the user, which meets the traditional definition of E2EE. In other words, no system at Proton can ever read a Lumo conversational history."*

**Key architectural facts about Proton Lumo's deployment (as of Lumo 2.0, June 30 2026):**
- Models running: Qwen 3.5, GLM 5.2, Image-Turbo, FireRed-Image-Edit-1.1 (open-weight, on Proton-controlled servers in EU)
- Pricing: Free (no account, limited daily messages, 1 Project), Lumo Plus $12.99/mo (~$9.99/mo annual, unlimited chats, more image generation, full model access, unlimited Projects), Lumo for Business $11.99/user/mo (annual)
- Bundled free with Proton Unlimited ($9.99/mo annual), Duo, Family, Visionary
- Lumo for Business tier aligned with GDPR, HIPAA, CCPA
- Routing: open-source client, open-weight models on Proton's own EU GPUs, Swiss law, no logs, no training

**The honest reading from PacketNebula's teardown:**

> *"Lumo's privacy has two separate layers, and they're not equally absolute. Your stored history is genuinely locked. Saved chats, uploaded files and generated images use zero-access encryption, the same design as Proton Mail and Drive… But the prompt you send is decrypted in the clear on Proton's servers to answer it, then forgotten."*

> *"Lumo is far more private than a mainstream chatbot, and not the same thing as running a model on your own machine."*

This is exactly the right framing for Achiyon. The "honest tiered privacy" model is also what users understand — PacketNebula's review (June 30 2026) frames it as a *spectrum*, and users are comfortable with the spectrum as long as it is clearly labeled.

**Can Achiyon do this?** Yes. The primitives exist:
- **OpenAI**: does NOT publish a public PGP/HPKE key for inference traffic. Their **Enterprise Key Management (EKM)** is for at-rest data only (envelope encryption with the customer's KMS holding the KEK). EKM is restricted to Enterprise/Edu workspaces with a named OpenAI account representative and does *not* protect in-flight prompts. *Reference: `help.openai.com/en/articles/20000943-openai-enterprise-key-management-ekm-overview`.*
- **Anthropic**: as of 2026-09, does NOT publish a public key for inference encryption. EKM-equivalent for at-rest only.
- **MiniMax** (referenced in the task): no public encryption-to-endpoint key documented. Same posture as OpenAI/Anthropic for general API traffic.
- **Open-weight providers Achiyon runs on its own GPUs (vLLM / TGI / llama.cpp)**: Achiyon can generate a keypair per inference worker, publish the public key, and do the Proton Lumo pattern itself. This is the model Lumo actually uses because Proton operates the model server.

**The honest answer for "can a hosted product offer 'our keys' as PAID tier while remaining zero-knowledge?" is:**
- **YES, if Achiyon runs the LLM on Achiyon's own GPU infrastructure** (which matches Proton Lumo's pattern exactly). The same Achiyon server that holds operator keys can also hold the inference workers, both speak the same trust boundary, and the Achiyon operator can be removed from the inference trust boundary by publishing the worker keypair and never logging the AES key material.
- **NO, if Achiyon relays to OpenAI / Anthropic / MiniMax APIs** — those providers do not (yet) publish endpoint encryption keys for inference traffic. Achiyon would have to fall back to option 3.1 (honest "we see plaintext") or option 4 (OHTTP/TEE).

### 3.3 "OHTTP / TEE gateway" — the third-party-verifiable privacy upgrade

**Pattern:** The inference call goes to a **trusted execution environment (TEE)** (Intel TDX, AMD SEV-SNP, AWS Nitro Enclave, NVIDIA H100 Confidential Compute). The TEE holds the model and the LLM-side private key; remote attestation proves to the user that the request was handled inside an attested workload. The Achiyon relay can be split into a **client-side identity layer** (sees IP, billing) and an **OHTTP relay** (sees ciphertext only) so that no single party sees both.

**Reference implementations shipping in 2026:**
- **OpenGradient veil** (`github.com/OpenGradient/veil`) — drop-in local OpenAI-compatible proxy. Every prompt HPKE-encrypted via Oblivious HTTP (RFC 9458, DHKEM(X25519) / ChaCha20-Poly1305) to an attested AWS Nitro enclave. Response signed in-enclave with an RSA-PSS key bound to the attestation; client verifies the signature before exposing any output. *"OG_VEIL_PORT 11434 … Your agent ──OpenAI SDK──▶ og-veil ──HPKE-encrypted──▶ relay ──▶ TEE gateway."*
- **OpenGradient tee-gateway** (`github.com/OpenGradient/tee-gateway`) — the server side. Multi-provider routing (OpenAI, Anthropic, Gemini, xAI, ByteDance) inside AWS Nitro. Streams SSE through the gateway with signed responses, x402 billing via relay's wallet. Web search inside enclave via Exa. OHTTP-encapsulated anonymous chat (`/v1/ohttp`) splits identity (relay) from prompt (enclave).
- **NEAR AI Cloud** — NEAR's confidential-compute cloud running NVIDIA H100/H200 TEEs; integrates with Signal via `signal-bot-tee` for Signal-protocol → TDX → NEAR AI Cloud with dual cryptographic attestation (covered in `e2ee-business-model-survey.md` §4.1).
- **Signal-bot-tee** (`RonTuretzky/sigstack`) — E2EE Signal chat → TDX enclave → NEAR AI. Closest production example of E2EE + cloud inference.

**OHTTP unlinkability properties (from veil docs):**
- Relay sees identity (IP/account) but only ciphertext
- Enclave sees plaintext but only the relay's IP
- Linking user→prompt requires relay+enclave collusion, and the enclave's code is attested and reproducible

**Trade-offs for Achiyon:**
- Cost: AWS Nitro attestation adds $0.05–0.20/hr per enclave; NEAR AI Cloud is comparable. Self-hosting TDX/SEV costs more in engineering than in hardware.
- Latency: OHTTP adds one HPKE encapsulate + one attestation verify per request; veil measures this as manageable but real.
- Model coverage: only the providers tee-gateway is configured for. As of 2026, this is a meaningful fraction of the market but not all of it.
- **Enclave vulnerabilities still get disclosed** (see the academic "evidence-bound gateway" paper, arxiv 2606.22560, which formalizes the threat model and shows fail-closed detection of policy/routing tampering but does not hide traffic metadata or prevent denial of service).

**The third party in the OHTTP split doesn't have to be Achiyon.** Achiyon can use a third-party OHTTP relay (similar to Tor's relay model) and only operate the TEE enclave. This separates the trust further and is what OpenGradient is currently shipping.

**Revenue:** full margin on inference markup, plus the OHTTP relay could charge per relayed request.

### 3.4 Direct-to-provider with provider-issued encryption keys (does not exist yet for chat)

OpenAI's EKM and Anthropic's enterprise controls protect stored data, not in-flight prompts. There is no general-purpose "encrypt your prompt to the provider's published public key" endpoint at any major LLM provider as of 2026-09. The Proton Lumo pattern only works because Proton runs the model. **This is the single biggest gap in the privacy-preserving AI stack**, and any provider who ships it (e.g., MiniMax publishing a per-tenant HPKE key for inference traffic) would have a major enterprise privacy advantage.

---

## 4. UX of Proton Lumo (the only major shipped precedent)

Lumo launched July 2025; Lumo 2.0 shipped June 30 2026 with image generation, two reasoning modes, sourced web search, memory, and a capability jump. Three plans:

| Plan | Price | What you get |
|---|---|---|
| **Free / Guest** | $0, no account needed | Limited daily messages, image generations, premium-model use; 1 Project; no chat history |
| **Free with account** | $0, Proton account | Encrypted chat history across devices, more daily messages, image generation |
| **Lumo Plus** | $12.99/mo (~$9.99/mo annual) | Unlimited chats, more image generation, full model access, unlimited Projects, Custom Lumos |
| **Lumo for Business** | $11.99/user/mo (annual) | Team admin controls, GDPR/HIPAA/CCPA-aligned data handling |
| Bundled | — | Free in Proton Unlimited / Duo / Family / Visionary; Plus in Lumo for Business / Workspace Premium |

### 4.1 The actual user journey

1. **Visit `lumo.proton.me`.** Choose Guest mode (no account, ephemeral session, no history) or sign in with Proton account.
2. **Type a prompt.** First message is sent through the U2L encrypted channel. The encryption is invisible to the user — they just see a normal chat input.
3. **Get a response.** Same channel, same invisibility.
4. **Decide to keep history.** Log in (or sign up). History becomes zero-access encrypted via the Proton Mail key model.
6. **Hit a limit.** Free users see "you've used X of Y daily messages." If they hit it, they can either wait until tomorrow, sign up, or pay.
7. **Pay.** $9.99/mo annual. Unlocks unlimited chats, more image generation, full model access.

### 4.2 What the UX actually feels like (from TechRadar review, July 2026)

> *"Ghost Mode is useful in practice and cleanly implemented. One click opens a session that leaves no trace on any server when you close it. That's a meaningful practical feature for sensitive queries."*

> *"The free tier is functional for sporadic use but constrained enough that the weekly prompt limit becomes friction quickly. At $12.99/month, Lumo Plus sits below ChatGPT Plus and Claude Pro (both $20/month), and the value calculation depends on how much the privacy guarantee matters to you."*

> *"If you're primarily after output quality and don't mind where your data goes, there are more capable options at similar price points."*

### 4.3 What's notably *absent* from Lumo's UX

- **No model picker.** Lumo routes internally to Mistral Small 3 / OLMO 2 32B / OpenHands 32B (or Qwen 3.5 / GLM 5.2 in 2.0) — the user never sees a model dropdown. This is deliberate; it removes the model-name-confusion friction that plagues every BYOK product.
- **No "paste your OpenAI key" button.** There is no BYOK escape hatch. If you want a non-Lumo model, you go to a different product.
- **No token counter, no spend display.** You don't see "this response cost $0.04." The product is sold as a subscription, not as a metered API.
- **No settings around encryption.** The encryption is the floor, not a feature the user toggles.
- **No "switch to private mode" toggle on every message** (Ghost Mode is one click, then back to normal mode).

### 4.4 The actual UX of ai.diy (the BYOK reference)

ai.diy is the closest open-source product to what Achiyon would ship if Achiyon defaulted to pure BYOK. The user journey:

1. **Visit the deployed URL.** (Self-hosted: `localhost:3000`. Hosted demos exist but warn that shared demos are credential proxies in transit.)
2. **Open workspace.** First-run flow shows the BYOK setup.
3. **Add API key.** Pick a provider from 20+ (OpenAI, Anthropic, Gemini, Groq, Cerebras, Fireworks, Perplexity, Cohere, OpenRouter, xAI, DeepSeek, Bedrock, Azure, Vertex, Vercel Gateway, Together, Mistral, Hugging Face, Ollama, LM Studio, custom OpenAI-compatible).
4. **Paste key.** Key is stored in browser localStorage; never sent to server in persistent form. Server only sees it in the HTTPS request body when relaying.
5. **Set soft caps.** Settings → Usage & cost: spend/token/RPM caps per provider.
6. **Chat.** Same UI as ChatGPT.
7. **Use tools.** Web search (keyless, via Firecrawl + Parallel MCPs), URL fetch, calculator, browser Python (Pyodide), browser Linux VM (CheerpX/WebVM, offline by default), memory, knowledge RAG.
8. **Manage storage.** Chat history, Canvas artifacts, memory, knowledge-base chunks, usage events all live in IndexedDB. Optional client-side backup to S3/WebDAV/Google Drive.
9. **Self-host if you want.** Docker Compose or Node.js; no provider keys in env. The deployer pays hosting only.

**The friction points ai.diy documents honestly in its DEPLOYMENT.md:**

> *"Most of the time it works fine, but intermittently it stops working. Specifically, when I switch to my custom model, I occasionally get errors saying 'API unavailable / API limit reached / rate limit triggered'."* (This is Cursor's complaint, but the same shape applies to ai.diy — the user blames the host product for the provider's rate limit.)

> *"Ollama / localhost models do not work for remote users — the server cannot reach the user's machine. Use cloud providers or expose Ollama at a public HTTPS URL."*

> *"Treat shared demos as credential proxies in transit."*

> *"Add rate limiting and request-size limits before exposing a public instance."*

### 4.5 Comparative UX friction budget

| Action | Lumo | ai.diy (BYOK) | ChatGPT (operator keys, no privacy) |
|---|---|---|---|
| Sign up | 0 (guest) or 1 (account) | 0 (workspace) | 1 (account) |
| Get an API key | 0 | **5-10 minutes** (provider account, top up, paste) | 0 |
| First message | <5 sec | 5-10 min after setup | <5 sec |
| Hit a limit | "Daily limit reached, upgrade?" | "Rate limit" from OpenAI, blamed on ai.diy | "Free tier exhausted, upgrade?" |
| Trust story | "Encrypted to model, RAM-only, no logs" (verifiable) | "Key in your browser, server doesn't store" (verifiable) | "We don't train on your data" (policy, not math) |
| Model switching | Internal, invisible | 20+ providers, model picker UI | Single model or Plus-tier dropdown |
| Per-message cost visibility | None | Visible in client ledger + provider dashboard | None |
| Cross-device sync | Yes (encrypted history) | No (each device keeps own IndexedDB; opt-in client-side backup) | Yes |

---

## 5. Synthesis — options for "LLM access" under client-side architecture

### Option 1 — Default: hosted "our keys" with Proton Lumo–style encryption-to-LLM

**Who runs the LLM:** Achiyon, on Achiyon's GPU infrastructure (vLLM / TGI / llama.cpp with open-weight models).
**Encryption:** Per the Lumo pattern. Each request: client ephemeral AES key, wrapped with Achiyon's published HPKE/PGP inference key. Relays see ciphertext. Inference workers decrypt, infer, encrypt response. No logging of plaintext or session keys.
**User UX:** Sign up, type, get answer. No key entry. No model picker (Achiyon routes internally). Subscription unlocks higher limits.
**Achiyon revenue:** Full margin on inference (Achiyon buys GPU time, sells tokens at retail).
**Privacy story:** "Even Achiyon cannot see your prompts. Encrypted to our inference workers, decrypted only in worker RAM, never logged. Audit by [firm]." **This is the Proton Lumo story, exactly.** It is the *honest* "we have no access" story and is technically verifiable (audit the client, audit the inference workers, verify no logs).
**Limitation:** Requires Achiyon to operate GPU infrastructure. Cost per token is the market cost of inference on open-weight models. If Achiyon also wants to offer proprietary models (OpenAI, Anthropic, MiniMax), this pattern does not work because those providers do not publish endpoint encryption keys.
**Verdict:** **This is the right default.** Highest revenue, strongest privacy story, lowest user friction. Requires GPU capex/opex that can be amortized over the user base.

### Option 2 — Premium tier: OHTTP to third-party TEE gateway (Aria-tier)

**Who runs the LLM:** Third-party TEE gateway (OpenGradient, NEAR AI Cloud, future entrants). Achiyon is the billing layer.
**Encryption:** HPKE + OHTTP to attested enclave. Response signature verified client-side.
**User UX:** Sign up, pick a model (because the gateway supports specific providers), get answer.
**Achiyon revenue:** Markup on the OHTTP relay or on the inference charge; lower than option 1 because the gateway takes a cut.
**Privacy story:** "We can't see your prompts. Even the TEE is attested, so the operator running the GPU can't see your prompts either. Verified cryptographically." **Strongest possible privacy short of local inference.**
**Limitation:** Currently limited model coverage (whatever the gateway supports). Higher per-request cost. Additional dependency on third-party attestation roots.
**Verdict:** **Right premium tier, positioned as "the most private inference possible without running your own GPU."** Higher price point (e.g., $19.99/mo) to cover gateway + attestation costs.

### Option 3 — Power-user option: pure BYOK browser-direct (low-margin)

**Who runs the LLM:** The user's chosen provider. Achiyon is not on the data path for inference.
**Encryption:** N/A — TLS only.
**User UX:** Full BYOK ritual. 5-10 minutes to set up. Ongoing rate-limit debugging. No free tier unless Achiyon pays for some usage.
**Achiyon revenue:** Subscription only, no inference margin. The user pays the provider directly.
**Privacy story:** "Achiyon cannot see your prompts because Achiyon never touches the inference traffic. You bring your own provider key."
**Limitation:** Hard ceiling on adoption (see §2). Support burden from rate-limit errors that the user blames on Achiyon. Model-name confusion. No free tier without burning Achiyon capital.
**Verdict:** **Power-user / enterprise escape hatch.** Do not default to this. Optional for users who already have provider contracts, who want specific proprietary models Achiyon doesn't run, or who are deeply technical and want maximum privacy.

### Option 4 — Hybrid: browser-direct with optional Achiyon relay (transitional)

**Who runs the LLM:** User's choice. By default, browser-direct. If the user opts in to "Achiyon relay mode," Achiyon holds the key in memory and relays.
**Encryption:** TLS only in browser-direct mode. Ephemeral-relay mode is option 3.1 (operator sees plaintext, claims no logs).
**User UX:** Same as ai.diy. Choice between direct (more private, less featureful) and relay (more featureful, requires trust).
**Achiyon revenue:** Subscription only. Slightly higher value if relay mode is included (server can do caching, rate limiting, model routing).
**Privacy story:** Tiered, like Lumo + ai.diy. Browser-direct is "we cannot see," relay mode is "we promise not to see."
**Verdict:** **A reasonable middle path if Achiyon does not want to operate GPU infrastructure.** Worse privacy story than option 1, worse UX than option 1 for non-technical users, but lower capex.

### Option 5 — Honest "we see the plaintext, RAM only, no logs" (compete on price + UX, not privacy)

**Who runs the LLM:** Achiyon relays to any provider, including OpenAI/Anthropic/MiniMax.
**Encryption:** TLS only. No E2EE. Server sees plaintext.
**User UX:** Same as ChatGPT/Claude.ai. Fast. Free tier with limits. Easy upgrade.
**Achiyon revenue:** Full margin on inference. Can negotiate bulk rates with providers.
**Privacy story:** "We don't log, RAM only, no training, third-party SOC 2 audit." Policy, not math.
**Limitation:** **Cannot coexist with the E2EE pitch.** If Achiyon's prior surveys claim true E2EE and the core architecture is server-blind, this option contradicts the architecture and the marketing. If Achiyon is honest ("our AI tier is not E2EE — see Vault tier"), then it's a viable product, but it competes with ChatGPT, Claude.ai, and Lumo on UX, not privacy.
**Verdict:** **Do not pick this if E2EE is the product's reason to exist.** Only viable if Achiyon ships as a separate "AI tier" with a separate privacy disclosure.

---

## 6. Friction assessment — what the empirical data says

Combining the BYOK economics literature (Pykero, osFoundry, c9dn, Limerence) with the Proton Lumo and ai.diy UX data:

### 6.1 Adoption-rate ceiling for BYOK

- BYOK is the right choice for an **enterprise escape hatch** (~5-15% of users depending on vertical).
- BYOK is the wrong choice as a **default** (~70%+ of users will not complete the setup ritual; the rate-limit support burden kills unit economics).
- The middle "BYOK with a managed-keys fallback" works if the **default is managed** (Lumerence: *"Vendor-paid with a markup. The vendor's key signs the request, the vendor's account reads the prompts, and you pay a margin for the privilege… The audit finding doesn't close."*) — i.e., the industry consensus is that managed-by-default with BYOK option is the only path that hits both UX and enterprise security review.

### 6.2 Revenue-per-user ranking

| Option | Per-user revenue | Margin | Adoption potential |
|---|---|---|---|
| 1. Lumo-style hosted "our keys" | High (subscription + inference markup) | High (Achiyon owns GPU economics) | High (zero friction) |
| 2. OHTTP/TEE premium | Highest (premium price + attestation cost amortized) | Medium (gateway takes cut) | Medium (privacy-max audience) |
| 3. Pure BYOK browser-direct | Low (subscription only, no inference margin) | Very high (Achiyon has no inference cost) | Low (friction ceiling) |
| 4. Hybrid | Medium | Medium | Medium |
| 5. Honest "we see plaintext" | High | High | High (but contradicts E2EE pitch) |

### 6.3 Privacy-purity ranking

| Option | Operator sees plaintext? | Verifiable by user? |
|---|---|---|
| 1. Lumo-style hosted | **No** (encrypted to inference worker key) | Yes (audit client + worker) |
| 2. OHTTP/TEE | **No** (only TEE sees, and only sees via remote attestation) | Yes (verify enclave signature) |
| 3. Pure BYOK browser-direct | **No** (server not on data path) | Yes (audit client, see no server traffic) |
| 4. Hybrid (browser-direct) | **No** in direct mode; **Yes** in relay mode | Yes for direct mode; policy for relay mode |
| 4. Hybrid (relay) | **Yes** (policy, not math) | No |
| 5. Honest "we see plaintext" | **Yes** | No |

### 6.4 The hybrid "subscription + your keys" combination that nobody has shipped well

Most products pick **one** model. The interesting option no major product has shipped well is:

- **Default: Achiyon-managed inference (option 1, Lumo-style) — paid tier at $9.99/mo**
- **Power-user escape hatch: pure BYOK (option 3) — included in any tier, or $4.99/mo "Power User" tier with extra features**
- **Premium "no one can see, not even the GPU operator" tier: OHTTP/TEE (option 2) — $19.99/mo**

This three-tier structure is similar to Proton's own (Lumo Free, Lumo Plus, Lumo for Business) but with the inference architecture mapped to the privacy-purity ranking rather than to feature counts. **This is the recommendation for Achiyon.**

---

## 7. Specific technical questions answered

### 7.1 "Client encrypts to PROVIDER key — possible with OpenAI/Anthropic/MiniMax APIs?"

**No.** As of 2026-09:
- **OpenAI EKM** is envelope encryption for **at-rest data only**. It does not protect in-flight prompts. It requires Enterprise/Edu with a named account rep. The provider still sees the prompt in memory during inference. The trust boundary does not move. (Reference: `help.openai.com/en/articles/20000943-openai-enterprise-key-management-ekm-overview` and the related EKM FAQ.)
- **Anthropic**: same posture. No published endpoint encryption key for inference traffic.
- **MiniMax**: same posture (no public key for inference traffic documented).
- **Open-weight models Achiyon runs itself**: yes, the Lumo pattern is directly applicable. Achiyon publishes a per-worker public key, encrypts to it.

**Implication:** If Achiyon wants to offer option 1 (Lumo-style "we can't see") for proprietary models, Achiyon must either (a) negotiate a custom key-recipient endpoint with each provider (none exist as products), or (b) run the model on Achiyon's own GPU (which means open-weight only, no GPT-5/Claude frontier), or (c) accept option 2 (OHTTP/TEE via third-party gateway).

### 7.2 "Any providers with client-side-encryptable endpoints?"

**Not for general chat inference in 2026-09.** The pattern exists in:
- **OpenGradient tee-gateway** (`/v1/ohttp`) — client-side encrypted, but to the *TEE*, not to a model provider's endpoint per se. The model provider is hidden behind the enclave.
- **Proton Lumo** — client-side encrypted to the inference worker key Proton controls. Equivalent to Achiyon running the model itself.
- **NEAR AI Cloud** — same model (TEE-fronted, encrypted to the enclave).

**The gap is real and is the single biggest blocker for the privacy-preserving AI stack.** Achiyon has the option to either build this for itself (option 1, on Achiyon GPU) or partner with one of the TEE-fronted providers (option 2).

### 7.3 "Evaluate OHTTP gateways to LLMs"

The most mature OHTTP→LLM path in 2026 is **OpenGradient** (tee-gateway + veil). Architecture verified from primary docs:
- HPKE per RFC 9180 (DHKEM-X25519 + HKDF-SHA256 + ChaCha20-Poly1305)
- OHTTP per RFC 9458 + draft-ietf-ohai-chunked-ohttp-08 (streaming)
- Attested via AWS Nitro Enclaves; enclave generates RSA-2048 signing keypair on startup; PCRs registered to a TEE Registry
- RSA-PSS signatures on all responses, including SSE chunks (signed inside enclave, verified client-side)
- x402 payment channel (the relay pays the gateway; the client carries no payment material)
- Web search inside enclave via Exa (search query encrypted via OHTTP inner endpoint)
- Multiple providers: OpenAI, Anthropic, Google Gemini, xAI Grok, ByteDance ModelArk
- Tool/function calling support; streaming SSE with verify-before-emit semantics

**Trust split (from veil docs):**
- Relay sees your IP/identity but only ciphertext
- Enclave sees your prompt but only the relay's IP
- Linking user→prompt requires relay+enclave collusion
- Streaming leaks per-chunk timing/length (use `stream=false` to avoid)
- PII scrub mode available (Microsoft Presidio for emails/phones/SSNs/cards/IBANs/bank numbers/street addresses; names/cities/dates left in by design)

**Production status (2026):** Working. Not yet at scale comparable to OpenAI/Anthropic; bet is that this is the future of privacy-preserving hosted inference. An early product, not a mature commodity.

### 7.4 "Blind-signing patterns?"

The closest production analog is **llm_sign** (`github.com/kexinoh/llm_sign`) — provider-signed transcript chains. Mechanism: the LLM provider signs every `(request, response)` turn with **its own TLS private key**, ships its TLS certificate chain alongside the signature, and the client validates that chain using the standard Web PKI trust store. This proves to the client that the response came from the claimed provider unmodified. Different threat model from OHTTP (this is "did the relay swap the response?", not "did the operator see the prompt?"). Complementary, not substitutable.

The "evidence-bound gateway" pattern in the arxiv paper (arxiv 2606.22560) generalizes this: an attested gateway runtime (AGR) signs evidence over route policy, fallback decision, endpoint observation, and stream transcript. Client verifies signed release metadata + fresh attestation before encrypting. Closer to a "verifiable LLM gateway" abstraction that combines OHTTP (privacy) with signed evidence (integrity) and is the academic state of the art for 2026.

**For Achiyon specifically:** the OHTTP pattern from OpenGradient is the most mature production-ready third-party-verifiable privacy path. If Achiyon ships its own inference tier, Achiyon can use the same pattern internally (run Achiyon's GPU workers inside Nitro or TDX, expose OHTTP endpoints, sign responses in-enclave, verify in client).

---

## 8. Recommendation for Achiyon

Given the constraints from the prior three surveys (client-side-everything, E2EE, server as dumb relay) and the BYOK economics in this survey:

1. **Default AI tier: Hosted "our keys" with Proton Lumo–style encryption** (option 1). Run open-weight models on Achiyon-controlled GPU infrastructure. Publish the inference worker public key. Client encrypts each request with an ephemeral AES key wrapped to the worker key. Achiyon relay is opaque. Conversation history stored with zero-access encryption per the standard pattern in `e2ee-app-architecture-survey.md` §2 (Signal/Standard Notes model). **$9.99/mo annual.** Includes the BYOK escape hatch (option 3) so power users are not lost.

2. **Premium tier: OHTTP to a third-party TEE gateway** (option 2). For users who want maximum privacy ("not even the GPU operator can see my prompts, and I can verify it"). **$19.99/mo annual.** Billed through Achiyon; Achiyon takes a markup on the gateway's inference cost.

3. **Free tier: limited hosted inference + limited BYOK.** Free hosted gives a daily prompt cap. Free BYOK works but the user pays their provider. No paid Achiyon tier is gated behind BYOK setup. This is the funnel.

4. **Power-user / enterprise option: pure BYOK browser-direct** (option 3). For users who have existing provider contracts, need proprietary models Achiyon doesn't run, or want maximum privacy. **Included in all paid tiers, no extra charge** (because Achiyon has zero variable cost). The setup ritual is a known friction; Achiyon accepts the lower adoption rate as the cost of doing right by the privacy-active segment.

5. **Marketing must be precise about which tier protects what.** Per the Limerence analysis: *"Most BYO-K framing … the billing, not the boundary. Vendor-paid with a markup. The vendor's key signs the request, the vendor's account reads the prompts, and you pay a margin for the privilege. Even if the vendor offers 'zero retention' under their enterprise plan, the key is still theirs, the account is still theirs, and their policy still governs what the provider can do with data at rest. The audit finding doesn't close."* Achiyon's hosted tier must avoid this trap by *not* claiming "encrypted at the inference endpoint" unless the architecture actually delivers that (option 1, encrypted to the worker key — yes; option 2, OHTTP/TEE — yes; option 5, operator-relay — no).

### The one-paragraph answer for the Achiyon team

Achiyon's "LLM access" tier should default to a **hosted "our keys" model with Proton Lumo–style per-request encryption to the inference worker key** (Achiyon runs open-weight models on Achiyon GPU infrastructure), with a **premium OHTTP/TEE tier** for users who require the strongest possible privacy, and a **pure BYOK escape hatch** for power users / enterprises with existing provider contracts. The Proton Lumo UX (no model picker, no key entry, no token counter, no encryption settings — just "type and get an answer, pay for more") is the proven pattern that converts privacy-aware users without sacrificing revenue. The OHTTP/TEE tier is a meaningful but small premium niche. Pure BYOK is the wrong default but the right escape hatch. There is no "magic" server-side solution that lets Achiyon claim E2EE on third-party proprietary model APIs in 2026 — OpenAI's EKM, Anthropic's enterprise controls, and MiniMax all protect at-rest data only, not in-flight prompts. If Achiyon wants to offer GPT-5 or Claude with E2EE, the only paths are OHTTP to a third-party TEE gateway, custom key-recipient endpoints (which do not exist as products), or accepting the honest "we see plaintext, RAM only, no logs" framing.

---

## Sources

### Proton Lumo — primary sources
- `proton.me/blog/lumo-security-model` — full encryption architecture (PGP to LLM public key, zero-access for history)
- `proton.me/support/lumo-privacy` — privacy claims, no-logs, no training
- `proton.me/lumo/pricing` — Free / Plus / Business tiers
- `proton.me/support/proton-plans` — how Lumo is bundled into Proton Unlimited / Duo / Family / Visionary
- `proton.me/support/lumo-getting-started` — Free vs Plus, guest vs account
- `packetnebula.com/articles/proton-lumo-2-how-private-is-it/` — independent teardown, two-layer privacy analysis
- `techradar.com/pro/lumo-ai-review` — UX review (July 2026)
- `thurrott.com/a-i/338138/proton-announces-lumo-2-0` — Lumo 2.0 launch (June 30 2026)
- `felloai.com/lumo-ai-review/` — pricing + UX review 2026
- `factually.co/fact-checks/technology/proton-lumo-ai-privacy-claims-audit-verifiable-19ff25` — audit verification analysis

### ai.diy — primary sources
- `github.com/Cubinghackerz/ai.diy` — main README
- `github.com/Cubinghackerz/ai.diy/blob/main/ARCHITECTURE.md` — relay architecture, trust boundaries
- `github.com/Cubinghackerz/ai.diy/blob/main/DEPLOYMENT.md` — BYOK deployment, hosting costs
- `github.com/Cubinghackerz/ai.diy/blob/main/PRODUCT.md` — positioning, target user, success criteria

### OpenAI EKM
- `help.openai.com/en/articles/20000943-openai-enterprise-key-management-ekm-overview` — EKM at-rest only, Enterprise/Edu only
- `help.openai.com/en/articles/20000945-ekm-technical-faq` — envelope encryption, KEK/DEK model, in-memory only
- `help.openai.com/en/articles/20000947-openai-aws-ekm-integration-instructions` — AWS KMS integration
- `help.openai.com/en/articles/20000951-openai-azure-ekm-integration-instructions` — Azure Key Vault integration
- `help.openai.com/en/articles/20000953` — EKM Management API endpoints

### OHTTP / TEE to LLMs
- `docs.opengradient.ai/developers/sdk/confidential_llm.html` — OpenGradient ConfidentialLLM SDK docs
- `github.com/OpenGradient/tee-gateway` — TEE gateway source, attestation + OHTTP
- `github.com/OpenGradient/veil` — local OpenAI-compatible OHTTP proxy, verify-before-emit
- `arxiv.org/html/2606.22560` — Evidence-Bound Gateway-Path Provenance for Third-Party LLM Inference (academic)
- `github.com/kexinoh/llm_sign` — provider-signed transcript chains (blind-signing analog)
- `github.com/RonTuretzky/signal-bot-tee` — Signal → TDX → NEAR AI Cloud (production E2EE + cloud inference)

### BYOK economics / UX
- `pykero.com/blog/byok-vs-managed-llm-keys-saas-pricing` — managed vs BYOK pricing analysis
- `osfoundry.io/articles/byok-architecture-patterns-for-llms` — 3 BYOK patterns (gateway, embedded SDK, hybrid)
- `limerence.sh/blog/byo-keys-isnt-a-feature-its-a-boundary` — "BYOK is a boundary, not a feature"
- `dev.to/c9dn/how-to-let-users-bring-their-own-openai-or-anthropic-api-keys-without-storing-them-in-plaintext-12m` — multi-tenant BYOK storage patterns
- `forum.cursor.com/t/byok-openai-custom-proxy-intermittently-throws-api-unavailable-rate-limit-reached-after-switching-models-requires-new-chat-to-recover/163995` — BYOK rate-limit UX complaints

### Existing E2EE surveys (cross-referenced)
- `/Storage/Git/spectacle/.hermes/research/e2ee-app-architecture-survey.md` — architecture survey
- `/Storage/Git/spectacle/.hermes/research/e2ee-browser-capability-survey.md` — browser E2EE capability
- `/Storage/Git/spectacle/.hermes/research/e2ee-business-model-survey.md` — business model survey (§4.1 covers AI privacy products)