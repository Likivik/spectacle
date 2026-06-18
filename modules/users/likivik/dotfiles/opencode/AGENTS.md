## Workflow
- Delegate as much as possible
- Create plan -> ask user
- ALWAYS ask to confirm a commit message.
- Never commit without explicit permission

## Response style (IMPORTANT!!!)
- Terse, technical, no fluff. Fragments OK. Arrows for causality (X → Y).
- Conserve tokens, answer shortly, laconically.

## Commit discipline
- Always confirm commit message with user before committing.
- Never push without explicit permission.
- Never force-push or --amend without explicit permission.
- Never commit secrets or API keys.

## `nh os switch` requires sudo
- This command requires a sudo password and cannot be run non-interactively.
- Agent must delegate: print the exact command for the user to copy-paste and run manually.

## Memory (Mnemosyne MCP)

~28 tools available via MCP. Writes to `~/.hermes/mnemosyne/data/mnemosyne.db`.

### On session start
1. `mnemosyne_recall_canonical(category="identity")` — who is the user
2. `mnemosyne_recall_canonical(category="preference")` — user preferences
3. `mnemosyne_recall(query="recent session", limit=5)` — recent activity
4. `mnemosyne_recall(query="<current project name>", limit=5)` — project context

### When to use each tool

| Situation | Tool | Notes |
|---|---|---|
| User says "remember/save this" | `mnemosyne_remember(content, importance=0.7, scope="global")` | Higher importance for decisions, lower for trivia |
| User asks about past work or gives vague instructions | `mnemosyne_recall(query, limit=5)` | Call BEFORE answering |
| Stable fact about user (name, OS, stack, style) | `mnemosyne_remember_canonical(category, name, body)` | Auto-supersedes old value in same slot. No need to invalidate first. |
| Query structured facts | `mnemosyne_triple_query` or `mnemosyne_recall_canonical` | |
| Multi-step complex task — track progress | `mnemosyne_scratchpad_write(content)` → later `mnemosyne_scratchpad_read` → done: `mnemosyne_scratchpad_clear` | One scratchpad per session, survives context compaction |
| Old fact is now wrong | `mnemosyne_invalidate(memory_id="<id>")` | Expires it. Won't surface in default recall. |
| Old fact replaced by new understanding | `mnemosyne_invalidate(memory_id="<old>", replacement_id="<new>")` then `mnemosyne_remember(content, importance=0.7, scope="global")` | Chains old→new |
| Before long session gap | `mnemosyne_sleep` | Consolidates working memory to episodic |
| Backup | `mnemosyne_export(output_path)` | |
| Link related memories | `mnemosyne_graph_link(source_id, target_id, relationship, weight)` | |

### Importance scoring
- `0.0-0.3`: Trivial, session-specific, likely useless later
- `0.4-0.6`: Useful context, not critical (default)
- `0.7-0.9`: Important decisions, user preferences, project conventions
- `1.0`: Critical identity facts

### Scope
- `session` (default): Temporary, consolidated on `mnemosyne_sleep`
- `global`: Permanent, cross-session

### When you detect a contradiction
If recall or conversation shows old fact A but new information proves fact B:
1. `mnemosyne_invalidate(memory_id="<A-id>")` — expire the old
2. `mnemosyne_remember(content="<B>", importance=0.7, scope="global")` — store the new
3. For canonical facts: just `mnemosyne_remember_canonical` with new body (auto-supersedes)
