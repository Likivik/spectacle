#!/usr/bin/env bash
# poweredge VM smoke probe — runs INSIDE the guest, as root.
#
# Runs as the oneshot `vmcheck-poweredge.service`, whose ExecStart redirects
# stdout/stderr to /dev/ttyS0 (serial-getty@ttyS0 is disabled in
# tests/poweredge-smoke.nix for exactly that reason). List-like inputs arrive as
# FILE paths, because systemd word-splits a space-joined Environment entry.
#
# Keep the marker strings stable: the app wrapper greps POWEREDGE_SMOKE_PASS and
# exits non-zero when it is absent, because the guest powers itself off — QEMU
# therefore exits 0 even for a red gate.
set -u
FAILED=0

fail() { printf 'POWEREDGE_SMOKE_FAIL %s: %s\n' "$1" "$2"; FAILED=$((FAILED + 1)); }
ok() { printf 'POWEREDGE_SMOKE_OK %s\n' "$1"; }
warn() { printf 'POWEREDGE_SMOKE_WARN %s\n' "$1"; }
sub() { printf '\n== %s\n' "$1"; }

echo "=== POWEREDGE_SMOKE_START (in-guest probe) ==="
echo "guest: $(cat /etc/hostname 2>/dev/null) $(uname -r) at $(date '+%H:%M:%S')"

# ── settling ────────────────────────────────────────────────────────────────
# This probe is wantedBy multi-user.target, so multi-user cannot report "running"
# until the probe FINISHES: `systemctl is-system-running --wait` is a guaranteed
# self-deadlock. Measured once: 30 minutes of silence after "== boot", then the
# VM timeout killed QEMU. The honest signal is "nothing is in flight except us".
sub "settling (max 120s, heartbeat every 20s)"
ST=unknown
BENIGN='vmcheck-poweredge.service|multi-user.target|timers.target|sops-install-secrets.service'
# The signal is multi-user.target being ACTIVE, not "no other jobs": the first run
# asserted while the system was still `starting` (jobs hidden behind the target's
# own job), so every assertion after this point ran against a half-booted host.
for i in $(seq 1 90); do
    if systemctl is-active --quiet multi-user.target; then
        echo "  multi-user.target active after ~$((i * 2))s"
        break
    fi
    OTHERS=$(timeout 10 systemctl list-jobs --no-legend --plain 2>/dev/null \
        | awk '{print $1}' | grep -v '^$' | grep -Ev "^($BENIGN)$" | wc -l)
    if [ $((i % 10)) -eq 0 ]; then
        echo "  settle[$i]: state=$(timeout 5 systemctl is-system-running 2>/dev/null) jobs_other=$OTHERS"
    fi
    sleep 2
done
ST=$(timeout 10 systemctl is-system-running 2>/dev/null || echo probe-timeout)
echo "system state: $ST"
case "$ST" in
    running) ok "system state running" ;;
    degraded) ok "system state degraded (a unit failed; see below)" ;;
    *)
        fail boot "system state is '$ST' after 120s"
        echo "--- jobs still in flight --"
        timeout 15 systemctl list-jobs --no-legend --plain 2>/dev/null | head -20 || true
        ;;
esac

# multi-user.target is asserted explicitly: a unit stuck in `activating` is
# neither `failed` nor caught by an exit-code check, and that is how the
# couchdb-init wedge on this host stayed invisible (docs/smoke-gates-verdict-2026.md §2.6).
if systemctl is-active --quiet multi-user.target; then
    ok "multi-user.target active"
else
    fail boot "multi-user.target is not active ($(systemctl is-active multi-user.target 2>&1))"
fi

