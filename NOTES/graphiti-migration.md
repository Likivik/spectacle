# Graphiti + FalkorDB Migration Plan

**Status:** Plan, not yet executed
**Blocker:** Deploy VPS first (separate session)
**Goal:** Replace mnemosyne with Graphiti (bi-temporal knowledge graph) backed by FalkorDB on the VPS, shared by hermes, omp, and opencode.

---

## Why Graphiti

The user's specific use case for hermes personal-life memory:
- Long-term insights into the past (decisions, preferences, mistakes, financial outcomes)
- Complicated relationships between ideas, decisions, projects, friendships, priorities
- Bi-temporal recall (what was true at time T)
- Auto-invalidation when facts change
- Cross-tool sharing (hermes + omp + opencode)

Mnemosyne is insufficient: no graph relationships, no bi-temporal, no auto-invalidation. Cross-tool sharing was the original motivation and is currently NOT working despite all three tools having mnemosyne MCP.

Graphiti is the best fit. See `NOTES/memory-comparison.md` for the full comparison.

## Why FalkorDB (not Neo4j)

- VPS: 4 cores, 8GB RAM. FalkorDB fits comfortably (~100MB). Neo4j needs 500MB-2GB minimum.
- Single binary, no JVM, simpler backup
- Graphiti supports both as first-class
- For single-user <10M nodes, performance is equivalent

## Cost estimate (real usage: 300K tokens/day, 39 sessions/14d)

| Component | Cost/month |
|---|---|
| FalkorDB (self-hosted) | $0 |
| Graphiti (self-hosted) | $0 |
| LLM API for Graphiti (DeepSeek V4 Flash, ~$0.14/M) | $0.10–2 |
| **Total** | **$0.10–2** |

LLM choice is deferred to deployment. DeepSeek V4 Flash is the default (cheapest).

---

## Phase 1: FalkorDB on VPS

### Files to modify

- `modules/hosts/vps/default.nix` (or wherever VPS services are defined)

### Nix config

```nix
services.falkordb = {
  enable = true;
  bind = "127.0.0.1";  # localhost only; no public exposure
  port = 6379;          # default
  # data dir defaults to /var/lib/falkordb — verify persistent
};
```

### Firewall

- 6379 must NOT be in `networking.firewall.allowedTCPPorts` (bind=127.0.0.1 already blocks it, but double-check)
- No external access; only the VPS-local Graphiti service connects

### Backup

- Add daily snapshot to `/var/backup/falkordb` via `services.falkordb.backup` or systemd timer
- Or use `services.postgresqlBackup`-style wrapper for redis (FalkorDB is Redis-compatible)
- Keep 7 daily + 4 weekly snapshots

### Validation

```bash
# Deploy: nh os switch .#vps
redis-cli -h 127.0.0.1 -p 6379 ping  # → PONG
```

---

## Phase 2: Graphiti service on VPS

### Approach: Graphiti MCP server in a Python venv, run as systemd user service

### Files to create

- `modules/hosts/vps/graphiti.nix` — Nix-managed service definition
- `modules/users/likivik/dotfiles/graphiti/` — config (if any user-level)

### Service shape

```nix
systemd.services.graphiti-mcp = {
  description = "Graphiti MCP server (bi-temporal memory)";
  wantedBy = [ "multi-user.target" ];
  after = [ "network.target" "falkordb.service" ];

  serviceConfig = {
    ExecStart = "${pkgs.python311}/bin/python -m graphiti_mcp_server";
    Restart = "on-failure";
    RestartSec = "5s";
    User = "likivik";
    EnvironmentFile = "/run/secrets/graphiti.env";  # SOPS-managed
  };
};
```

### Environment variables (SOPS-encrypted at `/run/secrets/graphiti.env`)

```
# LLM provider
OPENAI_API_KEY=<opencode-go API key>
OPENAI_BASE_URL=https://api.opencode-go.com/v1
GRAPHITI_LLM_MODEL=opencode-go/deepseek-v4-flash
GRAPHITI_EMBEDDER_MODEL=opencode-go/deepseek-v4-flash

# Database
FALKORDB_HOST=127.0.0.1
FALKORDB_PORT=6379
FALKORDB_DATABASE=graphiti

# Misc
GRAPHITI_LOG_LEVEL=INFO
```

### Validation

```bash
systemctl --user status graphiti-mcp
# → active (running)
```

Test MCP manually:
```bash
echo '{"jsonrpc":"2.0","method":"initialize","params":{...},"id":1}' | nc -U /run/user/$(id -u)/graphiti-mcp.sock
```

---

## Phase 3: Migration script (mnemosyne → Graphiti)

### One-shot Python script: `modules/users/likivik/bin/migrate-mnemosyne-to-graphiti.py`

### What it does

1. Opens `~/.hermes/mnemosyne/data/mnemosyne.db` read-only
2. Reads all 2,579 memories
3. Categorizes: working, episodic, canonical
4. Connects to Graphiti at `http://127.0.0.1:8000` (or MCP socket)
5. For each memory, calls `add_episode`:
   ```python
   await client.add_episode(
       name=f"mnemosyne-{memory.id}",
       episode_body=memory.content,
       source_description="Migrated from mnemosyne SQLite (2026-07-XX)",
       reference_time=memory.created_at,
       group_id="migration-2026-07"
   )
   ```
6. Verifies count
7. Runs sample search to validate

### Idempotency

