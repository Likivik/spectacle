# CB4A + Credential Broker Tools (2026-07)

## CB4A (IETF Internet-Draft)

- **Spec**: `draft-hartman-credential-broker-4-agents-00` (March 2026)
- **Author**: Kenneth G. Hartman (SANS Institute)
- **Status**: Individual draft, expires 30 September 2026
- **Goal**: Standardize credential vaulting/brokering for AI agents. Agents never hold real creds.
- **Core components**:
  - **PDP** (Policy Decision Point) — stateless, decides if agent gets access. Zero credential access.
  - **CDP** (Credential Delivery Point) — mints tokens, vault access. Zero policy authority.
  - **SPIFFE/SPIRE** — workload identity (X.509 SVID or JWT)
  - **DPoP** (RFC 9449) — sender-constrained tokens binding each token to an ephemeral key
- **Three proxy models**:
  - **Model A** (Proxy Gateway) — broker intercepts API calls, injects credentials transparently. Our approach.
  - **Model B** (Short-Lived Token Minting) — broker mints temporary tokens, agent uses directly. Preferred when upstream supports it.
  - **Model C** (Credential Wrapping) — credentials encrypted to target service, opaque to agent. Last resort.
- **Strategy**: Model B primary, Model A selectively for DPoP enforcement, Model C discouraged.
- **Key mitigations**: DPoP for token theft/replay, ultra-short TTLs, credential zeroing, fail-closed.

## Tools implementing CB4A pattern (partial)

| Tool | Language | License | Stars | Maturity | Model | Key features |
|---|---|---|---|---|---|---|
| **Agent Vault** (Infisical) | Go | MIT | 1632 | v0.32.0, 42 releases, 20 contributors | A (MITM proxy) + vault | Web UI, agent tokens, PostgreSQL/SQLite, container isolation, Infisical integration |
| **Postern** | Go | Apache 2.0 | 8 | v0.6.0, early | A (MITM proxy) | 1Password/Bitwarden integration, YAML config, single binary |
| **Authsome** | Python | MIT | — | v0.7.2 alpha | A (MITM proxy) + PoP JWTs | 45 providers, OAuth flows, Ed25519 PoP, did:key DIDs, auto refresh |
| **Ephyr** | Go | ? | — | beta | A/B + DPoP + macaroon | HMAC-chained macaroons, SSH/HTTP/MCP proxy, epoch watermark, audit |
| **AgentWrit** | Go | PolyForm | — | v1.0.0, daily use | B (short-lived JWTs) | SPIFFE IDs, Ed25519 challenge-response, 4-level revoc, hash-chain audit |
| **nono** | Rust | Apache 2.0 | — | In llm-agents.nix | A (phantom token) + sandbox | Kernel sandbox, L7 filtering, tool sub-sandboxing, zeroized memory |
| **proveyouragent** | Python | ? | — | v0.2.0 | Identity + DPoP | Ed25519 keypairs, DPoP request signing, delegation chains |
| **Agent Cordon** | Rust | GPLv3 | 7 | early | A/B (proxy + vault) | Cedar policy engine, AES-256-GCM vault, MCP gateway |
| **agent-iam** | TypeScript | ? | — | alpha | Token broker | Capability tokens, hierarchical delegation, persistent identity |
| **agent-creds** | (Docker) | ? | — | early | A (Envoy proxy) | Macaroons + Envoy proxy, Docker-based |
| **CapSeal** | Rust | ? | — | academic | Capability-based | MCP adapter, academic paper, not production |
| **Mintkey** | Go (multi) | ? | — | pre-alpha | A (Kong proxy) | Postgres/Docker Compose, SSH bastion, MCP, audit hash chain |
| **hasp** | Go | FCL→Apache | — | — | Env injection + MCP | Hermes profile, HMAC-audit, MCP tools |
| **ghbrk** | Rust | MIT | — | — | CLI prefix | git/gh only, root-owned policy file, minimal |
| **AgentVault** (agentvault.inflectiv.ai) | Python | MIT | — | early | Vault + MCP | AVP protocol spec, encrypted memory, MCP integration |

## Organizational stances

| Org | Position | Details |
|---|---|---|
| **Anthropic** | Managed Agents Vaults | "Harness never sees credentials" — placeholder substitution in proxy |
| **Vercel** | Sandbox firewall-level injection | Credentials injected at sandbox egress boundary |
| **Cloudflare** | Outbound Workers | Workers connect to services, never expose tokens to untrusted code |
| **Google DeepMind** | "Intelligent AI Delegation" (arXiv:2602.11865) | Delegation Capability Token (DCT) architecture |
| **Microsoft** | MCP Enterprise-Managed Authorization | OAuth 2.1 + DPoP recommended for MCP |
| **Bitwarden** | Agent Access SDK | SDK for agent credential brokering |
| **Okta/Auth0** | Auth0 for AI Agents | Identity layer for agents |
| **Uber** | SPIRE/SPIFFE internal | Workload identity for production agents |
| **Akamai** | KYA (Know Your Agent) | Agent identity verification framework |
| **IETF/WIMSE** | Workload identity standards | AI agent authentication drafts |
| **OpenID AuthZEN** | Authorization for agents | PDP/PEP patterns |
| **OWASP** | AI Agent security guidance | Credential brokering recommended |
| **Gartner** | Agent credential management | Emerging market, predicted consolidation |

## Consensus pattern

1. Separate credential store from agent runtime
2. Inject at egress boundary (proxy or firewall)
3. Agent never sees credential bytes
4. DPoP for sender-constrained tokens (CB4A requirement)
5. PDP/CDP separation (policy vs credential delivery)
6. Ultra-short TTLs with automatic revocation
7. Audit trail for all credential access

## For erebus specifically

Our architecture: two-user process isolation, mitmproxy addon for credential injection, sops-nix for encrypted provisioning. This implements CB4A Model A (proxy gateway) at the simplest viable level.

Missing vs full CB4A:
- No DPoP (agent keypair + proof signing)
- No PDP (static env-based, not policy-driven)
- No short-lived token minting (Model B)
- No audit trail
- Credentials stay in memory indefinitely

Current state: hermes-credproxy service needs mitmdump flag fix deployed (`--no-web` doesn't exist in mitmdump).
