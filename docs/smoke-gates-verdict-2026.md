# Deploy smoke gates: audit + endorsed practice (2026)

Verdict: the fleet has **one** real boot gate (serenity) and it could not fail. Three of its
defects are correctness bugs, not coverage wishes: the app returned QEMU's exit code instead of the
probe's verdict, the unit allowlist was an unanchored regex that muted anything containing a
substring, and the second gate (`erebus-telegram`) reports OK on a DNS/TLS failure. Everything below
is either verified from the code in this repo or cited from upstream sources.

Line numbers refer to commit `b99c72b`; re-grep if they drift.

---

## 1. What the fleet has today

| Path | Kind | In `checks.ci` | Hosts covered |
|---|---|---|---|
| `tests/serenity-smoke.nix` + `tests/serenity-smoke-probe.sh` | full-host QEMU boot (`extendModules` on the real config) + in-guest oneshot probe | no | serenity |
| `tests/forgejo-boot.nix` | `pkgs.testers.nixosTest`, synthetic node importing one aspect | no | — (aspect only) |
| `tests/erebus-telegram.nix` | hand-rolled VM app, not a `nixosTest` | no | erebus (legacy) |
| `tests/litellm-boot.nix` | aspect boot test | no | — |

Wiring lives in `modules/defaults/checks.nix`: `checks.serenity-smoke-vm`, `apps.serenity-smoke`,
`checks.forgejo-boot`, `checks.litellm-boot`, `apps.erebus-telegram`, `apps.host-eval`.

**poweredge has no boot gate.** `.hermes/plans/2026-09-14_poweredge-boot-test.md` is research only:
nothing in `tests/` or `checks.nix` implements it, even though poweredge is where the *actual*
wedge happened (`couchdb-init.service` never completed its start job, held
`/run/nixos/switch-to-configuration.lock`, and every later deploy froze).

`AGENTS.md:180` explains why no VM test is in CI: `checks.serenity-smoke-vm` and the `*-boot`
tests cannot finish on a hosted runner. `checks.ci` (`checks.nix:21`) is the designed extension
point — a hermetic `nixosTest` that fits a runner's budget becomes a required gate with a one-line
addition.

---

## 2. Defects found

1. **The gate could not fail.** `apps.serenity-smoke` ended with `exit "$RC"`, where `RC` was QEMU's
   exit status (`checks.nix:515-533`). The probe powers the guest off, so QEMU exits 0 regardless of
   `SERENITY_SMOKE_FAIL`. A scripted caller saw success on a red gate. Fixed on branch
   `serenity-smoke-truth` by capturing the serial log and deciding on the marker.
2. **`erebus-telegram` reports success on connectivity failure.** The TLS assertion is
   `CODE=$(curl ... -w '%{http_code}' ... 2>&1)`; merging stderr into the code means a DNS or
   certificate error yields the curl error text plus `000`, which is `!= "000"`, so
   `TELEGRAM_TLS_OK` is printed. Reproduced against an unresolvable host. Its DNS check
   (`getent ... | head -2 || echo DNS_FAIL`) can never fire: the pipeline status is `head`'s.
   No poweroff, no marker, so the app also never returns a verdict.
3. **The allowlist muted by substring.** `ALLOW` was an unanchored regex matched with `grep -Ev`
   (`probe:53-68`): `swap`, `zfs[^ ]*`, `nvidia[^ ]*`, `tailscale[^ ]*` grant immunity to any unit
   whose *name contains* those substrings — measured: `swapfile-cleanup.service`,
   `my-zfs-checker.service`, `tailscale-helper.service`, `nvidia-persistenced.service`.
4. **Nine of seventeen entries were dead** — no such unit anywhere in the repo: `panther.mount`,
   `Storage.mount`, `Storage-Git.mount`, `krfb`, `krdp`, `mullvad`, `wg-quick*`, `wireguard*`,
   `forgejo-backup*` (the last one lives on poweredge, not serenity). Dead entries make the list look
   denser than the real risk set.
5. **The pattern that hid the host's actual failure.** `zfs[^ ]*` covers
   `zfs-import-gitpool.service` — the unit whose failure on 2026-10-22 stopped the whole boot
   (`serenity.nix:294,305`). A guest cannot import a real pool, so the gate structurally cannot
   observe that failure mode; the fix is an explicit, anchored entry plus visibility, not a wildcard.
