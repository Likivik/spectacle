# SurrealKV vs RocksDB for Achiyon — research note

**Project studied:** `/Storage/Git/achiyon` (workspace `Cargo.toml` pins `surrealdb = { version = "3.2", features = ["kv-rocksdb", "kv-mem"] }`; full app code lives in `/Storage/Git/achiyon/server/src/state.rs`).
**Question:** can SurrealKV replace RocksDB as the embedded backend while keeping SurrealDB as the application database, and should we do it on 3.2?
**Verdict at top:** **Yes, it is technically possible on 3.2 — but the official recommendation on the 3.2 line is still "RocksDB for production on-disk; SurrealKV is beta". For this project, hold RocksDB on 3.2 and re-evaluate when SurrealDB graduates SurrealKV past beta, or when we publish a desktop app where the embedded footprint actually matters.**
**Confidence:** high on the facts (surrealDB crate metadata, source repo, version pins); medium on the operational risk assessment (would require a real benchmark on the workload to confirm the perf delta).

---

## 1. Pinned state (verified, high confidence)

Read directly from `/Storage/Git/achiyon/Cargo.lock`:

| Crate | Version | Role |
|---|---|---|
| `surrealdb` | **3.2.4** | umbrella SDK / facade |
| `surrealdb-core` | 3.2.4 | query engine |
| `surrealdb-rocksdb` | **0.24.0-surreal.5** | SurrealDB's fork of RocksDB, gated behind `kv-rocksdb` |
| `surrealdb-librocksdb-sys` | 0.18.3+11.0.0-4 | bundled C/C++ rocksdb shim (bundles `libz-sys`, `lz4-sys`, `zstd-sys`, `bzip2-sys`) |
| `surrealkv` | _not present_ | the third-party engine is NOT in the lock — `kv-surrealkv` is OFF |

Workspace `Cargo.toml:30`: `surrealdb = { version = "3.2", features = ["kv-rocksdb", "kv-mem"] }`. Spec `"3.2"` is interpreted as `^3.2` (so `>=3.2.0, <4.0.0`); Cargo will not pick up `3.3.0-beta.x` because pre-releases are only resolved when the resolver is told to opt in. Current latest stable = 3.2.4 (2026-08-03); first prerelease on 3.3 = 3.3.0-beta.2 (2026-08-18).

App usage lives in `/Storage/Git/achiyon/server/src/state.rs`:

```
let db = Surreal::new::<surrealdb::engine::local::RocksDb>(path.as_path()).await?;
```

Plus a `Mem`-backed helper at line 67 used only by integration tests.

## 2. Is `kv-surrealkv` available in 3.2? (verified)

