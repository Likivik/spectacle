# VPS deploy: Ubuntu → NixOS + sops secrets

## Prerequisites

- You're on your local machine with the spectacle repo
- VPS is running Ubuntu, reachable via SSH from your machine
- All local file changes from this plan are committed

## Step 1: Generate your age key (one-time)

```sh
age-keygen -o ~/.config/sops/age/keys.txt
age-keygen -y ~/.config/sops/age/keys.txt > ~/.config/sops/age/keys.txt.pub
```

## Step 2: Prepare the flake

```sh
cd /Storage/Git/spectacle
nix flake check --no-build --keep-going   # verify everything evals
nix build .#nixosConfigurations.vps.config.system.build.toplevel --dry-run
```

## Step 3: Deploy via nixos-anywhere

```sh
nix run github:nix-community/nixos-anywhere -- \
  --flake .#vps \
  --generate-hardware-config nixos-facter ./modules/hosts/vps/facter.json \
  --target-host root@<vps-public-ip>
```

**What happens**: nixos-anywhere SSHes into Ubuntu, kexec's into a NixOS
installer, partitions the disk (via `modules/hosts/vps/disko.nix`), installs
NixOS from our flake config, and reboots.

After reboot, the VPS is running NixOS with the vps host config.

> **If the device name in disko.nix (`/dev/vda`) is wrong**: nixos-facter
> reports the actual device. Edit `modules/hosts/vps/disko.nix` with the
> correct device name and re-run nixos-anywhere.

## Step 4: Commit the hardware config

The first nixos-anywhere run produced a `facter.json`. Convert it:

```sh
# On the vps (via SSH):
sudo bash
cd /var/lib/spectacle
# Copy the facter.json from where nixos-anywhere put it
# (usually the --generate-hardware-config output path)
git add modules/hosts/vps/facter.json
git commit -m "vps: add facter hardware report"
```

Or if you used `nixos-generate-config` instead, commit the
`hardware-configuration.nix` that was generated.

## Step 5: Bootstrap the vps

Still on the vps as root:

```sh
# 1. Tailscale auth (if no auth key is in sops yet)
tailscale up --operator=likivik --accept-routes=true

# 2. Generate the vps age key for sops
ssh-to-age < /etc/ssh/ssh_host_ed25519_key.pub > /var/lib/spectacle/secrets/vps/age.pub

# 3. Commit the age key
cd /var/lib/spectacle
git add secrets/vps/age.pub
git -c user.name=likivik -c user.email=likivik@vps.local \
  commit -m "vps: add age public key for sops"
git push <remote>

# 4. Update .sops.yaml and secrets.yaml on your local machine
```

## Step 6: Encrypt real secrets from your local machine

```sh
cd /Storage/Git/spectacle

# Pull the vps age key (from the vps's push)
git pull

# Update secrets/vps/secrets.yaml with real values
# sops automatically decrypts (with your key) and re-encrypts (with both keys)
sops secrets/vps/secrets.yaml
# Fill in: tailscale_auth_key, hermes_openrouter_api_key

# Commit
git add secrets/vps/secrets.yaml
git commit -m "secrets: add initial vps secrets with both recipients"
git push
```

## Step 7: Pull on vps, rebuild

```sh
ssh likivik@<vps-ts-ip>
cd /var/lib/spectacle
git pull

# This rebuild will now:
# - Decrypt tailscale auth key → tailscaled auto-configures
# - Decrypt hermes API key → environment variable set
nh os switch .#vps
```

After this, `systemctl status tailscaled` should show authenticated.

## Step 8: Lock down SSH

```sh
# Edit /var/lib/spectacle/modules/hosts/vps/vps.nix
# Set lockSshToTailscale = true;
# Commit, push, pull on vps, nh os switch
```

After lockdown, only tailnet devices can SSH.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `nixos-anywhere` hangs on kexec | VPS has < 1GB RAM. Need at least 1GB real RAM (not swap) |
| After reboot, no SSH | Device name in disko.nix wrong. Check cloud console VNC |
| `sops-install-secrets` fails | VPS host SSH key doesn't match `.sops.yaml` recipient. Re-generate `age.pub` and re-encrypt |
| Tailscale says "not logged in" | Auth key missing or wrong. Re-run `sops secrets/vps/secrets.yaml` |
| Hermes says "invalid API key" | API key wrong. Check the value in sops |
