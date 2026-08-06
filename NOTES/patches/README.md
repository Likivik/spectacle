# graphiti-core edge-search patches

Upstream fix for [getzep/graphiti#1500](https://github.com/getzep/graphiti/pull/1500)
(replaces the closed [#1507](https://github.com/getzep/graphiti/pull/1507)).
Eliminates the O(matches×graph) per-row re-MATCH in `edge_fulltext_search`
and `edge_bfs_search` that causes FalkorDB `Query timed out` on graphs
with ~900+ `RELATES_TO` edges.

## Files

- `graphiti-core-edge-search.patch` — fix in 3 places:
  - `graphiti_core/driver/falkordb/operations/search_ops.py` (`edge_fulltext_search`)
  - `graphiti_core/driver/falkordb/operations/search_ops.py` (`edge_bfs_search`)
  - `graphiti_core/search/search_utils.py` (the live path used by `Graphiti.search()`)
- applied in `_graphiti.nix` `hermes-graphiti-seed` activation script via `patch -p1`

## Status

- Tested on `graphiti-core 0.29.2` + FalkorDB
- Both `search_nodes` and `search_memory_facts` succeed with patched source
- Plugin prefetch logged `facts: 10` post-patch

## Upstream merge

Tracked via [getzep/graphiti#1500](https://github.com/getzep/graphiti/pull/1500).
Remove this patch and the activation hook once `graphiti-core >= 0.29.4` lands
(or whatever version first includes the fix).

## Apply manually

```bash
cd /var/lib/hermes/graphiti/mcp_server/.venv/lib/python3.12/site-packages
patch -p1 < /var/lib/hermes/spectacle/NOTES/patches/graphiti-core-edge-search.patch
sudo -u hermes XDG_RUNTIME_DIR=/run/user/$(id -u hermes) systemctl --user restart graphiti-mcp
```