- Track migrated IDs in `~/.local/state/mnemosyne-migration.json`
- Skip already-migrated IDs on re-run
- Safe to re-run after partial failure

### Safety

- Source mnemosyne.db is opened read-only
- Source db is NOT deleted
- Old DB kept for 1 month post-migration as fallback
- After 1 month: archive to `~/archive/mnemosyne-2026-07.db`

### Run command

```bash
python3 migrate-mnemosyne-to-graphiti.py --dry-run  # preview
python3 migrate-mnemosyne-to-graphiti.py            # execute
```

---

## Phase 4: Tool wiring (cross-tool sharing)

### Goal: all three tools (hermes, omp, opencode) use Graphiti MCP

### 4a. shared-mcp.jsonc update

Add Graphiti MCP server to `modules/users/likivik/shared-mcp.jsonc`:

```jsonc
"graphiti": {
  "command": "nix",
  "args": [
    "shell",
    "nixpkgs#python311",
    "nixpkgs#python311Packages.pip",
    "-c",
    "pip",
    "run",
    "--target",
    "/run/user/1000/graphiti-venv",
    "graphiti-mcp-server",
    "--transport",
    "stdio"
  ],
  "env": {
    "OPENAI_API_KEY": "<from opencode-go>",
    "OPENAI_BASE_URL": "https://api.opencode-go.com/v1",
    "GRAPHITI_LLM_MODEL": "opencode-go/deepseek-v4-flash",
    "FALKORDB_HOST": "127.0.0.1",
    "FALKORDB_PORT": "6379"
  }
}
```

(Implementation may vary; the key is that all three tools reference the same canonical definition.)

### 4b. opencode.jsonc

After updating `shared-mcp.jsonc` to be the source of truth, remove the inline `mcp` section from `opencode.jsonc` and reference shared-mcp.jsonc instead. (This was already a TODO item.)

### 4c. omp/agent/mcp.json

Replace the contents with a symlink to `shared-mcp.jsonc`, or copy the new Graphiti entry.

### 4d. hermes

Update hermes config to use the Graphiti MCP server URL (hermes has its own config system, not in this repo's Nix setup). This is a manual step the user does on the VPS after deploy.

---

## Phase 5: Validation

### Smoke tests (run on VPS after deploy)

```bash
# FalkorDB
redis-cli -h 127.0.0.1 -p 6379 ping

# Graphiti
systemctl --user status graphiti-mcp
curl -X POST http://127.0.0.1:8000/mcp -d '{...test query...}'

# From omp (on laptop, after VPS is reachable)
omp> "remember what mnemosyne was"
# → should query Graphiti via MCP, return migration history

# From opencode
# Same test
```

### Cost monitoring

- Add a simple daily counter: log Graphiti LLM token usage to a file
- Use tokenscope (already installed) to track overall
- Set a hard cap in the opencode-go dashboard: $5/mo

### Performance check

- Test 100 search queries, measure p50/p99 latency
- Target: p99 < 1s

---

## Phase 6: Documentation

### Files to create/update

1. `NOTES/graphiti-migration.md` (this file)
2. `NOTES/graphiti-operations.md` — backup/restore, model swap, debugging
3. Update `NOTES/TODO.md`:
   - Mark OMP/MCP consolidation as DONE
   - Add Graphiti migration as DONE
4. Update `NOTES/memory-comparison.md` — note Graphiti chosen, link to migration plan
5. Update `modules/users/likivik/dotfiles/omp/agent/AGENTS.md` — reference Graphiti backend

---

## Risks and mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| FalkorDB OOM on VPS (8GB) | Low | FalkorDB is light (~100MB), plenty of headroom |
| Graphiti Python service crashes | Medium | systemd restart=on-failure, log to journal |
| LLM API rate limits | Low | DeepSeek has high limits, Graphiti caches results internally |
| Migration data loss | Medium | Keep mnemosyne.db read-only for 1 month, then archive |
| LLM cost spike | Low | $5/mo hard cap, monitor via tokenscope |
| FalkorDB data loss | Medium | Daily snapshot to `/var/backup/falkordb` |
| Cross-tool MCP not actually shared | Medium | Phase 4 explicitly tests from all three tools |

---

## Phased execution order

```
Phase 1 (FalkorDB) ──► Phase 2 (Graphiti service) ──► Phase 3 (Migration) ──► Phase 4 (Wiring) ──► Phase 5 (Validation) ──► Phase 6 (Docs)
       ~30 min               ~1 hour                       ~30 min                  ~1 hour              ~30 min              ~30 min
```

Total: ~4 hours of work, spread across multiple sessions.

---

## Open questions (to resolve at execution time)

1. **LLM choice** — Default to DeepSeek V4 Flash. Switch if quality is insufficient.
2. **Embedder model** — Same as LLM? Or use a cheaper embedder-only model? Start with same.
3. **Graphiti version** — Pin to latest stable. Check `pypi.org/project/graphiti-core` at execution time.
4. **Hermes wiring** — Hermes is outside this repo; user does this manually on VPS.
5. **Should mnemosyne coexist long-term?** — Initial plan: 1 month, then archive. Reconsider if usage shows both are needed.

---

## References

- `NOTES/memory-comparison.md` — full system comparison
- `NOTES/hermes-vps.md` — hermes deployment on VPS
- `modules/users/likivik/shared-mcp.jsonc` — canonical MCP definitions (will be updated)
- Graphiti docs: https://github.com/getzep/graphiti
- FalkorDB docs: https://github.com/FalkorDB/FalkorDB
