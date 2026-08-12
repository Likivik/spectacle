# Agent Instructions — Spectacle Repository

## Repo Location

- **Erebus**: `/Storage/Git/spectacle` — primary workspace (jj repo, local edits)
- **Serenity**: `/Storage/Git/spectacle` — build host (auto-pulls every 5 min)
- **Traversal**: `/Storage/Git/spectacle` — auto-pulls every 5 min

Agents run on erebus. Edit locally, build on serenity.

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

3. **Always push before deploying:**
   ```bash
   jj bookmark set dev -r @
   jj git push --all
   ssh serenity "cd /Storage/Git/spectacle && git pull --ff-only origin dev && nixos-rebuild switch --flake .#<host> --target-host likivik@<host> --use-remote-sudo"
   ```

4. **Build only on serenity.** Deploy via `--target-host` to other hosts (poweredge, erebus, etc).

5. **Working with jj changes:**
   - Each task = one `jj new`
   - Edit files normally
   - jj auto-tracks all changes (no `git add` needed)
   - `jj log` to see all changes
   - Before merging: `jj squash` + `jj describe` to clean up
   - Push: `jj bookmark set dev -r @ && jj git push --all`

6. **Migrating existing git branches:**
   - jj reads existing git history automatically
   - Old branches appear as bookmarks: `jj bookmark list`
   - No conversion needed — jj works on the same .git directory

7. **Emergency: fall back to git**
   - git commands still work: `git log`, `git status`, `git diff`
   - But prefer jj for all create/commit/push operations
   - If jj breaks: `git checkout` + `git commit` still function