# ── failed units: anchored allowlist, with evidence ─────────────────────────
# From docs/smoke-gates-verdict-2026.md §2.3 and §4.2: an unanchored pattern grants
# immunity by substring (`zfs[^ ]*` also masked my-zfs-checker.service), and a stale
# entry that silently accepts a real failure is worse than no allowlist. Every entry
# is a unit a QEMU guest cannot run, with the reason next to it.
# EMPTY on purpose, and it must stay that way unless a boot earns an entry.
#
# Run 5 had four entries (zfs-import-tank, qdrant, podman-collabora-code,
# tailscale-serve) and every one of them matched nothing: disabling those units in
# tests/poweredge-smoke.nix removed the failures outright. A disabled unit cannot
# fail, while an allowlist pattern grants immunity to a name forever — so disable
# first, and only allowlist what cannot be disabled, with the observation written
# next to the entry.
ALLOW_ANCHORED=(
    # Container-backed units. `virtualisation.oci-containers.containers = mkForce {}`
    # did NOT remove them (they come from the host's own container declarations via
    # den and are linked into /etc/systemd/system), and `systemd.services.<n>.enable`
    # does not apply either — both were tried. They sit in `activating` because no
    # image store exists in the guest. Cost: container definitions are NOT covered.
    # Timing-dependent: whichever container unit happens to be retrying when the
    # probe runs lands in `activating`. All four are the same class, so all four are
    # named — covering them individually is how qdrant slipped through a green run.
    '^nextcloud-mcp\.service$'
    '^immich-server\.service$'
    '^qdrant\.service$'
    '^podman-collabora-code\.service$'
)
MATCHED_ALLOW=""
unit_allowed() {
    local u="$1" p
    MATCHED_ALLOW=""
    for p in "${ALLOW_ANCHORED[@]}"; do
        if printf '%s' "$u" | grep -Eq "$p"; then MATCHED_ALLOW="$p"; return 0; fi
    done
    return 1
}

sub "failed units"
FAILED_UNITS=$(timeout 20 systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}')
: > /tmp/allow-used
if [ -z "$FAILED_UNITS" ]; then
    ok "no failed units"
else
    for u in $FAILED_UNITS; do
        if unit_allowed "$u"; then
            # Three verdicts, not two: a unit skipped by a Condition* is inactive
            # with Result=success — a clean skip, not a failure.
            STATE=$(timeout 10 systemctl show -p ActiveState -p Result -p ConditionResult --value "$u" 2>/dev/null | paste -sd' ' -)
            echo "ALLOWLISTED_FAILURE: $u ($STATE) via $MATCHED_ALLOW"
            printf '%s\n' "$MATCHED_ALLOW" >> /tmp/allow-used
        else
            fail units "failed unit outside the allowlist: $u (Result=$(systemctl show -p Result --value "$u" 2>/dev/null))"
            timeout 10 systemctl status --no-pager --full "$u" 2>&1 | head -10
            echo "--- journal $u (last 25) ---"
            timeout 15 journalctl -u "$u" --no-pager -n 25 2>&1 | tail -25
        fi
    done
fi

sub "units stuck activating"
# A unit that never completes start holds a job and blocks whatever orders after
# it. This is poweredge's failure class (couchdb-init), not serenity's.
STUCK=$(timeout 20 systemctl list-units --state=activating,reloading --no-legend --plain 2>/dev/null \
    | awk '{print $1}' | grep -v '^$' | grep -v '^vmcheck-poweredge\.service$')
if [ -z "$STUCK" ]; then
    ok "nothing stuck in activating/reloading"
else
    for u in $STUCK; do
        if unit_allowed "$u"; then
            echo "ALLOWLISTED_ACTIVATING: $u via $MATCHED_ALLOW"
            printf '%s\n' "$MATCHED_ALLOW" >> /tmp/allow-used
        else
            fail stuck "$u is activating"
        fi
    done
fi

sub "allowlist hygiene"
UNUSED=0
for p in "${ALLOW_ANCHORED[@]}"; do
    if ! grep -qxF "$p" /tmp/allow-used 2>/dev/null; then
        echo "ALLOWLIST_UNUSED: $p"
        UNUSED=$((UNUSED + 1))
    fi
