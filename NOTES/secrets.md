# Secrets management with sops-nix

## Key setup

Each machine needs a unique age identity. The vps starts with
ssh-to-age (bootstrap), then migrates to TPM.

### 1. Generate the RECOVERY key (on any machine, one-time)

```sh
age-keygen -o ~/hermes-recovery-key.txt
age-keygen -y ~/hermes-recovery-key.txt > ~/hermes-recovery-key.txt.pub
```

- **Private key**: encrypt with a strong password, store in Bitwarden.
- **Public key** (`.pub`): paste into `secrets/.sops.yaml` as `&recovery`.

### 2. Generate TPM keys on each machine

**Serenity** (desktop):
```sh
nix shell nixpkgs#age-plugin-tpm --command \
  age-plugin-tpm --generate -o ~/.config/sops/tpm-identity.txt
nix shell nixpkgs#age-plugin-tpm --command \
  age-plugin-tpm -y ~/.config/sops/tpm-identity.txt
```
Paste the recipient into `.sops.yaml` as `&serenity`.

**Traversal** (laptop): same, paste as `&traversal`.

**VPS**: after first NixOS deploy (see `vps-deploy.md`):
```sh
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

```sh
sops secrets/vps/secrets.yaml          # edit
sops --rotate --in-place secrets/vps/secrets.yaml  # re-encrypt
sops -d secrets/vps/secrets.yaml | grep tailscale  # view one
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
