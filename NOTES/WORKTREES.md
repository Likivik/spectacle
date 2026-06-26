# Worktree plugin design

Each opencode session auto-isolates into its own git worktree so concurrent sessions never collide on `git add` / uncommitted files. This doc covers the plugin stack, why we picked it, and how to debug when things go wrong.

## Architecture (two-plugin stack)

```
                   ┌─────────────────────────────────┐
                   │  .opencode/opencode.json        │
                   │  plugin: [                     │
                   │    "opencode-agent-monitor",    │
                   │    "opencode-worktree-manager", │  ← tools + TUI sidebar
                   │    "./plugins/auto-worktree.ts" │  ← session.created hook
                   │  ]                              │
                   └────────────┬────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
        ▼                       ▼                       ▼
   worktree_create       session.created          TUI sidebar
   worktree_list    ───►  auto-worktree.ts  ───►   (worktree list
   worktree_switch        (creates worktree,       with branch
   worktree_status         forks session,          info + select)
   worktree_finish         selects in TUI)
                                │
                                ▼
              .opencode/worktrees/opencode/ses_<id>/
              branch: opencode/ses_<id>
              state: .opencode/auto-worktree-state.json
```

**`opencode-worktree-manager`** (npm, 0.1.7) — supplies the 5 LLM-callable tools and a TUI sidebar. Stateless: each tool call loads worktree state from `git worktree list` directly. No background hook. The sidebar reads from the opencode sqlite db (`.local/share/opencode/opencode-stable.db`).

**`./plugins/auto-worktree.ts`** (local, 277 lines) — the auto-isolation hook. Two event handlers:
- `session.created` — if the session has no parent (or its parent is outside the worktree dir), creates `.opencode/worktrees/opencode/ses_<id>/`, branches from current HEAD, forks the session with `directory = worktreePath`, and `client.tui.selectSession` to follow the fork.
- `session.deleted` — looks up the session in `.opencode/auto-worktree-state.json` and runs `git worktree remove --force` + `git branch -D`. Also cleans up the parent session's worktree if it was itself an auto-spawned session.

## Why we didn't use `@tmegit/opencode-worktree-session`

The npm package `@tmegit/opencode-worktree-session` (1.1.0) is a viable alternative but has a different model: it splits work between a "master" session in the main repo and child sessions in worktrees, and uses an idle-time spawn loop. That works for agentic dispatch but is awkward for normal interactive use where you want one TUI = one worktree. The two-plugin stack above is closer to the mental model users already have: "I opened a session, I'm in a worktree, I commit there, I move on."

## State format

`.opencode/auto-worktree-state.json` (gitignored):

```json
{
  "ses_abc123": {
    "worktreePath": "/Storage/Git/spectacle/.opencode/worktrees/opencode/ses_abc123",
    "branch": "opencode/ses_abc123",
    "parentSessionId": null,
    "createdAt": 1719400000000
  },
  "ses_def456": {
    "worktreePath": "/Storage/Git/spectacle/.opencode/worktrees/opencode/ses_def456",
    "branch": "opencode/ses_def456",
    "parentSessionId": "ses_abc123",
    "createdAt": 1719400001000
  }
}
```

`parentSessionId: null` = root auto-spawned session.
`parentSessionId: "ses_X"` = child session, inherits parent's worktree (no new branch).

## Lifecycle

| Step | Trigger | Action |
|------|---------|--------|
| 1 | User opens TUI in main repo | opencode creates `ses_root` in main dir |
| 2 | `session.created` fires for `ses_root` | auto-worktree sees no state → creates worktree, branch, fork → `ses_child` in worktree, `tui.selectSession(ses_child)` |
| 3 | User works, commits in worktree | normal git flow, branch `opencode/ses_root` |
| 4 | User exits / closes TUI | `session.deleted` for `ses_child` → `git worktree remove --force` + `git branch -D` |
| 5 | If `ses_root` is also auto-spawned, its `session.deleted` fires | cleanup the original worktree too |

## Manual workflows

Even with auto-isolation, you sometimes want explicit worktree control (e.g. worktree on a specific branch, worktree in a sibling directory for a clean monorepo split). Use the 5 tools directly:

- `worktree_create(name="feat/foo", baseBranch="main")` — explicit worktree, prompts for branch suffix
- `worktree_list` — see all worktrees + which session is in each
- `worktree_switch(name="feat/foo")` — aborts current session, forks a new one in the named worktree, selects it in TUI
- `worktree_status` — diff between current worktree branch and main
- `worktree_finish` — commits + removes current worktree (does NOT push)

## Troubleshooting

### Orphan worktree dirs in `.opencode/worktrees/opencode/`
The `session.deleted` event may not fire if the opencode process is killed (SIGKILL) or the sqlite db is corrupted. Clean up manually:
```bash
git worktree list                                   # see all
git worktree remove .opencode/worktrees/opencode/ses_<id> --force
git worktree prune
git branch -D opencode/ses_<id>
```

### TUI shows a session but `git status` says clean
The session was forked into a worktree but the TUI's `directory` column may not have updated. Refresh by calling `worktree_status` — the TUI sidebar will re-read.

### "Worktree Restored" toast on session resume
Auto-worktree detects a resume (session id is in state file) and re-creates the worktree. If the branch was force-deleted out-of-band, the resume will create a new branch from current HEAD (loose end: any work committed to the old branch is orphaned). Check `git reflog` and `git fsck --unreachable` to recover.

### "fork failed" error toast
The v2 SDK `client.session.fork({directory})` can fail if the directory doesn't exist on disk yet (race with `mkdirSync`). The plugin handles this by removing the just-created worktree before saving state. If you see persistent fork failures, check that `.opencode/worktrees/opencode/` is writable.

### Branch name `opencode/ses_<id>` collides
`session_id` is a ULID-style 26-char string, collisions are practically impossible. If you see "branch already exists" errors, you have a corrupt state file (multiple entries for the same id) — delete it, the plugin rebuilds on next session.

## See also

- `.opencode/plugins/auto-worktree.ts` — source
- `modules/users/likivik/dotfiles/opencode/opencode.jsonc` — user-level opencode config (mnemosyne-bridge, system-context, etc.)
- `AGENTS.md` § Parallel sessions — short user-facing version
- `notes/awesome-opencode-catalog.md` — inventory of all available opencode plugins
