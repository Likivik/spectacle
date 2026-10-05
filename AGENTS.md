# Agent Instructions — Spectacle Repository

## Always research latest best practices first

Before designing, implementing, or choosing a library/architecture/approach
for ANY task (bots, infra, nix, scripts), search the web for up-to-date best
practices, official docs, and current literature FIRST. Do not rely on
memory of how things were done before — frameworks (aiogram etc.) and
standards change fast. Treat "I remember it" as a trigger to verify.
Cite/document what you found when it shapes a decision.

## Repo Location

- **Serenity**: `/Storage/Git/spectacle` — **the host the Hermes agent runs on** (moved
  there from Erebus on 2026-10-05; see `/var/lib/hermes/flip-to-serenity.sh`). Builds,
  tests, VM smoke gates and deploys happen here.
- **Erebus**: `/Storage/Git/spectacle` — edit-only scratch (jj repo). Its Hermes gateway is
  masked and it has no space: **never build here**, heavy Nix work belongs on Serenity.
- **Traversal**: `/Storage/Git/spectacle` — auto-pulls every 5 min

## VCS: Jujutsu (jj)

This repo uses **jj** (Jujutsu) on top of git. jj is the primary VCS.

### Key rules for agents:

1. **Use jj, not git** for all operations:
   - `jj new` — start a new change (equivalent of git checkout -b)
   - `jj describe -m "message"` — set commit message
   - `jj log` — view history
   - `jj bookmark set dev -r @` — point dev bookmark at current change
   - `jj git push --all` — push to origin
   - `jj squash` — combine changes
   - `jj edit <id>` — switch to an existing change
   - `jj abandon <id>` — discard a change
   - `jj diff` — view working changes

2. **Never create git worktrees.** jj handles parallel work via `jj new` — multiple changes in one checkout.

3. **Deploy flow — pre-deploy checks always before building/pushing:**

   ⏱ **TIME-BOX FIRST (mandatory):** before starting, state an estimate for the
   *whole* job — flake eval + dry-build + build + activation + any adjacent
   work (commit/push, other hosts, follow-up fixes). Then report elapsed vs
   estimate when done. NixOS flake evals (den + home-manager) take 5–15 min;
   builds 5–60 min depending on cache hits. Never begin a switch without
   saying how long it should take. Time-blindness needs an external clock.

   ```bash
   # 0. Check which host you're actually on (same repo path exists on
   #    Erebus, Serenity, Traversal — don't assume).
   hostname -s

   # 1. Pre-deploy check FIRST: dry-build.
   #    Never skip this before deploying. (Hydra cache check is §7 — only
   #    needed when bumping packages that might build from source.)
   nix build .#nixosConfigurations.<host>.config.system.build.toplevel --dry-run

   # 2. Serenity only: boot the WHOLE new host in a VM before anything touches
   #    disk. Builds the real toplevel and asserts: no failed system units
   #    outside a documented allowlist, the hermes user units (gateway,
   #    dashboard, graphiti), linger + the user bus, and that the upstream
   #    `systemd-run --user --scope` primitive works (cron dispatch needs it).
   #    ~5-10 min; prints SERENITY_SMOKE_PASS or SERENITY_SMOKE_FAIL.
   #    Note: it inherits everything except real hardware/secrets, so a green
   #    gate means the config boots healthy - not that the TPM unseals or the
   #    disks/zpool are fine. SKIP this only if you are not changing serenity.
   nix run .#serenity-smoke

   # 3. Push only AFTER dry-build (and the smoke gate) passes
   jj bookmark set dev -r @ && jj git push --all

   # 4. Deploy — LOCAL if you're on the target host, REMOTE otherwise.
   #    Serenity is the LOCAL host now (the agent runs on it).
   #
   # ⚠ Agents: do NOT run a bare `sudo nixos-rebuild switch` from your own
   # shell. You run inside the hermes-gateway.service cgroup, and when the
   # activation restarts that unit, the switch (sudo'd to root but still in
   # the same cgroup) leaves a root-owned process the user manager can't
   # kill → "Operation not permitted" → the gateway wedges half-stopped and
   # never comes back until a reboot. Detach into a SYSTEM-scope transient
   # unit so the switch survives its own gateway restart. Two gotchas:
   #   - flake must be `path:`-prefixed ABSOLUTE: systemd-run cwd is `/` and
   #     root fails libgit2 safe.directory on the git+file:// repo.
   #   - wrap in `bash -lc`: nixos-rebuild's activation runs
   #     `switch-to-configuration test`, which needs coreutils (`test`) +
   #     systemctl on PATH — absent from systemd-run's minimal env.
   sudo systemd-run --collect --unit=nixos-rebuild-serenity \
     --working-directory=/Storage/Git/spectacle \
     bash -lc 'exec nixos-rebuild switch --flake path:/Storage/Git/spectacle#serenity'

   # (A human on a real root shell may use the plain `sudo nixos-rebuild
   #  switch --flake .#serenity` — the cgroup hazard is agent-specific.)

   # Erebus / Traversal / Poweredge (remote)
   nixos-rebuild switch --flake .#erebus --build-host likivik@erebus --target-host likivik@erebus --elevate=sudo
   nixos-rebuild switch --flake .#traversal --build-host likivik@traversal --target-host likivik@traversal --elevate=sudo
   nixos-rebuild switch --flake .#poweredge --build-host likivik@poweredge --target-host likivik@poweredge --elevate=sudo
   ```

   Gotchas:
   - Local = `sudo nixos-rebuild ...` with no `--host` — but as an *agent* detach it
     (`sudo systemd-run --collect --unit=nixos-rebuild-<host> ...`, see above). Remote =
     `--build-host` + `--target-host` + `--elevate=sudo`.
   - ⚠ If the deploy bumps nixpkgs the **kernel changes** (6.18.49 → 6.18.55 in the
     2026-10-06 bump). `switch` activates userspace only: the running kernel cannot load
     the new module tree (nvidia, ZFS), so the box is in a half-state until reboot. Prefer
     `nixos-rebuild boot` + reboot, or reboot right after the switch. The VM smoke gate
     validates exactly that fresh-boot path — a switch does not exercise it.
   - To avoid a reboot entirely, bump **only** the input you need (e.g. `nix flake update
     hermes-agent`) and leave nixpkgs pinned: userspace-only changes take effect on switch.
   - `--elevate=sudo` is required for remote deploys (NOPASSWD sudo on `likivik`); old form `--use-remote-sudo` is obsolete.
   - `--flake .#<hostname>` must match the *target*, never the calling host.

