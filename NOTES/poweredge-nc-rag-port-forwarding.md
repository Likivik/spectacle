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