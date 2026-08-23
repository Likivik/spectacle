# Agent Instructions — Spectacle Repository

## Repo Location

- **Erebus**: `/Storage/Git/spectacle` — primary workspace (jj repo, local edits, agents run here)
- **Serenity**: `/Storage/Git/spectacle` — auto-pulls every 5 min
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

   ```bash
   # 0. Check which host you're actually on (same repo path exists on
   #    Erebus, Serenity, Traversal — don't assume).
   hostname -s

   # 1. Pre-deploy check FIRST: dry-build.
   #    Never skip this before deploying. (Hydra cache check is §7 — only
   #    needed when bumping packages that might build from source.)
   nix build .#nixosConfigurations.<host>.config.system.build.toplevel --dry-run

   # 2. Push only AFTER dry-build passes
   jj bookmark set dev -r @ && jj git push --all

   # 3. Deploy — LOCAL if you're on the target host, REMOTE otherwise:
   # Erebus (local — agents run here).
   #
   # ⚠ Agents: do NOT run a bare `sudo nixos-rebuild switch` from your own
   # shell. You run inside the hermes-gateway.service cgroup, and when the
   # activation restarts that unit, the switch (sudo'd to root but still in
   # the same cgroup) leaves a root-owned process the user manager can't
   # kill → "Operation not permitted" → the gateway wedges half-stopped and
   # never comes back until a reboot. Detach into a SYSTEM-scope transient
   # unit so the switch survives its own gateway restart. NOTE the flake path
   # must be ABSOLUTE and `path:`-prefixed — systemd-run's cwd is `/` (a
   # relative `.` finds no flake.nix) and root fails libgit2's safe.directory
   # check on the git+file:// repo (owned by hermes).
   sudo systemd-run --collect --unit=nixos-rebuild-erebus \
     nixos-rebuild switch --flake path:/Storage/Git/spectacle#erebus

   # (A human on a real root shell may use the plain `sudo nixos-rebuild
   #  switch --flake .#erebus` — the cgroup hazard is agent-specific.)

   # Serenity / Traversal / Poweredge (remote)
   nixos-rebuild switch --flake .#serenity --build-host likivik@serenity --target-host likivik@serenity --elevate=sudo
   nixos-rebuild switch --flake .#traversal --build-host likivik@traversal --target-host likivik@traversal --elevate=sudo
   nixos-rebuild switch --flake .#poweredge --build-host likivik@poweredge --target-host likivik@poweredge --elevate=sudo
   ```

   Gotchas:
   - Local = `sudo nixos-rebuild ...` with no `--host`. Remote = `--build-host` + `--target-host` + `--elevate=sudo`.
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