4. **Each host builds its own closure.** No central build host — `--build-host` and `--target-host` point to the same machine.

5. **Pre-deploy check — always run FIRST, before push then deploy:**

   ```bash
   # Dry-build: check if derivation evaluates and what will be built vs fetched
   nix build .#nixosConfigurations.<host>.config.system.build.toplevel --dry-run
   ```

6. **Hydra cache check — separate tip, run when bumping packages** that might build from source:

   ```bash
   # The flake pins nixpkgs to a recent revision; Hydra may not have cached
   # those versions yet, causing 30-60min source builds.
   nix run nixpkgs#hydra-check -- python312Packages.pymupdf python312Packages.onnxruntime

   # If Hydra shows ✔ for the exact version in the flake → binary cache hit expected.
   # If versions mismatch → expect source build. Consider pinning nixpkgs older
   # or waiting for the build.
   ```

7. **CN cache fallback — for when VPN breaks / official cache unreachable from a host.** Rare; use only if `cache.nixos.org` is slow or blocked. Prefix any `nixos-rebuild`/`nix build` with these substituters (USTC, TUNA, SJTU):

   ```bash
   NIX_CONFIG='substituters = https://mirrors.ustc.edu.cn/nix-channels/store https://mirrors.tuna.tsinghua.edu.cn/nix-channels/store https://mirror.sjtu.edu.cn/nix-channels/store https://cache.nixos.org' \
     nixos-rebuild switch --flake .#<host> ...
   ```

8. **Working with jj changes:**
   - Each task = one `jj new`
   - Edit files normally
   - jj auto-tracks all changes (no `git add` needed)
   - `jj log` to see all changes
   - Before merging to main: `jj squash` + `jj describe` to clean up
   - Push: `jj bookmark set dev -r @ && jj git push --all`

9. **Migrating existing git branches:**
   - jj reads existing git history automatically
   - Old branches appear as bookmarks: `jj bookmark list`
   - No conversion needed — jj works on the same .git directory

10. **Emergency: fall back to git**
   - git commands still work: `git log`, `git status`, `git diff`
   - But prefer jj for all create/commit/push operations
   - If jj breaks: `git checkout` + `git commit` still function
