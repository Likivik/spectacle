# Credential Brokering for AI Agents — Landscape

## Industry Consensus

The pattern is universal: **separate credential store → short-lived/scoped token → inject at egress boundary → agent never sees credential bytes.**

Production vendors use network-level sandbox injection (firewall/proxy), not separate-VPS proxies.

### Organisations endorsing the pattern

| Org | Product | Mechanism |
|---|---|---|
| Anthropic | Managed Agents Vaults | MCP credentials (static_bearer, mcp_oauth) + env var placeholders substituted at egress. Envelope encryption, signed request tokens |
| Vercel | Sandbox Credential Brokering | Firewall-level header injection at microVM boundary. Network policy allow/deny + credential transform per-host |
| Cloudflare | Outbound Workers / Egress Policies | Programmable JS proxy per host. KV-stored secrets. Allow/deny/header-injection/Proxy/VPC routing. Dynamic Workers with globalOutbound intercept |
| Microsoft | MCP Enterprise-Managed Authorization | IdP-centric OAuth via ID-JAG token exchange. Centralised policy in Entra ID |
| Okta | Auth0 for AI Agents / Okta for AI Agents | Agent as first-class identity. Short-lived credentials, kill switch, audit trail. ID-JAG for cross-app access |
| Bitwarden | Agent Access SDK | Noise-encrypted tunnel. `aac run` injects creds as env vars into child process. Open protocol |
| Google Cloud | Agent Identity (SPIFFE) | X.509 + DPoP double-bound tokens. Auth manager vault. mTLS mandatory |
| LangChain | LangSmith Sandboxes | Sandboxed code execution with egress control |
| CrowdStrike | Continuous Identity | Zero-trust identity enforcement for agents |
| Uber | SPIRE/SPIFFE | Internal workload identity federation |
| Akamai | KYA (Know Your Agent) | Agent identity verification at edge |
| HashiCorp | SPIFFE promotion | SPIFFE IDs for non-human workload identity |

### Standards bodies

- **IETF CB4A** / **WIMSE** — formalising PDP/CDP split, SPIFFE/SPIRE, DPoP
- **OpenID AuthZEN** — authorisation for AI agents
- **MCP Enterprise-Managed Authorization** — standardised IdP-controlled MCP auth
- **OWASP** — LLM Top 10 prompt injection guidance
- **Gartner** — credential brokering as AI security best practice

---

## Tools Orgs Use / Recommend

| Org | Tool | Type | Key Detail |
|---|---|---|---|
| Anthropic | Managed Agents Vaults | Built-in (SaaS) | MCP creds (static_bearer, mcp_oauth) + env var creds. Envelope encrypted at rest, signed request tokens for retrieval |
| Vercel | Sandbox SDK | Platform (microVM) | `networkPolicy.allow[*].transform` injects headers at firewall. Credentials never enter sandbox. Also supports `forwardURL` for proxying |
| Cloudflare | Outbound Workers / Egress Policies | Platform (Worker/Container) | `outboundByHost` JS handler per domain. KV secrets referenced by egress rules. Allow/deny/inject/proxy/VPC |
| Cloudflare | Dynamic Workers `globalOutbound` | Platform (Worker) | Intercepts every `fetch()` from dynamic Worker. `ctx.props` for per-tenant context |
| Okta | Auth0 AI SDK | SDK | Token retrieval within tool execution context. Never exposes raw credential |
| Microsoft | MCP EMA extension | Standard | IdP-centralised OAuth. ID-JAG flow. Supported by Anthropic, Microsoft, Okta |
| Bitwarden | Agent Access SDK | Tunnel + CLI | Noise protocol E2EE tunnel. `aac run --env` injects into child process |
| Google Cloud | Agent Identity + Auth Manager | Platform (GCP) | SPIFFE ID per agent. X.509 (24h auto-rotate) + DPoP. Auth manager vaults API keys/OAuth tokens |

---

## Unmentioned Tools Implementing the Pattern

### MITM Proxy (transparent, any protocol, needs CA trust)

| Tool | Lang | Status | Key Features |
|---|---|---|---|
| **Agent Vault** (Infisical) | Go | Active, 39 releases | **Has official Hermes-on-VPS guide** ⭐. Single binary, MITM proxy. Separate host recommended. CLI + UI. TypeScript SDK for ephemeral sandbox tokens |
| **Paude Proxy** | Go | Active | goproxy-based. gcloud ADC auto-refresh (Vertex AI / Gemini). Stub ADC files. Strict suffix matching against CONNECT target |
| **Sluice** | Go | Active, 36 releases | MCP gateway + SOCKS5. Phantom token swap. Telegram human approval. All-protocol DLP (HTTP, gRPC, WebSocket, SSH, IMAP, DNS, QUIC). Encrypted vault (age, Vault, 1PW, Bitwarden) |
| **Postern** | Go | Active, 9 releases | Brokers 1Password & Bitwarden at request time. Pluggable providers. Fails closed (502 on resolver error). Docker-first, non-root |
| **Crebro** | Rust | Active | Local wrapper, redacts secrets from LLM requests. Different angle — runs alongside agent, not as separate host |

