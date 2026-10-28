#!/usr/bin/env bash
# serenity VM smoke probe - this file runs INSIDE the guest, as root.
#
# It runs as the in-guest oneshot `vmcheck-serenity.service`, whose ExecStart
# redirects stdout/stderr to /dev/ttyS0 (serial-getty@ttyS0 is disabled in
# tests/serenity-smoke.nix for exactly this reason). Everything it needs arrives
# as an environment variable; list-like values are passed as FILE paths because
# systemd word-splits a space-joined Environment entry.
#
# Keep the marker strings stable: the app wrapper in modules/defaults/checks.nix
# greps for SERENITY_SMOKE_PASS and exits non-zero when it is absent.
set -u
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

# Units a QEMU guest cannot possibly run. Every pattern is ANCHORED: the old
# unanchored list granted immunity by substring, so `swap` also masked
# swapfile-cleanup.service, `zfs[^ ]*` also masked my-zfs-checker.service and
# `tailscale[^ ]*` also masked tailscale-helper.service. Unit names below were
# read from the deployed config
# (`nix eval .#nixosConfigurations.serenity.config.systemd.units`), not guessed.
#
# Evidence per pattern:
#   boot.mount          host ESP; the guest mounts its own root, no /boot
#   dev-disk-by*.swap   the host's swap device does not exist in QEMU
#   display-manager     no DRM device
#   nvidia-*            no NVIDIA device
#   zpool-*, zfs-*      no real pool: zfs-import-gitpool cannot import one
#   tailscale*          no tailnet and no auth key (tailscale is disabled)
#   v2raya              TUN-mode VLESS needs the tailnet route
#
# Removed because no such unit exists anywhere in this repo (the patterns only
# inflated the list): panther.mount, Storage.mount, Storage-Git.mount, krfb,
# krdp, mullvad-daemon, wg-quick*, wireguard*, forgejo-backup*.
ALLOW_PATTERNS=(
  'boot\.mount'
  'dev-disk-by.*\.swap'
  'display-manager\.service'
  'nvidia-[a-z0-9_.@-]+\.service'
  'zpool-[a-z0-9_.@-]+\.(service|target|timer)'
  'zfs-[a-z0-9_.@-]+\.(service|target|timer)'
  'tailscale[a-z0-9_.@-]*\.service'
  'v2raya\.service'
)
ALLOW_UNITS="^($(IFS='|'; echo "${ALLOW_PATTERNS[*]}"))\$"
FAILED_UNITS=$(timeout 20 systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | grep -v '^$' || true)
BAD=$(printf '%s\n' "$FAILED_UNITS" | grep -Ev "$ALLOW_UNITS" | tr '\n' ' ' || true)

# Report what the allowlist hides on THIS boot instead of swallowing it, and
# name the reason systemd recorded. A skipped-by-condition unit is expected; a
# unit that failed with ConditionResult=yes is a real breakage the allowlist
# used to mute.
ALLOWED_FAILED=$(printf '%s\n' "$FAILED_UNITS" | grep -E "$ALLOW_UNITS" || true)
if [ -n "${ALLOWED_FAILED// /}" ]; then
  echo "--- allowlisted failures on this boot ---"
  while IFS= read -r u; do
    [ -n "$u" ] || continue
    CR=$(timeout 10 systemctl show -p ConditionResult --value "$u" 2>/dev/null || echo '?')
    RES=$(timeout 10 systemctl show -p Result --value "$u" 2>/dev/null || echo '?')
    echo "  ALLOWLISTED_FAILURE: $u (ConditionResult=$CR Result=$RES)"
  done <<ALLOWED
$ALLOWED_FAILED
ALLOWED
fi

# Rot detection: a pattern that matched nothing has usually outlived the unit it
# was written for. Informational, not fatal - a timer-driven unit may only fail
# on some boots.
for pat in "${ALLOW_PATTERNS[@]}"; do
  printf '%s\n' "$FAILED_UNITS" | grep -Eq "^${pat}\$" || echo "  ALLOWLIST_UNUSED: ${pat}"
done
if [ -n "${BAD// /}" ]; then
  echo "UNEXPECTED_FAILED_UNITS: $BAD"
  # Report WHY, not just which. Without this a failed system unit is a bare
  # name, and "is this my change or the environment?" becomes unanswerable from
  # the gate's own output - the same blindness that let a user-unit failure go
  # unreported earlier.
  for u in $BAD; do
    echo "--- why $u failed ---"
    timeout 15 systemctl status "$u" --no-pager -l 2>&1 | head -14 || true
    timeout 15 journalctl -u "$u" -n 25 --no-pager 2>&1 | tail -25 || true
  done
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
for u in hermes-dashboard; do
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

