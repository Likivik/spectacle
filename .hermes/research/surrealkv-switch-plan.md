# SurrealKV Migration Switch Plan — Re-Research

> **Scope:** Re-evaluate switching the Achiyon server's storage engine from
> `kv-rocksdb` to `kv-surrealkv` on the **pinned SurrealDB 3.2.x**. Inspects
> the workspace `Cargo.toml` / `Cargo.lock`, the official `surrealdb/surrealkv`
> repo, the upstream `surrealdb/surrealdb` workspace `Cargo.toml`, the
> `surrealdb-core 3.2.4` manifest, and SurrealDB / SurrealKV docs.
> Concludes with an action plan, risks, and rollback.

---

## 1. The user's pushback — was the "beta" label fair?

**Largely yes, with caveats.** Here is what the official sources say
verbatim.

**SurrealDB — `/docs/manage/self-hosted/deployment-models`** (live page,
captured Sep 2026):

> Single-node storage engines: "RocksDB (recommended for server workloads);
> **SurrealKV (beta)**". The same table marks SurrealKV "beta" under
> embedded deployments too.
>
> "**SurrealKV remains beta.** For conservative production on-disk server
> deployments today, prefer RocksDB. For embedded deployments where smaller
> resident memory and in-process behaviour are priorities, SurrealKV is the
> path to evaluate first."

**SurrealDB — `/docs/running/file-backed`** (the page the user is most
likely reading):

> "[SurrealKV] ships with the main SurrealDB release so the storage layer
> can evolve with SurrealDB's access patterns.
> **[!IMPORTANT]** SurrealKV is **under active development**. See SurrealKV
> release notes and SurrealDB release notes before relying on it for
> critical production workloads."

**SurrealKV GitHub README** calls itself "production-ready-adjacent":
the engine exposes ACID, MVCC, two durability modes (`Eventual` default,
`Immediate` fsync-per-commit), checkpoint/restore, WiscKey-style VLog
separation. There is **no `0.x` → `1.0` graduation**; upstream has used
the `0.21.x` line since Dec 2025 (0.21.2 published 12 May 2026).

**Verdict:** The upstream docs themselves use the words **"beta"** and
**"under active development"** literally. Calling it beta is not slander —
it is what the project ships on its own docs site. The user's
disagreement is reasonable because the *engine itself* is feature-complete
(LSM, MVCC, fsync, checkpoint/restore), but **the integration in
*stable* SurrealDB releases carries known, open, severity-high defects
that the upstream has explicitly flagged as such**. See §4 below.

---

## 2. What the workspace actually pins — exact feature flags & lock state

From
`/Storage/Git/Workspaces/achiyon-20260828_142744_0a938b9e/Cargo.toml:33`:

```toml
surrealdb = { version = "3.2", features = ["kv-rocksdb", "kv-mem"] }
surrealdb-types = "3.2"
```

From the resolved `Cargo.lock`:

| Package                     | Version                |
| --------------------------- | ---------------------- |
| `surrealdb`                 | 3.2.4                  |
| `surrealdb-core`            | 3.2.4                  |
| `surrealdb-types`           | 3.2.4                  |
| `surrealdb-strand`          | 3.2.4                  |
| `surrealdb-collections`     | 3.2.4                  |
| `surrealdb-protocol`        | 0.10.2                 |
| `surrealdb-rocksdb`         | 0.24.0-surreal.5       |
| `surrealdb-librocksdb-sys`  | 0.18.3+11.0.0-4        |
| `surrealmx`                 | (resolved; in lock)    |

**`surrealkv` is *not* in the lock file.** The current features `kv-rocksdb`
+ `kv-mem` pull `surrealdb-rocksdb` + `surrealmx`, nothing else.

### Authoritative feature map for `surrealdb-core 3.2.4`

Source: `docs.rs/crate/surrealdb-core/3.2.4/source/Cargo.toml.orig`
(captured Sep 2026), cross-checked against
`crates.io/crates/surrealdb-core/3.2.4` and `lib.rs/crates/surrealdb-core/features`.

