#!/usr/bin/env bash
set -euo pipefail

exec 3>&2                          # save real stderr → fd 3 (so run() can punch through 2>/dev/null)
run() {
    echo "+ $*" >&3                # $* joins args → one string for display
    "$@"                           # $@ keeps args separate (preserves spaces/quoting)
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && git rev-parse --show-toplevel 2>/dev/null)"

if [ -z "$REPO_ROOT" ]; then
  echo "Error: could not determine repository root — is redeploy.sh inside the spectacle repo?" >&2
  exit 1
fi

cd "$REPO_ROOT"

DEFAULT_IP="148.253.214.185"

read -r -p "Enter VPS IP [${DEFAULT_IP}]: " IP
IP="${IP:-$DEFAULT_IP}"
IP="${IP//[[:space:]]/}"

# ---- Step 1: Clear old host key

echo ""
echo "=== Step 1: Clear old host key ==="
run ssh-keygen -R "$IP" || true
run ssh-keygen -F "$IP" &>/dev/null && { echo "Error: stale host key still present" >&2; exit 1; } || echo "✅ Old host key cleared"

# ---- Step 2: Install SSH key

echo ""
echo "=== Step 2: Install SSH key (enter root password when prompted) ==="
run ssh-copy-id -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "root@$IP"
run ssh -o StrictHostKeyChecking=accept-new -o PasswordAuthentication=no -o BatchMode=yes -o ConnectTimeout=5 "root@$IP" true && echo "✅ Passwordless SSH verified" || { echo "Error: SSH connection failed" >&2; exit 1; }

# ---- Step 3: Get age pubkey

echo ""
echo "=== Step 3: Get age pubkey ==="
if ! command -v ssh-to-age &>/dev/null; then
  echo "Error: ssh-to-age not found in PATH" >&2
  echo "Install: nix shell nixpkgs#ssh-to-age -c bash" >&2
  exit 1
fi

NEW_AGE_PUBKEY=$(run ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "root@$IP" cat /etc/ssh/ssh_host_ed25519_key.pub | run ssh-to-age)
[ -n "$NEW_AGE_PUBKEY" ] || { echo "Error: failed to fetch age pubkey" >&2; exit 1; }
[[ "$NEW_AGE_PUBKEY" =~ ^age1[0-9a-z]+$ ]] || { echo "Error: fetched key doesn't look like an age pubkey (doesn't start with age1): $NEW_AGE_PUBKEY" >&2; exit 1; }
echo "🔑 New age key: $NEW_AGE_PUBKEY"

# ---- Step 4: Update .sops.yaml

echo ""
echo "=== Step 4: Update .sops.yaml ==="
SOPS_FILE="secrets/.sops.yaml"
SECRETS_FILE="secrets/erebus/secrets.yaml"
if [ ! -f "$SOPS_FILE" ]; then
  echo "Error: $SOPS_FILE not found" >&2
  exit 1
fi

run sed -i "s/\(&erebus[[:space:]]*\)age1[^[:space:]]*/\1${NEW_AGE_PUBKEY}/" "$SOPS_FILE"
run git --no-pager diff -- secrets/.sops.yaml || true
FILE_KEY=$(grep '&erebus' "$SOPS_FILE" | grep -oE 'age1[0-9a-z]+')
[ "$FILE_KEY" = "$NEW_AGE_PUBKEY" ] || { echo "Error: key mismatch — file has '$FILE_KEY', expected '$NEW_AGE_PUBKEY'" >&2; exit 1; } && echo "✅ Updated $SOPS_FILE"

# ---- Step 5: Re-encrypt secrets

echo ""
echo "=== Step 5: Re-encrypt secrets ==="
run sudo sops updatekeys -y "$SECRETS_FILE"
run git diff --stat -- "$SECRETS_FILE" || true
run grep -q "$NEW_AGE_PUBKEY" "$SECRETS_FILE" && echo "✅ Secrets re-encrypted" || { echo "Error: new pubkey not found among sops recipients" >&2; exit 1; }

# ---- Step 6: Commit

echo ""
echo "=== Step 6: Commit changes ==="

run git add "$SOPS_FILE" "$SECRETS_FILE"

if run git diff --cached --quiet; then
  echo "✅ Already up-to-date — nothing to commit"
else
  run git commit -m "feat(erebus): update age pubkey for redeploy"
  echo "✅ Committed"
fi

echo ""
echo "=== Flake check ==="
run nix build .#nixosConfigurations.erebus.config.system.build.toplevel --dry-run
echo "✅ Flake checks pass"

# ---- Deploy

echo ""
echo "Command to run:"
echo "  nix run github:nix-community/nixos-anywhere -- \\"
echo "    --flake .#erebus \\"
echo "    --copy-host-keys \\"
echo "    --generate-hardware-config nixos-facter \\"
echo "      ./modules/hosts/erebus/facter.json \\"
echo "    --target-host root@$IP"
echo ""
read -r -p "Run nixos-anywhere now? [Y/n] " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn] ]]; then
  echo "Aborted."
  exit 0
fi
run nix run github:nix-community/nixos-anywhere -- \
  --flake .#erebus \
  --copy-host-keys \
  --generate-hardware-config nixos-facter \
    ./modules/hosts/erebus/facter.json \
  --target-host "root@$IP"

# Planned improvements (TODO — post-MVP):
# ──────────────────────────────────────────────
# 1. Wait for reboot after nixos-anywhere, poll SSH every 5s (max 12 tries).
# 2. Fail with ❌ if SSH doesn't come back (instead of letting user discover it).
# 3. Use provider API (hosting-vds.com) to automate:
#    - Reinstall Ubuntu via /servers/{id}/reinstall
#    - Fetch primary_ip + gateway from the response
#    - Inject IP/gateway into erebus.nix's static networkd config
#    - Then run nixos-anywhere
#    This would make redeploy fully one-shot.