echo "--- hermes version (install stamp -> CLI; upstream #130070 / #135217) ---"
# Regression gate for the stamp-based version. v0.21.7 moved pyproject.toml to the
# `0.0.0` placeholder (upstream #102765) and the CLI now reads baseVersion from
# install-stamp.json; Nix sources keep no .git, so upstream's flake stamps 0.0.0
# unless the package is told the version. The aspect passes it explicitly — if that
# override is ever dropped, this reports 0.0.0 and fails the gate.
# ⚠ keep the literal below in sync with the hermes-agent input tag.
HV=$(timeout 60 sudo -u hermes HOME=/var/lib/hermes HERMES_HOME=/var/lib/hermes/.hermes \
  /run/current-system/sw/bin/hermes -V 2>&1 | head -1)
echo "  ${HV:-<no output>}"
case "$HV" in
  *v0.21.7*) echo "HERMES_VERSION_OK" ;;
  *) echo "HERMES_VERSION_BAD: ${HV:-<no output>}"; FAILED=1 ;;
esac
# The date in parentheses is hermes_cli.__release_date__, a checked-in literal that
# no release since v2026.9.24 has bumped (upstream #135217). Expected stale here; it
# becomes stamp-derived when upstream #135223 lands. Not gated — upstream's bug.
echo "  (parenthesised date is expected stale until upstream #135223)"

echo "--- secret pipeline: no present-but-empty assignments in unit env files ---"
# A present-but-empty assignment in a LATER EnvironmentFile silently overrides
# the real value from an earlier one — systemd only lets a later file win for
# keys it actually defines. 2026-10-14: a switch left TELEGRAM_BOT_TOKEN= in
# sops-env, the gateway came up with no bot credential, and Telegram was dead
# for ~11h until a plain restart.
EMPTY_FILES=""
MISSING_FILES=""
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if [ ! -r "$f" ]; then
    # Tracked separately from a blank assignment: both are fatal, but "the file
    # is not there" and "the file defines an empty key" have entirely different
    # causes, and lumping them under one label sends you down the wrong path.
    MISSING_FILES="$MISSING_FILES $f"
    continue
  fi
  bad=$(grep -nE '^[A-Za-z_][A-Za-z0-9_]*=$' "$f" 2>/dev/null || true)
  if [ -n "$bad" ]; then
    echo "  EMPTY ASSIGNMENT in $f:"
    echo "$bad" | sed 's/^/    /'
    EMPTY_FILES="$EMPTY_FILES $f"
  fi
done < "$SMOKE_ENV_FILES"
if [ -n "${MISSING_FILES// /}" ]; then
  echo "ENV_FILE_MISSING:$MISSING_FILES"
  FAILED=1
fi
if [ -n "${EMPTY_FILES// /}" ]; then
  echo "ENV_EMPTY_ASSIGNMENT_BAD:$EMPTY_FILES"
  FAILED=1
fi
if [ -z "${MISSING_FILES// /}${EMPTY_FILES// /}" ]; then
  echo "ENV_NO_EMPTY_ASSIGNMENTS_OK"
fi

echo "--- secret pipeline: provisioned by a systemd unit, not activation ---"
# Proves the mode switch took effect AND that the dummy age key was placed
# before the unit ran. With useSystemdActivation=false this unit does not exist
# at all (sops decrypts inside the `setupSecrets` activation script), so
# "absent" here means the host silently went back to activation-time
# provisioning — which is the ordering gap this change exists to close.
SOPS_STATE=$(systemctl is-active sops-install-secrets.service 2>/dev/null || true)
if [ "$SOPS_STATE" = "active" ]; then
  echo "SOPS_SYSTEMD_ACTIVATION_OK"
  # The ordering is the whole point, so assert it rather than assume it: our key
  # unit must appear in the consumer's After=.
  ORD=$(systemctl show -p After sops-install-secrets.service --value 2>/dev/null | tr ' ' '\n' | grep -c 'smoke-age-key' || true)
  if [ "${ORD:-0}" -ge 1 ]; then
    echo "  ordering asserted: smoke-age-key.service is in After= (${ORD})"
  else
    echo "SOPS_KEY_ORDERING_BAD: smoke-age-key.service is not in sops-install-secrets' After="
    FAILED=1
  fi
else
  echo "SOPS_SYSTEMD_ACTIVATION_BAD: sops-install-secrets.service is '${SOPS_STATE:-absent}'"
  # Report WHY. An inactive sops-install-secrets installs NO secrets, so every
  # downstream symptom (missing files, gateway with no token) is a consequence —
  # and "inactive" rather than "failed" usually means a Requires= dependency
  # failed, which points somewhere else entirely.
  for u in sops-install-secrets smoke-age-key; do
    echo "--- $u ---"
    timeout 15 systemctl status "$u" --no-pager -l 2>&1 | head -10 || true
    timeout 15 journalctl -u "$u" -n 20 --no-pager 2>&1 | tail -20 || true
  done
  FAILED=1
