# Hermes Deployment Issues — Erebus VPS

## Overview

Issues encountered while deploying hermes-agent + MITM credential proxy on the erebus VPS. The final architecture uses a hybrid: hermes CLI owns the gateway unit file, NixOS manages everything else.

## Issue timeline (chronological)

### 1. `hermes cred-proxy` command doesn't exist

**Symptom**: `hermes cred-proxy start` fails — command not found
**Root cause**: PR #4695 was merged after v0.18.2. The `proxy` subcommand in the current release is an OpenAI-compatible OAuth proxy, not MITM.
**Fix**: Switched to `mitmdump` directly with a custom 18-line Python addon for header injection.

### 2. `--no-web` flag invalid for mitmdump

**Symptom**: mitmdump fails to start with "unknown flag --no-web"
**Root cause**: `--no-web` is a mitmweb flag, not mitmdump. mitmdump has no web UI.
**Fix**: Removed the flag.

### 3. Nix/Python escaping collision in addon script

**Symptom**: Addon throws exception on first request, journal shows raw Nix string interpolation artifacts
**Root cause**: Nix `''` strings + Python f-strings with `\"` produced broken Python. The escaping collided.
**Fix**: Rewrote addon with string concatenation, single quotes, `sys.stderr.write()` for logging, pre-compiled `re.compile()` patterns.

### 4. `awk` not found in activation script

**Symptom**: CA activation script fails — `awk: command not found`
**Root cause**: NixOS activation scripts run with minimal PATH — no `awk`, `coreutils`, etc.
**Fix**: Use full Nix store paths: `${pkgs.gawk}/bin/awk`, `${pkgs.coreutils}/bin/cat`, etc.

### 5. GitHub PAT expired/returning 401

**Symptom**: MITM proxy injects `GITHUB_TOKEN` but API returns 401
**Root cause**: PAT was stale/expired
**Fix**: User updated the PAT in sops. Also renamed from `pat-spectacle` to `pat-hermes-full`.

### 6. Dashboard can't switch models — config overwritten on restart

**Symptom**: Select model in dashboard → save → reload → reverts to default
**Root cause**: NixOS hermes-agent module's `configFile` mode overwrites `config.yaml` on every service start via `install -D`. The `settings` mode uses `configMergeScript` but Nix keys override existing values.
**Fix**: Removed `configFile` entirely. Set only `settings.display = { host, port }`. Hermes owns everything else in config.yaml.

### 7. Dashboard can't restart gateway — `Access denied`

**Symptom**: Click "restart gateway" → "action failed". `sudo -u hermes systemctl restart hermes-agent.service` → Access denied
**Root cause**: Services were system-level (`systemd.services.hermes-agent`). `hermes` user can't restart system services without polkit/sudo.
**Fix**: Converted to user-level services (`systemd.user.services`). Enabled linger for hermes user.

### 8. Wrong service name — `hermes-agent` vs `hermes-gateway`

**Symptom**: `hermes gateway status` says "Running manually, not as a system service" even though user service is active
**Root cause**: Hermes CLI hardcodes `_SERVICE_BASE = "hermes-gateway"` in `hermes_cli/gateway.py`. Our NixOS module created `hermes-agent.service`.
**Fix**: Renamed `systemd.user.services.hermes-agent` → `systemd.user.services.hermes-gateway`.

### 9. `refresh_systemd_unit_if_needed` fails on read-only Nix store symlink

**Symptom**: `hermes gateway restart` → traceback ending in `unit_path.write_text()` → `Read-only file system`
**Root cause**: `systemd.user.services` creates symlinks to `/nix/store/` (read-only). Hermes CLI calls `refresh_systemd_unit_if_needed()` on every restart, which tries to rewrite the unit file. These are fundamentally incompatible.
**Fix**: Approach A — let hermes own the unit file (see issues 10-13).

### 10. Writing unit files directly to `/etc/systemd/user/` fails

