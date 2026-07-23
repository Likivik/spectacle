# Email Agent Security Setup — Requirements

**Created:** 2026-07-16
**Status:** Planning
**Decision:** Use AgentCloak as base

---

## Goal

Give Hermes (AI agent on Erebus) safe access to personal Gmail for email management.

## Core tasks the agent should do

1. **Read emails** — full content, not just headers
2. **Sort/categorize** — spam, important, promo, personal, action required
3. **Create tasks** from emails when needed
4. **Propose trash** for deletion
5. **Propose unsubscribes** from subscriptions
6. **Propose old/irrelevant mail** for deletion

## Security requirements

1. **PII/secrets redaction** — API keys, passwords, OTP codes, credit cards, SSNs redacted before LLM sees them
2. **Prompt injection protection** — HTML strip, unicode normalization, injection pattern detection
3. **No raw HTML** reaching the agent — converted to clean plaintext
4. **Security email blocking** — password resets, 2FA codes, verification emails blocked or flagged
5. **Financial email blocking** — bank statements, payment confirmations blocked or flagged

## Access control

1. **Read-only by default** — agent cannot send emails
2. **Draft creation only** — if agent proposes a reply, it goes as draft for human review
3. **Approval gate for destructive actions** — delete, unsubscribe require human approval
4. **Folder restrictions** — agent only sees folders you allow

## Infrastructure constraints

1. **Self-hosted on Erebus** — no SaaS, no external services
2. **Gmail connection** — Apps Script preferred (no Google Cloud project needed)
3. **MCP integration** — Hermes connects as MCP client
4. **Simple setup** — docker compose or NixOS module, minimum config
5. **NixOS compatible** — runs on existing erebus infrastructure

## Non-goals (for now)

- Sending emails autonomously
- ML-based injection detection (regex is fine)
- Attachment content reading
- Multi-user / multi-tenant
- Audit logging (nice to have, not required)
- Outlook/Microsoft 365 support

## Chosen solution: Fork rusty-imap-mcp

**Why:** Full email capabilities (24 tools) + injection defense + we add PII redaction directly in Rust. Single binary, zero wiring.

**Links:**
- Upstream: https://github.com/randomparity/rusty-imap-mcp
- License: MIT / Apache-2.0

**What it covers out of the box:**
- IMAP (Gmail, any server)
- HTML sanitization (hidden elements, CSS tricks)
- Unicode NFKC normalization + invisible char stripping
- Look-alike/homoglyph detection
- Display-name spoofing detection
- 4 security postures (readonly → destructive)
- 24 MCP tools (read, search, flag, label, move, draft, send, delete, folders)
- Append-only JSONL audit log
- Token-bucket rate limiting
- Circuit breaker
- TLS fingerprint pinning

**What we add (fork):**
- leakguard crate (PII detection, zero deps, 19+ built-in detectors)
- 3 custom Russian detectors (phone, OTP, password context)
- ~50 lines of Rust total

**Gaps we accept:**
- No ML injection detection (regex sufficient for 90%+)
- No attachment content reading
- No web dashboard
- Gmail App Password (not OAuth2 yet)

## Future improvements (if needed)

- Swap injection detection for ML-based (prompt-guard, 169 stars)
- Add privatiser for advanced PII detection
- Swap to rusty-imap-mcp for deeper structural injection defense
- Add audit logging
- Add attachment content reading

## Research notes

### Projects evaluated

| Project | Stars | Status | Covers |
|---|---|---|---|
| AgentCloak | 0 | alpha | Gmail + PII + injection + MCP |
| rusty-imap-mcp | low | experimental | IMAP + injection + MCP (no PII) |
| ClawGuard | low | prototype | Gmail + PII + injection (no MCP) |
| MailGuard-MCP | low | toy prototype | IMAP + trust system + MCP (no PII) |
| e2a | 172 | v1.0 RC | Email infrastructure + identity (no security filtering) |
| Commune | 5 | alpha | Email infra + injection (no PII) |
| AgentTeam Email | 80 | alpha | Email infra + web client |

### Key insight

No single project combines all three layers (email access + PII redaction + injection defense) in a mature, production-ready state. AgentCloak is the closest. This is a nascent field (2025-2026).

### Why not build from scratch

Three separate tools (langmail + privatiser + prompt-firewall) can do the same thing, but require custom integration, separate maintenance, and no dashboard. AgentCloak gives all three + Gmail connection + MCP + dashboard in one package.
