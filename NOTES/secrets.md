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

TPM identity is at `/var/lib/sops/tpm-identity.txt` (needs root for TPM device).
Run sops with the identity and age-plugin-tpm on PATH:

```sh
nix shell nixpkgs#sops nixpkgs#age-plugin-tpm --command \
  sops --age-identity /var/lib/sops/tpm-identity.txt secrets/vps/secrets.yaml

nix shell nixpkgs#sops nixpkgs#age-plugin-tpm --command \
  sops --age-identity /var/lib/sops/tpm-identity.txt \
    --rotate --in-place secrets/vps/secrets.yaml

nix shell nixpkgs#sops nixpkgs#age-plugin-tpm --command \
  sops --age-identity /var/lib/sops/tpm-identity.txt \
    -d secrets/vps/secrets.yaml | grep tailscale
```

## Adding a new secret

1. `sops secrets/vps/secrets.yaml` — add the new key-value
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
