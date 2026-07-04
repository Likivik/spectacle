## Workflow
- ALWAYS ask user to choose direction/strategy/approach, NEVER decide on your own without approval

## Response style (IMPORTANT!!!)
- 4 lines max by default. Longer only on request.
- Terse. Fragments. Arrows for causality.
- No preamble, no postamble, no restating the question.

## Commit discipline
- ALWAYS ask to confirm a commit message, NEVER commit without explicit permission
- Never push without explicit permission.
- Never force-push or --amend without explicit permission.
- Never commit secrets or API keys.

## Memory (Mnemosyne MCP)

~28 tools available via MCP. Writes to `~/.hermes/mnemosyne/data/mnemosyne.db`.

### Recall
Plugin auto-injects `## Mnemosyne Context` on every turn using dynamic recall from your last message. Call `mnemosyne_recall` only when context is stale or insufficient.

### Auto-store
Plugin auto-captures conversation turns: `[USER]` (imp 0.5), `[ASSISTANT]` (imp 0.15), and identity signals (imp 0.85, scope=global). Explicit `mnemosyne_remember` calls still work for manual storage.

### When to use each tool

| Situation | Tool | Notes |
|---|---|---|
| User says "remember/save this" | `mnemosyne_remember(content, importance=0.7, scope="global")` | Higher importance for decisions, lower for trivia |
| User asks about past work or gives vague instructions | `mnemosyne_recall(query, limit=5)` | Call BEFORE answering |
| Retrieve a specific memory by ID | `mnemosyne_get(memory_id)` | Pure read, no search |
| Stable fact about user (name, OS, stack, style) | `mnemosyne_remember_canonical(category, name, body)` | Auto-supersedes old value in same slot. No need to invalidate first. |
| Query structured facts | `mnemosyne_triple_query` or `mnemosyne_recall_canonical` | |
| Add a structured fact triple | `mnemosyne_triple_add(subject, predicate, object)` | E.g. `("user", "prefers", "neovim")` |
| Link related memories | `mnemosyne_graph_link(source_id, target_id, relationship, weight)` | |
| Traverse memory graph | `mnemosyne_graph_query(seed_memory_id, max_hops, edge_type)` | BFS from seed |
| Multi-step complex task — track progress | `mnemosyne_scratchpad_write(content)` → later `mnemosyne_scratchpad_read` → done: `mnemosyne_scratchpad_clear` | One scratchpad per session, survives context compaction |
| Update a memory's content/importance | `mnemosyne_update(memory_id, content?, importance?)` | |
| Delete a memory | `mnemosyne_forget(memory_id)` | Permanent |
| Old fact is now wrong | `mnemosyne_invalidate(memory_id="<id>")` | Expires it. Won't surface in default recall. |
| Old fact replaced by new understanding | `mnemosyne_invalidate(memory_id="<old>", replacement_id="<new>")` then `mnemosyne_remember(content, importance=0.7, scope="global")` | Chains old→new |
| Attest/validate another agent's memory | `mnemosyne_validate(memory_id, action, validator)` | Collaborative ownership |
| Before long session gap | `mnemosyne_sleep` | Consolidates working memory to episodic |
| Memory stats | `mnemosyne_stats` | Working/episodic counts |
| Diagnostics | `mnemosyne_diagnose(repair_vec_working=true)` | PII-safe, checks deps + DB |
| Backup | `mnemosyne_export(output_path)` | |
| Cross-agent surface storage | `mnemosyne_shared_remember(content, kind="meta")` | Shared DB, not private |
| Cross-agent surface recall | `mnemosyne_shared_recall(query, limit=5)` | |
| Sync | `mnemosyne_sync_push` / `mnemosyne_sync_pull` / `mnemosyne_sync_status` | Remote sync server |

### Store triggers — fire these during conversation
| When | Action | Importance | Scope |
|---|---|---|---|
| User states a preference | `mnemosyne_remember_canonical(category="preference", name="<topic>", body="<value>")` | — | global |
| Commit made | `mnemosyne_remember(content="<subject>: <files>", ...)` | 0.6 | global |
| Build command succeeds | `mnemosyne_remember(content="<cmd> works for <purpose>", ...)` | 0.5 | global |
| Architecture decision | `mnemosyne_remember(content="<decision>", ...)` | 0.8 | global |
| User says "remember" | `mnemosyne_remember(content="<exact quote>", ...)` | 0.7 | global |
| User voices identity signal ("I'm proud", "imposter", "barely know", etc.) | `mnemosyne_remember(content="[IDENTITY] ...", source="identity", importance=0.85, scope="global", veracity="stated")` | 0.85 | global |

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
