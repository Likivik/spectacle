# poweredge — Deployment Notes

## Hardware

- Dell PowerEdge T110 II
- Intel Xeon E31220 @ 3.10GHz (4C/4T)
- 8 GB RAM (needs upgrade — recommend ≥16 GB)
- 240 GB SSD (Crucial BX500, SATA)
- 2× 4 TB HDD (Seagate ST4000VN006 + Toshiba HDWG440, ZFS mirror)
- Matrox G200eW (embedded video)
- Broadcom BCM5722 (embedded NIC)

## Architecture

```
SSD (ext4)     → /boot, / (OS + apps + Postgres + Redis)
HDD ×2 (ZFS)   → /tank/{nextcloud, immich, backups} (mirror, lz4, atime=off)
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
| `modules/hosts/poweredge/_disko.nix` | Partitioning — uses confirmed `/dev/disk/by-id/` paths |
| `modules/hosts/poweredge/_hardware-configuration.nix` | Nix wrapper: `hardware.facter.reportPath = ./facter.json;` |
| `modules/hosts/poweredge/facter.json` | Hardware report from nixos-facter (auto-generated) |
| `secrets/poweredge/secrets.yaml` | Encrypted secrets (see below) |

## Prerequisites before deploy

### Hardware prep
1. Install RAM (≥8 GB minimum, 16 GB recommended)
2. Connect power + network
3. Boot from NixOS minimal ISO (USB)

### Secrets setup

```bash
# After machine is booted from NixOS ISO:
cat /etc/ssh/ssh_host_ed25519_key.pub  # get the SSH public key

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

### Automated (recommended)

```bash
# Interactive — shows every command, explains it, asks for approval:
./scripts/deploy-poweredge.sh

# Skip LAN scan if you already know the IP:
./scripts/deploy-poweredge.sh --ip 192.168.0.20

# Non-interactive (auto-approve all steps):
./scripts/deploy-poweredge.sh --yes
```

The script walks through 9 steps interactively:
1. Preflight checks (tools, git state)
2. LAN discovery (nmap scan + NixOS detection)
3. SSH host key extraction → age key conversion
4. Disk ID discovery (lsblk + by-id mapping)
5. `_disko.nix` update with real disk paths
6. `.sops.yaml` update with poweredge age key
7. Secrets creation (nextcloud password + tailscale auth key)
8. `nixos-anywhere` deployment (partition + install + reboot)
9. Post-deploy verification (SSH, tailscale, nextcloud, sops, swap)

Each step shows the command, explains what it does, and waits for [Y/n].

### Manual

```bash
# 1. Boot PowerEdge from NixOS ISO (use minimal ISO)
# 2. Get network connectivity
ip addr  # find the IP

# 3. From serenity (or any flake host), deploy via nixos-anywhere:
nix run github:nix-community/nixos-anywhere -- \
  --flake .#poweredge \
  --generate-hardware-config nixos-facter ./modules/hosts/poweredge/facter.json \
  --copy-host-keys \
  --target-host root@<poweredge-ip>

# 4. After deploy, commit generated files:
git add modules/hosts/poweredge/facter.json
git commit -m "feat(poweredge): add facter.json and hardware config"

# 5. Verify:
nix build .#nixosConfigurations.poweredge.config.system.build.toplevel --dry-run
```

## Disk layout (confirmed via nixos-facter)

| Slot | by-id path | Model | Size | Role |
|------|-----------|-------|------|------|
| SATA-1 | `ata-CT240BX500SSD1_2023E401B128` | Crucial BX500 | 240 GB | OS (ext4) |
| SATA-3 | `ata-ST4000VN006-3CW104_WW60T7FC` | Seagate IronWolf | 4 TB | ZFS mirror |
| SATA-4 | `ata-TOSHIBA_HDWG440_4230A03FFZ0G` | Toshiba MG07 | 4 TB | ZFS mirror |
| USB | `usb-JetFlash_Transcend_128GB_...` | Ventoy | 128 GB | Install media (ignore) |

## Known issues / gotchas

- **Disko ZFS**: the `_disko.nix` uses disko's ZFS support. If `disko.zfs` doesn't recognize the pool syntax, simplify to partitioning without ZFS and create the pool manually post-install.
- **Nextcloud app versions**: `pkgs.nextcloud32Packages.apps` depends on the current nixpkgs version. If 25.11 ships a different version, adjust `services.nextcloud.package` and the apps reference.
- **PowerEdge RAID controller**: If the HDDs are connected via a PERC controller in RAID mode, they'll appear as a single virtual disk (e.g., `/dev/sda`). Switch the controller to HBA mode or pass disks through to get individual disk access for ZFS.
- **by-id vs by-path**: `/dev/disk/by-id/` was empty on the NixOS ISO but nixos-facter found the paths via sysfs. If by-id disappears again after reboot, fall back to by-path in `_disko.nix`.