**Symptom**: Activation script `cat > /etc/systemd/user/hermes-gateway.service` → `Read-only file system`
**Root cause**: `/etc/systemd/user/` is managed by NixOS — read-only during activation.
**Fix**: Write to `~/.config/systemd/user/` instead (hermes user's home).

### 11. Dangling symlinks from removed NixOS services

**Symptom**: `cat > /var/lib/hermes/.config/systemd/user/hermes-gateway.service` → `Read-only file system`
**Root cause**: Previous NixOS deploys left dangling symlinks pointing to `/nix/store/` paths (which no longer exist after `systemd.user.services` was removed). `cat > symlink` follows the symlink target, which is read-only or gone.
**Fix**: `rm -f` the dangling symlinks before writing.

### 12. `sudo: command not found` in activation scripts

**Symptom**: Activation script fails — `line 103: sudo: command not found`
**Root cause**: NixOS activation scripts run with minimal PATH. `sudo` binary is not on PATH.
**Fix**: Use full Nix store path: `${pkgs.sudo}/bin/sudo -u hermes ...`

### 13. `.managed` marker file blocks `hermes gateway install` + config writes

**Symptom**: `hermes gateway install` refuses — "Hermes is managed by NixOS". Also `hermes config set` and dashboard config saves fail with the same error.
**Root cause**: Previous NixOS-module deploys created `/var/lib/hermes/.hermes/.managed` marker file. Hermes CLI checks `is_managed()` and refuses to install, set config, or save dashboard settings.
**Fix**: Activation script removes `.managed` before running `hermes gateway install` and does NOT restore it afterwards. Permanent removal allows config writes via dashboard/CLI. The `.managed` marker was initially restored to prevent hermes self-updates, but self-updates would fail anyway (no write access to `/nix/store/`).

### 14. `_wait_for_systemd_service_restart` hangs forever in crash loop

**Symptom**: `hermes gateway restart` never returns. Process hangs indefinitely when the gateway repeatedly crashes on startup.

**Root cause**: `_wait_for_systemd_service_restart()` in `hermes_cli/gateway.py` polls `systemctl is-active` in a loop. Logic: if active → done; if activating → wait and retry; else (inactive/failed) → `systemctl restart` again. **No deadline or max-retry on the auto-restart branch** — if the service enters a crash loop (immediately goes inactive after each restart), it retries forever.

**Status**: Unreported upstream. No existing issue on NousResearch/hermes-agent found.

**Fix**: Add a `max_retries` counter (e.g. 3) to the auto-restart path. Surface the error instead of looping.

**Symptom**: `hermes gateway install` refuses — "Hermes is managed by NixOS". Also `hermes config set` and dashboard config saves fail with the same error.
**Root cause**: Previous NixOS-module deploys created `/var/lib/hermes/.hermes/.managed` marker file. Hermes CLI checks `is_managed()` and refuses to install, set config, or save dashboard settings.
**Fix**: Activation script removes `.managed` before running `hermes gateway install` and does NOT restore it afterwards. Permanent removal allows config writes via dashboard/CLI. The `.managed` marker was initially restored to prevent hermes self-updates, but self-updates would fail anyway (no write access to `/nix/store/`).

## Final architecture

| Component | Managed by | Unit file location |
|---|---|---|
| hermes-gateway | Hermes CLI (`hermes gateway install` in activation script) | `~/.config/systemd/user/hermes-gateway.service` (real file, writable) |
| hermes-gateway env vars | NixOS (drop-in override) | `~/.config/systemd/user/hermes-gateway.service.d/override.conf` |
| hermes-dashboard | NixOS (`systemd.user.services`) | `/etc/systemd/user/hermes-dashboard.service` (symlink to /nix/store) |
| hermes-mitmproxy | NixOS (`systemd.services`) | `/etc/systemd/system/hermes-mitmproxy.service` (symlink to /nix/store) |
| falkordb, graphiti-mcp | NixOS (`systemd.user.services`) | `/etc/systemd/user/` (symlinks to /nix/store) |

## Key insights

1. **Hermes CLI `refresh_systemd_unit_if_needed()` only rewrites the MAIN unit file** — drop-in overrides (`hermes-gateway.service.d/override.conf`) survive the rewrite. This is by design in systemd.

2. **`systemd_unit_is_current()` only compares the main unit file** — drop-ins don't affect the "is current" check. So hermes will periodically try to rewrite the main unit file, but it succeeds (writable real file) and the drop-in override stays in place.

3. **NixOS activation scripts run with minimal PATH** — always use full Nix store paths for binaries (`${pkgs.sudo}/bin/sudo`, `${pkgs.gawk}/bin/awk`, etc.). Bare commands like `sudo` or `awk` will fail.

4. **Dangling symlinks from removed NixOS services silently break `cat >` redirects** — `cat > dangling-symlink` follows the symlink to its (possibly read-only) target. Always `rm -f` old symlinks before writing.

5. **`.managed` marker must be permanently removed** — hermes CLI's `is_managed()` check prevents `hermes gateway install`, `hermes config set`, and dashboard config saves. Remove it permanently (not just temporarily). Self-updates are prevented by the read-only Nix store anyway.

6. **`systemd.user.services` always creates symlinks to `/nix/store/`** — there's no NixOS option for regular files. If you need writable unit files, manage them via activation scripts or let the application's CLI install them.

7. **`hermes gateway` vs `hermes gateway run`** — the CLI uses `_SERVICE_BASE = "hermes-gateway"` and generates `ExecStart` with `gateway run` subcommand. Our NixOS unit used `hermes gateway` (no `run`), which also works because the CLI dispatches to `run` by default. The hermes-generated unit adds `gateway run` explicitly.
