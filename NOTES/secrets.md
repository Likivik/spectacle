# Secrets management with sops-nix

## Key setup

Each machine needs a unique age identity. The vps starts with
ssh-to-age (bootstrap), then migrates to TPM.

### 1. Generate the RECOVERY key (on any machine, one-time)

```sh
age-keygen -o ~/likivik-nixos-sops-recovery-key.txt
age-keygen -y ~/likivik-nixos-sops-recovery-key.txt > ~/likivik-nixos-sops-recovery-key.txt.pub
```

- **Private key**: encrypt with a strong password, store in Bitwarden.
- **Public key** (`.pub`): paste into `secrets/.sops.yaml` as `&recovery`.

### 2. Generate TPM keys on each machine

**Serenity** (desktop):
```sh
sudo mkdir -p /var/lib/sops
sudo nix shell nixpkgs#age-plugin-tpm --command \
  age-plugin-tpm --generate -o /var/lib/sops/tpm-identity.txt
sudo nix shell nixpkgs#age-plugin-tpm --command \
  age-plugin-tpm -y /var/lib/sops/tpm-identity.txt
```
Paste the recipient into `.sops.yaml` as `&serenity`.

**Traversal** (laptop): paste as `&traversal`.

**VPS**: after first NixOS deploy (see `vps-deploy.md`):
```sh
sudo mkdir -p /var/lib/sops
sudo age-plugin-tpm --generate -o /var/lib/sops/tpm-identity.txt
sudo age-plugin-tpm -y /var/lib/sops/tpm-identity.txt
```
Paste as `&vps`. Then migrate from ssh-to-age to TPM.

### 3. TPM migration on vps

Once the vps TPM identity exists:
1. Add its pubkey to `.sops.yaml` as `&vps`
2. `sops --rotate --in-place secrets/vps/secrets.yaml`
3. Edit `modules/aspects/server/sops/sops.nix`:
   - Comment `age.sshKeyPaths`
   - Uncomment `age.keyFile` + `age.plugins`
4. Commit, push, rebuild on vps

## Daily workflow

The `.envrc` at the repo root sets up the sops environment automatically
via direnv:

```sh
cd /Storage/Git/spectacle          # direnv loads .envrc
sudo sops secrets/vps/secrets.yaml # decrypts using TPM, opens $EDITOR
# edit plaintext → save → sops encrypts
```

The `env_keep` rule in the sops-cli aspect preserves `SOPS_AGE_KEY_FILE`,
`SOPS_CONFIG`, and `SOPS_EDITOR` through `sudo`.

Editor setup:
- `$SOPS_EDITOR=micro` (sops-cli aspect, system-wide) — sops overrides
  `$EDITOR` for its own editing; safe to run as root
- `$EDITOR=micro` (direnv aspect, system-wide) — terminal fallback for
  programs that don't check `$SOPS_EDITOR or `$VISUAL`
- `$VISUAL=vscodium` (direnv aspect, user-level) — GUI editor for
  programs that check `$VISUAL` first (git, etc.); kept out of root's
  env

## Adding a new secret

1. `sudo sops secrets/vps/secrets.yaml` — add the new key-value
2. Declare in `modules/hosts/vps/vps.nix`:
   ```nix
   "new-service/api-key" = {
     sopsFile = ../../../secrets/vps/secrets.yaml;
     key = "new_service_api_key";
     owner = "new-service-user";
     group = "new-service-user";
     mode = "0600";
   };
   ```
3. Reference: `config.sops.secrets."new-service/api-key".path`
4. `nh os switch .#vps`

## Security model

Each secret mounts at `/run/secrets/<name>` with per-service ACLs.
TPM-sealed keys can't be extracted from the TPM — even root on a
compromised machine can't steal them. Recovery key in Bitwarden
(passphrase-locked) is the only backdoor.
