# JJ ↔ Git: how the operation/commit store maps to .git

Research based on official Jujutsu docs (docs.jj-vcs.dev), Arch man pages
(jj-git-push, jj-bookmark-set, jj-bookmark-move), the Git-compatibility /
Git-comparison / Bookmarks / Operation-log guides, and the Concurrency /
architecture design docs. All citations inline.

## 1. The dual store: commits + operations (+ views)

jj holds **two** content-addressed stores backed by the working directory:

- **Commit store** (`GitBackend`, by default). This *is* a git repo. In a
  colocated workspace it lives at `./.git`; in non-colocated mode it lives at
  `.jj/repo/store/git` and `.git` is just a symlink/redirect file
  (`.jj/repo/store/git_target` pointing at `../../../.git`).
  Source: https://docs.jj-vcs.dev/latest/git-compatibility/ (§Colocated
  workspaces, §Converting a workspace) and the `colocation.rs` source
  https://github.com/jj-vcs/jj/blob/main/cli/src/commands/git/colocation.rs
  which literally `mv .jj/repo/store/git .git`.
- **Operation store** + **op-heads store**. Operations are atomic snapshots of
  "the view" (bookmarks + tags + Git-ref targets + heads + working-copy id).
  Operations and views are content-addressed like git objects; op heads are
  tracked by file presence for atomicity.
  Source: https://docs.jj-vcs.dev/latest/technical/concurrency/
  ("The operation objects and view objects are stored in content-addressed
  storage just like Git commits are…") and architecture doc
  https://github.com/jj-vcs/jj/blob/main/docs/technical/architecture.md.
  Every mutating command opens a transaction, snapshots the working copy,
  computes a new `MutableRepo`, commits a new Operation pointing to a new
  View, then advances the op-heads file.
- jj also pins commits that would otherwise be GC'd by git via
  `refs/jj/keep/` refs in the backing git repo.
  ("To prevent GC from deleting commits that are still reachable from the
  operation log, the GitBackend stores a ref for each commit in the operation
  log in the refs/jj/keep/ namespace." — architecture.md).

So a single `jj <anything>` is operationally equivalent to "snapshot, do some
mutation in both stores, commit, advance op-head" — that's what makes
`jj op log` / `jj undo` / `jj op restore` work: the entire repo state is
recoverable from the operation log alone.

## 2. What `jj git fetch` / `jj git push` actually do to git refs

**Fetch** delegates to plain `git fetch` underneath (jj uses libgit2/gix over
the same git protocol stack — see git-compatibility "Authentication: Yes.
`git` is used for remote operations under the hood."):
https://docs.jj-vcs.dev/latest/git-compatibility/ and the `jj-git-fetch(1)`
man page https://man.archlinux.org/man/extra/jujutsu/jj-git-fetch.1.en.

What changes after fetch:
- `refs/remotes/<remote>/<branch>` (git's remote-tracking branches) get the
  usual updates from the fetch.
- On the next `jj` command, the colocated workspace's auto-import reads those
  refs and:
  1. Records `<bookmark>@<remote>` as jj's last-seen position for that remote.
  2. If `<bookmark>@<remote>` is tracked, updates the local bookmark
     `<bookmark>` to match.
  3. If local and remote positions diverged, merges them: if one side is
     strictly ahead of the other, that wins; otherwise the local bookmark
     becomes **conflicted** (shows `main??`).
  Source: https://docs.jj-vcs.dev/latest/bookmarks/ §"Remotes and tracked
  bookmarks" and the "details: how fetch pulls bookmarks" sub-section.

**Push** likewise shells out to `git push` but layers safety checks on top
(`jj-git-push(1)` man page https://man.archlinux.org/man/extra/jujutsu/jj-git-push.1.en,
Bookmarks §"Pushing bookmarks: Safety checks"
https://docs.jj-vcs.dev/latest/bookmarks/#pushing-bookmarks-safety-checks):

1. The remote ref must still be at the position jj last saw; otherwise the
   push is refused. → functionally identical to `git push --force-with-lease`
   ("…this makes `jj git push` similar to `git push --force-with-lease`.").
2. The local bookmark must not be conflicted.
3. If the remote bookmark already exists, it must be tracked.

If fetch is run on a timer (a common pitfall with background
`force-with-lease`), jj converts the race into a visible *bookmark conflict*
that the user must resolve before any push is even attempted. That's the
defense the docs cite as jj's safety story.

Pushing a non-tracking bookmark with `--bookmark foo` will push but mark
`foo@origin` as tracked automatically on success (Bookmarks §"Automatic
tracking" / "When you push a local bookmark, the newly created bookmark on
the remote is marked as tracked.").

## 3. Why `jj rebase` rewrites git commit hashes (and bookmarks follow)

A commit has two identifiers in jj
(https://docs.jj-vcs.dev/latest/tutorial/):

- **Commit ID** — a git object hash. Matches `git log` output. Mutates
  whenever tree/parents/message/author changes.
- **Change ID** — a separate 16-byte (default) stable identifier shared by all
  rewrites of the same conceptual change. Stored as a reverse-hex header in
  the commit (git-compatibility §"Format mapping details": "Change IDs are
  stored in git commit headers as reverse hex encodings.").

Rebasing a commit creates a new git object (different tree, different parent
list, different commit hash) **carrying the same change ID**. Because jj is
the one identifying revisions, the new git hash is harmless to jj — but
**bookmarks follow the change ID, not the commit ID**, which is why
"`jj rebase` rewrites git commit hashes and bookmarks move along with it"
(https://docs.jj-vcs.dev/latest/git-comparison/ §"Descendant commits are
automatically rebased: Whenever you rewrite a commit (e.g. by running
`jj rebase`), all its descendants commits will automatically be rebased on
top. Branches pointing to it will also get updated…"; Bookmarks §"Bookmark
updates" — "Currently Jujutsu automatically updates local bookmarks when
these conditions are met: When a commit has been rewritten (e.g. when you
rebase), bookmarks and the working-copy will move along with it.").

So the git-side object graph after `jj rebase -s X -o Y` looks like a normal
rebase (new commits, old ones still in `.git/objects` reachable via
`refs/jj/keep/*`). The bookmark ref file `refs/heads/<name>` now points at
the new tip. That is exactly the situation git considers a "non-fast-forward"
when the remote still points at the old tip.

## 4. Force-push is the normal outcome of rebasing a pushed branch

If you pushed branch `B` at commit hash `abc123`, then locally did
`jj rebase`, the local `refs/heads/B` now points at `def456` (same change
ID, different commit hash). From git's perspective this is a non-fast-forward
update of `B`. `git push` would refuse with `non-fast-forward`, and so does
`jj git push` — except jj's safety check (the `--force-with-lease` analogue)
notices the remote `B` is at `abc123` (jj's last-seen `@origin` position).
If that last-seen position matches the remote, jj pushes the new ref
unconditionally; if it doesn't match (someone else updated the remote since
the last fetch), jj refuses.

So "force-push" is the **expected** and **automatic** outcome of rewriting
locally + pushing, and:

- **Use `jj git push`** for a pushed-rebase flow. By design this is the
  safe equivalent of `--force-with-lease` against your own last-seen remote
  state, and it self-resolves into a bookmark conflict instead of silently
  clobbering concurrent updates.
  (Bookmarks §"Pushing bookmarks: Safety checks", GitHub docs
  https://docs.jj-vcs.dev/latest/github/ §"Rewriting commits": "Push the
  updated bookmark to the remote. Jujutsu automatically makes it a force
  push — `jj git push --bookmark your-feature`.")
- **Avoid** reaching for `git push --force-with-lease` directly inside a
  colocated workspace. You'll skip the bookmark-tracking and remote-position
  bookkeeping and leave the local view out of sync with the remote.
- **Never** use bare `git push --force` — it skips both safety nets.

If you genuinely need to interact with a remote the jj view hasn't seen (e.g.
CI pushed while you had no network): run `jj git fetch --remote <name>`
first, resolve any `main??` conflict, then `jj git push`. Don't push through
it.

## 5. "Divergent bookmark" — what it really is

A bookmark can become **conflicted** when there is no single jj-acceptable
answer for where the ref points. Concretely, from the Bookmarks doc
(https://docs.jj-vcs.dev/latest/bookmarks/#conflicts):

> "Both local bookmarks (e.g. `main`) and the remote bookmark (e.g.
> `main@origin`) can have conflicts. Both can end up in that state if
> concurrent operations were run in the repo. The local bookmark more
> typically becomes conflicted because it was updated both locally and on
> a remote."

Under the hood this is a `RefTarget` with multiple add edges preserved in
the conflicted view, exposed via the revset `bookmarks(exact:main)`
(https://neugierig.org/software/blog/2025/08/jj-bookmarks.html). Concrete
trigger:
- Local side moved `main` from A to B.
- Remote side moved `main` from A to C (via fetch).
- B and C are not on a single line so neither "wins"; the view records
  `main??` with both targets.

Display: `main??` suffix in `jj log` and `jj bookmark list`, full listing of
target revisions via `jj bookmark list` and the revset
`bookmarks(exact:main)` (FAQ: https://jj-vcs.github.io/jj/v0.26.0/FAQ/).

### Correct commands to move/clean it

Three commands, each with a precise role — quoting the man pages:

| Command | When |
|---|---|
| `jj bookmark set NAME -r R` | Create-or-update by name to a specific rev (Bookmarks + jj-bookmark-set(1) https://man.archlinux.org/man/jj-bookmark-set.1.en: "Create or update a bookmark to point to a certain commit."). Default -r is `@`. **Default-refuses backwards/sideways moves**. |
| `jj bookmark create NAME -r R` | Strict create; errors if the bookmark already exists. Use when you *want* a "must be new" guarantee. |
| `jj bookmark move NAME --to R` | Move *existing* bookmarks only (cannot create). Use `--from <revset>` to filter which bookmarks move. Honors `-B/--allow-backwards`. Source: jj-bookmark-move(1) https://man.archlinux.org/man/extra/jujutsu/jj-bookmark-move.1.en ("Move existing bookmarks to target revision… Unlike `jj bookmark set`, this command cannot create new bookmarks."). |

`--allow-backwards` (`-B`) is the explicit escape hatch that lets `set` /
`move` place the bookmark on a revision that isn't a descendant of its
current target. Without it, jj protects you from accidentally regressing a
shared branch by rewind. Use it deliberately, on a bookmark you have
already decided should move backwards (e.g. you're abandoning a stack and
want to point `feature` back at its root).

### Resolution recipe for a conflicted bookmark

From Bookmarks §"Conflicts" and FAQ:

1. Inspect: `jj bookmark list`, `jj log -r 'bookmarks(exact:main)'`.
2. Decide on the target — `jj new <bookmark>` fails (multiple revset
   results) so refer by change ID/commit ID.
3. Pick one of:
   - `jj bookmark set main -r <chosen-rev>` to resolve by naming the new
     target.
   - `jj new main` then resolve/commit the merge of all targets, and
     `jj bookmark set main -r @` to land the bookmark on the merge.
   - `jj rebase -r <unwanted-side> -d <kept-side>` to drop one branch and
     `jj bookmark set main -r <kept-side>`.
4. Remote-side conflict (`main@origin??`) auto-resolves on next
   `jj git fetch --remote <name>` (Bookmarks §"Conflicts": "To resolve a
   conflicted state in a remote bookmark (e.g. `main@origin`), simply pull
   from the remote.").
5. Local-side conflict (`main??`): `jj bookmark set main -r <target>` is
   the standard move; `jj bookmark move` is the alternative when you need
   `--from` filtering or want to assert that the bookmark exists.

Use `jj bookmark create` only when a "must be new" guarantee is wanted
(migrating old git branches, scripting); use `jj bookmark set` for routine
"ensure this ref points at this commit".

## 6. Adjacent concept: **divergent change** (not a bookmark)

Worth flagging because the keyword "divergent" is overloaded.

A **divergent change** is when a single change ID has multiple visible
commits — typically because a commit got rewritten twice concurrently (or
two processes each amended the same change), producing two siblings with
the same change ID. The Glossary
(https://www.jj-vcs.dev/v0.41.0/glossary/) and the dedicated guide
(https://docs.jj-vcs.dev/latest/guides/divergence/) cover it.

Display: change ID with `??` suffix and a change offset (`/0`, `/1`,
newest-first), e.g. `puqltutt??` — must be addressed by commit ID or
`change_id_with_offset`. Cause surface: "When using the Git backend jj
propagates change-id. The change-id is stored in the commit header, so
after jj git fetch you can end up with a second commit with the same
change-id." (Design doc
https://www.jj-vcs.dev/latest/design/jj-converge-command/.)

Resolution is independent of bookmark cleanup:
- Drop one: `jj abandon <commit-id>`.
- Keep both with new IDs: `jj metaedit --update-change-id <commit-id>` on
  the survivor, then `jj duplicate` if you need both kept under different
  IDs (FAQ https://jj-vcs.github.io/jj/v0.26.0/FAQ/).
- Merge both: `jj new 'change_id(prefix)'` then resolve and `jj squash`.

Eventually jj will ship a dedicated `jj converge` / `jj resolve-divergence`
that walks the evolution graph and produces a single successor via a
heuristic merge (design doc above).

## 7. jj OR git for a given op?

Both write to the same `.git`, but only jj maintains the operation log,
view objects, change-ID bookkeeping, remote-bookmark tracking, and
GC-protection refs. Things break when git mutates state that jj hasn't
seen yet; here's the decision matrix:

**Use `jj` for** (always, on this repo — AGENTS.md says so):
- Creating/amending/merging commits → `jj new`, `jj describe`, `jj squash`,
  `jj split`, `jj commit`, `jj merge`.
- Moving history → `jj rebase` (auto-rebases descendants and moves
  bookmarks along change IDs).
- Bookmarks → `jj bookmark set`/`create`/`move`/`delete`/`track`.
- Branches from origin → `jj git fetch`, push → `jj git push [--all]`.
- Recovery → `jj undo`, `jj op log`, `jj op restore`,
  `jj op revert` (these read the operation store, not git).
- Init in a git dir → `jj git init` (creates the colocated workspace).

**Use raw `git` for** (read-only is safe; mutating only when unavoidable):
- Read-only inspection: `git log`, `git show`, `git diff`, `git status`,
  `git ls-files`, `git cat-file -p <hash>` (e.g. to inspect the
  reverse-hex change-id header that `git log` strips — see Format mapping
  details).
- Operations on remotes that have no jj equivalent, e.g. complex refspec
  fetches, submodules, worktrees (jj doesn't support worktrees — see
  git-compatibility §Supported features). `AGENTS.md §2` explicitly forbids
  git worktrees in this repo and says "jj handles parallel work via
  `jj new`".
- Pulling/pushing during the brief pre-`jj` era when bootstrapping; once
  `jj` is initialized here, switch back to `jj git *`.

**Never mix mutating git inside a jj checkout for**:
- `git commit`, `git merge`, `git cherry-pick`, `git reset`, `git
  rebase`, `git pull --rebase`, `git push`, `git checkout -b`,
  `git branch -f` — all of these move the tree without going through a
  jj transaction. They're stored in `.git`'s history and in jj only as an
  "import git refs" operation in the operation log (git-compatibility
  §Colocated workspaces: "You can undo the results of mutating `git`
  commands using `jj undo` and `jj op restore`. Inside `jj op log`,
  changes by `git` will be represented as an `import git refs`
  operation."). Recovery *works* but only because jj notices and imports;
  it is not the design intent.

### Concretely: `git rebase --onto` inside a `jj` checkout

What happens:
1. git rewrites refs and creates new commits in `.git`. jj doesn't see this
   through a transaction.
2. On the next `jj` command, the colocated workspace's auto-import fires,
   reads the new git ref positions, and creates an "import git refs"
   operation in jj's operation log. Bookmarks may jump, may conflict, may
   become divergent.
3. If git dropped or rewrote a commit that's part of an active change ID
   chain, the change becomes divergent (see §6 above), because change IDs
   propagate via the git commit header but git's rebase doesn't preserve
   non-standard headers.

Recovery path that existed in this incident:
- `jj op log` → find the last clean "good" operation prior to the git
  rebase.
- `jj op restore <op-id>` to roll the operation log back to that point.
- Verify bookmarks: `jj bookmark list`, resolve conflicts with
  `jj bookmark set` as in §5.
- Re-do with `jj rebase -r X -d Y` (or `-s X -o Y`) so change IDs and the
  operation log stay coherent.

If you ever need raw git and the import looks messy, `jj op restore` is
the safety net.

## 8. Mixing jj and git — safe rules

For agents operating on `/Storage/Git/spectacle` (colocated jj+git
workspace, AGENTS.md says jj is the primary VCS):

1. **Default to `jj` for every mutating op.** The AGENTS.md rules are
   binding: `jj new` / `jj describe` / `jj squash` / `jj bookmark set
   <name> -r @` / `jj git push` / `jj rebase`. Don't reach for `git
   commit`, `git rebase`, `git checkout -b`, `git push` first.
2. **Read-only git is fine.** `git log`, `git show`, `git diff`,
   `git cat-file`, `git status` etc. are side-effect-free.
3. **If you must mutate via git** (e.g. weird refspec workflow):
   - Record the current op id first (`jj op log -r @ --no-graph -T 'id
'`
     or simply eyeball `jj op log`) so you can roll back.
   - Run the git command.
   - Immediately run `jj op log` and inspect the auto-created "import git
     refs" op. If anything looks off (divergent changes `??`, conflicted
     bookmarks `??`, unexpected refs), `jj op restore <previous-op>` and
     redo the work through `jj`.
4. **Push/force-push only via `jj git push`.** It implements
   `--force-with-lease` semantics keyed on the last-seen remote position
   and turns race-induced overwrites into visible bookmark conflicts you
   can resolve.
5. **Never `git push --force` with no lease.** It bypasses both git's and
   jj's safety nets. If you must, it is a stop-the-line event — fetch,
   audit, then push.
6. **Do not use git worktrees** (AGENTS.md §2). Use `jj new` for parallel
   work or `jj workspace` for sibling working copies.
7. **Resolve divergent changes carefully.** `??` after a change ID means
   two visible commits share the ID — refer by commit ID or
   `change-id/offset`, `jj abandon` the loser (or `jj metaedit
   --update-change-id` to keep both with separate IDs).
8. **Resolve bookmark conflicts with `jj bookmark set`, not `git push`.**
   - Inspect: `jj bookmark list`, `jj log -r 'bookmarks(exact:main)'`.
   - Pick the target. Then
     `jj bookmark set main -r <rev>` (creates-or-updates).
   - Use `jj bookmark move main --to <rev> [--from <rev>] [--allow-backwards]`
     when you need the "must already exist" guarantee or `--from` filtering.
   - Use `jj bookmark create name -r @` only when you intentionally want
     "must be new" semantics (scripting, branch migration).
   - Add `--allow-backwards` only when you have already decided the
     bookmark should regress (e.g. before deleting/rewriting a stack).
9. **Bookmark divergence + push interaction is automatic.** After
   resolving a local `main??` with `jj bookmark set`, `jj git push` will
   succeed against `<remote>` only if the remote is at jj's last-seen
   position; if not, `jj git fetch` first.
10. **When in doubt, restore.** `jj op log` → pick the last known-good op
    → `jj op restore <op-id>`. The operation store is the source of
    truth; re-importing the git state from a restored view typically
    cleans up divergent changes and stray refs without losing work (jj
    retains hidden predecessors and `refs/jj/keep/*` GC-protection).

## Citations (all URL-verified)

- Bookmarks: https://docs.jj-vcs.dev/latest/bookmarks/
- Git compatibility: https://docs.jj-vcs.dev/latest/git-compatibility/
- Git comparison: https://docs.jj-vcs.dev/latest/git-comparison/
- Working with GitHub: https://docs.jj-vcs.dev/latest/github/
- Operation log: https://docs.jj-vcs.dev/latest/operation-log/
- Concurrency design: https://docs.jj-vcs.dev/latest/technical/concurrency/
- Architecture: https://github.com/jj-vcs/jj/blob/main/docs/technical/architecture.md
- Divergence guide: https://docs.jj-vcs.dev/latest/guides/divergence/
- Converge design: https://www.jj-vcs.dev/latest/design/jj-converge-command/
- Glossary: https://www.jj-vcs.dev/v0.41.0/glossary/
- FAQ (divergent changes/bookmarks): https://jj-vcs.github.io/jj/v0.26.0/FAQ/
- Tutorial (commit/change IDs): https://docs.jj-vcs.dev/latest/tutorial/
- jj-git-push(1): https://man.archlinux.org/man/extra/jujutsu/jj-git-push.1.en
- jj-git-fetch(1): https://man.archlinux.org/man/extra/jujutsu/jj-git-fetch.1.en
- jj-bookmark-set(1): https://man.archlinux.org/man/jj-bookmark-set.1.en
- jj-bookmark-move(1): https://man.archlinux.org/man/extra/jujutsu/jj-bookmark-move.1.en
- jj-rebase(1): https://man.archlinux.org/man/extra/jujutsu/jj-rebase.1.en
- jj-operation-log(1): https://man.archlinux.org/man/jj-operation-log.1.en.txt
- colocation.rs source: https://github.com/jj-vcs/jj/blob/main/cli/src/commands/git/colocation.rs
- op_heads_store.rs source: https://github.com/jj-vcs/jj/blob/main/lib/src/op_heads_store.rs
- Git command table: https://jj-vcs.github.io/jj/latest/git-command-table
- Practical bookmarks write-up: https://neugierig.org/software/blog/2025/08/jj-bookmarks.html
- GitHub discussion #2485 (real divergent-change recovery case):
  https://github.com/jj-vcs/jj/discussions/2485