done
if [ "$UNUSED" -eq 0 ]; then
    ok "every allowlist pattern matched a unit"
else
    warn "$UNUSED allowlist pattern(s) matched nothing — dead weight that will hide a real failure later"
fi
rm -f /tmp/allow-used

# ── poweredge's own historical failure modes ────────────────────────────────
sub "poweredge-specific units"
if systemctl list-unit-files 2>/dev/null | grep -q '^couchdb-init'; then
    fail units "couchdb-init.service exists — it wedged a deploy by never completing start"
else
    ok "couchdb-init.service absent"
fi
for u in nginx.service sshd.service; do
    if systemctl is-active --quiet "$u"; then ok "$u active"; else fail units "$u is $(systemctl is-active "$u" 2>&1)"; fi
done

# ── nextcloud ───────────────────────────────────────────────────────────────
sub "nextcloud"
for u in phpfpm-nextcloud.service nextcloud-setup.service; do
    ACT=$(systemctl is-active "$u" 2>&1)
    RES=$(systemctl show -p Result --value "$u" 2>/dev/null)
    if [ "$ACT" = active ] || [ "$RES" = success ]; then ok "$u ok ($ACT)"; else fail nextcloud "$u is $ACT"; fi
done
if curl -sSf -o /dev/null http://127.0.0.1/login; then ok "GET /login"; else fail nextcloud "GET /login failed"; fi
# Called directly, as root: that is what nixpkgs' own nextcloud tests do
# (nixos/tests/nextcloud/default.nix: nextcloud.succeed("nextcloud-occ status")).
# `sudo -u www-data` was my invention and failed with "unknown user www-data".
OCC=$(command -v nextcloud-occ || echo /run/current-system/sw/bin/nextcloud-occ)
OCC_OUT=$($OCC status 2>&1); OCC_RC=$?
if [ "$OCC_RC" -eq 0 ]; then ok "occ status"; else fail nextcloud "occ status failed (rc=$OCC_RC): $(printf '%s' "$OCC_OUT" | head -2 | tr '\n' ' ')"; fi
# exit code, not just grep: occ prints its listing before failing, which is how this
# check passed while occ itself was exiting non-zero.
APP_OUT=$($OCC app:list 2>&1); APP_RC=$?
if [ "$APP_RC" -eq 0 ] && printf '%s' "$APP_OUT" | grep -q 'ocrflow'; then
    ok "app ocrflow enabled"
else
    fail nextcloud "app ocrflow not enabled (occ rc=$APP_RC)"
fi

# ── panel ───────────────────────────────────────────────────────────────────
sub "ocrflow app wiring"
# `/settings/user/ocrflow` is a WEB-UI route: Nextcloud answers 401 to Basic auth there
# and expects a session, so probing it proved nothing about the app (it 401'd even
# when everything was installed). What is actually assertable without a browser:
# the app resolves on disk, its panel bundle is served, and the owner of the secret
# is written into the app config.
OCC=$(command -v nextcloud-occ || echo /run/current-system/sw/bin/nextcloud-occ)
APP_PATH=$($OCC app:getpath ocrflow 2>/dev/null)
if [ -n "$APP_PATH" ] && [ -f "$APP_PATH/appinfo/info.xml" ]; then
    ok "app path resolves ($APP_PATH)"
else
    fail panel "occ app:getpath ocrflow returned '$APP_PATH'"
fi
# The bundle is asserted ON DISK: it ships inside the app package, and static app
# assets are nginx's business, not the cutover's. (A 404 here earlier said nothing
# about the app — the file is served from the app dir, not /apps/... unconditionally.)
if [ -n "$APP_PATH" ] && [ -f "$APP_PATH/js/ocrflow-panel.js" ]; then
    ok "panel bundle ships with the app ($(wc -c <"$APP_PATH/js/ocrflow-panel.js") bytes)"
