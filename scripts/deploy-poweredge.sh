#!/usr/bin/env bash
# deploy-poweredge.sh — Automated deployment of poweredge
#
# Run from: traversal (or any machine with the spectacle flake)
# Prerequisites: poweredge booted from NixOS minimal ISO, on the same LAN
#
# Usage: ./scripts/deploy-poweredge.sh [--ip <ip>] [--dry-run]
set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────
HOSTNAME="poweredge"
HOST_DIR="modules/hosts/${HOSTNAME}"
DISKO_FILE="${HOST_DIR}/_disko.nix"
HARDWARE_FILE="${HOST_DIR}/_hardware-configuration.nix"
SOPS_YAML="secrets/.sops.yaml"
SECRETS_DIR="secrets/${HOSTNAME}"
SECRETS_FILE="${SECRETS_DIR}/secrets.yaml"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# ─── Parse args ───────────────────────────────────────────────────────
TARGET_IP=""
DRY_RUN=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --ip) TARGET_IP="$2"; shift 2 ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--ip <ip>] [--dry-run]"
      echo "  --ip <ip>    Skip LAN scan, deploy to this IP directly"
      echo "  --dry-run    Show what would be done without executing"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ─── Colors & helpers ─────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
fail()  { echo -e "${RED}[FAIL]${NC}  $*"; exit 1; }
step()  { echo -e "\n${GREEN}── Step $1: $2 ──${NC}"; }

# ─── Preflight ────────────────────────────────────────────────────────
step 0 "Preflight checks"

# Must be in the spectacle repo
[[ -f "$REPO_DIR/flake.nix" ]] || fail "Not in spectacle repo (no flake.nix found at $REPO_DIR)"
cd "$REPO_DIR"
info "Working directory: $(pwd)"

# Check required tools
for cmd in ssh nix-shell git ssh-to-age sops; do
  command -v "$cmd" &>/dev/null || {
    # Try via nix-shell for tools that might not be on PATH
    if nix-shell -p "$cmd" --run "which $cmd" &>/dev/null 2>&1; then
      info "$cmd available via nix-shell"
    else
      fail "Required tool not found: $cmd"
    fi
  }
done
ok "All required tools available"

# ─── Step 1: Discover poweredge on LAN ────────────────────────────────
step 1 "Discover poweredge on LAN"

if [[ -z "$TARGET_IP" ]]; then
  # Auto-detect LAN subnet from default route
  SUBNET=$(ip route show default | awk '/^default/ {print $3}' | sed 's/\.[0-9]*$/.0\/24/')
  info "Scanning subnet: $SUBNET"

  # Get list of hosts with open SSH (port 22)
  info "Scanning for SSH hosts (this may take a moment)..."
  CANDIDATES=$(nmap -p 22 --open -sn "$SUBNET" 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' || true)

  if [[ -z "$CANDIDATES" ]]; then
    # Fallback: try ARP table
    info "nmap found nothing, trying ARP table..."
    CANDIDATES=$(ip neigh show | grep -v FAILED | awk '/inet/ {print $1}' || true)
  fi

  if [[ -z "$CANDIDATES" ]]; then
    fail "No candidates found. Is poweredge booted and on the LAN?"
  fi

  info "Found candidates:"
  echo "$CANDIDATES" | nl

  # Try each candidate — look for NixOS ISO (root login, no password, nixos in hostname or description)
  for ip in $CANDIDATES; do
    info "Probing $ip..."
    # NixOS ISO root login works without password by default
    if OUTPUT=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 -o BatchMode=yes root@"$ip" "cat /etc/os-release 2>/dev/null || true" 2>/dev/null); then
      if echo "$OUTPUT" | grep -qi "nixos\|nix"; then
        TARGET_IP="$ip"
        ok "Found NixOS ISO at $ip"
        break
      fi
    fi
  done

  if [[ -z "$TARGET_IP" ]]; then
    # If no NixOS found, ask user to pick
    warn "Could not auto-detect NixOS ISO. Candidates:"
    echo "$CANDIDATES" | nl
    echo ""
    read -rp "Enter the poweredge IP manually: " TARGET_IP
    [[ -n "$TARGET_IP" ]] || fail "No IP provided"
  fi
else
  info "Using provided IP: $TARGET_IP"
fi

ok "Target IP: $TARGET_IP"

# ─── Step 2: Get SSH host key → age key ───────────────────────────────
step 2 "Extract SSH host key and convert to age"

info "Fetching SSH host key from $TARGET_IP..."
SSH_PUB_KEY=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@"$TARGET_IP" "cat /etc/ssh/ssh_host_ed25519_key.pub" 2>/dev/null) \
  || fail "Cannot SSH into $TARGET_IP — is the ISO booted with SSH enabled?"

info "SSH public key: $SSH_PUB_KEY"

AGE_KEY=$(echo "$SSH_PUB_KEY" | nix-shell -p ssh-to-age --run 'ssh-to-age' 2>/dev/null) \
  || fail "ssh-to-age conversion failed"

ok "Age public key: $AGE_KEY"

# ─── Step 3: Get disk IDs ─────────────────────────────────────────────
step 3 "Discover disk IDs"