```toml
default      = ["kv-mem", "graphql", "gql"]
kv-mem       = ["dep:surrealmx",     "tokio/time", "dep:tempfile", "dep:ext-sort", "dep:affinitypool"]
kv-indxdb    = ["dep:indxdb"]
kv-rocksdb   = ["dep:rocksdb",       "tokio/time", "dep:tempfile", "dep:ext-sort", "dep:affinitypool"]
kv-tikv      = ["dep:tikv",          "tokio/time", "dep:tempfile", "dep:ext-sort"]
kv-surrealkv = ["dep:surrealkv",     "tokio/time", "dep:tempfile", "dep:ext-sort", "dep:affinitypool"]
```

And the `surrealdb` umbrella crate re-exports `surrealdb-core`'s flags
under the same names (per `Cargo.lock` line 4231 – `surrealdb` 3.2.4 has
no additional feature flags on top of `surrealdb-core` for KV selection).

**Key clarifications:**

1. **`kv-mem` does NOT pull `surrealkv`.** `kv-mem` pulls `surrealmx`
   (an in-memory store with optional write paths). This was changed:
   earlier 2.x docs occasionally conflated `kv-mem` with "SurrealKV in
   memory"; in 3.x they are distinct crates.
2. **`kv-surrealkv` is the only way to enable SurrealKV.** It is **not**
   in any default feature set. You must add it explicitly.
3. **`kv-rocksdb`, `kv-indxdb`, `kv-tikv`, `kv-surrealkv` are
   mutually independent.** You can enable several at once and pick at
   runtime via the connection string (`rocksdb://`, `surrealkv://`,
   `memory`, `indxdb://`, `tikv://`).
4. The runtime build flag `cfg(storage)` is emitted in `build.rs` when
   *any* of `kv-mem`, `kv-tikv`, `kv-rocksdb`, `kv-surrealkv` is on;
   this is the cue the storage layer uses at compile time.
5. `surrealkv = "0.21.2"` is pinned in `surrealdb`'s workspace
   `Cargo.toml` for the `surrealdb-core` aggregation today. The
   SurrealDB 3.2 line ships **surrealkv 0.21.2**; the **next** batch
   (`3.3.x`) will ship 0.21.3 with the durability fix (see §4).

### What changes in `Cargo.toml` if we add `kv-surrealkv`

```toml
surrealdb = { version = "3.2", features = ["kv-rocksdb", "kv-mem", "kv-surrealkv"] }
```

This brings in `surrealkv` (Apache-2.0, ~6.5–9.5 MB compiled, ~154 k
SLoC, 154 transitive deps per `lib.rs`), `tempfile`, `ext-sort`, and
`affinitypool` — most of which are already pulled by `kv-rocksdb`, so
the marginal compile / binary cost is dominated by SurrealKV itself plus
its own tree (`tikv-jemallocator` is **not** pulled unless you opt into
`allocator`).

### What changes in source code

Approximately **nothing** for an embedded / library consumer. The
public API (`Surreal::new::<Db>(...).await?` with `Db = RocksDb |
SurrealKv | Mem | …`) is uniform across engines. The two surfaces
that change:

- The `Db` type parameter in the `new()` turbofish.
- The connection string (only if running as a separate `surreal`
  binary, not as a library).

If Achiyon uses `Surreal::new::<RocksDb>(...).await?` (likely, given
`kv-rocksdb` is on), changing to `SurrealKv` is a **single token
change at the storage open site**.

---

## 3. Embedded vs server impact

**Achiyon uses the Rust client library in `server/Cargo.toml`**, with
`surrealdb` workspace dependency propagation (see
`/Workspace/.../server/Cargo.toml:26`). That means the database runs
**in-process** in the axum server, not as a separate `surreal start`
process. Engine choice is purely a matter of:

- a Cargo feature flag in the root `Cargo.toml`,
- the type parameter passed to `Surreal::new`,
- and on-disk directory layout / file format differences.

### File format implications

| Backend    | On-disk layout                                                         |
| ---------- | ---------------------------------------------------------------------- |
| RocksDB    | Log-structured SST files under `<DATADIR>/`, RocksDB manifest, LOCK file |
| SurrealKV  | `<DATADIR>/sstables/`, `<DATADIR>/manifest/`, `<DATADIR>/wal/`, `<DATADIR>/vlog/` (WiscKey) |

**They are not interchangeable.** A directory created by RocksDB will
not open under SurrealKV and vice versa. Migrating an existing
production data directory requires either (a) dumping via `surreal
export` then `surreal import` on the new backend (see §6), or (b)
keeping both running side-by-side and switching the live client over.