else
    fail panel "panel bundle missing at ${APP_PATH:-?}/js/ocrflow-panel.js"
fi
# Length only — the value must never reach the serial log.
SECRET_LEN=$($OCC config:app:get ocrflow worker_secret 2>/dev/null | tr -d '\n' | wc -c)
if [ "$SECRET_LEN" -gt 0 ]; then
    ok "app config holds worker_secret (${SECRET_LEN} chars)"
else
    fail panel "app config worker_secret is empty — the seeding oneshot did not run"
fi

# ── secret chain, app side ──────────────────────────────────────────────────
sub "worker secret chain (app side)"
# From the unit FILE, not `systemctl show -p LoadCredential`: show returned empty here
# for a unit whose file has all three entries, and a gate must not invent failures.
UNITS_CREDS=$(systemctl cat ocrflow-worker.service 2>/dev/null | sed -n 's/^LoadCredential=//p')
SECRET_FILE=$(printf '%s\n' "$UNITS_CREDS" | sed -n 's/^ocrflow-worker-secret://p' | head -1)
if [ -z "$SECRET_FILE" ]; then
    fail secretchain "could not resolve the worker secret path from LoadCredential"
else
    HDR=$(mktemp)
    {
        printf 'header = "OCS-APIRequest: true"\n'
        printf 'header = "X-OcrFlow-Worker: poweredge-smoke"\n'
        printf 'header = "X-OcrFlow-Secret: %s"\n' "$(cat "$SECRET_FILE" 2>/dev/null)"
    } > "$HDR"
    CODE=$(curl -sS -K "$HDR" -o /tmp/status.json -w '%{http_code}' \
        -X POST "http://127.0.0.1/ocs/v2.php/apps/ocrflow/api/v1/queue/next" 2>/dev/null || echo 000)
    rm -f "$HDR"
    # 200 = a job was handed out; 204 = no job in the queue. Both mean the secret
    # was ACCEPTED. 401/403 is the rejection this assertion exists for.
    if [ "$CODE" = "200" ] || [ "$CODE" = "204" ]; then
        ok "worker plane accepts the delivered secret (queue/next $CODE)"
    else
        # Redact, do not suppress: ocs.meta.message separates "invalid secret"
        # (rotation / fast-cache) from "maintenance" from "app disabled", so a gate
        # that hides it cannot be acted on. Secret substituted out of a 300-char body.
        BODY=$(head -c 300 /tmp/status.json 2>/dev/null | tr -d '\n')
        SV=$(cat "$SECRET_FILE" 2>/dev/null)
        if [ -n "$SV" ]; then BODY=$(printf '%s' "$BODY" | sed "s|$SV|[REDACTED]|g"); fi
        fail secretchain "POST queue/next with the delivered secret -> $CODE body: $BODY"
        unset SV
    fi
    rm -f /tmp/status.json
fi

# ── secret rendering (all declared secrets) ─────────────────────────────────
sub "secret rendering"
SRC=${SMOKE_SECRETS:-}
if [ -z "$SRC" ] || [ ! -s "$SRC" ]; then
    fail secrets "expected secret list missing ($SRC)"
