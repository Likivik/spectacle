# Forgejo CI (Actions) on Serenity — PLAN

> **Status:** PLAN ONLY. Nothing executed.
> Decisions to confirm at the bottom. Corrects the achiyon-session handoff where
> it disagrees with the actual pinned nixpkgs module.

**Goal:** Forgejo Actions CI for the private `likivik/achiyon` repo, running its
two `runs-on: nix` jobs on a self-hosted runner on serenity. The jobs run bare
`nix develop -c cargo …` — so the runner must execute **on the host**, not in a
container.

## Verified facts (read from our pin / hosts)

- Actions is enabled by default in Forgejo 15.x; we pin `[actions] ENABLED=true` for clarity.
- Runner NixOS module exists in our pin:
  `/nix/store/byjzdjpvrh...-source/nixos/modules/services/continuous-integration/gitea-actions-runner.nix`
  - Option attr is **`services.gitea-actions-runner`** ← the handoff said `services.forgejo-actions-runner` (wrong).
  - `package` default is `gitea-actions-runner`; override to **`pkgs.forgejo-runner`** for Forgejo compat.
  - Host-executor label is matched via `hasSuffix ":host"`, example `"native:host"` → correct label is **`nix:host`**, NOT `nix:host://-` (handoff wrong; `://image` is docker/lxc-only).
- achiyon workflow exists: `.forgejo/workflows/ci.yml`, jobs `build/main` + test, `runs-on: nix`; gates: `fmt`, `clippy -- -D warnings`, `test`, `install`.
- Serenity: podman + `podman.socket` already **active** (unused if we go host-executor), **no sops** (token storage decision below), no `services.gitea-actions-runner` yet.
- `pkgs.forgejo-runner` available in our pin (confirmed).

## Design decisions

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Executor | **host** (`nix:host`) | CI needs `nix develop` + system nix; a container image would have to carry nix. Host exec = no isolation → **only trusted repos** (achiyon private + single user = within Forgejo's "host runner only for trusted repos" guidance). |
| 2 | Runner host | **serenity** | Achiyon work lives on serenity (`/Storage/Git/achiyon`); sccache/store sharing assumption. |
| 3 | Concurrency | 1 job at a time (module default) | sccache + nix store sharing. |
| 4 | Token storage | **depends on decision A** (below) | serenity lacks sops. |

## Change 1 — enable Actions on the server (forgejo aspect)
In `modules/aspects/server/forgejo/forgejo.nix` `settings`:
```nix
actions.ENABLED = true;
```
(optionally `actions.DEFAULT_ACTIONS_URL = "https://codeberg.org"` only if we want
GitHub/Forgejo-hosted `uses:` actions — achiyon's ci.yml is `run:`-only, so not needed now.)

## Change 2 — add the runner (new module or aspect)
Prefer a **den aspect** `modules/aspects/server/forgejo-runner/forgejo-runner.nix` (or
inline in serenity.nix if you want it host-scoped). Core block:
```nix
services.gitea-actions-runner = {
  package = pkgs.forgejo-runner;
  instances.serenity = {
    enable = true;
    name = "serenity";
    url = "https://serenity.oryx-galaxy.ts.net";
    tokenFile = <path to TOKEN=... env file>;   # sops template, or local root-only file
    labels = [ "nix:host" ];
    settings.container.valid_volumes = [];       # keep closed
  };
};
```
Gotchas from the module:
- Module sets `DynamicUser=true`, `User=gitea-runner`, `StateDirectory`.
- **Host executor needs a writable `$HOME`** for sccache + cargo registry → override:
  `systemd.services.gitea-runner-serenity.serviceConfig.WorkingDirectory` /
  `Environment = { HOME = "/var/lib/gitea-runner/serenity"; }`, pre-create it. (sccache cold on first run is fine.)
- No container runtime needed for `nix:host` label → no podman dependency (less surface; serenity already has it anyway).

## Change 3 — token
- Generate: Site Admin → Actions → Runners → *Create new runner* (or `GET /api/v1/admin/actions/runners/registration-token`).
- **Decision A (blocking):** serenity has no sops.
  - A1 (recommended): add `den.aspects.server.sops` to serenity + an age key for the host; store token via a sops template `TOKEN=…` fed to `tokenFile`. Consistent with the fleet.
  - A2 (quick, weaker): root-only plaintext file `/var/lib/gitea-runner/token.env` (`chmod 600`) — fine for a single-user forge but not fleet-idiomatic.
- Module assertion: `token` XOR `tokenFile` (not both).

## Change 4 — host prerequisites
- **nix flakes** for the runner user: host-level `nix.settings.experimental-features = ["nix-command" "flakes"]` is already the repo standard; confirm after deploy (`nix config show` as gitea-runner).
- **cuda substituter**: the bogus `cuda-maintainers.cachix.org` was REMOVED from the repo earlier this session (`modules/aspects/core/nix.nix`). Serenity's **live** `/etc/nix/nix.custom.conf` still 401s until this deploy lands — verify `nix config show | grep substituters` on serenity and confirm it's gone, else achiyon's `nix develop` fails in CI.

## Change 5 — test & first run
1. Deploy to serenity (`nixos-rebuild switch --flake .#serenity --build-host …`, ~15-30 min).
2. Verify runner visible in Forgejo Admin → Runners (green, label `nix`).
3. **Decision B (blocking):** first achiyon CI run will likely go **RED** — `ci.yml` gates `cargo clippy -- -D warnings` + `cargo fmt --check` are strict and untested against the tree.
   - B1: accept a red first run (honest baseline).
   - B2: push a temporarily softened gate (clippy advisory, fmt off) to achiyon first, flip strict later. (That's an achiyon-repo change, not spectacle.)
4. Trigger: push to achiyon `main`, or Actions tab → workflow dispatch. Watch logs in Actions tab; runner log `journalctl -u gitea-runner-serenity`.

## Success criteria
- Runner green + label `nix` in Admin → Runners.
- One achiyon CI run reaches `test`/`install` (pass or honestly-failed with readable logs, per Decision B).
- No 401 spam from `cuda-maintainers.cachix.org` on serenity.
- (Optional) add a `scripts/verify` guard or NixOS VM test for the runner module later.

## Files touched (planned)
- `modules/aspects/server/forgejo/forgejo.nix` — `actions.ENABLED`.
- `modules/aspects/server/forgejo-runner/forgejo-runner.nix` (new) or `modules/hosts/serenity/serenity.nix`.
- `modules/hosts/serenity/serenity.nix` — include aspect (+ sops if Decision A1).
- `secrets/serenity/…` (sops, if A1) / or a root-only token file (A2).

## Confirm
- **A:** token via sops (A1) or local root-only file (A2)?
- **B:** accept red first run (B1) or soften achiyon gate first (B2)?
- C: runner as a separate `forgejo-runner` aspect, or inline in `serenity.nix`?
