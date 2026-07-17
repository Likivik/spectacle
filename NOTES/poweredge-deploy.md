# poweredge — Deployment Notes

## Hardware

- Dell PowerEdge (model TBD)
- 240 GB SSD (slow SATA SSD)
- 2× 2 TB HDD (ZFS mirror for data)
- RAM: needs upgrade (recommend ≥16 GB)

## Architecture

```
SSD (ext4)     → /boot, / (OS + apps + Postgres + Redis)
HDD ×2 (ZFS)   → /tank/data/{nextcloud, immich} (mirror, lz4, atime=off)
```

All access via **Tailscale**. No public HTTP exposure for now.
- nextcloud: `http://poweredge:80`
- immich:     `http://poweredge:3001`
- collabora:  internal only (CODE container bound to localhost:9980)

## Files created in this commit

### New aspects

| Aspect | Path | Description |
|--------|------|-------------|
| `den.aspects.server.nextcloud` | `modules/aspects/server/nextcloud/default.nix` | Nextcloud + Collabora CODE + Postgres + Redis |
| `den.aspects.server.immich` | `modules/aspects/server/immich/default.nix` | Immich with CPU ML |
| `den.aspects.server.cloudflare-tunnel` | `modules/aspects/server/cloudflare-tunnel/default.nix` | (future use) Cloudflare Tunnel for public exposure |

### Host files

| File | Notes |
|------|-------|
| `modules/hosts/poweredge/poweredge.nix` | Includes `nextcloud` + `immich`. **Not** `cloudflare-tunnel`. |
| `modules/hosts/poweredge/_disko.nix` | Partitioning — replace `REPLACE_WITH_*_ID` placeholders with real `/dev/disk/by-id/` paths |
| `modules/hosts/poweredge/_hardware-configuration.nix` | Placeholder — will be overwritten by nixos-anywhere |
| `secrets/poweredge/secrets.yaml` | Encrypted secrets (see below) |

## Prerequisites before deploy

### Hardware prep
1. Install RAM (≥8 GB minimum, 16 GB recommended)
2. Connect power + network
3. Identify actual disk device IDs (run `ls -la /dev/disk/by-id/` on the NixOS ISO)

### DNS / Domain (optional — for now Tailscale is enough)
1. Buy domain (e.g. `likivik.com`)
2. Add to Cloudflare DNS (change nameservers)
3. Create Cloudflare Tunnel → get tunnel token → put in sops secrets

### Secrets setup

```bash
# After machine is booted, from the NixOS ISO:
cat /etc/ssh/ssh_host_ed25519.pub  # get the SSH public key

# On traversal (or any machine with sops):
nix-shell -p ssh-to-age --run 'ssh-to-age < ~/poweredge-ssh.pub'
# → outputs age1... key

# Add this key to secrets/.sops.yaml under keys:
#   &poweredge age1...
#
# And add a creation_rule:
#   - path_regex: poweredge/.*\.yaml$
#     key_groups:
#       - age:
#           - *recovery
#           - *traversal
#           - *poweredge

# Create the secrets file:
mkdir -p secrets/poweredge
sops secrets/poweredge/secrets.yaml
# Add:
#   nextcloud/admin-password: <your-password>
```

### Immich notes
- `services.immich` module exists in nixpkgs unstable.
- ML runs on CPU since PowerEdge has no GPU. Slow but works.
- Immich requires a JWT secret — the NixOS module generates one on first run. If it fails, set `services.immich.environment` with `IMMICH_SECRET_KEY`.

### Collabora CODE notes
- After deployment, login as admin and go to:
  `Settings → Nextcloud Office → WOPI URL`
- Set WOPI URL to: `http://localhost:9980`
- The `richdocuments` app is already installed via `extraApps`.

## Deploy

```bash
# 1. Boot PowerEdge from NixOS ISO (use minimal ISO)
# 2. Get network connectivity
ip addr  # find the IP

# 3. From traversal, deploy via nixos-anywhere:
nix run github:nix-community/nixos-anywhere -- \
  --flake .#poweredge \
  --generate-hardware-config nixos-facter ./modules/hosts/poweredge/_hardware-configuration.nix \
  root@<poweredge-ip>

# 4. After deploy, from traversal:
git add modules/hosts/poweredge/_hardware-configuration.nix
git commit -m "chore(poweredge): add hardware config"

# 5. Verify:
nix build .#nixosConfigurations.poweredge.config.system.build.toplevel --dry-run
```

## Known issues / gotchas

- **Disko ZFS**: the `_disko.nix` uses disko's ZFS support. If `disko.zfs` doesn't recognize the pool syntax, simplify to partitioning without ZFS and create the pool manually post-install.
- **Nextcloud app versions**: `pkgs.nextcloud32Packages.apps` depends on the current nixpkgs version. If 25.11 ships a different version, adjust `services.nextcloud.package` and the apps reference.
- **PowerEdge RAID controller**: If the HDDs are connected via a PERC controller in RAID mode, they'll appear as a single virtual disk (e.g., `/dev/sda`). Switch the controller to HBA mode or pass disks through to get individual disk access for ZFS.
