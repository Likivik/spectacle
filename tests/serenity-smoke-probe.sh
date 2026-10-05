#!/usr/bin/env bash
# serenity VM smoke probe - this file runs INSIDE the guest, as root.
#
# The host pipes it into the guest's `smoke-shell` socket (a systemd unit with
# StandardInput=socket -> `bash -s`), which QEMU forwards from 127.0.0.1:2222.
# The host prepends EXPECTED_UNITS="..." before this body, because `bash -s`
# cannot take arguments.
#
# Keep the marker strings stable: the app greps for them.
set -u
EXPECTED_UNITS="${EXPECTED_UNITS:-}"
FAILED=0

echo "=== SERENITY_SMOKE_START (in-guest probe) ==="
echo "guest: $(cat /etc/hostname) $(uname -r) at $(date '+%H:%M:%S')"

echo "--- settling (max 120s, heartbeat every 20s) ---"
# This probe is wantedBy multi-user.target, so multi-user cannot report "running"
# until the probe FINISHES. Waiting on `is-system-running` therefore always burns
# the full timeout. The honest signal is "nothing is in flight except us".
ST=unknown
for i in $(seq 1 60); do
  ST=$(timeout 10 systemctl is-system-running 2>/dev/null || echo probe-timeout)
  if [ "$ST" = running ] || [ "$ST" = degraded ]; then break; fi
  # Not worth waiting for: the llama services need a GPU (the host runs them with
  # -ngl 99, there is none in QEMU), and targets only complete once everything
  # they order has - including this probe.
  BENIGN='vmcheck-serenity.service|llama-embedder.service|llama-reranker.service|multi-user.target|graphical.target|timers.target|zfs-scrub.timer'
  OTHERS=$(timeout 10 systemctl list-jobs --no-legend --plain 2>/dev/null \
    | awk '{print $1}' | grep -v '^$' | grep -Ev "^($BENIGN)$" | wc -l)
  if [ "$OTHERS" -eq 0 ]; then
    echo "  no jobs in flight except this probe"
    break
  fi
  if [ $((i % 10)) -eq 0 ]; then echo "  settle[$i]: state=$ST jobs_other=$OTHERS"; fi
  sleep 2
done
echo "system state: $ST"
if [ "$ST" != running ] && [ "$ST" != degraded ]; then
  echo "--- jobs still in flight (candidates for the allowlist) ---"
  timeout 15 systemctl list-jobs --no-legend --plain 2>/dev/null | head -20 || true
fi

echo "--- FAILED system units ---"
timeout 20 systemctl --failed --no-legend --plain || true

# Units a QEMU guest cannot possibly run: host disks/mounts, zpools, GPU, TPM
# secrets, display/remote-desktop, and the LAN-only helpers.
#   tailscale-serve-*      - needs a tailnet (tailscale itself is off here)
#   forgejo-backup         - nightly dump shipped to poweredge over the tailnet;
#                            timer-driven, so it only fails on some boots (flake)
ALLOW='boot\.mount|panther\.mount|Storage\.mount|Storage-Git\.mount|swap|zfs[^ ]*|zpool[^ ]*|nvidia[^ ]*|display-manager|krfb|krdp|tailscale[^ ]*|v2raya|mullvad|wg-quick[^ ]*|wireguard[^ ]*|forgejo-backup[^ ]*'
BAD=$(timeout 20 systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | grep -v '^$' | grep -Ev "$ALLOW" | tr '\n' ' ' || true)
if [ -n "${BAD// /}" ]; then
  echo "UNEXPECTED_FAILED_UNITS: $BAD"
  FAILED=1
else
  echo "no unexpected system failures"
fi

echo "--- hermes user / linger / user manager ---"
if id hermes >/dev/null 2>&1; then echo "hermes user present"; else echo "NO_HERMES_USER"; FAILED=1; fi
UID_H=$(id -u hermes 2>/dev/null || echo 0)
if [ -e /var/lib/systemd/linger/hermes ]; then echo "LINGER_OK"; else echo "LINGER_MISSING"; FAILED=1; fi
if [ -e "/run/user/$UID_H/bus" ]; then echo "USER_BUS_OK"; else echo "USER_BUS_MISSING"; FAILED=1; fi
timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user is-system-running 2>/dev/null || echo "user-manager: not reachable yet"

