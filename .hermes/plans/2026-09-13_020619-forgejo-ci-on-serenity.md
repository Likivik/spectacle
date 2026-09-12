# Forgejo CI (Actions) on Serenity — PLAN

> **Status:** PLAN ONLY. Nothing executed.
> Decisions resolved 2026-09-13: **A1 sops** · **C = runner lives inside the
> existing `forgejo` aspect** · CI caches contained under `/Storage/forgejo/`.
> **B** (achiyon's clippy/fmt gate) is the **user's** call — not touched by this plan.

**Goal:** Forgejo Actions CI for the private `likivik/achiyon` repo, running its
two `runs-on: nix` jobs on a self-hosted runner on serenity. Jobs run bare
`nix develop -c cargo …` → runner executes **on the host**, not in a container.

## Verified facts (read from our pin / hosts)

- Actions enabled by default in Forgejo 15.x; we pin `[actions] ENABLED=true` for clarity.
- Runner NixOS module in our pin: `…/continuous-integration/gitea-actions-runner.nix`
  - Option attr **`services.gitea-actions-runner`** (handoff said `services.forgejo-actions-runner` — wrong).
  - `package` default `gitea-actions-runner` → override to **`pkgs.forgejo-runner`**.
  - Host label matched via `hasSuffix ":host"`, example `native:host` → **`nix:host`**, NOT `nix:host://-` (handoff wrong).
- achiyon workflow `.forgejo/workflows/ci.yml`: two jobs `runs-on: nix`; gates `fmt`, `clippy -- -D warnings`, `test`, `install`.
- Serenity: podman+`podman.socket` active (unused for host exec), **no sops** (→ A1 adds it), no runner yet.
- `pkgs.forgejo-runner` available in our pin.

## Decisions (resolved)

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Executor | **host** (`nix:host`) | `nix develop` needs system nix; container would have to carry it. Host = no isolation → only trusted repos (achiyon private + single user, within Forgejo guidance). |
| 2 | Runner host | **serenity** | achiyon lives on serenity; sccache/store sharing. |
| 3 | Concurrency | 1 job at a time (module default) | nix store + sccache sharing. |
| 4 | Token | **A1 = sops** | fleet-idiomatic; serenity gains the sops aspect. |
| 5 | Placement | **inside the `forgejo` aspect** (`services.gitea-actions-runner` added to `forgejo.nix`) | forgejo already has its own aspect; runner is forgejo-scoped. |
- **B**: achiyon's strict `clippy -D warnings` / `fmt` gates — **user manages** the repo gate; this plan just wires CI. First run may be red by design of that repo, not this config.

## Storage (contained under `/Storage/forgejo/`)

| Path | Owner | What |
|---|---|---|
| `/var/lib/gitea-runner/serenity` | gitea-runner (SSD) | runner registration/control state (module default) |
| `/Storage/forgejo/runner/` | gitea-runner (ZFS) | `work/` (act_runner job dir), `sccache/` (`SCCACHE_DIR`), `cargo/` (`CARGO_HOME`, incl. `target`, can be 10s of GB) |
| `/Storage/forgejo/repositories` + `lfs/` | forgejo (ZFS) | already live |
| `/Storage/forgejo/dumps/` | forgejo (ZFS) | backup dumps |

- **small/stateful → SSD root; heavy mutable caches → ZFS pool** (parallel to forgejo's DB-on-SSD / repos-on-ZFS split).
- **Ownership change:** `/Storage/forgejo` goes `0750 forgejo:forgejo` → **`0770 forgejo:users`** so `gitea-runner` (joined to `users`) can traverse the shared root to reach `runner/`; each subdir stays owned by its own user. `gitea-runner` also joins `users` (same traversal fix as forgejo).
- Dirs created idempotently by the **existing `forgejo-dirs` activation script** (extend it — no separate activation needed).

## Change 1 — Actions on server (forgejo aspect)
`settings` add:
```nix
actions.ENABLED = true;
```
Not setting `DEFAULT_ACTIONS_URL` — achiyon's workflow is `run:`-only (no remote `uses:`).

## Change 2 — runner (inside forgejo aspect)
```nix
services.gitea-actions-runner = {
  package = pkgs.forgejo-runner;
  instances.serenity = {
    enable = true;
    name = "serenity";
    url = "https://serenity.oryx-galaxy.ts.net";
    tokenFile = config.sops.templates."forgejo/runner/token".path;  # A1
    labels = [ "nix:host" ];
    settings.container.valid_volumes = [];   # closed
  };
};
```
Module gotchas:
- `DynamicUser=true`, `User=gitea-runner`, `StateDirectory`.
- Host exec needs writable `$HOME` for sccache/cargo → override:
  `systemd.services.gitea-runner-serenity.serviceConfig.WorkingDirectory` /
  `Environment = { HOME = "/Storage/forgejo/runner"; SCCACHE_DIR = "/Storage/forgejo/runner/sccache"; CARGO_HOME = "/Storage/forgejo/runner/cargo"; }`
- Host label → no podman dependency (less surface; serenity has podman anyway).
- Join `gitea-runner` to `users` group.

## Change 3 — sops + token (A1)
- Add `den.aspects.server.sops` to serenity includes + an **age key for serenity** (ssh-to-age from its host key, following repo sops convention).
- Generate reg token: Site Admin → Actions → Runners → *Create new runner* (or `GET /api/v1/admin/actions/runners/registration-token`).
- Store via sops template `TOKEN=…` → `sops.templates."forgejo/runner/token"` → `tokenFile`.
- Module assertion: `token` XOR `tokenFile`.

## Change 4 — host prerequisites
- nix flakes for runner user: repo-standard `nix.settings.experimental-features` already set; confirm `nix config show` as gitea-runner after deploy.
- **cuda substituter**: bogus `cuda-maintainers.cachix.org` already removed from repo earlier; serenity's **live** `/etc/nix/nix.custom.conf` still 401s until this deploy — verify gone or achiyon's `nix develop` fails.

## Change 5 — test & first run
1. Deploy (15-30 min).
2. Runner green + label `nix` in Admin → Runners.
3. Run: push to achiyon `main` or workflow dispatch. Watch Actions logs; `journalctl -u gitea-runner-serenity`.
4. First achiyon run may be **red** (its own strict gate) — that's the user's repo call (B), not blockable here.

## Success criteria
- Runner green, label `nix`; one achiyon CI run reaches `test`/`install`.
- No `cuda-maintainers.cachix.org` 401s on serenity.
- sccache/cargo land under `/Storage/forgejo/runner/`; forgejo + runner both traverse `/Storage/forgejo`.
- forgejo-boot VM test still green (ownership change didn't break the aspect).

## Files touched (planned)
- `modules/aspects/server/forgejo/forgejo.nix` — `actions.ENABLED`, `services.gitea-actions-runner`, activation-script extension (`0770` root + `runner` subdirs), gitea-runner users-group.
- `modules/aspects/server/sops/sops.nix` — included (A1), if not already on serenity.
- `modules/hosts/serenity/serenity.nix` — include `sops` aspect (+ age-key wiring).
- `secrets/serenity/…` — sops secret+template for the runner token.

## Blocking inputs from user (before build)
1. Runner registration token (generate via Admin UI, paste to me to encrypt into sops).
2. Confirm serenity sops age key routing (fleet uses ssh host-ed25519 → age; same for serenity).