info "Fetching block device info from $TARGET_IP..."
LSBLK_OUTPUT=$(ssh root@"$TARGET_IP" "lsblk -ndo NAME,SIZE,TYPE,MODEL" 2>/dev/null) \
  || fail "Cannot fetch lsblk from target"

info "Block devices on poweredge:"
echo "$LSBLK_OUTPUT"

# Identify SSD (smallest) and HDDs (largest pair)
# Get full disk paths with sizes
DISK_INFO=$(ssh root@"$TARGET_IP" "lsblk -ndo NAME,SIZE,TYPE | grep ' disk$'" 2>/dev/null) \
  || fail "Cannot parse disk info"

info "Parsing disk layout..."

# Sort by size, smallest = SSD, largest two = HDDs
SSD_NAME=$(echo "$DISK_INFO" | sort -k2 -h | head -1 | awk '{print $1}')
HDD_NAMES=$(echo "$DISK_INFO" | sort -k2 -hr | head -2 | awk '{print $1}' | sort)

SSD_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/${SSD_NAME}$' | awk '{print \$9}'" 2>/dev/null | head -1)
HDD1_ID=$(echo "$HDD_NAMES" | head -1)
HDD2_ID=$(echo "$HDD_NAMES" | tail -1)

HDD1_FULL_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/${HDD1_ID}$' | awk '{print \$9}'" 2>/dev/null | head -1)
HDD2_FULL_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/${HDD2_ID}$' | awk '{print \$9}'" 2>/dev/null | head -1)

# Get full /dev/disk/by-id paths
SSD_BY_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/${SSD_NAME}$' | awk '{print \$NF}'" 2>/dev/null | head -1)
HDD1_BY_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/${HDD1_ID}$' | awk '{print \$NF}'" 2>/dev/null | head -1)
HDD2_BY_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/${HDD2_ID}$' | awk '{print \$NF}'" 2>/dev/null | head -1)

if [[ -z "$SSD_BY_ID" || -z "$HDD1_BY_ID" || -z "$HDD2_BY_ID" ]]; then
  warn "Auto-detection ambiguous. Here's the full disk-by-id mapping:"
  ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/" 2>/dev/null
  echo ""
  read -rp "Enter SSD by-id path: " SSD_BY_ID
  read -rp "Enter HDD1 by-id path: " HDD1_BY_ID
  read -rp "Enter HDD2 by-id path: " HDD2_BY_ID
fi

ok "SSD:  /dev/disk/by-id/${SSD_BY_ID}"
ok "HDD1: /dev/disk/by-id/${HDD1_BY_ID}"
ok "HDD2: /dev/disk/by-id/${HDD2_BY_ID}"

# ─── Step 4: Update _disko.nix ────────────────────────────────────────
step 4 "Update _disko.nix with real disk IDs"

if [[ "$DRY_RUN" == true ]]; then
  info "[DRY RUN] Would update ${DISKO_FILE}:"
  info "  SSD:  REPLACE_WITH_SSD_ID  → ${SSD_BY_ID}"
  info "  HDD1: REPLACE_WITH_HDD1_ID → ${HDD1_BY_ID}"
  info "  HDD2: REPLACE_WITH_HDD2_ID → ${HDD2_BY_ID}"
else
  sed -i "s|REPLACE_WITH_SSD_ID|${SSD_BY_ID}|g" "$DISKO_FILE"
  sed -i "s|REPLACE_WITH_HDD1_ID|${HDD1_BY_ID}|g" "$DISKO_FILE"
  sed -i "s|REPLACE_WITH_HDD2_ID|${HDD2_BY_ID}|g" "$DISKO_FILE"
  ok "Updated ${DISKO_FILE}"
fi

# ─── Step 5: Update secrets/.sops.yaml ───────────────────────────────
step 5 "Update secrets/.sops.yaml with poweredge age key"

if grep -q "poweredge" "$SOPS_YAML" 2>/dev/null; then
  info "Poweredge already in .sops.yaml — updating key"
  # Replace the existing key line
  sed -i "/&poweredge/c\\  - \\&poweredge ${AGE_KEY}" "$SOPS_YAML"
else
  info "Adding poweredge to .sops.yaml"
  # Add key under keys section
  sed -i "/&erebus/a\\  - \\&poweredge ${AGE_KEY}" "$SOPS_YAML"

  # Add creation rule
  cat >> "$SOPS_YAML" <<CREATION_RULE

  - path_regex: poweredge/.*\\.yaml\$
    key_groups:
      - age:
          - *recovery
          - *traversal
          - *poweredge
CREATION_RULE
fi

ok "Updated ${SOPS_YAML}"

if [[ "$DRY_RUN" == false ]]; then
  # Commit sops changes early (nixos-anywhere reads it from the flake)
  info "Committing sops config..."
  git add "$SOPS_YAML"
  git commit -m "chore(poweredge): add age pubkey to sops config" 2>/dev/null \
    || warn "Nothing to commit (sops config unchanged)"
fi

# ─── Step 6: Create secrets file ─────────────────────────────────────
step 6 "Create nextcloud secrets"

