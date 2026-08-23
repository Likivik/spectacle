# Plan: profile name → graphiti group_id scoping

## Goal
Derive each profile's graphiti memory partition (`group_id`) from its Hermes
profile identity, with the **default profile deferring to the MCP server's
configured default** (no `"likivik"` literal in plugin code).

## Verified facts (source-checked)
- Plugin gets `hermes_home` + `agent_context` in `**kwargs` from
  `agent/agent_init.py:1895-1900`. `agent_context` is a *turn type*
  (`primary|subagent|cron|flush`), not tenant identity — unusable.
- Profile identity source: `hermes_home` (`~/.hermes` for default,
  `~/.hermes/profiles/<name>` for named) or `HERMES_PROFILE` env var.
- Server fallback is symmetric:
  - write `graphiti_mcp_server.py:449`: `group_id or config.graphiti.group_id`
  - read `:519-525` / facts: `group_ids if not None else [config.graphiti.group_id]`
- `config.graphiti.group_id` = `"likivik"` (config.yaml), falkordb `database` =
  `"likivik"` (single shared graph; group_id is the tenant column inside it).
- Default profile today: `HERMES_HOME=/var/lib/hermes/.hermes`, `HERMES_PROFILE`
  empty, no `profiles/` dir. "default" is a reserved alias for `~/.hermes`.

## Design
```
resolve_scope(hermes_home, HERMES_PROFILE):
    HERMES_PROFILE set            -> "<name>"          (named profile)
    hermes_home under profiles/<n>-> "<n>"             (named profile)
    else                          -> None              (default -> defer)
```
- named profile -> pass `group_id`/`group_ids` explicitly.
- default profile -> **omit** on both write and read -> server uses config default.

## Changes
All in `modules/aspects/server/hermes/hermes-graphiti-plugin/__init__.py`:

1. **Scope resolution** (`:173-190`, `:577-578`, `:604-605`):
   - New `resolve_scope(hermes_home=..., profile=os.environ.get("HERMES_PROFILE"))`
     returning `str | None`.
   - `current_scope(...)` reduced to a shim calling `resolve_scope`; returns
     `str | None` instead of hardcoded `"likivik"`.
   - `cascading_scopes(scope) -> [scope] if scope else []`.
   - `__init__`/`initialize` capture `hermes_home` from `kwargs` and set
     `self._scope = resolve_scope(...)`.

2. **`add_memory` client** (`:373-384`): `group_id: str | None = None`; build
   arg conditionally (`if group_id: args["group_id"] = group_id`). Matches the
   read methods' existing conditional pattern.

3. **No other call sites**: `_sync_loop` (`:740`) already passes `self._scope`;
   `_start_prefetch`/`_search` (`:666`, `:962`, `:1026`) already call
   `cascading_scopes(self._scope)` and the read methods omit on empty.

4. **No config change**: `_graphiti.nix` `group_id: "likivik"` + falkordb
   `database: "likivik"` stay — they *are* the fallback.

## Tests
Extend `pkgs/hermes-tests/graphiti/test_config.py`:
- `test_no_likivik_literal_in_plugin` — assert `"likivik"` never appears as a
  literal in the plugin source (forces the "defer, never hardcode" invariant).
- `test_resolve_scope_named_vs_default` — `resolve_scope(profiles/gf)` == "gf";
  `resolve_scope(~/.hermes, HERMES_PROFILE unset)` is None.
- Keep `test_falkordb_database_is_likivik` (config side unchanged).

## Verification before deploy
1. `nix flake check` (or at least `checks.x86_64-linux.hermes-tests`) green.
2. New guards pass against the changed plugin.
3. Live smoke: `graphiti_list_episodes(limit=3)` still returns 3 (default still
   lands on "likivik").

## Explicitly out of scope (this change)
- The default→`likivik` clone (separate task, after this lands).
- Adding the `gf` profile / her bot token / per-profile config.
- Per-user litellm keys, langfuse projects, dashboard auth.
