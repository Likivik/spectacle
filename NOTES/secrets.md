# Secrets management with sops-nix

## Key setup

Each machine needs a unique age identity.
- **Desktops** (serenity, traversal): TPM-sealed keys via age-plugin-tpm.
- **Servers** (erebus, poweredge): ssh-to-age — derived from the host's SSH
  ed25519 key. No TPM migration needed.

### 1. Generate the RECOVERY key (on any machine, one-time)

```sh
age-keygen -o ~/likivik-nixos-sops-recovery-key.txt
age-keygen --convert ~/likivik-nixos-sops-recovery-key.txt > ~/likivik-nixos-sops-recovery-key.txt.pub
```

- **Private key**: encrypt with a strong password, store in Bitwarden.
- **Public key** (`.pub`): paste into `secrets/.sops.yaml` as `&recovery`.

### 2. Generate TPM keys (desktops only)

**⚠️ IMPORTANT: ** age-plugin-tpm v1.0.0+ defaults to
`p256tag` format (`age1tag1...`) when converting to recipient, but SOPS doesn't support it yet
([getsops/sops#2129](https://github.com/getsops/sops/issues/2129)).
when extracting public part(recipient) - `sudo age-plugin-tpm --convert --tpm-recipient` - --tpm-recipient is the important part. The whole issue is just a recipients format. that's it.

**Serenity** (desktop):
```sh

# 1) create folder
sudo mkdir -p /var/lib/sops

# 2) generate actual tpm key
sudo age-plugin-tpm --generate -o /var/lib/sops/tpm-identity.txt

# 3) extract the private part in the format you want/need (--tpm-recipient for current version of sops as of 18-07-2026)
sudo age-plugin-tpm --convert --tpm-recipient /var/lib/sops/tpm-identity.txt

# 4) manually copy the public part to .sops.yaml

# 5) use recovery key to update allowed keys (you need recovery passed as env, or ssh from another pc. but you need to decrypt before you encrypt with newly generated file)
sudo SOPS_AGE_KEY_FILE=/tmp/recovery-key.txt sops updatekeys secrets/erebus/secrets.yaml
```

### 3. Server keys (ssh-to-age)

Servers use ssh-to-age — no generation needed. The age public key is derived
from the host's SSH ed25519 key:

```sh
ssh root@<server-ip> cat /etc/ssh/ssh_host_ed25519_key.pub | ssh-to-age
# → age1...
```

Paste the result into `secrets/.sops.yaml` under `keys:` as `&<hostname>`.
This is permanent — no TPM migration.

## Encrypt a file
`sops --encrypt --in-place secrets.yaml`

## Daily workflow

The `.envrc` at the repo root sets up the sops environment automatically
via direnv:

```sh
cd /Storage/Git/spectacle          # direnv loads .envrc
sudo sops secrets/erebus/secrets.yaml  # opens $EDITOR, sops decrypts/encrypts
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

1. `sudo sops secrets/erebus/secrets.yaml` — add the new key-value
2. Declare in `modules/hosts/erebus/erebus.nix`:
   ```nix
   "new-service/api-key" = {
     sopsFile = ../../../secrets/erebus/secrets.yaml;
     key = "new_service_api_key";
     owner = "new-service-user";
     group = "new-service-user";
     mode = "0600";
   };
   ```
3. Reference: `config.sops.secrets."new-service/api-key".path`
4. `nh os switch .#erebus`

## Security model

Each secret mounts at `/run/secrets/<name>` with per-service ACLs.

- **Desktops**: TPM-sealed keys can't be extracted from the TPM — even root
  on a compromised machine can't steal them.
- **Servers**: ssh-to-age derives the key from the host SSH ed25519 key.
  The key lives on disk but is protected by SSH host key permissions.

Recovery key in Bitwarden (passphrase-locked) is the only backdoor.
