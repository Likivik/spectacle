# General git cheatsheet

## General Overview

See all branches, tags, commits
`git log --oneline --graph --all --decorate`

Last commit overview
`git show --stat HEAD`

Commits on current branch not on main:
`git log --oneline main..HEAD`

---

## Diff

Unstaged changes
`git diff`

Staged (index) changes
`git diff --cached`

Files-only summary
`git diff --stat`

___

