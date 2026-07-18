#!/usr/bin/env bash
# deploy-poweredge.sh — Interactive, step-by-step deployment of poweredge
#
# Every command is shown, explained, and requires approval before execution.
# Run from: traversal (or any machine with the spectacle flake)
# Prerequisites: poweredge booted from NixOS minimal ISO, on the same LAN
#
# Usage: ./scripts/deploy-poweredge.sh [--ip <ip>] [--yes]
set -euo pipefail

# ─── Config ───────────────────────────────────────────────────────────
HOSTNAME="poweredge"
HOST_DIR="modules/hosts/${HOSTNAME}"
DISKO_FILE="${HOST_DIR}/_disko.nix"
FACTER_FILE="${HOST_DIR}/facter.json"
SOPS_YAML="secrets/.sops.yaml"
SECRETS_DIR="secrets/${HOSTNAME}"
SECRETS_FILE="${SECRETS_DIR}/secrets.yaml"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# ─── Parse args ───────────────────────────────────────────────────────
TARGET_IP=""
AUTO_YES=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --ip) TARGET_IP="$2"; shift 2 ;;
    --yes|-y) AUTO_YES=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--ip <ip>] [--yes]"
      echo "  --ip <ip>    Skip LAN scan, deploy to this IP directly"
      echo "  --yes, -y    Skip approval prompts (non-interactive)"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ─── Colors & helpers ─────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()    { echo -e "${CYAN}ℹ${NC}  $*"; }
ok()      { echo -e "${GREEN}✓${NC}  $*"; }
warn()    { echo -e "${YELLOW}⚠${NC}  $*"; }
fail()    { echo -e "${RED}✗${NC}  $*"; exit 1; }
header()  { echo -e "\n${BOLD}═══ $* ═══${NC}\n"; }
explain() { echo -e "${DIM}   $*${NC}"; }
cmd()     { echo -e "${BOLD}\$ ${*}${NC}"; }

# Ask for approval before running a command
# Usage: approve "description" command args...
approve() {
  local desc="$1"; shift
  echo ""
  echo -e "${CYAN}━━━ Action Required ━━━${NC}"
  echo -e "  ${BOLD}$desc${NC}"
  echo ""
  echo -e "  Command:"
  cmd "$*"
  echo ""

  if [[ "$AUTO_YES" == true ]]; then
    echo -e "  ${DIM}(--yes mode, auto-approving)${NC}"
  else
    read -rp "  Run this? [Y/n]: " choice
    if [[ "$choice" == "n" || "$choice" == "N" ]]; then
      warn "Skipped by user"
      return 1
    fi
  fi

  # Execute
  if output=$("$@" 2>&1); then
    if [[ -n "$output" ]]; then
      echo -e "${DIM}$(echo "$output" | head -20)${NC}"
      if [[ $(echo "$output" | wc -l) -gt 20 ]]; then
        echo -e "${DIM}  ... ($(( $(echo "$output" | wc -l) - 20 )) more lines)${NC}"
      fi
    fi
    ok "Done"
    return 0
  else
    warn "Command failed (exit code $?)"
    if [[ -n "$output" ]]; then
      echo -e "${RED}$(echo "$output" | tail -5)${NC}"
    fi
    return 1
  fi
}

# ─── Step 0: Preflight ───────────────────────────────────────────────
header "Step 0: Preflight checks"

info "Checking we're in the spectacle repo..."
[[ -f "$REPO_DIR/flake.nix" ]] || fail "Not in spectacle repo (no flake.nix at $REPO_DIR)"
cd "$REPO_DIR"
ok "Working directory: $(pwd)"

info "Checking required tools are available..."
for cmd in ssh git nix-shell ssh-to-age sops; do
  if command -v "$cmd" &>/dev/null; then
    ok "$cmd found at $(which $cmd)"
  elif nix-shell -p "$cmd" --run "which $cmd" &>/dev/null 2>&1; then
    ok "$cmd found via nix-shell"
  else
    fail "Required tool not found: $cmd"
  fi
