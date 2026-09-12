# Forgejo Actions cache for Rust (NixOS + `nix develop`) — PLAN

> **Status:** PLAN ONLY. Research complete (3 parallel deep-dives, cited below). Nothing executed.
> **Decision (2026-09-14):** **Layer 2 alone** (persistent on-host cargo dirs). Layers 1 & 3 deferred.
> **Scope:** cache strategy for Rust projects built on the self-hosted Forgejo runner on `serenity` (the `forgejo` aspect), jobs run in host-networked Podman containers via `nix develop`.

**Goal:** Persistentially cache Rust build output (cargo registry, `target/`, and optionally compiler hits via sccache) so CI jobs on the singleton runner don't re-download/recompile from cold.

**Why this is non-trivial:** jobs run in a **fresh container per job** (`nix:docker://forgejo-runner-nix`, container.network=host, `--user nixuser` with `HOME=/tmp`). The repo checkout, `$HOME`, and `target/` are all ephemeral — cargo's default state (`~/.cargo`, `<repo>/target`) dies with the container. **The `/nix` store IS persistent** (bind-mounted, host daemon), so the toolchain (rustc/cargo from `nix develop`) is already reused across jobs; only cargo's user-level cache and the target dir are lost.

---

## Verified facts about the CURRENT setup (read from `forgejo.nix`)

- Forgejo Actions **enabled**; singleton runner, `capacity=1`, label `nix:docker://forgejo-runner-nix`.
- **Built-in actions-cache server already configured and correct:**
  `settings.cache = { enabled = true; dir = "/Storage/forgejo/actcache"; }` (lines 176-179). This is a Forgejo-native cache server/proxy that speaks the GitHub `actions/cache` REST protocol; the runner injects `ACTIONS_CACHE_URL` into each job automatically. **Do not set it in workflow env.**