fi

echo "--- secret pipeline: the sops template rendered every key non-empty ---"
# Keys come from the EVALUATED template content the host passed in, so adding a
# key extends this automatically — no hand-list to rot.
#
# sops-nix renders this file in the SAME sops-install-secrets pass that installs
# the secrets, and refuses to proceed when a placeholder has no matching secret.
# So a missing or blank key here means the file was NOT produced by sops-nix —
# e.g. someone reintroduced a hand-written generator, which is precisely the
# 2026-10-14 bug (a `cat` that failed wrote `KEY=`).
RENDERED="${SMOKE_RENDERED_ENV:-}"
if [ ! -r "$RENDERED" ]; then
  echo "RENDERED_ENV_MISSING: ${RENDERED:-<unset>}"
  FAILED=1
else
  echo "  rendered: $RENDERED ($(grep -c . "$RENDERED" 2>/dev/null || echo 0) assignments)"
  MISSING=""
  BLANK=""
  while IFS= read -r k; do
    [ -n "$k" ] || continue
    n=$(grep -cE "^${k}=" "$RENDERED" 2>/dev/null || true)
    if [ "${n:-0}" -eq 0 ]; then
      MISSING="$MISSING $k"
      continue
    fi
    v=$(grep -E "^${k}=" "$RENDERED" | head -1 | cut -d= -f2-)
    [ -n "$v" ] || BLANK="$BLANK $k"
  done < "$SMOKE_EXPECTED_KEYS"
  if [ -n "${MISSING// /}${BLANK// /}" ]; then
    [ -n "${MISSING// /}" ] && echo "RENDERED_ENV_KEY_MISSING:$MISSING"
    [ -n "${BLANK// /}" ] && echo "RENDERED_ENV_KEY_BLANK:$BLANK"
    FAILED=1
  else
    echo "RENDERED_ENV_ALL_KEYS_NONEMPTY_OK"
  fi
fi

echo "--- secret pipeline: gateway credential delivery ---"
# The guest does a REAL (dummy) sops round-trip, so delivery is asserted rather
# than stubbed — a stubbed env file is non-empty by construction, which is why
# this used to be impossible to test here. The gateway process must hold the
# dummy token:
#   blank  -> the 2026-10-14 incident signature
#   absent -> the unit never loaded the rendered file at all
#   other  -> something delivered a value sops did not render
GW_PID=""
TOK=""
for _i in $(seq 1 12); do
  GW_PID=$(timeout 15 sudo -u hermes XDG_RUNTIME_DIR="/run/user/$UID_H" systemctl --user show -p MainPID --value hermes-gateway 2>/dev/null || true)
  if [ -n "$GW_PID" ] && [ "$GW_PID" != 0 ] && [ -r "/proc/$GW_PID/environ" ]; then
    TOK=$(tr '\0' '\n' < "/proc/$GW_PID/environ" | grep -E '^TELEGRAM_BOT_TOKEN=' | head -1 | cut -d= -f2-)
    [ -n "$TOK" ] && break
  fi
  sleep 5
done
if [ -z "$GW_PID" ] || [ "$GW_PID" = 0 ]; then
  echo "GATEWAY_PID_UNAVAILABLE"
  FAILED=1
elif [ -z "$TOK" ]; then
  if tr '\0' '\n' < "/proc/$GW_PID/environ" | grep -qE '^TELEGRAM_BOT_TOKEN=$'; then
    echo "GATEWAY_CREDENTIAL_IN_ENV_BLANK: gateway holds an EMPTY TELEGRAM_BOT_TOKEN"
  else
    echo "GATEWAY_CREDENTIAL_IN_ENV_ABSENT: gateway never loaded the rendered env file"
  fi
  FAILED=1
elif [ "$TOK" = "${SMOKE_DUMMY_VALUE:-}" ]; then
  echo "GATEWAY_CREDENTIAL_DELIVERED_OK"
else
  echo "GATEWAY_CREDENTIAL_UNEXPECTED: non-empty token that is not the rendered dummy value"
  FAILED=1
fi

echo "--- summary ---"
timeout 20 systemctl list-units --type=service --state=running --no-legend --plain 2>/dev/null | wc -l | sed 's/^/running services: /'
timeout 20 systemctl list-units --type=service --no-legend --plain 2>/dev/null | wc -l | sed 's/^/loaded services:  /'

# A degraded system with nothing in the failed list means a unit is spinning in
# auto-restart: "degraded" alone is not a good state, it is an unclassified one.
if [ "$ST" = degraded ] && [ -z "${BAD// /}${ALLOWED_FAILED// /}" ]; then
  echo "SYSTEM_DEGRADED_WITHOUT_FAILED_UNITS: nothing failed, so something is auto-restarting"
  FAILED=1
fi

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
