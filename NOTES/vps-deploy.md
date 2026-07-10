# VPS deploy: Ubuntu → NixOS + sops secrets

## Prerequisites

- Local spectacle repo with latest commits
- VPS running Ubuntu, reachable via SSH
- Recovery key generated (see `NOTES/secrets.md`)

## Step 1: Prepare the flake

```sh
cd /Storage/Git/spectacle
nix flake check --no-build --keep-going
nix build .#nixosConfigurations.vps.config.system.build.toplevel --dry-run
```

## Step 2: Run nixos-anywhere

```sh
nix run github:nix-community/nixos-anywhere -- \
  --flake .#vps \
  --generate-hardware-config nixos-facter ./modules/hosts/vps/facter.json \
  --target-host root@<vps-public-ip>
```

Converts Ubuntu to NixOS via kexec, partitions disk, installs, reboots.

> **Wrong device in `_disko.nix`?** nixos-facter reports the real device.
> Edit and re-run.

## Step 3: Bootstrap ssh-to-age (first deploy only)

```sh
# On vps after reboot:
tailscale up --operator=likivik --accept-routes=true
cd /var/lib/spectacle && git pull

# Get the vps host SSH key for sops
ssh-to-age < /etc/ssh/ssh_host_ed25519_key.pub
# Paste output into secrets/.sops.yaml as &vps (temporary)
```

## Step 4: Encrypt real secrets from your local machine

```sh
cd /Storage/Git/spectacle
# 1. Add vps pubkey to .sops.yaml
# 2. Add recovery + serenity + traversal pubkeys too
sops secrets/vps/secrets.yaml
# Fill in: tailscale_auth_key, hermes_openrouter_api_key
git add secrets/.sops.yaml secrets/vps/secrets.yaml
git commit -m "secrets: add vps secrets"
git push
```

## Step 5: Rebuild on vps

```sh
ssh likivik@<vps-ts-ip>
cd /var/lib/spectacle && git pull
nh os switch .#vps
```

Tailscale auto-auths, hermes gets its API key.

## Step 6: Migrate to TPM

See `NOTES/secrets.md` "TPM migration on vps".

## Step 7: Lock down SSH

```sh
# vps.nix: lockSshToTailscale = true; → rebuild
```

Only tailnet devices can SSH after this.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `nixos-anywhere` hangs | VPS < 1GB RAM |
| No SSH after reboot | Wrong device in `_disko.nix` |
| `sops-install-secrets` fails | Host key mismatch. Regenerate |
| Tailscale not logged in | Auth key missing |