done

info "Checking git state..."
CHANGES=$(git status --short 2>/dev/null || echo "unknown")
if [[ "$CHANGES" != *"poweredge"* ]]; then
  ok "No uncommitted poweredge changes (clean slate)"
else
  warn "Uncommitted poweredge changes detected:"
  echo "$CHANGES" | grep poweredge || true
  echo ""
  read -rp "  Continue anyway? [y/N]: " choice
  [[ "$choice" == "y" || "$choice" == "Y" ]] || exit 1
fi

# ─── Step 1: Discover poweredge on LAN ────────────────────────────────
header "Step 1: Discover poweredge on LAN"

if [[ -n "$TARGET_IP" ]]; then
  ok "Using provided IP: $TARGET_IP"
else
  # Auto-detect LAN subnet
  SUBNET=$(ip route show default | awk '/^default/ {print $3}' | sed 's/\.[0-9]*$/.0\/24/')
  info "Detected LAN subnet: $SUBNET"

  explain "Scanning for hosts with SSH open on port 22..."
  explain "Using nmap ping sweep (-sn) to find live hosts without port scanning."

  CANDIDATES=$(nmap -p 22 --open -sn "$SUBNET" 2>/dev/null | grep -oP '\d+\.\d+\.\d+\.\d+' || true)

  if [[ -z "$CANDIDATES" ]]; then
    info "nmap found nothing, falling back to ARP table..."
    CANDIDATES=$(ip neigh show | grep -v FAILED | awk '/inet/ {print $1}' || true)
  fi

  if [[ -z "$CANDIDATES" ]]; then
    fail "No SSH hosts found. Is poweredge booted and on the LAN?"
  fi

  info "Found SSH-capable hosts:"
  echo "$CANDIDATES" | nl

  explain "Now probing each host for NixOS ISO (checking /etc/os-release)..."
  for ip in $CANDIDATES; do
    if OUTPUT=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=3 -o BatchMode=yes root@"$ip" "cat /etc/os-release 2>/dev/null || true" 2>/dev/null); then
      if echo "$OUTPUT" | grep -qi "nixos\|nix"; then
        TARGET_IP="$ip"
        ok "Found NixOS ISO at $ip"
        break
      fi
    fi
  done

  if [[ -z "$TARGET_IP" ]]; then
    warn "Could not auto-detect NixOS ISO from candidates."
    echo ""
    read -rp "  Enter poweredge IP manually: " TARGET_IP
    [[ -n "$TARGET_IP" ]] || fail "No IP provided"
  fi
fi

# Purge any stale known_hosts entry for this IP (e.g. from a previous host)
info "Removing stale SSH host key for ${TARGET_IP} (if any)..."
ssh-keygen -R "$TARGET_IP" 2>/dev/null || true
ok "known_hosts cleaned"

# ─── Step 2: SSH host key → age key ───────────────────────────────────
header "Step 2: Extract SSH host key and convert to age key"

explain "We need poweredge's SSH host key to derive an age key for sops."
explain "Servers use ssh-to-age permanently — the age key is derived from"
explain "the SSH ed25519 host key that nixos-anywhere preserves with --copy-host-keys."

CMD_SSH_KEY="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@${TARGET_IP} cat /etc/ssh/ssh_host_ed25519_key.pub"
approve "Fetch poweredge's SSH public key from the live ISO" \
  ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@"$TARGET_IP" cat /etc/ssh/ssh_host_ed25519_key.pub \
  || fail "Cannot SSH into $TARGET_IP — is the ISO booted with SSH enabled?"

SSH_PUB_KEY=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 root@"$TARGET_IP" cat /etc/ssh/ssh_host_ed25519_key.pub 2>/dev/null)
info "SSH key: $SSH_PUB_KEY"

explain "Converting SSH ed25519 key to age format using ssh-to-age."
explain "This derives an age public key from the SSH host key."
explain "Output format: age1..."

