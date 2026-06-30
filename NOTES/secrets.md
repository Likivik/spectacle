# Secrets management with sops-nix

## First-time setup (on your local machine)

```sh
# 1. Generate your age key (one-time)
age-keygen -o ~/.config/sops/age/keys.txt

# 2. Get the public key
age-keygen -y ~/.config/sops/age/keys.txt

# 3. Update secrets/.sops.yaml with your public key (replace &user_age value)
#    Then commit the change.
```

## After vps is deployed

```sh
# 4. SSH into the vps, generate its age key from the host SSH key
ssh likivik@<vps-ts-ip>
sudo ssh-to-age < /etc/ssh/ssh_host_ed25519_key.pub

# 5. Copy the output into secrets/.sops.yaml as &vps_age
#    Then: sops --rotate --in-place secrets/vps/secrets.yaml

# 6. Commit both changes
```

## Daily workflow

```sh
# Edit secrets
sops secrets/vps/secrets.yaml

# Re-encrypt after adding a new key (e.g., a new machine)
sops --rotate --in-place secrets/vps/secrets.yaml

# View a specific secret (printing to terminal, piped to clipboard)
sops -d secrets/vps/secrets.yaml | grep tailscale

# Keys and rotation
# - User key: ~/.config/sops/age/keys.txt — protect it!
# - Vps key: /etc/ssh/ssh_host_ed25519_key — derived at runtime
# - To rotate: generate new key, add it to .sops.yaml, re-encrypt,
#   then remove old key. All clients must have the new key.
```

## Adding a new secret

1. Add the decrypted placeholder to `secrets/vps/secrets.yaml`:
   ```yaml
   new_service_api_key: "placeholder"
   ```
2. Save and close (sops re-encrypts on save).
3. Declare the secret in `modules/hosts/vps/vps.nix`:
   ```nix
   "new-service/api-key" = {
     sopsFile = ../../../secrets/vps/secrets.yaml;
     key = "new_service_api_key";
     owner = "new-service-user";
     group = "new-service-user";
     mode = "0600";
   };
   ```
4. Reference it where needed: `config.sops.secrets."new-service/api-key".path`
5. Rebuild: `nh os switch .#vps`

## Security model

Each secret is mounted at `/run/secrets/<name>` with the declared `owner`/`group`/`mode`.
A service can only read secrets declared for its own user:

- `/run/secrets/hermes/*` → 0600 hermes:hermes → only hermes-agent can read
- `/run/secrets/tailscale/*` → 0600 root:root → only tailscaled can read
- *(future)* `/run/secrets/kokoro/*` → 0600 kokoro:kokoro → only kokoro can read

No service can see another service's secrets. To escalate, an attacker needs
root access.
