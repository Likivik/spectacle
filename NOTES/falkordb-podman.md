# FalkorDB + rootless podman on NixOS

## Issues

### 1. Docker Hub rate limit
Anonymous pull limit (100/6hr per IP) exhausted from podman service restarts.

**Fix:** Pull image on traversal (different IP), `podman save`, scp to erebus, `podman load`.

### 2. GID 42 extraction in rootless podman
Known upstream bug (containers/podman#25798, #12715, #9967, container-libs#700). Images with `/etc/shadow` or `/etc/gshadow` owned by `root:shadow` (GID 42) fail layer extraction in rootless mode — even with correct subuid/subgid.

Error: `"potentially insufficient UIDs or GIDs available in user namespace (requested 0:42 for /etc/shadow)"`

**Fix:** `loginctl enable-linger hermes` then `podman system migrate` (one-time per user). Migrate reinitializes user namespace storage so newuidmap/newgidmap work.

### 3. FalkorDB image was wrong
Plan used `falkordb/falkordb:latest` (429 MB, includes browser UI on :3000). Server-only variant `falkordb/falkordb-server:edge-alpine` (161 MB) is lighter and sufficient.

## Current state
- Image saved at `~/data/containers/falkordb-server.tar` (traversal) and `/var/lib/hermes/falkordb-server.tar` (erebus)
- Nix service uses `falkordb/falkordb-server:edge-alpine`
- Activation script runs `podman system migrate` on each deploy
- FalkorDB starts on `127.0.0.1:6379`
