# Poweredge port-forwarding + nc-rag deploy — lessons learned

**Session:** 2026-08-04 → 2026-08-05 (after compacted handoff).

## The bug

Podman 5.8 / netavark / NixOS 26.11 / kernel 6.18.38: **host→container port
forwarding silently drops packets after DNAT**. FORWARD chain stays 0.
Tcpdump shows SYN out, no SYN/ACK. `connection refused` instantly.

- Inside container: works (nsenter → curl 127.0.0.1 = 200).
- Tailscale had stale `10.88.0.0/16 dev tailscale0` in table 52 — hijacks
  podman0 route. Fix: `ip rule add to 10.88.0.0/16 lookup main priority 100`
  via systemd oneshot. (Not the final fix; route was correct after but
  packets still dropped.)
- Reboot didn't help. Firewall off didn't help. `route_localnet=1` didn't
  help. Quadlets didn't help (same netavark/bridge under the hood).
- Same broken pattern: erebus kokoro-tts works (port 8880), erebus
  falkordb breaks (port 6379) — rootful podman 5.8 on NixOS 26.11.

## The fix

**`--network=host`** (quadlet-nix: `networks = [ "host" ]`). Container
shares host netns → listens on host lo directly, no netavark/bridge/DNAT.
Side effects: no port isolation (insecure per podman docs, fine for
internal RAG services), no per-container IP, conmon socket on host.

## nc-rag stack (poweredge)

Quadlets + host network. Deployed as commit a772725 on dev. qdrant HTTP
200 + nc-mcp HTTP 200 (`mode: basic`).

- `qdrant` (m.daocloud.io mirror of qdrant/qdrant:v1.18.2)
- `nextcloud-mcp` (ghcr.io/pi0n00r/nextcloud-mcp-server:v1.5.1.1)
- Env vars per upstream: `NEXTCLOUD_HOST` (not `_URL`),
  `NEXTCLOUD_USERNAME`, `NEXTCLOUD_PASSWORD` (app password, not user pw),
  `MCP_DEPLOYMENT_MODE=single_user_basic`.
- Tailscale magic DNS host works because trusted_domains includes it.
- Sops secret `nextcloud/mcp-app-password` already exists.
- Semantic search (QDRANT_URL/OLLAMA_URL/RERANKER_URL) disabled for now —
  can re-enable later via VECTOR_SYNC_ENABLED once basic mode proven.

## Quadlet-nix gotchas

- API field is `networks = [ "host" ]` (list of str), not `networkOptions`
  or `network`.
- Module must be imported in host context, NOT in den-aspect — aspects
  don't see host imports, and quadlet-nix needs `assertions` option.
- `nixosModules.quadlet`, not `.default`.
- After deploy, quadlet services don't auto-start as `podman-X.service` —
  they're named after the quadlet (e.g. `qdrant.service`). Start with
  `systemctl start qdrant.service`.
- `daemon-reload` needed to pick up new `.container` files.

## Path through debug hell (DON'T repeat)

1. Rootless pasta/slirp4netns — broken in different ways, won't fix.
2. Rootful + bridge — what we tried last (still broken).
3. Rootful + `--network=host` — **actually works**.

Skip 1 and 2 next time. Default to `--network=host` for any internal
service on this NixOS version unless port isolation matters.

## Files

- `modules/hosts/poweredge/poweredge.nix` — quadlet config + route fix
- `modules/aspects/server/nc-rag/nc-rag.nix` — serenity-side llama.cpp
  (no poweredge quadlets, those live in the host module)
- `modules/defaults/inputs.nix` — added `quadlet-nix` input
- Daocloud mirror dodges Docker Hub rate limit; keep using for qdrant.

## Semantic search — Ollama-compat proxy on serenity (commits 9149e0b, d60c57c)