AGE_KEY=$(echo "$SSH_PUB_KEY" | nix-shell -p ssh-to-age --run 'ssh-to-age' 2>/dev/null) \
  || fail "ssh-to-age conversion failed"

ok "Age key: $AGE_KEY"

# ─── Step 3: Get disk IDs ─────────────────────────────────────────────
header "Step 3: Discover disk layout"

explain "Disko needs exact /dev/disk/by-id/ paths to partition correctly."
explain "We'll SSH in, list block devices, and identify:"
explain "  - SSD (smallest disk) → OS root + swap"
explain "  - HDD × 2 (largest pair) → ZFS mirror pool"

approve "List block devices on poweredge" \
  ssh root@"$TARGET_IP" lsblk -ndo NAME,SIZE,TYPE,MODEL

LSBLK_OUTPUT=$(ssh root@"$TARGET_IP" "lsblk -ndo NAME,SIZE,TYPE,MODEL" 2>/dev/null)
info "Block devices:"
echo "$LSBLK_OUTPUT"

# Parse disk info
DISK_INFO=$(ssh root@"$TARGET_IP" "lsblk -ndo NAME,SIZE,TYPE | grep ' disk$'" 2>/dev/null) \
  || fail "Cannot parse disk info"

SSD_NAME=$(echo "$DISK_INFO" | sort -k2 -h | head -1 | awk '{print $1}')
HDD_NAMES=$(echo "$DISK_INFO" | sort -k2 -hr | head -2 | awk '{print $1}' | sort)

approve "Map device names to /dev/disk/by-id/ paths" \
  ssh root@"$TARGET_IP" ls -la /dev/disk/by-id/

SSD_BY_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/${SSD_NAME}$' | awk '{print \$NF}'" 2>/dev/null | head -1)
HDD1_BY_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/$(echo "$HDD_NAMES" | head -1)$' | awk '{print \$NF}'" 2>/dev/null | head -1)
HDD2_BY_ID=$(ssh root@"$TARGET_IP" "ls -la /dev/disk/by-id/ | grep '/dev/$(echo "$HDD_NAMES" | tail -1)$' | awk '{print \$NF}'" 2>/dev/null | head -1)

if [[ -z "$SSD_BY_ID" || -z "$HDD1_BY_ID" || -z "$HDD2_BY_ID" ]]; then
  warn "Auto-detection ambiguous. Please enter manually:"
  echo ""
  echo "  Available by-id paths:"
  ssh root@"$TARGET_IP" "ls /dev/disk/by-id/" 2>/dev/null | sed 's/^/    /'
  echo ""
  read -rp "  SSD by-id (e.g., ata-SAMSUNG_...): " SSD_BY_ID
  read -rp "  HDD1 by-id: " HDD1_BY_ID
  read -rp "  HDD2 by-id: " HDD2_BY_ID
fi

echo ""
ok "Detected disk layout:"
echo "  SSD:  /dev/disk/by-id/${SSD_BY_ID}"
echo "  HDD1: /dev/disk/by-id/${HDD1_BY_ID}"
echo "  HDD2: /dev/disk/by-id/${HDD2_BY_ID}"

# ─── Step 4: Update _disko.nix ────────────────────────────────────────
header "Step 4: Update _disko.nix with real disk IDs"

explain "Replacing placeholder paths in _disko.nix with actual disk IDs."
explain "This tells disko exactly which physical disks to partition."
echo ""
echo "  ${DIM}Changes:${NC}"
echo "    REPLACE_WITH_SSD_ID  → ${SSD_BY_ID}"
echo "    REPLACE_WITH_HDD1_ID → ${HDD1_BY_ID}"
echo "    REPLACE_WITH_HDD2_ID → ${HDD2_BY_ID}"
echo ""
echo "  ${DIM}File: ${DISKO_FILE}${NC}"

