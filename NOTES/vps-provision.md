# VPS Provisioning

## 1. Manual steps

### Prerequisites
- VPS with root SSH access (Ubuntu/Debian/etc)
- Repo at `/Storage/Git/spectacle`, flake passes `nix flake check --no-build --keep-going`
- Your SSH pubkey ready (`~/.ssh/id*.pub`)

### Generate keys locally

```bash
WORKDIR=~/.cache/vps-provision/rootfs
mkdir -p $WORKDIR/etc/ssh
mkdir -p $WORKDIR/var/lib/sops
mkdir -p $WORKDIR/home/likivik/.ssh

# SSH host key (VPS identity)
ssh-keygen -t ed25519 -f ~/.cache/vps-provision/ssh_host_ed25519 -N "" -C "root@vps"

# Derive age key from SSH key (same Ed25519 curve)
umask 077
nix shell github:numtide/ssh-to-age# -c sh -c '
  ssh-to-age -private-key -i ~/.cache/vps-provision/ssh_host_ed25519 \
    > ~/.cache/vps-provision/sops-age-key.txt
'

# Print pubkeys — paste age pubkey into .sops.yaml below
echo "=== Age pubkey (add to .sops.yaml) ==="
cat ~/.cache/vps-provision/sops-age-key.txt | grep "public key"
echo "=== SSH pubkey (for known_hosts) ==="
cat ~/.cache/vps-provision/ssh_host_ed25519.pub
```

### Stage extra files (injected into VPS's root on first boot)

```bash
cp ~/.cache/vps-provision/ssh_host_ed25519    $WORKDIR/etc/ssh/
cp ~/.cache/vps-provision/ssh_host_ed25519.pub $WORKDIR/etc/ssh/
cp ~/.cache/vps-provision/sops-age-key.txt     $WORKDIR/var/lib/sops/age-key.txt
cp ~/.ssh/id_rsa.pub                           $WORKDIR/home/likivik/.ssh/authorized_keys
```

### Edit `.sops.yaml` (`secrets/.sops.yaml`)

- Change `&vps ""` → `&vps age1...` (from grep output above)
- Uncomment `# - *vps` in the `vps/.*\.yaml$` creation rule
- Commit this before running nixos-anywhere (or the sops decryption will fail)

### Re-encrypt secrets

```bash
sops updatekeys -y secrets/vps/secrets.yaml
sudo sops secrets/vps/secrets.yaml
```

Replace `REPLACE_ME` with real values:
- `tailscale_auth_key`: generate from Tailscale admin → Settings → Keys → Generate auth key (ephemeral recommended)
- `hermes_openrouter_api_key`: generate from OpenRouter dashboard

### Pre-flight checklist

Before nixos-anywhere, verify:

- [ ] `ssh root@VPS_IP lsblk` — disk device matches `_disko.nix`
- [ ] Age pubkey added to `secrets/.sops.yaml` (`&vps age1...`, uncomment `*vps` in creation_rules)
- [ ] `sops updatekeys -y secrets/vps/secrets.yaml` — file re-encrypted for VPS
- [ ] `sudo sops secrets/vps/secrets.yaml` — placeholders replaced with real values
- [ ] `nix flake check --no-build --keep-going` — all hosts pass

### Run nixos-anywhere

```bash
nix run github:nix-community/nixos-anywhere -- \
  --flake .#vps \
  --generate-hardware-config nixos-facter ./modules/hosts/vps/facter.json \
  --extra-files ~/.cache/vps-provision/rootfs \
  --chown "etc/ssh/ssh_host_ed25519" "0:0" \
  --chown "etc/ssh/ssh_host_ed25519.pub" "0:0" \
  --chown "var/lib/sops/age-key.txt" "0:0" \
  --chown "home/likivik/.ssh/authorized_keys" "1000:100" \
  --target-host root@VPS_IP
```

### After reboot (VPS running NixOS)

```bash
# SSH in (no password — key is already authorized)
ssh likivik@VPS_IP

# Verify sops decrypted secrets
ls /run/secrets/tailscale/auth-key
sudo journalctl -u sops-nix --no-pager | tail -20

# Verify Tailscale joined
tailscale status

# Clean up local keys
rm -rf ~/.cache/vps-provision

# Commit infra changes
git add -A
git commit -m "feat(vps): add vps host with sops secrets"
git push
```

### If disko phase fails (wrong disk device)

```bash
# Check what disk the VPS actually has
ssh root@VPS_IP lsblk -ndo NAME | grep -v loop | head -1
# Edit _disko.nix device path to match
# Re-run nixos-anywhere (safe — VPS is still booted into installer)
```

---

## 2. Q&A

**Q: Can nixos-anywhere auto-detect the disk device?**  
A: No. It uses `_disko.nix` as-is. Wrong device → disko phase fails harmlessly. Check with `lsblk`, edit, re-run.

**Q: How does age key derivation work?**  
A: Ed25519 SSH keys and age use the same curve. `ssh-to-age` reads the SSH private key and outputs the same key in age format. The public half goes in `.sops.yaml`.

**Q: What does `--extra-files` do?**  
A: Copies the local directory tree into the new NixOS install's root (`/`) before first boot. E.g., `rootfs/var/lib/sops/key` → `/var/lib/sops/key`.

**Q: SSH host key vs authorized keys?**  
A: Host key (`/etc/ssh/ssh_host_*`) — VPS proves its identity to you. We pre-generate it so `known_hosts` stays clean. Authorized keys (`~/.ssh/authorized_keys`) — who can SSH in. We pre-seed traversal's pubkey so you can log in immediately.

**Q: Does this VPS have TPM for age keys?**  
A: No. Most VPSes (Hetzner, DO, Linode) don't expose TPM. We use age-keygen + `--extra-files` to seed the private key at install time.

**Q: How does sops work on the VPS?**  
A: On boot, sops-nix reads `/var/lib/sops/age-key.txt` (pre-seeded via extra-files), decrypts `secrets/vps/secrets.yaml`, writes to `/run/secrets/*` (RAM tmpfs). Nix config wires those to Tailscale auth, Hermes API key, etc.

**Q: Is `~/.cache/` secure for key files?**  
A: Yes — `~/.cache/` is `0700` by default. Key files are `0600` (set by `umask 077`). Delete with `rm -rf ~/.cache/vps-provision` when done.

**Q: Need a password for sudo?**  
A: No — `sudo NOPASSWD` is configured. SSH key IS your auth. Password adds management overhead for zero security gain on a single-user VPS.

**Q: 2FA for SSH?**  
A: Tailscale mesh VPN (`lockSshToTailscale = true`) — SSH only listens on `tailscale0`, unreachable from public internet. Tailscale auth uses your SSO provider (can have 2FA). No extra client setup.

**Q: What happens on each nixos-anywhere phase?**  
A: 1) kexec (reboot into NixOS installer). 2) disko (destroy partitions, create per `_disko.nix`). 3) install (copy closure, apply config, `--extra-files` copied here). 4) reboot into new NixOS.

**Q: What do Den/Numtide/etc contributors use?**  
A: Same pattern: pre-generate age key → `.sops.yaml` → `--extra-files` → nixos-anywhere → sops decrypts on first boot. Vic: `nh os switch` for updates. Numtide: Colmena. No tool packages this as one command.

**Q: Why script this for monthly VPS re-creation?**  
A: One-time cost. The logic is: detect disk → generate keys → encrypt secrets → inject files → nixos-anywhere → commit. Automatable in a single shell script.