6. **`degraded` was accepted as healthy** (`probe:24`), and `multi-user.target` was never asserted.
   A unit stuck in `activating` (the `couchdb-init` class) is neither `failed` nor caught.
7. **Only two units were required to be `active`** — `hermes-gateway`, `graphiti-mcp`.
   `hermes-webui`, `forgejo.service`, the three `llama-*` units and FalkorDB were covered only
   implicitly, by "not failed".
8. **Documentation contradicted the implementation.** The probe header and
   `serenity-smoke.nix:223-233` described a host-driven `smoke-shell` over forwarded ports
   2222/9999; no such unit, socket or forward exists. `EXPECTED_UNITS` was passed
   (`serenity-smoke.nix:250`) and never read.
9. **`forgejo-boot` cannot catch the regression it documents.** It boots a synthetic node with no
   `fileSystems`, so `/Storage` is a plain directory, while on the host it is a ZFS dataset owned
   `0770 likivik:users` — the exact permission failure the test was written for is unreproducible
   there. It also asserts existence of paths created by the very activation script it is testing.
10. **The version assertion pins a literal** (`v0.21.7`, `probe:172`): an input bump fails as
    `HERMES_VERSION_BAD` instead of saying "update the test".

---

## 3. Endorsed practice (upstream sources)

- **Public test interface**: `pkgs.runNixOSTest` (`nixosTest`, `make-test-python.nix` are legacy).
  Declare `checks.<system>.<name>` so `nix flake check` builds them.
  <https://nixos.org/manual/nixos/unstable/#sec-calling-nixos-tests>,
  <https://github.com/NixOS/nixpkgs/blob/master/pkgs/build-support/testers/default.nix>
- **Assert with the machine API, not a shell script**: `wait_for_unit` (waits for `active`, raises on
  `failed`, and on `inactive` when no jobs are pending), `require_unit_state`,
  `wait_for_open_port` (proves the service answers), `get_unit_property(u, "NRestarts")`,
  `wait_until_succeeds` / `wait_until_fails`.
  <https://github.com/NixOS/nixpkgs/blob/master/nixos/lib/test-driver/src/test_driver/machine/__init__.py>
- **Multi-node tests**: `nodes.<a>` / `nodes.<b>` in one run, framework-assigned IPs and
  `/etc/hosts` — cross-host scenarios stop being "impossible in a single guest".
  <https://github.com/NixOS/nixpkgs/blob/master/nixos/lib/testing/network.nix>
- **Real TPM in the guest**: `virtualisation.tpm.enable = true` (swtpm) plus
  `virtualisation.tpm.provisioning` to seed the TPM2 instance before boot.
  <https://github.com/NixOS/nixpkgs/blob/master/nixos/modules/virtualisation/qemu-vm.nix>
- **sops-nix**: `sops.age.generateKey = true` (machine key generated at activation when absent),
  `sops.templates.<name>.content` (literal template content, no sops file needed),
  `sops.validateSopsFiles` (fail at evaluation, not at boot).
  <https://github.com/Mic92/sops-nix/blob/master/modules/sops/default.nix>
- **Skip, don't fail, hardware-dependent units**: `systemd.services.<n>.unitConfig.Condition*`
  (`ConditionPathExists`, `ConditionVirtualization`). A false `Condition*` skips the unit *without*
  putting it in `failed`; `Assert*` is the opposite and fires loudly.
  <https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html>
- **Static checks that need no guest**: `systemd-analyze verify --recursive-errors=yes`,
  `nix flake check` (builds `checks`, evaluation-checks every `nixosConfigurations.<host>`),
  `nixos-rebuild dry-activate` (blast radius without changing anything).
  <https://nix.dev/manual/nix/latest/command-ref/new-cli/nix3-flake-check>,
  <https://nixos.org/manual/nixos/unstable/#sec-switching-systems>
- **Deploy-time confirmation**: deploy-rs `deployChecks` (schema-validated in `nix flake check`) and
  `magicRollback` with `autoRollback`, `activationTimeout`, `confirmTimeout` — the post-activation
  half the VM boot gate does not cover. <https://github.com/serokell/deploy-rs>
