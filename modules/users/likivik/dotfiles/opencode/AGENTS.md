## Workflow
- Delegate as much as possible
- Create plan -> ask user
- Never invent new steps without confirming with user.
- Never take new direction without confirming with user.
- ALWAYS ask user before next steps or sub-steps!
- stop and ask — do NOT decide alone.
- ALWAYS ask to confirm a commit message.
- Never commit without explicit permission
- CONFIRM EVERY STEP WITH USER - DON'T TRY TO DO SEVERAL TASKS AT ONCE.

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

## Memory

Use **Mnemosyne** (MCP tools `mnemosyne_remember` / `mnemosyne_recall`)
for persistent cross-session memory.
On session start, proactively call `mnemosyne_recall` with relevant keywords.
