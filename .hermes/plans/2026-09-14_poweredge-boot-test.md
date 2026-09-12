# poweredge-boot NixOS VM test — plan (NOT yet implemented)

> Goal: guard poweredge against the two failure classes that burned us in the
> obsidian/forgejo incident — a config that *stops evaluating* (covered by the
> `hosts-eval` check) and a config that *wedges at boot* (a service whose unit
> never leaves `activating`, holding the switch lock). This plan covers the
> latter: a hermetic boot VM test for the poweredge host.
> Status: PLAN ONLY — research done, not implemented.

## Why
- 2026-09-13: poweredge became unreachable because `couchdb-init.service` (a
  dead Obsidian LiveSync init) never completed its start job → it held
  `/run/nixos/switch-to-configuration.lock` → every subsequent deploy froze.
- An eval-guard test (#1) catches "config no longer evaluates". A boot test
  (#2) catches "a unit wedges activation / multi-user never reached" — the
  switch-lock class, which no eval guard can see.

## Community ground-truth (research, 2026-09-14)
- `pkgs.testers.runNixOSTest` is the out-of-tree API; nodes are full NixOS
  systems (nix.dev, nixpkgs manual).
- Reuse a host's OWN modules in a test node:
  `nodes.machine.imports = <poweredge modules>` (NixOS Discourse #11542,
  ponkila/homestaking-infra). VMs auto-override `fileSystems` via
  `mkVMOverride`/`virtualisation.fileSystems`, so real ZFS/disk config is not a
  blocker — same mechanism as the existing `erebus-telegram` VM (already boots
  the erebus host config).
- ZFS is testable in-VM (upstream `nixos/tests/zfs.nix`).
- Nobody boots a full GPU/quadlet production host in a VM wholesale; heavy
  services (immich-ML, qdrant/nextcloud quadlets) are scoped via test overrides
  (`mkVMOverride`-disable or tolerate) and the test asserts guards, not
  full-service health. QEMU VM needs KVM/TCG on the builder (erebus already
  runs the forgejo-boot VM fine).

## Design
- File: `tests/poweredge-boot.nix`, wired into `modules/defaults/checks.nix`
  as `poweredge-boot` (mirrors `tests/forgejo-boot.nix`).
- `pkgs.testers.runNixOSTest`:
  - `nodes.machine.imports = <poweredge host modules>` (via
    `inputs.self.nixosConfigurations.poweredge._module.args.modules` or a
    shared module list), plus hermetic overrides:
    - `sops.secrets` disabled / dummy (`sops.enable = false` or stub the
      secret files the eval requires).
    - heavy green,ist services tolerant or disabled with `mkVMOverride`
      (immich-GPU, qdrant/nextcloud quadlets) — experiment to find the minimum
      that still boots the real nginx/sshd/core.
- testScript assertions:
  - `machine.wait_for_unit("multi-user.target")`
  - **no unit stuck in `activating`** → `systemctl list-jobs` empty after a
    timeout (the couchdb-init wedge guard)
  - `systemctl --failed` ≤ tolerated set
  - **obsidian absent**: `couchdb.service` / `couchdb-init.service` do not exist
  - `nginx` + `sshd` active

## Steps to implement (when green-lit)
1. Probe: build a reduced poweredge VM (`runNixOSTest { nodes.machine = { ... } }`)
   and measure boot time / what needs disabling on a KVM builder. Adjust scope
   until it boots deterministically in reasonable time (target < a few min).
2. Write `tests/poweredge-boot.nix` with 5 assertions above.
3. Wire into `checks.nix: poweredge-boot = import ../../tests/poweredge-boot.nix {...};`
4. `nix build .#checks.x86_64-linux.poweredge-boot` → green.
5. Commit.

## Risks / fallback
- If the trimmed poweredge VM is too heavy/flaky, scope down to a
  boot-complete + no-wedge + obsidian-absent assertion on a service subset
  (nginx/sshd/core) rather than the full host.
- `runNixOSTest` builds the full VM + the os services under test — heavier than
  `hosts-eval`; acceptable as a periodic/CI check, not a per-edit hot path.
