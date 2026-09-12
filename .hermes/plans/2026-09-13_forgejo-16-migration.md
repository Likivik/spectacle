# Forgejo 15.0.7 (LTS) → 16.0.3 Migration Plan

> **Goal:** Upgrade the Serenity Forgejo from `forgejo-lts` 15.0.7 to the non-LTS
> `pkgs.forgejo` 16.0.3 to unlock the Actions job-log / run-jobs API endpoints
> (`GET …/actions/runs/{run}/jobs`, `GET …/actions/jobs/{id}/logs`) that this
> build lacks — our only remaining dev friction point.

## Current context (verified)
- Running: `forgejo-lts` **15.0.7** (`/api/v1/version` → 15.0.7, confirmed live).
- Target: `pkgs.forgejo` in the pinned nixpkgs (dc5d91f) = **16.0.3**
  (`nix eval --raw nixpkgs#forgejo.version` → 16.0.3).
- **Cache check (asked):** our flake's `forgejo-16.0.3` (`lwg7i7zg…`) **IS in `cache.nixos.org`** — verified two ways:
  `nix path-info --store https://cache.nixos.org/ /nix/store/lwg7i7zg…-forgejo-16.0.3` → valid,
  and narinfo `…/lwg7i7zg0ih9id792nb9q7h61hxd039b.narinfo` → HTTP 200.
  (Note: narinfo URL is `/<<storehash>>.narinfo` — hash only, NO `-forgejo-16.0.3`
  suffix. The earlier "404 → source-build" conclusion was a wrong-URL artifact;
  forgejo 16.0.3 and 16.0.4 are all binary-cached.) → **no source build; bump is a
  normal cache-fetched deploy.**
- Deployment: `services.forgejo.package = pkgs.forgejo;` is the one-line flip in
  the aspect.
- Runner: `forgejo-runner 13.1.0` is protocol-compatible with Forgejo 16
  (Actions container runner already proven green on 15 via the storeDeps "nix"
  label).

## v16 breaking changes — impact on OUR config
Our `app.ini` (settings block in the aspect) sets only: DOMAIN, ROOT_URL,
HTTP_ADDR 127.0.0.1, HTTP_PORT 3000, SSH_PORT 22, DISABLE_SSH=false,
DISABLE_REGISTRATION=true, actions.ENABLED=true. No LFS_JWT, no webhook
host-list, no reverse-proxy-auth.

| Change | Impact here | Action |
|---|---|---|
| DB **irreversible migrations** on first 16 start | Real | Backup + verify restorable BEFORE switch (rollback = restore only) |
| `REVERSE_PROXY_TRUSTED_PROXIES` `*` default removed | Low — we don't use `ENABLE_REVERSE_PROXY_AUTHENTICATION` (Forgejo's own login; tailscale serve just TLS-terminates to 127.0.0.1) | Add `[security]REVERSE_PROXY_TRUSTED_PROXIES = 127.0.0.1,::1` anyway (safe + correct) |
| Git hooks centralized (removes per-repo hooks) | Backwards-compatible; we only have default sample hooks | No forced action; optional cleanup after |
| JWT signing secrets unified | None — we don't override LFS_JWT/defaults | None |
| Webhook `ALLOWED_HOST_LIST` default = `external` | Only if we add tailnet-webhook destinations (e.g. achiyon → poweredge) | Add `[webhook]ALLOWED_HOST_LIST = external, *.oryx-galaxy.ts.net` IF we want tailnet webhooks |

## Assumptions
- sereni stays the only forgejo host; single SQLite instance; downtime is fine
  (seconds-to-a-minute restart + migration window).
- We keep `forgejo-lts` semantics otherwise — this is just the LTS→rolling
  package swap; the module options we use are unchanged in 16.

## Step-by-step
### Task 1: Pre-upgrade backup (mandatory, ~5 min)
On serenity:
- ZFS atomic snapshot of the forgejo dataset (covers `/Storage/forgejo/{repositories,lfs}`):
  `sudo zfs snapshot <datasets>/forgejo@pre-v16-$(date +%Y%m%d%H%M%S)` (match the
  actual dataset path for the `/Storage/forgejo` mount).