if [[ -f "$SECRETS_FILE" ]] && [[ "$DRY_RUN" == false ]]; then
  info "Secrets file already exists: ${SECRETS_FILE}"
  read -rp "Overwrite? [y/N]: " OVERWRITE
  [[ "$OVERWRITE" == "y" || "$OVERWRITE" == "Y" ]] || { info "Skipping secrets creation"; }
fi

if [[ ! -f "$SECRETS_FILE" ]] || [[ "$OVERWRITE" == "y" ]]; then
  echo ""
  echo "Enter the Nextcloud admin password (or press Enter to generate one):"
  read -rsp "Password: " NC_PASSWORD
  echo ""

  if [[ -z "$NC_PASSWORD" ]]; then
    NC_PASSWORD=$(openssl rand -base64 24)
    info "Generated password: ${NC_PASSWORD}"
    info "SAVE THIS — you'll need it to log into Nextcloud"
  fi

  if [[ "$DRY_RUN" == true ]]; then
    info "[DRY RUN] Would create ${SECRETS_FILE} with nextcloud admin password"
  else
    mkdir -p "$SECRETS_DIR"
    echo "nextcloud/admin-password: ${NC_PASSWORD}" > "$SECRETS_FILE"
    ok "Created ${SECRETS_FILE}"

    # Encrypt with sops
    info "Encrypting secrets with sops..."
    sudo sops updatekeys -y "$SECRETS_FILE" 2>/dev/null || {
      info "First-time encryption — using sops edit mode"
      info "The file is now ready. It will be encrypted on first sops edit/save."
    }
  fi
fi

# ─── Step 7: Run nixos-anywhere ──────────────────────────────────────
step 7 "Deploy with nixos-anywhere"

info "Deploying to ${TARGET_IP}..."
info "This will take 10-15 minutes. Grab a coffee."
echo ""

if [[ "$DRY_RUN" == true ]]; then
  info "[DRY RUN] Would run:"
  info "  nixos-anywhere --flake .#${HOSTNAME} \\"
  info "    --generate-hardware-config nixos-facter ${HARDWARE_FILE} \\"
  info "    --copy-host-keys \\"
  info "    root@${TARGET_IP}"
else
  # shellcheck disable=SC2086
  nix run github:nix-community/nixos-anywhere -- \
    --flake ".#${HOSTNAME}" \
    --generate-hardware-config nixos-facter "./${HARDWARE_FILE}" \
    --copy-host-keys \
    "root@${TARGET_IP}" \
    || fail "nixos-anywhere deployment failed!"
fi

ok "Deployment complete!"

# ─── Step 8: Post-deploy verification ────────────────────────────────
step 8 "Verify deployment"

if [[ "$DRY_RUN" == true ]]; then
  info "[DRY RUN] Would verify:"
  info "  1. SSH to likivik@${TARGET_IP}"
  info "  2. Check tailscale status"
  info "  3. Check nextcloud status"
  info "  4. Git add hardware config"
else
  info "Waiting for reboot (1-5 minutes)..."
  RETRIES=0
  until ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no likivik@"$TARGET_IP" true 2>/dev/null; do
    RETRIES=$((RETRIES + 1))
    if [[ $RETRIES -gt 30 ]]; then
      fail "Poweredge did not come back after 5 minutes. Check manually."
    fi
    sleep 10
  done

  ok "SSH is up"

  # Check tailscale
  info "Checking Tailscale..."
  ssh likivik@"$TARGET_IP" "tailscale status" 2>/dev/null || warn "Tailscale not connected yet (may need 'tailscale up')"

  # Check nextcloud
  info "Checking Nextcloud..."
  ssh likivik@"$TARGET_IP" "systemctl status nextcloud --no-pager" 2>/dev/null | head -5 || warn "Nextcloud service not found"

  # Check sops
  info "Checking sops-nix..."
  ssh likivik@"$TARGET_IP" "sudo systemctl status sops-nix --no-pager" 2>/dev/null | head -5 || warn "sops-nix service not found"
fi

# ─── Step 9: Commit generated files ──────────────────────────────────
step 9 "Commit generated files"

if [[ "$DRY_RUN" == true ]]; then
  info "[DRY RUN] Would commit:"
  info "  git add ${HARDWARE_FILE} ${DISKO_FILE} ${SECRETS_FILE}"
  info "  git commit -m 'feat(poweredge): add hardware config and disk layout'"
else
  git add "$HARDWARE_FILE" "$DISKO_FILE" "$SECRETS_FILE" 2>/dev/null || true
  git commit -m "feat(poweredge): add hardware config and disk layout" 2>/dev/null \
    || warn "Nothing new to commit"
fi

# ─── Done ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PowerEdge deployment complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Nextcloud:  http://${HOSTNAME}:80"
echo "  SSH:        ssh likivik@${TARGET_IP}"
echo "  Tailscale:  ssh likivik@<poweredge-tailnet-ip> (after tailscale up)"
echo ""
echo "  If Tailscale isn't connected, SSH in and run:"
echo "    sudo tailscale up"
echo ""