**Problem:** nc-mcp is hardcoded to the Ollama client API (POST /api/embed,
GET /api/tags). llama.cpp b9999+ (PR #13659) had Ollama-compat, but it
was reverted in **PR #22165 (April 2026)** — see ggerganov comment "no
benefits in implementing the ollama API, VS Code will soon do the right
thing." Our b10133 binary doesn't have `/api/tags`.

**Why not Ollama container?** CVE-2026-7482 (CVSS 9.1, heap OOB read via
malicious GGUF) — ~300k exposed servers, unpatched. Go server overhead
~5-10%, +100MB RAM vs raw llama.cpp.

**Solution:** tiny Python FastAPI proxy in front of llama.cpp.
[`deposist/llama.cpp-Control-Deck/ollama_proxy.py`](https://github.com/deposist/llama.cpp-Control-Deck)
— 350 lines, translates `/api/{tags,embed,chat,generate}` to llama.cpp's
OpenAI endpoints. Pinned to commit `87f531e5f7b868cbcd87a65ab54333f51d21dbdc`.

### Deploy shape

```
serenity:11434 (ollama_proxy.py) → serenity:8081 (llama-server bge-m3)
                                     ↑
                                     OpenAI-compat /v1/embeddings
```

- `llama-ollama-proxy.service` — `python ${ollamaProxy}/bin/ollama_proxy.py
  --host 0.0.0.0 --port 11434 --target-base-url http://127.0.0.1:8081/v1
  --model bge-m3`
- `DynamicUser = true`, `Restart = on-failure`, `RestartSec = 5`.
- Built via `pkgs.stdenvNoCC.mkDerivation` over `pkgs.fetchurl` (pinned
  sha256, no need to fetch whole repo).
- `python3.withPackages [ fastapi uvicorn httpx ]`.

### Critical gotchas (each one cost a debug cycle)

1. **Proxy MUST bind `0.0.0.0`, not `127.0.0.1`.** nc-mcp in container
   on poweredge resolves `serenity` via Tailscale DNS → Tailscale IP
   (100.x.x.x) → on serenity, traffic to 127.0.0.1 arrives on the
   Tailscale iface, NOT loopback. Firewall allows 11434 on
   `tailscale0` — but loopback binding never sees Tailscale traffic.
   *Symptom: nc-mcp hangs at "Qdrant collection init attempt N/30 failed
   (ConnectError)" but `curl http://127.0.0.1:11434/api/tags` from
   serenity itself returns 200.*

2. **Firewall on tailscale0 must allow 11434.** serenity already has
   `interfaces.tailscale0.allowedTCPPorts = [ 11434 ]` in
   `modules/aspects/server/nc-rag/nc-rag.nix`. (Same for any future
   Ollama-style service exposed cross-host via Tailscale.)

3. **nc-mcp env vars are NOT in any nc-mcp README.** Found them in
   `env.sample` + `docs/semantic-search-architecture.md` of
   `pi0n00r/nextcloud-mcp-server`. Correct names:
   - `ENABLE_SEMANTIC_SEARCH=true` (not `VECTOR_SYNC_ENABLED` — that
     one is **deprecated**, still works, removed in v1.0.0)
   - `QDRANT_URL=http://127.0.0.1:6333` (qdrant is on poweredge via
     `--network=host`, no separate container)
   - `OLLAMA_BASE_URL=http://serenity:11434` (proxy port, not 8081)
   - `OLLAMA_EMBEDDING_MODEL=bge-m3` (matches `--model` arg to proxy)
   - `SEARCH_MODE=hybrid` (default; dense + BM25 sparse)
   - **No `RERANKER_URL`** — nc-mcp doesn't support reranker; it uses
     Ollama for embeddings only, Qdrant for vector + sparse.

4. **Proxy `--model bge-m3`** — name reported in `/api/tags` must
   match `OLLAMA_EMBEDDING_MODEL` in nc-mcp env. Otherwise nc-mcp
   requests embeddings for "bge-m3" but proxy returns "local-llama"
   mismatch.

### Verification commands

```bash
# On serenity
systemctl status llama-ollama-proxy llama-embedder
curl -s http://127.0.0.1:11434/api/tags | jq .

# From poweredge (cross-host via Tailscale)
curl -s http://serenity:11434/api/tags | jq .
# { "models": [ { "name": "bge-m3", ... } ] }

# From inside nc-mcp container
sudo podman exec nextcloud-mcp curl -s http://serenity:11434/api/tags

# nc-mcp health
curl -s http://127.0.0.1:8000/health/ready | jq .
# { "status": "ready", "checks": { "qdrant": "ok", ... } }

# Qdrant collection indexes (created on first boot)
sudo journalctl -u nextcloud-mcp --since '15:55' | grep "Qdrant collection ready"
```

### Future: when to revisit Ollama-direct

- llama.cpp adds Ollama-compat again (search PR #13659 resurrection
  discussions; ggerganov quoted as skeptical)
- Ollama CVE-2026-7482 is patched + new release
- Need reranking (would require Ollama — it bundles embeddings +
  reranker in same model API)...[truncated]