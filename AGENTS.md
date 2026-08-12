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

3. **Always push before deploying.** Each host builds its own config locally:
   ```bash
   # Push first
   jj bookmark set dev -r @ && jj git push --all

   # Erebus (local — agents run here)
   sudo nixos-rebuild switch --flake .#erebus

   # Serenity (remote)
   nixos-rebuild switch --flake .#serenity --build-host likivik@serenity --target-host likivik@serenity --use-remote-sudo

   # Traversal (remote)
   nixos-rebuild switch --flake .#traversal --build-host likivik@traversal --target-host likivik@traversal --use-remote-sudo

   # Poweredge (remote)
   nixos-rebuild switch --flake .#poweredge --build-host likivik@poweredge --target-host likivik@poweredge --use-remote-sudo
   ```

4. **Each host builds its own closure.** No central build host — `--build-host` and `--target-host` point to the same machine.

5. **Working with jj changes:**
   - Each task = one `jj new`
   - Edit files normally
   - jj auto-tracks all changes (no `git add` needed)
   - `jj log` to see all changes
   - Before merging to main: `jj squash` + `jj describe` to clean up
   - Push: `jj bookmark set dev -r @ && jj git push --all`

6. **Migrating existing git branches:**
   - jj reads existing git history automatically
   - Old branches appear as bookmarks: `jj bookmark list`
   - No conversion needed — jj works on the same .git directory

7. **Emergency: fall back to git**
   - git commands still work: `git log`, `git status`, `git diff`
   - But prefer jj for all create/commit/push operations
   - If jj breaks: `git checkout` + `git commit` still function
