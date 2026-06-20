---
description: Group staged/unstaged changes into logical commits, then push.
agent: build
---

Package changes into meaningful conventional commits, then push.

1. Gather: `git status --short` + `git diff --stat` + `git log --oneline -10` + `git rev-parse --abbrev-ref HEAD`
2. Group files by logical area into commits with conventional prefixes + optional scopes
3. Propose in order, ask "Commit all? (y/n/edit)"
4. For each: `git add <files>` → `git commit` → push at the end

Abort conditions: empty status / detached HEAD / merge in progress.
