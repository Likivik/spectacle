# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues.

## Conventions

- **Create an issue**: `github_create_issue` with `owner`, `repo`, `title`, `body`, `labels`
- **Read an issue**: `github_get_issue` for body/labels/state. For comments fall back to `gh issue view <number> --comments` (native tools don't expose comments)
- **List issues**: `github_list_issues` with label/state/sort. For comments fall back to `gh issue list --state open --json number,title,labels,comments --jq '...'` with label/state filters
- **Comment on an issue**: `github_add_issue_comment`
- **Apply / remove labels**: `github_update_issue` with `labels` array
- **Close**: `github_update_issue` with `state="closed"`

Infer owner/repo from `git remote -v`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue via `github_create_issue`.

## When a skill says "fetch the relevant ticket"

Use `github_get_issue` for body/labels. Add `gh issue view <number> --comments` if comments are needed.