### Clean Reverse Proxy (no CA cert, agent targets proxy URL)

| Tool | Lang | Status | Key Features |
|---|---|---|---|
| **Outpost** | Python + TS | Active | Capability-based. Cloudflare Workers deployable. Built-in auth modules (bearer, basic, API-key, HMAC, OAuth2 CC). Policy gates for sensitive writes. 32 MB image |
| **Mintkey** | Go + Python | Pre-alpha | Kong + Go plugin. MCP service discovery. SSH bastion. Per-request audit with hash chain. 20 ADRs, very thorough architecture |

### Local Daemon (shared host, weaker isolation, lower latency)

| Tool | Lang | Status | Key Features |
|---|---|---|---|
| **Hermetic** | Rust | Active, open core | "★★★ Brokered" — daemon makes the HTTPS call, agent gets response only. MCP proxy + SSH agent. Binary attestation, per-message sender verification, process-bound tokens. Core crates AGPL-3.0, daemon proprietary |
| **ghbrk** | Rust | Active | git/gh only. Root-owned policy file. Simple, focused, no MITM |
| **agent-iam** | TS | Active | Capability tokens (HMAC-SHA256). Hierarchical delegation. MCP tool access control with schema TOFU pinning (rug-pull defense). RFC 8707 audience-bound credentials |
| **Authsome** | Python | Active | OAuth2 + API key gateway. Agent skill integration (`npx skills add`). Local-first, no SaaS |

### Ephemeral Token Broker

| Tool | Lang | Status | Key Features |
|---|---|---|---|
| **AgentWrit** | Go | Active | EdDSA JWT. 4-level revocation (token/agent/task/chain). Tamper-evident audit hash chain. SPIFFE IDs. Python SDK |
| **LinkAuth** | Go | Active | Device-flow UX for credential brokering. Zero-knowledge: RSA-OAEP + AES-256-GCM end-to-end encryption. No plaintext at broker |

### Platform-Level

| Org | Product | Mechanism |
|---|---|---|
| Alibaba | OpenSandbox Credential Vault (OSEP) | Sidecar MITM for sandboxed agents. Policy-aware injection. `networkPolicy.defaultAction=deny` required. Transparent mitmproxy path |

---

## Categories Summary

| Approach | Pros | Cons | Representative Tools |
|---|---|---|---|
| **MITM Proxy** | Transparent to agent, any protocol | Needs CA cert install, MITM complexity | Agent Vault, Paude Proxy, Sluice, Postern |
| **Clean Reverse Proxy** | No CA cert, clean architecture | Agent must target proxy URL | Outpost, Mintkey |
| **Local Daemon** | No separate host, low latency | Shared host with agent, weaker isolation | Hermetic, ghbrk, agent-iam |
| **Ephemeral Token** | Short-lived, per-task scoping | Requires resource server integration | AgentWrit, LinkAuth |
| **Platform-Level** | Full isolation, no agent-side config | Vendor-specific, production infra only | Vercel, Cloudflare, Anthropic, OpenSandbox |

## Key References

- Anthropic: [Scaling Managed Agents](https://www.anthropic.com/engineering/managed-agents), [Vaults docs](https://platform.claude.com/docs/en/managed-agents/vaults)
- Vercel: [Credential brokering changelog](https://vercel.com/changelog/safely-inject-credentials-in-http-headers-with-vercel-sandbox)
- Cloudflare: [Sandbox auth blog](https://blog.cloudflare.com/sandbox-auth/), [Egress policies](https://github.com/cloudflare/claude-managed-agents/blob/main/docs/applying-egress-policies.md)
- Microsoft: [EMA blog](https://blog.modelcontextprotocol.io/posts/enterprise-managed-auth/)
- Bitwarden: [Agent Access SDK](https://bitwarden.com/blog/introducing-agent-access-sdk/)
- Google: [Agent Identity overview](https://docs.cloud.google.com/iam/docs/agent-identity-overview)
- Okta: [Okta for AI Agents](https://www.okta.com/products/govern-ai-agent-identity/)
- Agent Vault: [Hermes on VPS guide](https://docs.agent-vault.dev/guides/hermes-on-vps)
- IETF: [CB4A draft](https://datatracker.ietf.org/doc/draft-ietf-wimse-arch/)
- Infisical: [Credential brokering explained](https://infisical.com/blog/credential-brokering-for-ai-agents)