approve "Apply disk ID substitutions to _disko.nix" \
  sed -i "s|REPLACE_WITH_SSD_ID|${SSD_BY_ID}|g;s|REPLACE_WITH_HDD1_ID|${HDD1_BY_ID}|g;s|REPLACE_WITH_HDD2_ID|${HDD2_BY_ID}|g" "$DISKO_FILE"

ok "Updated ${DISKO_FILE}"

# ─── Step 5: Update .sops.yaml ────────────────────────────────────────
header "Step 5: Update secrets/.sops.yaml with poweredge age key"

explain "Adding poweredge's age key to the sops config so it can decrypt"
explain "secrets on first boot. We also add a creation rule so sops knows"
explain "which keys to encrypt secrets/poweredge/*.yaml with."

if grep -q "poweredge" "$SOPS_YAML" 2>/dev/null; then
  info "Poweredge key already in .sops.yaml — will update it."
  approve "Replace existing poweredge key in .sops.yaml" \
    sed -i "/&poweredge/c\\  - \\&poweredge ${AGE_KEY}" "$SOPS_YAML"
else
  info "Adding poweredge as a new key to .sops.yaml"

  explain "Adding &poweredge anchor after &erebus in the keys section..."
  approve "Add poweredge age key to .sops.yaml keys section" \
    sed -i "/&erebus/a\\  - \\&poweredge ${AGE_KEY}" "$SOPS_YAML"

  explain "Adding creation rule so sops encrypts poweredge secrets with these keys..."
  cat >> "$SOPS_YAML" <<CREATION_RULE

  # Poweredge — decrypted via SSH host key (ssh-to-age)
  - path_regex: poweredge/.*\\.yaml\$
    key_groups:
      - age:
          - *recovery
          - *traversal
          - *poweredge
CREATION_RULE
  ok "Added creation rule for poweredge secrets"
fi

ok "Updated ${SOPS_YAML}"

echo ""
explain "Committing .sops.yaml early — nixos-anywhere reads it from the flake."
explain "If not committed, sops decryption fails on first boot."

approve "Stage and commit .sops.yaml changes" \
  git -C "$REPO_DIR" add "$SOPS_YAML" && git -C "$REPO_DIR" commit -m "chore(poweredge): add age pubkey to sops config"

# ─── Step 6: Create secrets file ─────────────────────────────────────
header "Step 6: Create secrets for poweredge"

explain "Creating the sops-encrypted secrets file that poweredge will decrypt."
explain "Contains: nextcloud admin password, tailscale auth key."

if [[ -f "$SECRETS_FILE" ]]; then
  info "Secrets file already exists: ${SECRETS_FILE}"
  read -rp "  Overwrite with new secrets? [y/N]: " choice
  [[ "$choice" == "y" || "$choice" == "Y" ]] || { info "Skipping — using existing secrets"; }
fi

if [[ ! -f "$SECRETS_FILE" ]] || [[ "$choice" == "y" ]]; then
  echo ""
  echo -e "  ${BOLD}Nextcloud admin password:${NC}"
  echo "  (Press Enter to auto-generate a random password)"
  read -rsp "  Password: " NC_PASSWORD
  echo ""

  if [[ -z "$NC_PASSWORD" ]]; then
    NC_PASSWORD=$(openssl rand -base64 24)
    echo ""
    ok "Generated password: ${NC_PASSWORD}"
    echo -e "  ${YELLOW}⚠ SAVE THIS — you'll need it to log into Nextcloud${NC}"
  fi

  echo ""
  echo -e "  ${BOLD}Tailscale auth key:${NC}"
  echo "  (Generate at https://login.tailscale.com/admin/settings/keys)"
  echo "  (Reusable, pre-approved recommended)"
  read -rsp "  Auth key (or Enter to skip): " TS_KEY
  echo ""

  mkdir -p "$SECRETS_DIR"
  {
    echo "# poweredge secrets — managed by deploy-poweredge.sh"
    echo "# After deploy, re-encrypt with poweredge's SSH host key:"
    echo "#   sops updatekeys -y ${SECRETS_FILE}"
    echo "nextcloud:"
    echo "  admin-password: ${NC_PASSWORD}"
    echo "tailscale:"
    if [[ -n "$TS_KEY" ]]; then
      echo "  auth-key: ${TS_KEY}"
    else
      echo "  auth-key: tskey-REPLACE_ME"
    fi
  } > "$SECRETS_FILE"

  ok "Created ${SECRETS_FILE}"