- SQLite online backup of the DB:
  `sqlite3 /var/lib/forgejo/data/forgejo.db ".backup /var/backup/forgejo/forgejo.db.pre-v16"`
- Copy both off-host to Erebus (e.g. `/Storage/Git/...` or a backup dir) so a
  serenity failure can't destroy the only copy.
- **Verify restorability:** `sqlite3 <backup> "PRAGMA integrity_check;"` → `ok`,
  and `zfs list -t snapshot` shows the new snapshot. Do NOT proceed until both
  verify.

### Task 2: Add the 16-safe config knobs (aspect, ~5 min)
In `modules/aspects/server/forgejo/forgejo.nix` `services.forgejo.settings`:
```nix
security.REVERSE_PROXY_TRUSTED_PROXIES = "127.0.0.1,::1";
# only if we want tailnet webhook destinations:
webhook.ALLOWED_HOST_LIST = "external, *.oryx-galaxy.ts.net";
```

### Task 3: Swap the package + dry-build (blocking on the source build)
- Add `package = pkgs.forgejo;` to `services.forgejo` in the aspect.
- `nix build .#nixosConfigurations.serenity.config.system.build.toplevel --dry-run`
  → must evaluate clean (this only checks eval; it does NOT trigger the Go build).
- ⏱ **Time-box:** first real deploy/build of `forgejo-16.0.3` from source is
  **30–60 min** on serenity's CPU (not cached — see Context). State this to the
  user before the deploy.

### Task 4: Deploy + migrate + verify (10–20 min after build)
- `jj describe -m "forgejo: 15.0.7 → 16.0.3 (package swap) + reverse-proxy/webhook safety"`
  then `nixos-rebuild switch --flake .#serenity --build-host … --target-host … --elevate=sudo`
  **without** a tail pipe so SWITCH_EXIT is real (the unit-restart exit-4 wart is
  expected/benign — config still applies; verify by generation).
- First start runs the v16 DB migrations; watch `journalctl -u forgejo` for
  `migrate` / v16b_* / errors; the service starts after migrations finish.
- Verify:
  - `curl -s http://127.0.0.1:3000/api/v1/version` → **`"16.0.3"`**
  - HTTP 200 on local + tailnet HTTPS (`serenity.oryx-galaxy.ts.net`).
  - **The win:** `GET …/api/v1/repos/likivik/forgejo-test/actions/runs/{run}/jobs`
    and `GET …/api/v1/repos/likivik/forgejo-test/actions/jobs/{id}/logs` now
    return 200 (not 404) — prove with a fresh `forgejo-test` push.
  - Runner re-registers (label `nix`), a container job succeeds.
  - Run the `forgejo-boot` NixOS VM check still green:
    `nix build .#checks.x86_64-linux.forgejo-boot --no-link`.

### Task 5: Post-upgrade housekeeping (optional, later)
- Per the v16 upgrade guide, clean up the now-unused per-repo default git
  `hooks/` dirs on existing repos if desired (backwards-compatible; optional).

## Files likely to change
- Modify: `modules/aspects/server/forgejo/forgejo.nix` (package + 2 config knobs)
- No test changes expected; `tests/forgejo-boot.nix` must stay green on 16.

## Rollback
- **`v16` DB migrations are irreversible — there is no "flip the package back".**
  The only rollback is restoring the Task-1 snapshot + sqlite backup, then
  redeploying `forgejo-lts`. This is why Task 1 verification is non-negotiable.

## Risks / tradeoffs
- **LTS → rolling**: we now track Forgejo's faster cadence; acceptable for a private
  single-user forge, and we already run the rolling nixpkgs pin.
- The forgejo-16 binary is **cache-fetched** (verified), so no first-build time
  spike; remaining risk is only the irreversible DB migration (→ backup mandate).

## Open questions for the user
1. Keep `forgejo-lts` for a conservative path and skip to 16 later, or proceed
   with 16.0.3 now?
2. Do we want tailnet webhook destinations today (determines whether the
   `[webhook]ALLOWED_HOST_LIST` knob is added now)?