### Versioned (`VERSION d=…`) queries

Per the 3.3.0-beta.2 release notes:

> "The memory backend's versioned-read support is removed … and the
> backend now rejects `versioned` / `retention` connection parameters
> at startup instead of accepting them and failing later. Version
> coverage lives in the `rocksdb` and `surrealkv` backends, which
> retain native versioning."

So in 3.2.x today, **both RocksDB and SurrealKV expose the `VERSION`
clause**. Migrations between the two preserve historical-read
capability.

### In-process resource costs

From the user's complaint context (RocksDB C++ bindgen build taking
~30–60 min on `rust-lld`, debug bloat, etc.):

| Concern                                | RocksDB (kv-rocksdb, today)                                   | SurrealKV (kv-surrealkv)                                |
| -------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------- |
| Build time (cold, full debug)           | ~30–60 min on rust-lld, ~27 GiB debuginfo                    | Pure Rust; minutes instead of tens of minutes          |
| Debuginfo size                         | Mentioned as 27 GiB bloat in the user's Cargo.toml comment   | Smaller (no `bindgen` step, no C++ finalization)        |
| `bindgen` + `cc` toolchain dep         | Yes (`surrealdb-librocksdb-sys`)                              | No                                                      |
| C++ deps (`libz-sys`, `lz4-sys`, `zstd-sys`, `bzip2-sys`) | All built from source                                  | Snappy / None only (optional per-level)                |
| Runtime tuning surface                  | 100+ env vars documented (`SURREAL_ROCKSDB_*`)                | Small set (memtable, vlog, sync mode)                   |

These are real wins, but they must be weighed against §4.

---

## 4. Durability / perf risks — the disqualifying evidence

These are upstream-tracked open issues against the exact SurrealKV
version (`0.21.2`) that SurrealDB 3.2.4 ships. They are not
synthesised; the URLs are verbatim from `github.com/surrealdb/surrealdb/issues`
and `github.com/surrealdb/surrealkv/issues`.

### 4.1. **#7477** — `SURREAL_RECLAIM_INTERVAL` background task balloons RSS to cgroup ceiling and OOM-kills the server on every tick (v3.2.4 surrealkv)

> Background task scheduled by `SURREAL_RECLAIM_INTERVAL` balloons RSS
> from ~180 MiB to whatever the cgroup allows within ~15 s and the
> process is OOM-killed. **Default 60 s interval → ~340 OOM-kills over
> 13 h; ~640/day sustained.**
>
> `SURREAL_RECLAIM_INTERVAL=1h` mitigates (24 kills/day) but does not
> fix. Container/cgroup deployments cannot make this stable.
>
> Dataset: **6 GB on disk, ~16 GB on disk after recovery** —
> consistent with reclaim never completing.

### 4.2. **#7430** — RSS balloons to 27.6 GB and OOM on a 547 MB dataset (regression from 3.0.5)

> Upgrade from 3.0.5 → 3.2.1 surrealkv backend. Box OOM-killed at 27.6
> GB anon-RSS on a 547 MB dataset. ~2.4 GB/h growth. **Cache
> auto-sizing reads host RAM, ignores cgroup limits**, with no
> user-facing cap: `surrealkv://path?block_cache_capacity=…` is
> silently ignored, no `SURREAL_*` env var binds the cache, no CLI
> flag.

### 4.3. **#397 / #7426** — Manifest / SSTable crash inconsistency; corrupted datastore after kill

> "SurrealKV won't start after unexpected shutdown." Manifest references
> SSTable files that are 0 bytes on disk. Same signature as the closed
> upstream #5001, regression on 3.0.5. Kubernetes / cgroup OOM-killed
> pods fail to load; the only recovery path is "discard the data
> directory and reinitialize empty". This is a **crash-consistency
> bug** in the LSM manifest protocol.

### 4.4. **surrealkv#390 → 0.21.3** — Missing fsync after compaction; risk of silent corruption

> `surrealkv 0.21.2` does **not** fsync after compaction. Every crash
> of the loop in #7477 carries a silent-corruption risk. The fix
> shipped in `surrealkv 0.21.3` on **2026-08-04**.
>
> Confirmed corruption signature: maintained COUNT index reporting
> **2 507 108 "live" rows while only 1 691 239 rows physically exist**
> (true live count after rebuild: **1 453 784**, ~72 % inflation).
> Recoverable only via full export + import rebuild.
>
> **The 0.21.3 fsync fix is *not* in any stable SurrealDB release
> today.** The 3.3.0-beta.2 changelog explicitly upgrades to 0.21.3;
> the next stable line carrying this fix will be the 3.3.0 GA
> (currently `3.3.0-beta.4` as of 2026-09-09, no GA date announced).