Yes. From the official crates.io metadata for `surrealdb` 3.2.4
(<https://crates.io/crates/surrealdb/3.2.4>), the feature manifest includes:

```
kv-surrealkv -> dep:surrealdb-engine-local, surrealdb-engine-local/kv-surrealkv, dep:surrealdb-kvs, tokio/time
kv-rocksdb   -> dep:surrealdb-engine-local, surrealdb-engine-local/kv-rocksdb,   dep:surrealdb-kvs, tokio/time
kv-mem       -> dep:surrealdb-engine-local, surrealdb-engine-local/kv-mem,       dep:surrealdb-kvs, tokio/time
kv-tikv      -> dep:surrealdb-engine-local, surrealdb-engine-local/kv-tikv,      tokio/time
kv-indxdb    -> dep:surrealdb-engine-local, surrealdb-engine-local/kv-indxdb
```

And in the SurrealDB source repo, tag `v3.2.4/Cargo.toml` directly depends on `surrealkv = "0.21.2"` (curl of raw file at the tag, line 88).

The `SurrealKv` type itself is `#[cfg(feature = "kv-surrealkv")]` on `surrealdb::engine::local::SurrealKv` (docs.rs source for `mod.rs`). So enabling the feature is sufficient to import the engine.

## 3. Maturity: stable or experimental? (high confidence on quotes)

**Beta, not experimental.** Both words matter:

- **"Under active development"** — verbatim from
  <https://surrealdb.com/docs/running/file-backed>: _"SurrealKV is under active
  development. See [SurrealKV](https://github.com/surrealdb/surrealkv) release
  notes and [SurrealDB release notes](https://surrealdb.com/releases) before
  relying on it for critical production workloads."_
- **Labelled "beta"** — verbatim from
  <https://surrealdb.com/docs/manage/self-hosted/deployment-models>: _"SurrealKV
  (beta)"_ in the deployment matrix, _"SurrealKV remains beta. For conservative
  production on-disk server deployments today, prefer RocksDB. For embedded
  deployments where smaller resident memory and in-process behaviour are
  priorities, SurrealKV is the path to evaluate first."_
- **Not gated behind the experimental-capability flag** —
  `--allow-experimental / SURREAL_CAPS_ALLOW_EXPERIMENTAL` only enables
  `files` and `surrealism` in 3.2; `kv-surrealkv` is NOT in that list
  (<https://surrealdb.com/docs/reference/cli/surrealdb-cli/commands/start>).
  So it's a normal compile-time feature, not a runtime capability switch.
- The SDK doc `surreal-kv with versioning` example
  (<https://surrealdb.com/docs/reference/rust/methods/new>) treats `SurrealKv`
  as a first-class supported engine — no "_experimental_" prefix on the type
  or the docs section.

## 4. Dependency footprint

Adding `kv-surrealkv` and removing `kv-rocksdb` to the SurrealDB dependency in Achiyon would:

| Effect | Today (`kv-rocksdb`) | With `kv-surrealkv` |
|---|---|---|
| Native code compiled | `librocksdb` via `surrealdb-librocksdb-sys` (pulls `bindgen`, `cc`, `libc`, `libz-sys`, `lz4-sys`, `zstd-sys`, `bzip2-sys`) | none — `surrealkv` is pure Rust |
| `surrealdb-kvs` | already indirect via `kv-rocksdb` | also indirect via `kv-surrealkv` |
| Engine crate version | `surrealdb-rocksdb 0.24.0-surreal.5` (vendored fork) | `surrealkv 0.21.2` |
| Cross-compile pain | `bindgen` needs `clang`/`libclang`; `cc` needs a C toolchain. The Cargo `bindgen` feature is on by default for `surrealdb-librocksdb-sys`. | none |
| Binary size / cold compile time | bigger, much slower first build (snappy/native builds of C++ rocksdb) | smaller, faster cold build |

For a desktop app (Tauri) that has to build on developer laptops and CI, removing the rocksdb native build is a meaningful win — but only if the underlying binary doesn't break.

## 5. Does it replace RocksDB or layer on it?

It **replaces** RocksDB in the embedded-storage role: each is a KV backend that SurrealDB's `surrealdb-core` engine can be opened against. `Surreal::new::<RocksDb>(path)` and `Surreal::new::<SurrealKv>(path)` are two paths through the same engine façade. They do not coexist in a single database file. The on-disk formats are completely different (LSM vs SurrealKV's own LSM/WiscKey format), so data is not interchangeable at the file level.

## 6. Persistent embedded support: yes

Both engines are documented as embedded, file-backed, on the same `surrealdb::engine::local::*` module. `SurrealKv` is constructed with a directory path; `Surreal::new::<SurrealKv>(path)` returns a `Db`-typed client (the same `Db` alias Achiyon already uses at `server/src/state.rs:8`). Sync / durability behaviour is configurable via the same `SyncMode` enum (`Every`/`Interval`/etc.) regardless of backend; `kv-surrealkv` is a `cfg`-on-gate for `sync()` per docs.rs source.

## 7. Migration / backup compatibility

There is **no in-place binary migration** between RocksDB and SurrealKV on-disk stores — the page formats are different. Use the **logical export/import path** SurrealDB ships with both backends:

- `surreal export --ns <ns> --db <db> dump.surql` from the running RocksDB instance (the file is SurrealQL text, readable and diffable) — <https://surrealdb.com/docs/reference/cli/surrealdb-cli/commands/export>.
- Start a fresh instance against `surrealkv://...` (or change the Cargo feature + data path), then `surreal import --ns <ns> --db <db> dump.surql` — <https://surrealdb.com/docs/manage/instances/import-and-export>.
- Important caveat from the same export doc: `surreal import` commits each statement; a partial-failure import leaves partial data. The 3.x build emits an `OPTION IMPORT` header that disables events/live-queries/field-processing during import for perf and safety.
- Achiyon-specific: live queries, `DEFINE EVENT`, `DEFINE TABLE`/`PERMISSIONS`, and possibly the 2FA secret table — these should roundtrip through `surreal export` because the import contract reads the same SurrealQL the export writes. Audit logs and `DEFINE ANALYZER` (analyzers vector) are also exportable (the CLI has `--analyzers`/`--only` flags).

For the user's environment, the cheaper fallback is: drop the existing data directory and recreate — Achiyon's `data/` tree is local-first and not yet carrying cross-version migrations.

## 8. Recommendation for this project

**Short answer: keep RocksDB on SurrealDB 3.2.x; do not swap on 3.2.**

Reasoning, in order:

1. **Official guidance on the pinned line is explicit.** 3.2 docs say SurrealKV is "beta" and recommend RocksDB for "conservative production on-disk server deployments today". Achiyon is on-disk server-style (auth API, chats, sessions). SurrealKV is recommended for "embedded and local-first … where smaller resident memory and in-process behaviour are priorities" — a future Tauri desktop app is exactly that use case, **but we are not there yet** on 3.2.
2. **Risk asymmetry.** RocksDB on 3.2 is the most-tested, best-documented combination. A swap to SurrealKV on 3.2 trades known-good for less-trodden; if the 2FA secret table or session store misbehaves on shutdown, we own the incident. Backup discipline (`surreal export`) makes this recoverable, but the value is low for the product today.
3. **The compile-time win is real but small right now.** RocksDB native build is slow, but Achiyon's CI/Nix build caches it; the user-cost is mostly "first time on a clean machine" and "rebinding on toolchain bumps". Removing it now saves a few minutes per developer laptop, costs runtime risk. Re-evaluate when:
   - the desktop build (`src-tauri/`) becomes a shipped artifact (then embedded footprint matters), or
   - SurrealDB ships a stable release where SurrealKV is no longer labelled "beta" in the deployment-models doc — the natural next minor after the 3.3 beta cycle.
4. **Migration cost is low but not zero.** A swap still costs one offline migration: `surreal export`, change `Cargo.toml` features + `state.rs` engine type, fresh data dir, `surreal import`. Trivial but not free — and it must happen at a point where we have proper export/import plumbing in our deploy story (which we should build independent of this swap, since the `surreal export` step works for backups regardless of engine).
5. **The repo code change is genuinely tiny** if/when we do swap: one feature flag in `Cargo.toml`, one generic argument swap in `state.rs:56`, plus the import. That makes the swap cheap to defer and cheap to do later.

**Concrete next steps (if the user still wants to swap now):**

1. In `Cargo.toml:30`, change features to `["kv-surrealkv", "kv-mem"]` (keep `kv-mem` — the test helper uses it).
2. In `server/src/state.rs:56`, swap `RocksDb` for `SurrealKv` (same constructor signature, same `&Path` argument).
3. Run `cargo update` so the lockfile picks up `surrealkv` 0.21.2 transitively and drops `surrealdb-rocksdb` / `surrealdb-librocksdb-sys`.
4. Stop the server, take a `surreal export --ns achiyon --db world pre-swap.surql`, point the data dir at a fresh path, start the server, run `surreal import --ns achiyon --db world pre-swap.surql`.
5. Add a `BACKUPS.md` note in `docs/` covering the export/import procedure regardless of which engine is in use — this is a permanent operational win, not just a migration hack.
6. Roll back is symmetrical: re-enable `kv-rocksdb`, restore the old data directory from before the migration.

**Concrete next steps (recommended path — keep RocksDB, do the prep work instead):**

1. Add `surreal export` to the systemd service stop hook (or a daily cron) — see `<data dir>/achiyon/world.db` for the source; archive to `<data dir>/backups/achiyon-<date>.surql`.
2. Re-evaluate the engine swap as part of the desktop-build work in `src-tauri/`, when SurrealKV is no longer marked "beta" in `docs/manage/self-hosted/deployment-models`.
3. Document the swap path (above) in `development-docs/` so we don't re-research from scratch.

## 9. Sources

- `/Storage/Git/achiyon/Cargo.toml` — Achiyon workspace, line 30 sets the pin.
- `/Storage/Git/achiyon/Cargo.lock` — lines 4143–4335 confirm `surrealdb 3.2.4`, `surrealdb-rocksdb 0.24.0-surreal.5`, `surrealdb-librocksdb-sys 0.18.3+11.0.0-4`; no `surrealkv` entry because the feature is off.
- `/Storage/Git/achiyon/server/src/state.rs` — actual usage (`RocksDb` + `Mem`).
- <https://crates.io/crates/surrealdb/3.2.4> — authoritative feature manifest including `kv-surrealkv`.
- <https://surrealdb.com/docs/running/file-backed> — official SurrealKV status ("under active development"), feature list, durability knobs.
- <https://surrealdb.com/docs/manage/self-hosted/deployment-models> — official "SurrealKV (beta)" classification and the explicit "prefer RocksDB on disk" recommendation.
- <https://docs.rs/surrealdb/latest/src/surrealdb/engine/local/mod.rs.html> — source confirms `#[cfg(feature = "kv-surrealkv")] pub struct SurrealKv;`.
- <https://surrealdb.com/docs/reference/rust/methods/new> — `Surreal::new::<SurrealKv>(...)` SDK example.
- <https://docs.rs/surrealdb/latest/surrealdb/struct.Connect.html> — `versioned()`, `sync()`, `retention()`, `snapshot()` are all gated on `kv-mem | kv-rocksdb | kv-surrealkv` features, confirming feature parity.
- <https://crates.io/crates/surrealkv> — third-party engine crate, latest 0.21.3 (2026-08-04); historical versions confirm SurrealKV is at 0.21 line in 3.2.4 (Cargo.toml pins `0.21.2`).
- <https://crates.io/crates/surrealdb-kvs-surrealkv> — internal SurrealDB shim crate, currently only published under `3.3.0-beta.*`; not yet present on the 3.2 stable line (low-impact for Achiyon since this crate is internal).
- <https://surrealdb.com/docs/reference/cli/surrealdb-cli/commands/start> — `--allow-experimental` only enables `files` and `surrealism`, not SurrealKV.
- <https://surrealdb.com/docs/manage/instances/import-and-export> and <https://surrealdb.com/docs/reference/cli/surrealdb-cli/commands/export> — export/import flow and 4 GiB per-import limit; partial-import commit semantics.

## 10. Confidence levels

| Finding | Confidence |
|---|---|
| `kv-surrealkv` feature exists on `surrealdb` 3.2.4 | **High** (crates.io metadata + source tag match) |
| SurrealKV is `0.21.2` in the 3.2.4 repo | **High** (raw `Cargo.toml` line 88 on tag `v3.2.4`) |
| SurrealKV is "beta" / "under active development" on the 3.2 docs line | **High** (verbatim quotes, two separate doc pages) |
| Migration = `surreal export` + swap feature + `surreal import`; no binary migration | **High** (official import/export docs, both engines are documented to support export) |
| SurrealKV fully replaces RocksDB at the engine layer (no co-existence in one DB file) | **High** (different file formats per docs.rs source) |
| Compiled footprint / build-time win is real for SurrealKV | **Medium** (based on the dep graph; not measured on this hardware) |
| Performance parity on Achiyon's workload between RocksDB and SurrealKV on 3.2 | **Low** — no benchmark. SurrealKV is LSM, so similar shape, but the docs page explicitly cautions about "production on-disk" workloads, implying SurrealKV's perf position vs RocksDB isn't a known win for chat/data workloads yet. |
