# graphiti-core patches

## edge-search.patch

Applies [PR #1500](https://github.com/getzep/graphiti/pull/1500) to
`graphiti-core 0.29.3` at pypi build time via `patches = [ ./patches/edge-search.patch ]`
in `pkgs/graphiti/core.nix`.

### What it fixes

`search_memory_facts` calls into `Graphiti.search()` →
`graphiti_core/search/search_utils.py::edge_fulltext_search`,
which generated Cypher that materialized the entire candidate set
on a per-row `MATCH (n:Entity)-[e:RELATES_TO {uuid: rel.uuid}]->(m:Entity)`.
On our 900-edge graph with broad-tokened OR queries this exceeded
FalkorDB's default 1000 ms TIMEOUT.

The fix replaces the per-row MATCH with `startNode(e)` / `endNode(e)`:

```cypher
-- BEFORE
CALL db.idx.fulltext.queryRelationships('RELATES_TO', $query)
    YIELD relationship AS rel, score
    MATCH (n:Entity)-[e:RELATES_TO {uuid: rel.uuid}]->(m:Entity)

-- AFTER
CALL db.idx.fulltext.queryRelationships('RELATES_TO', $query)
    YIELD relationship AS e, score
    WITH e, score, startNode(e) AS n, endNode(e) AS m
```

Per maintainer, expected ~225× speedup.

### Where it's applied

Three sites, all unified into one patch:

| File | Function |
|---|---|
| `graphiti_core/driver/falkordb/operations/search_ops.py` | `edge_fulltext_search` |
| `graphiti_core/driver/falkordb/operations/search_ops.py` | `edge_bfs_search` |
| `graphiti_core/search/search_utils.py` | `edge_fulltext_search` (the live path) |

### Why this directory

Patches live next to the package that uses them, so the
`patches = [ ./patches/edge-search.patch ]` reference in
`core.nix` is co-located with the patch itself.

### When to remove

When upstream PR #1500 merges + ships in a graphiti-core release.
Then:

1. Drop `patches = [ ... ]` from `pkgs/graphiti/core.nix`
2. Delete this directory
3. Bump `version` in `core.nix` to the new release