# Source of truth is the INSTALLED unit set, not a list passed in: the previous
# version read $EXPECTED_UNITS unquoted, bash word-split the space-separated
# list, and only the first entry (dbus) survived - so the "all expected user
# units present" assertion was vacuous and the gateway's real state was never
# checked. Anything the host installs into /etc/systemd/user is now reported.
echo "--- installed user units (/etc/systemd/user) and their state ---"
INSTALLED=$(ls /etc/systemd/user 2>/dev/null | sed -n 's/^\(.*\)\.service$/\1/p')
echo "installed service units: $(echo $INSTALLED | wc -w)"
# No user-unit allowlist. maid-activation used to fail here (and on the live host)
# with status=127 because all-maid had no nix-maid-hermes bundle; users.users.hermes
# now declares an empty `maid = { }`, so the bundle exists and the unit is a no-op.
# It is gated for real now - a regression must show up as a failure.
USER_ALLOW=''
USER_FAILED=""
for u in $INSTALLED; do
  S=$(timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user is-active "$u" 2>/dev/null || true)
  E=$(timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user is-enabled "$u" 2>/dev/null || true)
  echo "  $u -> ${S:-unknown} (${E:-?})"
  case "$S" in
    failed)
      case " $USER_ALLOW " in
        *" $u "*) echo "    (allowlisted known live failure: $u)" ;;
        *) USER_FAILED="$USER_FAILED $u" ;;
      esac
      ;;
  esac
done
if [ -n "${USER_FAILED// /}" ]; then
  echo "USER_UNITS_FAILED:$USER_FAILED"
  for u in $USER_FAILED; do
    echo "--- why $u is not running ---"
    timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user status "$u" --no-pager -l 2>&1 | head -10 || true
    timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" journalctl --user-unit "$u" -n 10 --no-pager 2>&1 | tail -10 || true
  done
  FAILED=1
else
  echo "no failed user units"
fi

echo "--- critical hermes units (state matters for a reboot) ---"
for u in hermes-gateway graphiti-mcp; do
  S=$(timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user is-active "$u" 2>/dev/null || true)
  echo "  $u -> ${S:-unknown}"
  if [ "$S" != active ]; then
    timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user status "$u" --no-pager -l 2>&1 | sed -n '2,8p' || true
  fi
  [ "$S" = active ] || USER_FAILED="$USER_FAILED $u"
done

# These two need the real thing (secrets / HERMES_HOME state) and cannot succeed in
# a guest; both were verified healthy on the live host. Require only that they are
# not outright failed - a guest will show them activating/auto-restart, which is
# exactly what a missing secret produces.
#   hermes-gateway-salem  guest: 78 (EX_CONFIG)  host: active, NRestarts=0
#   hermes-dashboard      guest: 1 (FAILURE)     host: active, NRestarts=0, webui 302
for u in hermes-gateway-salem hermes-dashboard; do
  S=$(timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user is-active "$u" 2>/dev/null || true)
  echo "  $u -> ${S:-unknown} (guest: needs real secrets/state; host: active)"
  case "$S" in
    failed) echo "CRITICAL_USER_UNIT_FAILED: $u"; USER_FAILED="$USER_FAILED $u" ;;
  esac
done

echo "--- FAILED user units ---"
timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user --failed --no-legend --plain 2>/dev/null || true

echo "--- CRON PRIMITIVE: systemd-run --user --scope as hermes (upstream #111484) ---"
if timeout 20 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemd-run --user --scope --collect /run/current-system/sw/bin/true; then
  echo "CRON_SCOPE_OK"
else
  echo "CRON_SCOPE_FAIL"
  FAILED=1
fi

echo "--- hermes gateway unit definition ---"
GW=$(readlink -f /etc/systemd/user/hermes-gateway.service 2>/dev/null)
if [ -n "$GW" ] && [ -f "$GW" ]; then
  grep -E "ConditionUser=|ExecStart=|EnvironmentFile=" "$GW" | head -4
  echo "GATEWAY_UNIT_OK"
else
  echo "GATEWAY_UNIT_NOT_FOUND"
  FAILED=1
fi

echo "--- summary ---"
timeout 20 systemctl list-units --type=service --state=running --no-legend --plain 2>/dev/null | wc -l | sed 's/^/running services: /'
timeout 20 systemctl list-units --type=service --no-legend --plain 2>/dev/null | wc -l | sed 's/^/loaded services:  /'

# The critical-unit checks above append to USER_FAILED after the block that raises
# FAILED, so re-check it here - otherwise a non-active hermes unit cannot fail the
# gate at all.
if [ -n "${USER_FAILED// /}" ]; then
  echo "USER_UNITS_FAILED_TOTAL:$USER_FAILED"
  FAILED=1
fi

if [ "$FAILED" = 0 ]; then echo "SERENITY_SMOKE_PASS"; else echo "SERENITY_SMOKE_FAIL"; fi
echo "=== SERENITY_SMOKE_END ==="

# Shut the guest down so QEMU exits and `nix run .#serenity-smoke` returns.
# This was lost when the probe moved into its own file, so VMs outlived their
# runs and held the qcow2 against the next one.
sync
timeout 15 systemctl poweroff 2>/dev/null || true
