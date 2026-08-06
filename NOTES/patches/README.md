# graphiti-core edge-search patches

Upstream fix for [getzep/graphiti#1500](https://github.com/getzep/graphiti/pull/1500)
(replaces the closed [#1507](https://github.com/getzep/graphiti/pull/1507)).
Eliminates the O(matches×graph) per-row re-MATCH in `edge_fulltext_search`
and `edge_bfs_search` that causes FalkorDB `Query timed out` on graphs
with ~900+ `RELATES_TO` edges.

## Files

- `graphiti-core-edge-search.patch` — falkordb driver (2 hunks: `edge_fulltext_search` + `edge_bfs_search`)
- bundled in `_graphiti.nix` `hermes-graphiti-seed` activation script via `git apply`

## Status

- Tested on `graphiti-core 0.29.2` + FalkorDB `edge-alpine`
- 9 facts retrieved in 1.7s (was 0 — `Query timed out`)
- Plugin prefetch logs `facts: 10` post-patch

## Upstream merge

Tracked via [getzep/graphiti#1500](https://github.com/getzep/graphiti/pull/1500).
Remove this patch and the activation hook once `graphiti-core >= 0.29.4` lands
(or whatever version first includes the fix).

## Apply manually

```bash
cd /var/lib/hermes/graphiti
git apply /var/lib/hermes/spectacle/NOTES/patches/graphiti-core-edge-search.patch
sudo -u hermes bash -c 'cd /var/lib/hermes/graphiti/mcp_server && uv sync --reinstall-package graphiti-core'
sudo -u hermes XDG_RUNTIME_DIR=/run/user/$(id -u hermes) systemctl --user restart graphiti-mcp
```
