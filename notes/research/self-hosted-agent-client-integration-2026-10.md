# Self-Hosted Agent Platforms — Client/Integration Comparison

_Compiled 2026-10-06. Bias toward Aug–Oct 2026 docs. "Shipped" / "announced" / "community" called out explicitly. URLs are the source — every endpoint, header, or product name quoted below was read from a primary doc, not invented._

## Candidate set & selection rule

Aim: 6–10 credible self-hostable agent platforms with a *real client story* (official or first-class third-party SDK, mobile app, versioned protocol). Filtered out: pure SDK frameworks with no self-hosted server (LangChain, CrewAI, AutoGen — no client surface to own), wrapper UIs without an agent runtime (Open WebUI counts because it ships a real server; LobeChat is just a frontend and is not in scope), and small one-repo "agent OS" projects whose client story is a single React Native file.

## Per-platform facts

### 1. Hermes Agent (Nous Research) — baseline
Source: https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration (read 2026-10-06).

- (a) **Documented API for third-party/custom clients:** three protocols, all on the same `AIAgent` core.
  - **ACP** — JSON-RPC over stdio, "Agent Client Protocol"; entry point `hermes acp`. Used by VS Code (Zed Industries' ACP extension), Zed, JetBrains. Code: `acp_adapter/`.
  - **TUI gateway** — JSON-RPC over stdio (or WebSocket via `tui_gateway/ws.py`); method catalog `prompt.submit`, `prompt.background`, `session.create/list/active_list/activate/close/interrupt/history/compress/branch/title/usage/status`, `clarify.lock`, `config.set/get`, `commands.catalog`, `client.capabilities`, `gateway.capabilities`, `ping`, `command.resolve/dispatch`, `cli.exec`, `reload.mcp/env`, `process.stop`, `delegation.status`, `subagent.interrupt/steer`, `spawn_tree.save/list/load`, `terminal.resize`, `clipboard.paste`, `image.attach`.
  - **API server** — HTTP + SSE, OpenAI-compatible frontends, defined in `gateway/platforms/api_server.py`.
- (b) **Official mobile/desktop/PWA:** "Hermes Desktop" installer mentioned on the docs home page for Windows/macOS; native Windows mentioned. No iOS/Android app. Android install path is Termux only (curl install.sh).
- (c) **SDK / public API contract:** documented method catalog above, but the page is descriptive — no published SemVer contract. The page explicitly says: "session.active_list, session.activate, and session.close are the process-local live-session controls used by the TUI session switcher… use active-session methods only for sessions that are currently open in the TUI gateway process" — i.e. the API is described by file path, not versioned. REST management surface is undocumented internals (per the user's own statement; confirmed — no admin REST page exists in the public docs).
- (d) **Auth:** the page only states "Within one authenticated gateway, resuming or activating a live session attaches another event subscriber rather than replacing the previous connection." No token, OAuth, or capability model published. The REST management surface authentication is undocumented. This is the *exact* gap the user complained about.
- (e) **Aimed at mobile / third-party client authors:** nothing. The page targets "IDE plugins, custom UIs, CI pipelines, embedded sub-agents." Messaging Gateway page lists Telegram, Discord, Slack, WhatsApp, Teams — i.e. third-party *messaging* clients, not a third-party-agent *client app story*.

### 2. OpenClaw (OpenClaw Foundation 501(c)(3), MIT)
Source: https://github.com/openclaw/openclaw, https://openclaw.ai/, https://docs.openclaw.ai/, https://docs.openclaw.ai/start/why-openclaw (all read 2026-10-06; repo snapshot in those pages: OpenClaw `7b624e9de25`).

- (a) **Documented API for third-party/custom clients:** layered.
  - **A2A 1.0** (Linux Foundation, https://a2a-protocol.org/latest/specification/) — "other agents reach it through the Linux Foundation A2A 1.0 protocol — Agent Card discovery, authenticated JSON-RPC tasks, and outbound peer messaging." A2A itself is versioned with `A2A-Version` header and `VersionNotSupportedError` semantics.
  - **MCP** — "Streamable HTTP, SSE, and stdio transports, with OAuth"; "an MCP client … and an MCP server, and plugins can ship their own MCP servers and apps."
  - **ACP** — "editors connect over the Agent Client Protocol, which OpenClaw also uses to host external harnesses."
  - **OpenAI-compatible HTTP** — `GET /v1/models`, `POST /v1/chat/completions` (with "documented function-tool subset"), `POST /v1/responses` (separately enabled), `POST /v1/embeddings`. *"disabled by default"* (quote).
  - **Skills** follow the AgentSkills spec; plugins auto-detect Agent Plugins/Codex/Claude/Cursor layouts.
  - **Observability** over OpenTelemetry + Prometheus; **discovery** over Bonjour/DNS-SD.
- (b) **Official mobile/desktop apps:** shipped. "Native apps for macOS, iOS, Android, Windows, and Linux" (README). Concrete distros: macOS .dmg, Windows x64+ARM64 installer (v2026.9.4 per the openclaw.ai homepage on 2026-10-06), Linux AppImage/Deb (v2026.9.5), iOS + Android via the same one-liner that provisions the Gateway. Plus a browser "Control UI" (chat, config, sessions, nodes) and TUI.
- (c) **SDK / public API contract:** yes — the A2A 1.0 spec, MCP spec, and OpenAI-compatible HTTP are externally governed (not OpenClaw-controlled), which *is* the contract. OpenClaw itself marks the A2A and ACP paths as the supported client surfaces.
- (d) **Auth:** MCP "with OAuth"; A2A per its security_schemes/security_requirements on the AgentCard; local Gateway controls are loopback-bound by default. No public per-token management API documented; security is described as "policy is enforced in code, and state is versioned and migrated" (Why-OpenClaw).
- (e) **Aimed at mobile / third-party client authors:** explicit. The Control UI is "the single same-origin front door" pattern; the README enumerates Companion apps, Nodes, and Channels; the Why-OpenClaw page is written as a buyer-facing comparison document; OpenClaw Foundation has a "Council on enterprise deployment."

### 3. Letta
Source: https://docs.letta.com/self-hosting/, https://docs.letta.com/reference/faq/, https://github.com/letta-ai/agent-sdk-mobile-app, https://docs.letta.com/v1-sdk/ (all read 2026-10-06).

- (a) **Documented API for third-party/custom clients:**
  - **App Server bidirectional WebSocket protocol** — native transport for the Letta Agent SDK. Default port 4500; `ws://127.0.0.1:4500/ws`.
  - **Built-in OpenAI-compatible HTTP** when started with `--openai-api` (per FAQ: "for clients that expect an HTTP API").
  - **Rest** for Cloud: `POST https://api.letta.com/v1/agents`, `POST /v1/agents/{id}/messages` (the V1 / generated-client API).
  - **ACP** via `letta-acp` adapter (Zed, Buzz).
- (b) **Official mobile/desktop/PWA:** **"Bloop"** — an *official* example mobile app (Expo/React Native + TypeScript + `@letta-ai/letta-agent-sdk`), shipped in the `letta-ai/agent-sdk-mobile-app` repo. The docs FAQ also links `letta-oss-ui` (Electron). FAQ is explicit: "There is currently no official native Letta mobile app for iOS or Android. We recommend using chat.letta.com on your mobile device" — but Bloop (Apache-2.0, in the `letta-ai` org) is the working reference. Bloop supports Letta Cloud *and* a self-hosted App Server.
- (c) **SDK / public API contract:** yes — the Letta Agent SDK is a *first-class high-level* TypeScript SDK. From the V1-vs-Agent-SDK comparison table: the Agent SDK is "the recommended" surface, V1 is deprecated, and **self-hosting is supported only on the Agent SDK** (V1 SDK: "Self-hosting option: No"). High-level primitives (sessions, turns, streaming, approvals, tools, sandboxes) managed for you.
- (d) **Auth:** the mobile-app README is the clearest source: Cloud uses **Authorization Code with PKCE**, redirect `letta-mobile://oauth/callback`, tokens in `expo-secure-store`. Self-hosted: capability token via `letta server --ws-auth capability-token --ws-token-file /tmp/ws-token`; "React Native always sends an `Origin` header, and app-servers only accept those on token-authenticated upgrades." Cloud public OAuth client id is published (`ci-let-94bf2d5e34984a684fb6b18880b6bc7d`) as a non-secret identifier.
- (e) **Aimed at mobile / third-party client authors:** explicit. The mobile-app repo is *built to be lifted* — "the whole SDK story … lives in one readable file you can lift into your own app." It includes a mock transport, the public OAuth client id, and a worked `expo-secure-store` flow. Clearest "build your own client" path in the candidate set.

### 4. Dify
Source: https://docs.dify.ai/en/api-reference/guides/get-started, https://docs.dify.ai/en/cli/authenticate, https://docs.dify.ai/en/self-host/deploy/configuration/environments (all read 2026-10-06).

- (a) **Documented API for third-party/custom clients:**
  - **Service API** per app — REST, "Every request carries the key as a Bearer token." Base URL: `https://api.dify.ai/v1` (Cloud) or `<your-instance>/v1` (self-hosted). Endpoints organised by app type: Chatflow, Workflow, Agent, Chatbot/Agent-chat, Text Generator, Knowledge Base (covered in get-started).
  - **`/openapi/v1/*` programmatic API** for the `difyctl` CLI and other machine clients. **Disabled by default;** requires both `OPENAPI_ENABLED=true` and `ENABLE_OAUTH_BEARER=true`. Rate limit: `OPENAPI_RATE_LIMIT_PER_TOKEN` (default 60/min, 0 = off), shared via Redis. CORS via `OPENAPI_CORS_ALLOW_ORIGINS`.
  - **OpenAPI specs published**: `openapi_service` in self-host docs.
  - **MCP Server** — expose Dify apps as MCP servers.
- (b) **Official mobile/desktop/PWA:** **none** from the Dify project. There is a market of third-party mobile apps that hit the Service API (e.g. Dify mobile apps in the app stores) but none are Dify-org.
- (c) **SDK / public API contract:** yes — Bearer-key Service API is per-app, "one key serves all your end users" (per the get-started guide). Plus the openapi service spec at `/openapi/v1/*`.
- (d) **Auth:** two tiers.
  - Per-app API key: `Authorization: Bearer <key>`, scoped to one app.
  - User-scoped: OAuth 2.0 device flow for `difyctl`; tokens prefixed `dfoa_`; stored in OS credential store (Keychain/Credential Manager/Secret Service), fallback `tokens.yml` with `0600`. Known client IDs gated by `OPENAPI_KNOWN_CLIENT_IDS`; adding your own client id does not require a code change.
- (e) **Aimed at mobile / third-party client authors:** moderate. The Service API is designed for backend integration, not for client-side embedding (the get-started guide is explicit: "Call the API from your backend only. A key embedded in frontend code or a client app can be extracted and abused"). No published mobile design guide; the CLI contract is a *machine* client, not a phone client.

### 5. Open WebUI
Source: https://docs.openwebui.com/reference/, https://docs.openwebui.com/reference/api-endpoints/ (read 2026-10-06).

- (a) **Documented API for third-party/custom clients:**
  - **OpenAI-compatible**: `POST /api/chat/completions` — "OpenAI API compatible chat completion endpoint for models on Open WebUI including Ollama models, OpenAI models, and Open WebUI Function models." Server-side tools, Filters/Functions, MCP tool servers all addressable through the same surface.
  - **Anthropic Messages API compatible**: `POST /api/v1/messages` (also `POST /api/message`); accepts `Authorization: Bearer YOUR_API_KEY` *or* `x-api-key: YOUR_API_KEY`; extended thinking, reasoning effort, structured outputs mapped through.
  - **Ollama passthrough**: `/ollama/api/*` plus an OpenAI-compatible embeddings endpoint.
  - **Functions/Filters**: explicit guidance that `POST /api/chat/completed` is the supported way to run `outlet()` for *pure API consumers* (Continue.dev, Claude Code, custom scripts). Filters behave differently on `main` vs `dev` — this is documented as a stability caveat.
  - **Custom models**: `/api/v1/models` for declarative JSON management.
- (b) **Official mobile/desktop/PWA:** PWA yes (the web UI is responsive and is what the project ships). **No native iOS/Android/desktop from the project.** Community apps exist:
  - **RonasIT/open-webui-react-native** — "production-ready, cross-platform mobile application" by Ronas IT, Apache/MIT; iOS 13+ / Android 8.0+; React Native; "Open MobileUI" on Google Play.
  - **Conduit** — Flutter, native iOS/Android, multi-auth (SSO, custom headers), home-screen widgets, Keychain/Keystore.
  - **Open MobileUI** on Google Play (com.open.web.ui).
- (c) **SDK / public API contract:** Bearer tokens (`sk-` prefix) and JWTs. Keys scoped to the creating user, inherit role + group permissions, optionally endpoint-restricted. The OpenAI/Anthropic compatibility is itself the contract — and Open WebUI's docs are explicit that filter behavior between `main` and `dev` differs, which is the *honest* answer to "is this stable?".
- (d) **Auth:** `Authorization: Bearer YOUR_API_KEY` *or* JWT; "Open WebUI accepts both … this is intentional: the web interface uses JWT tokens internally for the same API endpoints." Admin toggle + group permissions required for non-admin users to mint keys.
- (e) **Aimed at mobile / third-party client authors:** the *whole point* of the OpenAI/Anthropic/Ollama surface is to let other clients in. The reference mobile clients are third-party but explicitly "built on top of" the API. Docs do not promise stability of the JSON `/api/...` surfaces — only the OpenAI-compatible ones.

### 6. LibreChat
Source: https://www.librechat.ai/docs/features/agents_api, https://www.librechat.ai/docs/configuration/authentication, https://www.librechat.ai/docs/features/authentication (read 2026-10-06).

- (a) **Documented API for third-party/custom clients:**
  - **Agents API (Beta)** — explicitly versioned path: `/api/agents/v1/...`. Endpoints: `POST /api/agents/v1/chat/completions` (OpenAI-compatible), `POST /api/agents/v1/responses` (Open Responses spec), `POST /api/agents/v1/events`, management under `/api/agents/v1/agents` and `/api/agents/v1/skills`. Documented as "currently in beta. Endpoints, request/response formats, and behavior may change."
  - **OpenAPI/Swagger**: spec served at `/api/openapi.json`, interactive UI at `/api/docs`; both *disabled by default* — "Keep the routes disabled unless your deployment intends to expose API documentation."
  - Plus the existing REST under `/api/auth/...`, `/api/conversations/...` etc. that the web UI uses.
- (b) **Official mobile/desktop/PWA:** **no native apps** — "LibreChat is a self-hosted web application, not a native Windows app or Linux AppImage. On Windows, use Docker Desktop for the simplest local setup." Web is mobile-responsive. No shipped iOS/Android.
- (c) **SDK / public API contract:** Open Responses is an open spec (initiated by OpenAI, "built by the open-source AI community"); OpenAI-compatible Chat Completions is also a public contract. The Agents management API has a separate OIDC machine-token flow distinct from inference.
- (d) **Auth:** layered.
  - User session: short JWT access token (default 15 min, `SESSION_EXPIRY`) + longer refresh (default 7 days, `REFRESH_TOKEN_EXPIRY`).
  - `OPENID_REUSE_TOKENS=true` causes the cookie to hold the OpenID provider's refresh token (lifetime/rotation/revocation are then the IdP's problem).
  - Email/password (gated by `ALLOW_EMAIL_LOGIN`), LDAP, OAuth (Google, GitHub, Discord, OpenID, SAML), social login (`ALLOW_SOCIAL_LOGIN`).
  - Agents API: Bearer OIDC access token for inference; management API uses deployment-bound OIDC machine identities (configured under `endpoints.agents.managementApi`), not Remote Agents API keys or browser sessions.
- (e) **Aimed at mobile / third-party client authors:** yes, with a "beta" sticker. The Agents API is the project's first explicit *non-browser* client surface, and the management API is separated by design.

### 7. n8n
Source: https://docs.n8n.io/connect/n8n-api/api-reference, https://docs.n8n.io/connect/n8n-api/authentication, https://github.com/n8n-io/n8n-docs/blob/main/docs/api/v1/openapi.yml (read 2026-10-06).

- (a) **Documented API for third-party/custom clients:** **Public REST API**, OpenAPI 3.0 spec at `https://<host>:<port>/<path>/api/v1/...`. Endpoints include `/api/v1/workflows`, `/api/v1/credentials`, `/api/v1/credentials/{id}/transfer`, `/api/v1/credentials/schema/{credentialTypeName}`, `/api/v1/executions`, `/api/v1/audit`, `/api/v1/data-tables` and rows. Operations carry `x-required-scope` (e.g. `credential:list`, `credential:create`) and `x-eov-operation-id`. Security schemes: `ApiKeyAuth` and `BearerAuth`.
- (b) **Official mobile/desktop/PWA:** PWA-friendly web app, but no native iOS/Android/desktop from n8n.io. There is an "n8n mobile" in app stores but it's third-party and not under n8n-io on GitHub.
- (c) **SDK / public API contract:** yes — `openapi.yml` is checked into the docs repo, `@n8n/rest-api-client` is published on npm ("This package contains the REST API calls for n8n"). License: "Sustainable Use License" — **not OSI-open**; the OpenAPI file is `Sustainable Use License`. Scopes are per-key.
- (d) **Auth:** `X-N8N-API-KEY` header, *or* `Bearer` (both declared in the spec). Key created in `Settings > n8n API`, with label + expiration. **Enterprise** plans can scope keys (per the auth doc); non-Enterprise plans do not get scopes.
- (e) **Aimed at mobile / third-party client authors:** yes, with the caveat that the API is for *managing* workflows (CRUD, executions, credentials, audit) — not for chatting with an agent. n8n is workflow automation with an LLM node; not a chat agent runtime.

### 8. Home Assistant
Source: https://developers.home-assistant.io/docs/api/rest/, https://developers.home-assistant.io/docs/api/native-app-integration/setup/, https://developers.home-assistant.io/docs/api/native-app-integration/sending-data/, https://companion.home-assistant.io/ (read 2026-10-06).

- (a) **Documented API for third-party/custom clients:**
  - **REST API** on the same port as the web UI: `GET /api/`, `GET /api/states`, `GET /api/states/<entity_id>`, `POST /api/services/<domain>/<service>`, `POST /api/intent/handle`. Default port 8123.
  - **WebSocket API** — companion `webhook/handle` command for push.
  - **`mobile_app` integration** — a *first-class developer surface* for mobile clients: `POST /api/mobile_app/registrations` (Zeroconf `_home-assistant-mobile-app._tcp.local.` discovery) returns a webhook URL plus encryption key.
- (b) **Official mobile/desktop apps:** **yes — and they're the gold standard for this comparison.** Home Assistant Companion App for iOS and Android, with TestFlight beta channel. Open source.
- (c) **SDK / public API contract:** yes. The `mobile_app` integration *is* the SDK; the developer docs spell out the device-registration flow, webhook URL lifecycle (cloudhook → remote UI URL → local URL with fallback chain), Sodium-based secret-key encryption, and HTTP status semantics (200/201/400/404/410).
- (d) **Auth:**
  - REST: `Authorization: Bearer <long-lived access token>` (created in user profile).
  - Mobile webhooks: **unauthenticated** by design (the URL is the capability), but payloads are encrypted with a per-device shared secret using **libsodium** (`sodium_base64_VARIANT_ORIGINAL`).
- (e) **Aimed at mobile / third-party client authors:** the most explicit of any platform in this comparison. There is a `developers.home-assistant.io` site dedicated to the topic, with a native-app-integration setup guide, sending-data guide, and full REST + WebSocket reference.

### 9. Ollama
Source: https://docs.ollama.com/api/introduction (read 2026-10-06).

- (a) **Documented API for third-party/custom clients:** REST at `http://localhost:11434/api/...`. Endpoints `/api/generate`, `/api/chat`, `/api/tags`, `/api/show`, `/api/embed`, etc. Cloud equivalent at `https://ollama.com/api/...`. NDJSON streaming.
- (b) **Official mobile/desktop/PWA:** **no native apps from Ollama itself.** Third-party mobile clients (Ollama Android Client by chartmann1590 — Kotlin/Compose; Ollama GUI by dontknow492 — KMP/Compose Multiplatform with Android build) are MIT/Apache. Security gateways like `kaansrflioglu/ollama-secure-gateway` exist precisely because the bare API has no auth.
- (c) **SDK / public API contract:** the HTTP API *is* the contract. Official libraries for Python and JavaScript; community libraries for the rest. No versioning policy published.
- (d) **Auth:** **none on the local API by default** (loopback only). Cloud uses standard API keys. This is the reason proxy projects (ollama-secure-gateway, litellm) exist as the de-facto client tier.
- (e) **Aimed at mobile / third-party client authors:** no. Ollama ships an HTTP server; everything on top of it is community.

### 10. (Optional) Langflow / Flowise
Not selected for the comparison table. Both are visual builders with a self-hosted server and an OpenAI-compatible surface, but neither ships a mobile app or a versioned public client API beyond the OpenAI compat layer; mobile clients (if any) are third-party. Including them as #10 would duplicate the Open WebUI / Dify story without adding signal.

## Ranking — "I want to own a good mobile client for my own agent. Which platform makes that easiest today?"

| # | Platform | Decisive fact |
|---|---|---|
| 1 | **OpenClaw** | Ships *official* native iOS, Android, macOS, Windows, Linux apps **and** a documented OpenAI-compatible HTTP surface, plus A2A 1.0, MCP, and ACP — so a custom client can choose between "use the official app" and "roll your own against a versioned external spec" without leaving the platform. (https://github.com/openclaw/openclaw) |
| 2 | **Letta** | Ships the **Bloop** reference mobile app in the `letta-ai` org (Expo + RN), with a *public* OAuth client id and PKCE flow, an Electron reference UI, **and** the Agent SDK is *the* first-class surface (V1 SDK can't even self-host). Self-host + own-client is the documented happy path. (https://github.com/letta-ai/agent-sdk-mobile-app) |
| 3 | **Home Assistant** | The `mobile_app` integration is the *most explicit* "build your own mobile client against our server" developer surface in this comparison — dedicated docs site, device registration, webhook URLs, libsodium payload encryption, fallback chain (cloudhook → remote UI → local). Native Companion App is the proof. (https://developers.home-assistant.io/docs/api/native-app-integration/setup/) |
| 4 | **Open WebUI** | Three compatible surfaces (OpenAI Chat Completions, Anthropic Messages, Ollama passthrough) plus Bearer/JWT auth and *multiple* working third-party mobile clients (RonasIT, Conduit) you can fork. Caveat: the project itself ships *no* native app. (https://docs.openwebui.com/reference/api-endpoints/) |
| 5 | **LibreChat** | New **Agents API (Beta)** at `/api/agents/v1/...` is the first *explicit non-browser* client surface, with Open Responses + OIDC machine-token auth. Marked beta, no native app. (https://www.librechat.ai/docs/features/agents_api) |
| 6 | **Dify** | Per-app Service API with Bearer keys, **disabled-by-default** `/openapi/v1/*` programmatic surface, OAuth device flow for `difyctl`, OpenAPI spec published. Docs explicitly say "from your backend only … a key embedded in frontend code or a client app can be extracted and abused" — i.e. *don't* build a phone client against the Service API. (https://docs.dify.ai/en/api-reference/guides/get-started) |
| 7 | **n8n** | Public REST API + checked-in OpenAPI 3.0 + `@n8n/rest-api-client` npm package + per-key scopes on Enterprise. But the API is for *managing* workflows, not talking to an agent. Useful for orchestration clients, not chat clients. License is Sustainable Use, not OSI-open. (https://docs.n8n.io/connect/n8n-api/api-reference) |
| 8 | **Ollama** | Stable, simple, ubiquitous HTTP API — and *no auth, no native app, no versioned contract*. Mobile clients are all community; you would build your own against `/api/chat` and ship your own auth layer. (https://docs.ollama.com/api/introduction) |
| 9 | **Hermes Agent (baseline)** | Three documented protocols, no public versioned contract, no mobile app, REST management surface undocumented — i.e. the *exact* pain point the user is trying to escape. (https://hermes-agent.nousresearch.com/docs/developer-guide/programmatic-integration) |

## Bottom line

If "own a good mobile client" means **ship one and not have it break on the next upstream release**, the answer is the one with an *external* versioned protocol the upstream can't change unilaterally: **OpenClaw** (A2A 1.0 / MCP / ACP / OpenAI-compat — all governed outside the project) or **Letta** (Agent SDK is the supported surface, the mobile app lives in the same org, and the high-level primitives are what you actually want for a phone UI). Both ship native apps today. **Open WebUI** is the strongest "build my own phone client against a popular open chat server" pick, but you give up an official app. **Hermes** stays at the bottom of this list until/unless the REST management surface gets a documented, versioned client contract.

## Unknown / could not verify

- **Hermes** REST/management surface authentication: explicitly undocumented; cannot verify any token/OAuth model beyond "one authenticated gateway."
- **Letta** `letta-oss-ui` current status vs. "Bloop" as the recommended reference: the FAQ names `letta-oss-ui` as the open-source Electron chat UI but treats Bloop as a worked example; the relationship between the two is not formally declared in the docs.
- **n8n** license compatibility for a *closed-source* third-party mobile client: the API is reachable under the Sustainable Use License; whether a proprietary phone client counts as a "non-Compete" use was not verified.
- **OpenClaw** exact per-handshake / per-session token model for the Control UI and companion apps: the docs describe the architecture (trusted Gateway, policy in code) but do not publish a per-handshake ticket spec comparable to MCP's capability URLs.
- **Open WebUI** long-term stability of the *non-OpenAI* JSON surfaces (e.g. `/api/v1/models`): the docs explicitly warn that `outlet()` filter behavior differs between `main` and `dev`, so a custom client that depends on internal endpoints should treat that as an unstable contract.