fi

# ─── Step 7: nixos-anywhere ──────────────────────────────────────────
header "Step 7: Deploy with nixos-anywhere"

explain "This is the main deployment step. nixos-anywill:"
echo "  1. SSH into poweredge's live NixOS ISO"
echo "  2. Kexec into a NixOS installer environment"
echo "  3. Run disko to partition disks per _disko.nix"
echo "  4. Use nixos-facter to generate hardware config"
echo "  5. Install NixOS with our flake config"
echo "  6. Copy SSH host keys (--copy-host-keys)"
echo "  7. Reboot into the new system"
echo ""
echo -e "  ${BOLD}This takes 10-15 minutes.${NC}"
echo ""

DEPLOY_CMD=(
  nix run github:nix-community/nixos-anywhere --
  --flake ".#${HOSTNAME}"
  --generate-hardware-config nixos-facter "./${FACTER_FILE}"
  --copy-host-keys
  --target-host "root@${TARGET_IP}"
)

echo "  Command that will run:"
echo -e "  ${DIM}${DEPLOY_CMD[*]}${NC}"
echo ""

read -rp "  Ready to deploy? [y/N]: " choice
if [[ "$choice" != "y" && "$choice" != "Y" ]]; then
  warn "Deployment cancelled by user"
  exit 0
fi

echo ""
info "Starting deployment..."
"${DEPLOY_CMD[@]}" \
  || fail "nixos-anywhere deployment failed!"

ok "nixos-anywhere completed successfully!"

# ─── Step 8: Post-deploy verification ────────────────────────────────
header "Step 8: Verify deployment"

explain "Waiting for poweredge to reboot into NixOS..."
explain "This typically takes 1-5 minutes after nixos-anywhere finishes."

RETRIES=0
until ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no likivik@"$TARGET_IP" true 2>/dev/null; do
  RETRIES=$((RETRIES + 1))
  if [[ $RETRIES -gt 30 ]]; then
    fail "Poweredge did not come back after 5 minutes. Check manually."
  fi
  printf "."
  sleep 10
done
echo ""
ok "SSH is up after ~$((RETRIES * 10)) seconds"

# Verify services
for check in \
  "Tailscale|tailscale status" \
  "Nextcloud|systemctl is-active nextcloud" \
  "SOPS secrets|sudo systemctl is-active sops-nix" \
  "Swap|swapon --show" \
; do
  NAME="${check%%|*}"
  CMD="${check##*|}"
  if OUTPUT=$(ssh likivik@"$TARGET_IP" "$CMD" 2>/dev/null); then
    ok "$NAME: $OUTPUT"
  else
    warn "$NAME: not running or not available"
  fi
done

# ─── Step 9: Commit generated files ──────────────────────────────────
header "Step 9: Commit generated files"

explain "nixos-anywhere generated facter.json with real hardware data."
explain "We need to commit this so future rebuilds don't need to re-run facter."

approve "Stage and commit facter.json + disko layout" \
  git -C "$REPO_DIR" add "$FACTER_FILE" "$DISKO_FILE" "$SECRETS_FILE" && \
  git -C "$REPO_DIR" commit -m "feat(poweredge): add hardware config, disk layout, and secrets"

# ─── Done ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PowerEdge deployment complete! 🎉${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo "  Nextcloud:  http://${HOSTNAME}:80"
echo "  SSH:        ssh likivik@${TARGET_IP}"
echo "  Tailscale:  ssh likivik@<poweredge-tailnet-ip>"
echo ""
echo "  If Tailscale isn't connected, SSH in and run:"
echo "    sudo tailscale up"
echo ""