else
    MISSING=0
    while read -r name; do
        [ -z "$name" ] && continue
        p="$name"
        case "$name" in /*) ;; *) p="/run/secrets/$name" ;; esac
        if [ ! -s "$p" ]; then
            fail secrets "secret '$name' missing or empty at $p"
            MISSING=$((MISSING + 1))
        fi
    done <"$SRC"
    [ "$MISSING" -eq 0 ] && ok "every declared secret rendered non-empty"
fi

# ── worker ──────────────────────────────────────────────────────────────────
sub "ocrflow worker"
if systemctl is-active --quiet ocrflow-worker.service; then
    ok "ocrflow-worker active"
else
    fail worker "ocrflow-worker is $(systemctl is-active ocrflow-worker.service 2>&1)"
    systemctl status --no-pager --full ocrflow-worker.service 2>&1 | head -15
fi
CREDS=$(systemctl cat ocrflow-worker.service 2>/dev/null | sed -n 's/^LoadCredential=//p' | paste -sd' ' -)
for want in ocrflow-worker-secret ocrflow-dav-password; do
    case "$CREDS" in
        *"$want:"*) ok "LoadCredential $want" ;;
        *) fail worker "LoadCredential missing '$want'" ;;
    esac
done
ENVIRON=$(systemctl show -p Environment --value ocrflow-worker.service 2>/dev/null || true)
# The invariant is that no secret VALUE is in Environment, not that no suspicious
# NAME is: poweredge deliberately sets
# GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS_DIRECTORY/google-ocr-key" — a PATH to
# a LoadCredential file. Failing on the name red-flags a correct host.
PATTERNS=$(mktemp)
if [ -n "${SMOKE_SECRETS:-}" ] && [ -s "$SMOKE_SECRETS" ]; then
    while read -r sp; do
        [ -z "$sp" ] && continue
        case "$sp" in /*) ;; *) sp="/run/secrets/$sp" ;; esac
        [ -s "$sp" ] && cat "$sp"
        printf '\n'
    done <"$SMOKE_SECRETS" | grep -v '^$' > "$PATTERNS"
fi
if [ -s "$PATTERNS" ] && printf '%s' "$ENVIRON" | grep -qF -f "$PATTERNS"; then
    N=$(printf '%s' "$ENVIRON" | grep -oF -f "$PATTERNS" | wc -l)
    fail worker "unit Environment contains $N rendered secret value(s)"
else
    ok "no rendered secret value in unit Environment"
fi
rm -f "$PATTERNS"
NAMES=$(printf '%s' "$ENVIRON" | tr ' ' '\n' | grep -E '^[A-Z_]*(SECRET|PASSWORD)[A-Z_]*=' | cut -d= -f1 | paste -sd, -)
if [ -n "$NAMES" ]; then warn "worker: secret-named variables in Environment: $NAMES"; fi
unset NAMES

# ── queue table ─────────────────────────────────────────────────────────────
sub "queue"
if command -v psql >/dev/null 2>&1; then
    # Nextcloud's database is `nextcloud`, not the default `postgres`, and peer auth
    # needs the postgres role: both were missing, which turned "query failed" into
    # "migration did not land" — a false accusation against the app.
    QERR=$(mktemp)
    ROWS=$(sudo -u postgres psql -d nextcloud -tAc 'select count(*) from oc_ocrflow_jobs' 2>"$QERR" | tr -d ' \n')
    if [ -n "$ROWS" ]; then
        ok "oc_ocrflow_jobs reachable (rows=$ROWS)"
    else
        fail queue "oc_ocrflow_jobs not queryable: $(head -2 "$QERR" | tr '\n' ' ')"
    fi
    rm -f "$QERR"
else
    warn "queue: no psql in the guest — the jobs table is NOT asserted (reported, not silently passed)"
fi

# ── retired listener ────────────────────────────────────────────────────────
sub "retired listener"
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -q ':8095$'; then
    fail listener "something listens on :8095 (the retired webhook)"
else
    ok "nothing on :8095"
fi

# ── verdict ─────────────────────────────────────────────────────────────────
printf '\n'
# A distinct final marker: per-assertion lines also say POWEREDGE_SMOKE_FAIL, so
# grepping for that string alone cannot distinguish "one assertion failed" from
# "the probe died before it finished".
if [ "$FAILED" -eq 0 ]; then
    printf 'POWEREDGE_SMOKE_VERDICT: PASS\n'
else
    printf 'POWEREDGE_SMOKE_VERDICT: FAIL (%d assertion(s))\n' "$FAILED"
fi
# The guest must power itself off: that is what makes the wrapper terminate, and
# QEMU's exit code is NOT the verdict.
sync
poweroff -f || true
exit "$FAILED"