- **Exit code 4 is not a failed switch**: `switch-to-configuration-ng` returns 4 when a unit is
  `failed` *or* in `auto-restart` with non-zero `ExecMainStatus`. Read
  `journalctl -u nixos-rebuild-<unit>` instead of rolling back.
  <https://github.com/NixOS/nixpkgs/blob/master/pkgs/by-name/sw/switch-to-configuration-ng/src/main.rs>

---

## 4. How to exclude less

Ordered by effect per hour spent.

1. **`Condition*` instead of allowlist entries.** GPU, host-disk, zpool and tailnet-only units get
   `unitConfig.ConditionPathExists` / `ConditionVirtualization`. In the guest the unit is *skipped*
   (cleanly inactive), on real hardware it starts. The allowlist entry is deleted rather than muted,
   and the host gains correct behaviour on machines without the hardware.
2. **Anchor everything, and make the allowlist report itself.** Current fix: one bash array of
   anchored patterns, names taken from
   `nix eval .#nixosConfigurations.serenity.config.systemd.units`; every hidden failure is printed
   with `ConditionResult`/`Result` (`ALLOWLISTED_FAILURE:`); a pattern that matched nothing is
   printed as `ALLOWLIST_UNUSED:`.
3. **Three verdicts, not two**: `active` / `skipped-by-condition` / `failed`
   (`systemctl show -p ActiveState -p Result -p ConditionResult`). "Allowlisted but neither skipped
   nor failed for a condition" becomes a visible anomaly instead of an accepted one.
4. **Make secrets real in the guest** instead of allowlisting units that "fail on dummy secrets":
   `virtualisation.tpm.enable` for the TPM path, `sops.age.generateKey` with a per-guest key file,
   `sops.templates.<name>.content` for config files a service parses.
5. **Multi-node `nixosTest`** for anything that talks to a peer host — that class is currently
   "impossible in one guest" and therefore allowlisted.
6. **`forwardPorts` + `wait_for_open_port`** replaces "active-only" for HTTP services with a real
   request.
7. **Disable timer-driven units in the guest** (or gate them on a marker file the guest creates)
   instead of allowlisting "fails only on some boots".

A stale allowlist entry that silently accepts a real failure is worse than no allowlist at all.

---

## 5. sops templates: already in use

`sops.templates` is not a gap — it is load-bearing and already part of the gate:

- `modules/aspects/server/hermes/hermes-agent.nix:255` — `sops.templates = sopsTemplates;`
  with `envFileFor = name: config.sops.templates.${name}.path;` (`:140`)
- `modules/aspects/server/hermes/webui.nix:49` — `config.sops.templates."hermes/sops-env".path`
- `tests/serenity-smoke.nix:111` — `renderedEnv = config.sops.templates."hermes/sops-env".path`,
  and the probe verifies **every key** the template declares is present and non-empty
  (`probe:248-282`)

Repo totals: 29 `sops.secrets`, 11 `sops.templates` references. Missing: `sops.templates.<name>.content`
for non-env config files, and an explicit `validateSopsFiles` stance (the smoke force-disables it
because the dummy file is generated at build time — a host-side eval check would still be useful).

---

## 6. Priorities

1. ~~Fix the serenity exit code~~ — branch `serenity-smoke-truth`.
2. Fix `erebus-telegram`: drop the `2>&1`, capture stderr separately, power the guest off, grep the
   marker in the app wrapper.
3. Write `tests/poweredge-boot.nix` from the existing plan: `multi-user.target` reached, no unit in
   `activating`, `couchdb-init` absent, `nginx` and `sshd` active.
4. Convert the serenity probe into `pkgs.runNixOSTest` (`machine.wait_for_unit`,
   `wait_for_open_port`, `get_unit_property(u,"NRestarts")`) so assertions cannot pass silently and
   the exit code is structural rather than grepped.
5. `Condition*` on GPU/disk/zpool/tailnet units, then delete those allowlist entries.
6. Post-deploy on the live hosts: `systemctl show <unit> -p NRestarts` for units that must be up,
   plus one real request per service.

## 7. What a green gate still does not prove

Real TPM unsealing (swtpm proves the code path, not the host's sealed secret), real disks and zpools,
GPU, the tailnet, the *activation* step itself, and unit **stability** — `activating (auto-restart)`
is not `failed`, which is why `NRestarts` and a real request belong in the post-deploy step.
