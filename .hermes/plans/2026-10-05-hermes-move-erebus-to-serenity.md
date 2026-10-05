# Hermes → Serenity: moving the agent (2026-10-05)

Status: **Stage A committed** (`dev` = `05ea73e1`), dry-build gate running.
Stages B (cutover) and C (erebus cleanup) not started. erebus keeps serving
Telegram throughout Stage A by design.

## Goal

Run the Hermes agent on serenity (6 cores / 15G) instead of erebus (4 cores /
7G, storage-tight), without a service gap and without losing the agent's state.

## Scope (decided with the user)

**Moves** (the agent and everything it is wired to at `localhost`):
- the agent itself: gateway user units (`hermes-gateway`, `hermes-gateway-salem`,
  multiplexed profiles incl. `hiring`), dashboard (`:9119`)
- `hermes-webui` (`:8787`) — kept
- graphiti MCP (`:8000`) + FalkorDB (`:6379`) — our memory system
- LiteLLM (`:4000`) + llama-server (`:8081`) — ride along inside the aspect
- browser CDP / chromium (`:9222`)
- email MCP — himalaya + its TS wrapper run *on the agent host*, so it moves
  (it is not a separate service)

**Stays on erebus**: hr-bot (separate bot), and every remote dependency we
merely *point at* — nextcloud + trilium MCPs live on poweredge, Langfuse in the
cloud. No config change needed for those.

**Dropped**: `searxng` (verified unused — `web.search_backend: exa`; the
localhost:8888 section was an unused fallback), `sillytavern`, `beszel`,
`fishaudio-proxy`.

## The method (researched, not invented)

The documented way to move an install is `hermes backup` → transfer →
`hermes import`:
- `hermes backup` zips config, skills, sessions and data **while the agent runs**
  (`--quick` = critical state only). It excludes the codebase.
- `hermes import --force` restores it.
- `hermes profile export` is *not* a substitute: it deliberately strips
  credentials.

NixOS side: the `hermes-agent` aspect is host-agnostic; the only host-specific
pieces were the secrets file path (fixed) and the Langfuse project name (kept —
it is the same agent, just moved).

## Stage A — setup on serenity (done)

1. `hermes backup -o /tmp/hermes-backup-20261005.zip` on erebus (live, 2.05G,
   14,371 entries, integrity OK; `state.db` alone is 3.4G uncompressed, and both
   profiles `salem` + `hiring` are inside).
2. Parameterized `hermes-webui` (`sops.defaultSopsFile` instead of a hardcoded
   erebus path — the aspect was unusable on a second host).
3. Removed searxng from the shared aspect; added the agent + webui + email
   aspects to `serenity.nix` with the host's own secret declarations.
4. Secrets: re-sealed the agent's keys into **`secrets/serenity/hermes-secrets.yaml`**,
   encrypted to serenity's three recipients (two X25519 + `age1tpm1…`). Built on
   erebus from values already encrypted there — encryption needs only the public
   recipients. **Verified by a TPM round-trip on serenity** (exit 0, 4 branches).
5. Deploy serenity from erebus (its own checkout is unusable — orphaned commit +
   broken GitHub auth). This activates `dev`, which includes the OCR/Surya/Monkey
   decommission (~21G + RAM back) and makes the `/Storage/Git` SSD bind permanent.
6. **Cutover guard**: both gateway units are installed but NOT started
   (`wantedBy = mkForce []`). Two pollers on one Telegram token silently split
   updates, so the flip is an explicit step.

## Finding: `hermes backup` is lossy (measured, not assumed)

The zip skips anything it cannot store and only *warns* (1,394 warnings). Measured
against the live home:

| dir | on disk | in archive |
|---|---|---|
| skills/ | 657 files, 108 SKILL.md | 235 files, **55 SKILL.md** |
| plugins/ | 314 | 277 |
| profiles/ | 4,106 | 139 |
| mcp-servers/ | 13,018 | 132 |

Cause: 393 files have pre-1980 mtimes ("ZIP does not support timestamps before
1980"), plus deliberate exclusions (cache, lazy-packages). Losing history in
`state.db` is acceptable; losing skills/profiles/config is not — those are
procedure. Hence `bin/hermes-cutover-to-serenity` imports the zip **and** rsyncs
the meta dirs on top, then compares counts on both sides to prove the gaps closed.
Verify an import by counting, never by exit code.

## Stage B — cutover (~3 min, manual)

Script: `bin/hermes-cutover-to-serenity` (runs the strict order: final delta
backup → import on serenity → stop erebus's pollers → start serenity's →
verify). Must be run from a shell that is not the gateway's own session.

Then talk to the bot to verify, and make it declarative:
- `serenity.nix`: drop the two `wantedBy = mkForce [ ]` overrides
- `erebus.nix`: add them, so a reboot cannot resurrect the old poller

Rollback: stop serenity's units, start erebus's. Since we keep erebus's install
intact (stopped, tokens still present), this is seconds. Accept some state
divergence for messages processed on the other side — "some loss of history is
ok" was the agreed trade.

## Stage C — erebus cleanup

- drop `sillytavern`, `beszel`, `fishaudio-proxy` includes (searxng already
  gone) and reclaim their data
- keep the agent install present but declaratively stopped
- optionally retire `docs/serenity-dev-environment.md`'s edit-on-erebus /
  build-on-serenity split: once the agent lives on serenity, that split is what
  the move was meant to remove

## Open items

- The agent on serenity has no SSH key authorized on the other hosts yet
  (`hermes@erebus`'s key is what the fleet currently trusts). Needed before it
  can deploy the fleet from there.
- `hermes/webui-password` + dashboard exposure: webui reaches the tailnet via
  `tailscale serve 8444` (node-local, not in nix). Dashboard has no equivalent
  yet.
- Langfuse project is still named `hermes-erebus` (cosmetic).
- Plan doc itself is untracked, like the other sessions' plans.