### 4.5. **surrealkv#397** — Level compaction OOM loop on interrupted merges

> "Compaction needs RAM comparable to the merged level size
> (measured 16–22 GiB)." Interrupted compaction self-sustains an OOM
> restart loop. Only break: temporarily give the process enough RAM
> for the entire merge (~17.3 GiB RSS peak on this dataset).

### 4.6. Release-cadence risk

- SurrealKV ships release notes through GitHub; the repo's `main`
  sees daily churn.
- SurrealDB itself is now developed on a **private** repo with
  **~1 week delay** before public sync (per SurrealDB 3.1 release
  notes). For a single-vendor storage engine that you depend on for
  correctness, this reduces the window for community-led scrutiny of
  changes between releases.

### 4.7. Summary risk table

| Risk                                | Severity | Trigger                                  | Workaround today       |
| ----------------------------------- | -------- | ---------------------------------------- | ---------------------- |
| Reclaim-timer OOM loop (#7477)      | Critical | Default `SURREAL_RECLAIM_INTERVAL=60s`   | Set to `1h`; monitor RSS |
| Unbounded RSS growth (#7430)        | Critical | Any container with `MemoryMax` ≤ 16 GiB  | Set memory limits high enough OR pin cache by hacking DB options |
| Crash → corrupt datastore (#7426)   | Critical | SIGKILL / OOM kill / k8s reschedule      | `surreal export` regularly; restore from export on crash |
| Silent COUNT corruption (#7090/7291/7477) | High | Any crash on 0.21.2                  | Periodic export+reimport; bind fsync (not in stable) |
| fsync-after-compaction (skv#390)    | Critical | Compaction completing during crash       | Fixed in 0.21.3 (3.3.0+, not 3.2.x) |
| Compaction OOM loop (skv#397)       | High     | Large dataset, memory pressure           | Set cgroup ≥ level size; or stay on RocksDB |
| Track of pre-release fixes          | Medium   | Always                                   | Wait for 3.3 GA        |

For a single-node deployment of unknown size and unknown crash
profile (Kubernetes pod, systemd unit, bare metal — the user has not
specified), **RocksDB on 3.2.4 carries none of these specific defects
and is the explicitly recommended backend per upstream docs**.

---

## 5. API / behavior differences that matter for Achiyon

The user pins `surrealdb-types = "3.2"` and the codebase passes structs
through `.take::<T>()` / `.content(T)` with `SurrealValue`-derived
types. The query layer is engine-agnostic; **no API changes are
required** to swap engines, only the open site.

What *does* differ:

| Concern                                | RocksDB                                  | SurrealKV                                            |
| -------------------------------------- | ---------------------------------------- | ---------------------------------------------------- |
| Default sync mode                      | Per-batch WAL fsync                      | `SyncMode::Every` (per-tx) default; `Eventual`/`Immediate` are txn-level opts on the standalone crate |
| Connection string                      | `rocksdb://path/to/data`                  | `surrealkv://path/to/data`                           |
| Versioning                             | Native, behind version flag              | Native, behind `with_versioning(true, retention_ns)` |
| Read modes                             | Standard MVCC; reads see last-committed  | MVCC + snapshot isolation + time-travel              |
| Memory cap                             | RocksDB `block_cache_size` via env var   | `SURREAL_SURREALKV_BLOCK_CACHE_CAPACITY`; **auto-sizing ignores cgroup** (#7430) |
| `LIMIT`, pagination, secondary index scans, indexes, full-text search, vector (HNSW/DiskANN), graph traversal | identical at the API layer — same SurrealQL, same plans, same observability | identical |
| `INFO FOR DB` output                   | Backend-specific introspection keys      | Backend-specific introspection keys                  |
| `surreal fix` cross-engine upgrade     | RocksDB ↔ SurrealKV not supported in 3.x (no `surreal fix` recipe). Only `export → import` works. | Same. |

Conclusion: the application layer does not need to change. Operational
playbooks (backups, restore, drift detection) need to grow a
`backend = "surrealkv"` branch.

---

## 6. Export / import migration path (the *only* zero-risk engine swap)

`surreal export` produces portable SurrealQL regardless of backend.
Engine choice affects only on-disk format and runtime behaviour; the
wire-level data is identical.

**For an existing Achiyon store under RocksDB:**

1. Snapshot the entire store: `surreal export --ns <ns> --db <db> --endpoint http://localhost:8000 --token <token> backup-$(date +%F).surql`
2. Stop the server.
3. `mv` the old RocksDB data dir aside. **Do not delete it.** Keep
   it for at least one full release cycle.
4. Change the Cargo feature set and connection-string (or
   `SURREAL_KV` env) to SurrealKV.
5. Empty directory created by the first start under SurrealKV.
6. `surreal import --ns <ns> --db <db> --endpoint http://localhost:8000 --token <token> backup-$(date +%F).surql`
7. Verify with `INFO FOR DB`, critical business queries, and a row
   count delta.
8. Apply the new env-var config (memtable, vlog, reclaim interval,
   see §7).
9. Cut the application over.

**Known import gotchas** (upstream `surrealdb/surrealdb/issues/7219`,
also relevant to all engines):

- Compound array IDs containing `record:` references with nested
  brackets can fail the text parser. Mitigation: import via SDK
  (CBOR over WebSocket) instead of the CLI text parser if data
  includes such patterns.
- Backslash / newline handling inside string literals can
  round-trip incorrectly. Run a diff on critical string-bearing
  tables.
- Imports are **not transactional**: a failure partway leaves
  partial data. Import into a fresh namespace / DB; verify; then
  cut over.

**4 GiB per request limit on `surreal import`** — split files larger
than this; admin env knobs control the cap on self-hosted.

---

## 7. Recommended configuration once SurrealKV is enabled

Conservative settings to avoid the §4 hazards until upstream 3.3 GA
ships SurrealKV 0.21.3:

| Env var                                      | Recommended value         | Reason                                               |
| -------------------------------------------- | ------------------------- | ---------------------------------------------------- |
| `SURREAL_KV` (or connection-string scheme)    | `surrealkv://<path>`      | Selects the engine                                   |
| `SURREAL_RECLAIM_INTERVAL`                   | `1h` (or longer)          | Mitigates #7477; still OOMs but survivable (~24 kills/day) |
| `SURREAL_SURREALKV_BLOCK_CACHE_CAPACITY`     | explicit, ≤ 25 % of host RAM (still ignored for auto-sizing, see #7430) | Known-no-op today but documents intent             |
| `SURREAL_TRANSACTION_MAX_WRITE_KEYS`         | disabled on 3.2.x         | New cap in 3.2.4; off for single-node embedded       |
| cgroup `MemoryMax` / systemd `MemoryMax=`    | ≥ 2× largest LSM level   | Prevents skv#397 compaction OOM loop                |
| Backup cadence                               | `surreal export` daily; storage snapshot before risky ops (if Linux fs supports) | Mitigates #7426, #7291 |
| Liveness probe                               | RSS-based restart on sustained growth, not just liveness ping | Surfaces silent corruption before clients see it |

The 0.21.3 fix (compact-portion fsync + memtable rotation) cannot be
unlocked without either (a) patching surrealkv to 0.21.3 manually via
`[patch.crates-io]` in `Cargo.toml`, or (b) waiting for SurrealDB 3.3
GA.

---

## 8. Rollback plan

The cleanest rollback path is one we already control: **keep the
RocksDB data directory intact** while running on SurrealKV.

Trigger rollback when any of:

- Sustained RSS growth observed in metrics.
- `surreal-kv` manifest corruption on restart (`SSTable FileTooSmall`
  in logs — see #7426).
- Maintained COUNT index reports inflated values vs physical rows
  (#7090 / #7291).
- OOM-kill loop with no clients attached (#7477 signature).
- Maintenance window to apply a point-release suddenly introduces a
  regression affecting prior behaviour.

**Rollback steps:**

1. Stop the server.
2. Move `/data/surrealkv/` aside (do **not** delete until next
   successful export).
3. Restore `/data/rocksdb/` from the previous location / backup.
4. Revert Cargo feature flag to `features = ["kv-rocksdb", "kv-mem"]`
   (or simply build with `--no-default-features` and the old set).
5. Roll the deploy (jj + NixOS flow per `AGENTS.md`, or `jj git push
   --all` followed by `nixos-rebuild switch` on the host).
6. Restart; verify with `INFO FOR DB` and a critical-end-to-end
   smoke-test.
7. Post-mortem: file the upstream issue if reproducible; capture
   crash / `surreal export` diff for the next 3.3.0+ candidate.

**Time-box estimate for a rollback** (no release needed for the data
side): ≤ 15 minutes for the directory swap + service restart on a
single-node deployment.

---

## 9. Decision matrix

| Scenario                                              | Recommendation |
| ----------------------------------------------------- | -------------- |
| Achiyon stays single-node, on bare metal, host memory ≥ 32 GiB, can tolerate ≥ 24 OOM-kills/day via systemd auto-restart, dataset ≲ 5 GB | SurrealKV is on the table — but only after 3.3.0 GA ships 0.21.3 |
| Achiyon runs in Kubernetes with `MemoryMax` set, dataset ≥ 5 GB, downtime intolerable | **Stay on RocksDB on 3.2.x.** |
| Achiyon is dev / test / CI / ephemeral embedded       | SurrealKV is acceptable (`surrealkv::Tree` is small, fast to embed, nice for tests). |
| Achiyon is pre-production / staging                  | SurrealKV on a **separate** namespace/DB; do export/import drills; compare with RocksDB baseline weekly. |
| Achiyon is production with strict RPO/RTO             | RocksDB until SurrealKV ships GA-quality in a stable SurrealDB release **and** an export/import drill completes without `#7090 / #7426` signatures. |
| The user wants to add `kv-surrealkv` *alongside* `kv-rocksdb` (no engine swap today) | Acceptable: keeps an opt-in path; minimal compile overhead; enables A/B in a staging namespace. |

### Specific recommendation for *this* repository

Given:

- The workspace currently runs `kv-rocksdb + kv-mem` on 3.2.4.
- The pinned 3.2.4 ships SurrealKV 0.21.2, which is missing the
  fsync-after-compaction fix.
- Several open upstream issues of critical severity target the exact
  0.21.2 + 3.2.4 combination.
- Upstream explicitly recommends RocksDB for "conservative
  production on-disk server deployments today".

**The recommended action is: do not switch the production engine on
3.2.x. Plan to revisit on SurrealDB 3.3.x stable.**

A low-risk intermediate step: enable `kv-surrealkv` in the Cargo
features today (cheap — it sits beside `kv-rocksdb` without changing
the runtime engine), so that when 3.3.0+ ships and the upstream
issues are closed in a stable release, the only required change is
the runtime engine switch, not a feature-flag round-trip.

```toml
# no functional change today; prepares the runtime switch
surrealdb = { version = "3.2", features = ["kv-rocksdb", "kv-mem", "kv-surrealkv"] }
```

---

## 10. Open questions to confirm before any change

1. **Where does Achiyon run?** Bare metal, Kubernetes, systemd
   unit, NixOS service? (Determines whether the §4 OOM loop is
   survivable.)
2. **How large is the live dataset (rows, GB-on-disk) and the
   expected growth rate?** (Determines whether skv#397 compaction
   RAM is realistic to provide.)
3. **Is `surreal export` currently run daily? Weekly?** (Mitigates
   #7426 / #7291 silently-corrupting data paths.)
4. **Does any application code use `VERSION d=…` queries?** (Both
   backends support it today; but if it is load-bearing, the
   #7090 corruption risk applies.)
5. **What is the deploy / roll-back budget** for a forced engine
   revert? (≤ 15 min for a documented swap, more if upstream
   3.3.x requires a major-version upgrade at the same time.)

---

## 11. Sources (verified Sep 2026)

| Source                                                              | Used for                                                                                             |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `/Storage/Git/Workspaces/achiyon-20260828_142744_0a938b9e/Cargo.toml` & `Cargo.lock` | Pinned versions (`surrealdb` 3.2.4, `surrealdb-types` 3.2.4, `surrealdb-rocksdb` 0.24.0-surreal.5); resolution of `kv-mem → surrealmx`, not `surrealkv`. |
| `docs.rs/crate/surrealdb-core/3.2.4/source/Cargo.toml.orig`         | Authoritative feature map. Confirms `kv-mem → dep:surrealmx`, `kv-surrealkv → dep:surrealkv`.        |
| `github.com/surrealdb/surrealdb/blob/main/Cargo.toml`                | Workspace pin `surrealkv = "0.21.2"` (mainline, locked at the time of 3.2.x release).                |
| `crates.io/crates/surrealdb-core`                                   | Cross-check of feature → dep mapping.                                                                |
| `surrealdb.com/docs/manage/self-hosted/deployment-models`            | Upstream "SurrealKV (beta)" classification.                                                          |
| `surrealdb.com/docs/running/file-backed`                             | Engine descriptions, env-var names, "active development" warning.                                    |
| `surrealdb.com/blog/.../3-0-benchmarks`                              | Perf baseline for embedded SurrealKV vs 2.x; relevant to read-heavy workloads.                       |
| `surrealdb.com/blog/.../3-1-stability-diskann...`                    | "The operational maturity release" — note that SurrealKV maturity was *not* the 3.1 headline.         |
| `surrealdb.com/releases/3.2`                                         | 3.2.4 release notes; on-disk layout **unchanged** across 3.2.x; index build + write-key cap.          |
| `surrealdb.com/releases/3.3`                                         | 3.3 beta notes — confirms 0.21.3 upgrade path (fsync + memtable rotation) only in 3.3 beta.            |
| `github.com/surrealdb/surrealdb/issues/7477`                         | Reclaim-interval OOM-kill loop (critical).                                                          |
| `github.com/surrealdb/surrealdb/issues/7430`                         | RSS balloon / cgroup-ignored auto-sizing (critical).                                                |
| `github.com/surrealdb/surrealdb/issues/7426`                         | Crash → corrupt datastore manifest (critical).                                                       |
| `github.com/surrealdb/surrealkv/issues/397`                          | Compaction OOM loop; level-size ≈ RAM requirement (high).                                          |
| `github.com/surrealdb/surrealkv/pull/390` / release 0.21.3           | The fsync-after-compaction fix (critical, not yet in stable SurrealDB).                              |
| `github.com/surrealdb/surrealdb/blob/main/doc/RELEASING.md`         | Release-flow rationale; explains why changes lag upstream behind a private repo.                      |
| `github.com/surrealdb/surrealdb/issues/7219`                         | Export/import round-trip caveats (compound IDs, backslash escaping, multi-line INSERTs).             |
| `surrealdb.com/docs/manage/instances/import-and-export`              | Per-request 4 GiB import cap; partial-import behaviour; rollback advice.                            |
| `github.com/surrealdb/surrealkv/blob/main/docs/ARCHITECTURE.md`      | LSM / MVCC / VLog / `Eventual` vs `Immediate` durability semantics; recovery contract.                |
| `lib.rs/crates/surrealkv`                                           | API surface (`TreeBuilder`, `Mode`, `Durability`, `CompressionType`, `VLogChecksumLevel`).           |
| `github.com/surrealdb/surrealkv/blob/main/README.md`                | Platform compatibility table (Linux x86_64/aarch64 full; macOS full; WASM blocked; Windows partial). |

---

## 12. TL;DR for the parent agent

- **The "beta" label is correct and surfaced on the upstream docs.** The
  user is right that SurrealKV itself is feature-complete, but the
  integration in SurrealDB 3.2.x is not production-safe due to
  multiple open critical-severity issues against the exact pinned
  combination (fsync-after-compaction missing; OOM loops; manifest
  crash inconsistency; unbounded RSS in cgroup deployments).
- **Switching on 3.2.4 is not advisable.** Wait for SurrealDB 3.3.x
  stable, which upgrades to SurrealKV 0.21.3 with the durability
  fix.
- **The Cargo-level change is trivial:** add `"kv-surrealkv"` to the
  feature list and either keep it dormant (alongside RocksDB) or pass
  `Surreal::new::<SurrealKv>(...)`.
- **Migration is export/import only.** RocksDB ↔ SurrealKV data
  directories are not interoperable. See §6 for the canonical steps
  and the upstream-known gotchas.
- **Rollback is fast** (≤ 15 min directory swap + restart) provided
  the original RocksDB directory is preserved.
- **Recommended immediate action for Achiyon's pinned 3.2.4:**
  add `"kv-surrealkv"` to the Cargo features now (no runtime impact,
  small compile-time cost) so the runtime engine swap on
  3.3.0+ stable is one-line.