- `container.network = "host"` → job containers share the host loopback → no Pasta/bridge connectivity issue for the cache proxy. Current config is already the recommended Forgejo self-hosted pattern.
- `storeDeps` already bundles `tar` + `zstd` + `git` into `/bin` — exactly what `actions/cache` needs to pack/unpack archives. Nothing to add.
- Container mounts today: `-v /nix:/nix -v ${storeDeps}/bin:/bin -v ${storeDeps}/etc/ssl:/etc/ssl` (line 170). **No writable persistent cargo/target volume.**
- `[cache]` **does not exist** in Forgejo `app.ini` — cache is configured solely in the runner YAML. No server-side edit needed.
- **Known hazard:** the built-in `actcache` has **no TTL/eviction** — `actions/cache` entries created by the runner have no default expiration, so `/Storage/forgejo/actcache` grows monotonically (Codeberg incident #436). Needs monitoring/cleanup regardless of strategy.
- `nixuser` uid is NixOS-auto-assigned (not pinned). For writable bind-mount owned by the container's job user, the host dir must be owned by the host `nixuser` uid — read with `id nixuser` on serenity at deploy time.

---

## Recommended approach (3 independent, additive layers)

They **compose, do not duplicate**: registry+target via actions/cache, compiler hits via sccache, nix-store via cachix (only if building nix-side deps).

### Layer 1 — `actions/cache` on cargo registry + target (zero NixOS change, works today)

No infra change. Uses the already-configured `actcache`. Add to the repo workflow (e.g. `likivik/achiyon` `.forgejo/workflows/ci.yml`).

- **Two caches, keyed differently.**
  - registry/git: `path: ~/.cargo/registry/{index,cache}` + `~/.cargo/git/db` — key `cargo-registry-${{ hashFiles('**/Cargo.lock') }}`.
  - target: `path: target/` — key `cargo-target-${{ hashFiles('**/Cargo.lock') }}` (add toolchain/matrix vars if/when matrixed).
- **Apply `CARGO_INCREMENTAL=0`** (cargo auto-disables it under `CI=1`; be explicit).
- **Use the Forgejo mirror of the official action** (no 3rd-party fork needed — `hostphp/actions-cache` etc. unmaintained):
  ```yaml
  - uses: https://code.forgejo.org/actions/cache@v4
  ```
  or the de-facto shortcut `https://code.forgejo.org/swatinem/rust-cache@v2` which wires registry+target+incremental-off with the correct keys automatically.
- Order: `checkout` → (toolchain) → `rust-cache` → build.
- In a Nix container the toolchain comes from `/nix`, so `~/.rustup` caching is pointless; rust-cache's `cache-targets`/`cache-on-failure` can be left default.

**Cost reminder:** every hit costs a tar **upload+download round-trip** through `actcache`. On a singleton this is fine but not free.

### Layer 2 — persistent on-host shared dirs (best long-term for a singleton; small NixOS change)

Because the runner is a singleton with a big ZFS pool and host-networked containers, bind-mounting a **persistent writable cargo dir** gives zero-network, forever-persistent cache. Change `forgejo.nix`:

```nix
# container.options: add writable persistent cargo volumes
options = '' ... --user nixuser -v /nix:/nix -v ${storeDeps}/bin:/bin
  -v ${storeDeps}/etc/ssl:/etc/ssl
  -v /Storage/forgejo/rust-cache:/opt/cargo -v /Storage/forgejo/rust-target:/opt/target'';
# settings.container.valid_volumes must list the two new host paths.
```

- Create + own the dirs in the existing `forgejo-dirs` activation script:
  `install -d -o <nixuser-uid> -g users -m 0770 /Storage/forgejo/rust-cache /Storage/forgejo/rust-target` (owner = host `nixuser` uid so the container job can write; check `id nixuser` on serenity first).
- Workflow sets `CARGO_HOME=/opt/cargo CARGO_TARGET_DIR=/opt/target` on the build step.
- **No tar round-trip; survives runner restarts for free.** This is the recommended primary strategy for this fleet.

### Layer 3 — shared sccache daemon (compile-level hits across branches)

Best when builds hit the same crates across many runs/`Cargo.lock` variants (content-addressed by rustc invocation, not by lockfile). Runs as a host systemd service, exposed to job containers.

- **NixOS unit** (in `forgejo.nix`):
  - `users.users.sccache { isSystemUser; home = "/var/lib/sccache"; }` + tmpfiles for `/var/lib/sccache` and `/run/sccache`.
  - systemd service **`ExecStart = sccache --start-server`** (NOT a `.socket` unit — sccache socket-activation is unimplemented upstream, mozilla/sccache#2294), `SCCACHE_DIR=/var/lib/sccache`, `SCCACHE_SERVER_UDS=/run/sccache/sccache.sock`, `SCCACHE_CACHE_SIZE=100G`, `SCCACHE_IDLE_TIMEOUT=0`.
  - Expose to containers: bind-mount `/run/sccache:/run/sccache` in `container.options` + add to `valid_volumes`; chmod socket 0666 **or** match uid to the job user.
- Workflow: `RUSTC_WRAPPER=sccache SCCACHE_SERVER_UDS=/run/sccache/sccache.sock` on the `nix develop -c cargo …` step.
- **nix-develop gotchas (critical):**
  - Set `RUSTC_WRAPPER` in the devShell (`mkShell { RUSTC_WRAPPER = "${pkgs.sccache}/bin/sccache"; }`) — **never** a committed `.cargo/config.toml` `rustc-wrapper = "sccache"`, which breaks downstream `nix build` (naersk/cargo2nix vendor `.cargo` into the sandbox where sccache isn't on PATH).
  - sccache wraps the nix-store rustc; fine inside `nix develop`. If the devShell also sets `RUSTC_WORKSPACE_WRAPPER`, sccache still handles nesting, but verify with `SCCACHE_LOG=debug cargo build`.
  - Add `SCCACHE_BASEDIRS` pointing at the checkout root for stable hashes (insurance on a fixed singleton root).

### Layer 4 — (only if building Nix-side deps) cachix

Only relevant if jobs `nix build` non-trivial derivations (`buildRustCrate` etc.) per job. `cachix/cachix-action@v14` after `cachix/install-nix-action@v31`. **Out of scope unless the Rust repo builds nix derivations in CI.**

---

## Recommended adoption (DECIDED: Layer 2 alone)

1. **Layer 2** — this is the whole job now. NixOS change in `forgejo.nix` (writable volumes + valid_volumes + activation dirs + default env), then confirm `nix develop -c cargo` writes to `/opt/cargo`/`/opt/target`.
2. **Cache hygiene regardless:** add monitoring/cleanup for `/Storage/forgejo/actcache` (no TTL) — kept because the runner still uses it for its own artifact proxy; plus the two new cache dirs can grow, so a ZFS quota is cheap insurance.
3. Layers 1 & 3 — dropped for now.

## Layer 2 — exact changes to `modules/aspects/server/forgejo/forgejo.nix`

**1. Add default job env + writable volumes** (`container.options`, line 170; keep the `--user nixuser`):
```nix
options = ''-e NIX_BUILD_SHELL=/bin/bash -e PAGER=cat -e PATH=/bin
  -e SSL_CERT_FILE=/etc/ssl/certs/ca-bundle.crt
  -e CARGO_HOME=/opt/cargo -e CARGO_TARGET_DIR=/opt/target
  --user nixuser
  -v /nix:/nix -v ${storeDeps}/bin:/bin -v ${storeDeps}/etc/ssl:/etc/ssl
  -v /Storage/forgejo/rust-cache:/opt/cargo -v /Storage/forgejo/rust-target:/opt/target'';
```

**2. Allowlist the new host paths** (`valid_volumes`, line 171):
```nix
valid_volumes = [ "/nix" "${storeDeps}/bin" "${storeDeps}/etc/ssl"
  "/Storage/forgejo/rust-cache" "/Storage/forgejo/rust-target" ];
```

**3. Create + own the dirs** in the existing `forgejo-dirs` activation script (after line 216):
```nix
install -d -o nixuser -g nixuser -m 0770 /Storage/forgejo/rust-cache /Storage/forgejo/rust-target
```
Why `nixuser:nixuser`: the image's nixuser gets the **same uid+gid** as the host's `nixuser` (image is built from host `getent`, lines 117-121), and bind mounts preserve host ownership — so the in-container job user (owner nixuser, group nixuser, 0770) can write the mounted dirs. No `users` group needed (not in the image).

**No reproducibility in the workflow needed** for a single repo (capacity=1 → one job at a time, no clobber). If multiple Rust repos later share the runner, namespace `CARGO_TARGET_DIR` per repo (e.g. `/opt/target/<repo>`) in that repo's workflow.

## Layer 2 — validation

- `tests/forgejo-boot.nix` stays green (aspect guard).
- Smoke: `id nixuser` on serenity → confirm uid/gid; push a workflow doing `nix develop -c cargo build` twice; assert `/opt/cargo` + `/opt/target` are populated on the host after run 1 and that run 2 skips the dep builds.
- `du -sh /Storage/forgejo/rust-cache /Storage/forgejo/rust-target` bounded / quota'd.

---

## Unresolved / deferred (not blocking Layer 2)

- **`actcache` no TTL** → still grows (runner uses it for artifact proxy). ZFS quota on `/Storage/forgejo/actcache` is cheap insurance; do it now or note it.
- **Bound cargo caches:** `/opt/cargo` (registry) + `/opt/target` can grow with dep churn; ZFS quota optional.
- Multiple Rust repos on the runner later → namespace `CARGO_TARGET_DIR` per repo.
- Layers 1 & 3 deferred (user decision 2026-09-14).
