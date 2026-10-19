# Proposal: managing Hermes Agent under the Nix config

**Status:** research + proposal. **No implementation in this session.**
**Date:** 2026-10-18 · **Host inspected:** serenity · **Agent version:** Hermes Agent v0.21.7 (2026.9.24), upstream `71d34bad`

**Companion issue:** Likivik/spectacle#82 (nix install reports out of sync) — root-caused in §2.5.

---

## 0. Recommendation in one screen

**Adopt upstream's mechanisms, not upstream's module wholesale.**

Upstream *does* ship a full NixOS module (`nixosModules.default`) and a Home Manager module, and its answer to "the app writes its own config" is a **deep merge**: Nix keys are merged *into* the on-disk `config.yaml`, every key Nix does not declare is preserved, and a `HERMES_MANAGED` env var plus a `.managed` marker file make the CLI *refuse* to mutate config it cannot keep.

That mechanism is exactly what this fleet needs, and we are currently running a hand-rolled, subtly-inferior copy of it. But the upstream module is a **singleton** — one `HERMES_HOME`, one gateway — and this fleet runs **three profiles** (`default`, `salem`, `hiring`) on serenity, with per-profile gateway units and per-profile secrets. Full adoption would require dropping profiles or wrapping the module.

So: keep the package input, the sops templates, and the per-profile units; import upstream's *config-merge + managed-marker* behaviour; and stop hand-writing what upstream already writes.

Three things to decide first (they gate everything else):

| # | Decision | Recommendation |
|---|---|---|
| 1 | Is `config.yaml` policy Nix-owned or agent-owned? | Nix-owned **policy keys**, agent-owned **runtime keys**, enforced by a merge + a check |
| 2 | Adopt the `.managed` guard? | Yes — but only after `mkStandalone` stops using `hermes config set` (it is currently *the* thing blocking this) |
| 3 | Import `services.hermes-agent` or reimplement? | Import for the default profile; layer profile units on top (§11 stage 3) |

---

## 1. Method and one important caveat

Everything below is established by inspection on serenity with real command output, not from memory. Commands are in the appendix; raw capture is at
`/var/lib/hermes/.hermes/cache/scratch/hermes-state-2026-10-18.txt`.

> **Caveat — the checkout's working copy is 10 days behind `main`.**
> `/Storage/Git/spectacle` has `@` = `zywpkply` on top of `32c231a` (2026-10-08). `main` is `69845f1` (2026-10-18 02:36). `git merge-base --is-ancestor main HEAD` → **false**; `HEAD` *is* an ancestor of `main`.
> The on-disk `modules/aspects/server/hermes/hermes-agent.nix` is **327 lines and has no `sops.templates`**; `main`'s version is **447 lines and is sops-templates-based**. The *deployed* system matches `main` (`/etc/systemd/user/hermes-gateway.service` references `/run/secrets/rendered/hermes/sops-env`), not the working tree.
> **All "current state" claims below are read from `main`** (`git show main:...`). If you read the file on disk you will be reading a stale revision. This itself is a finding: the agent's default workspace is not on the branch that gets deployed.

---

## 2. Current state, established by inspection

### 2.1 Identity

```
$ hermes --version
Hermes Agent v0.21.7 (2026.9.24) · upstream 71d34bad
Install directory: /nix/store/vlkvynbpginvwy3yzhvnbgz39fr3gaz7-hermes-agent-0.0.0/lib/python3.14/site-packages
Install method: nix

$ readlink -f $(which hermes)
/nix/store/1sr6gsg1nfwqjdgq79njp3q58ksh3wkh-hermes-agent-0.21.7/bin/hermes
```

Note the two store paths: a versioned wrapper (`1sr6gsg1…-hermes-agent-0.21.7`) and an unversioned Python tree (`vlkvynbp…-hermes-agent-0.0.0`). The `0.0.0` is upstream's `version ? "0.0.0"` default; the repo works around it by passing `version = "0.21.7"` explicitly (main, lines 9–19), which only affects the *stamp*, not the tree name.

`install-stamp.json` inside the artifact:

```json
{"baseVersion":"0.21.7","commit":"71d34bad…","displayVersion":"0.21.7","distribution":"nix",
 "payload":"bootstrap","pmRuntime":"/nix/store/k020ww31…-hermes-pm-runtime",
 "schemaVersion":2,"source":"nix","updateMechanism":"external"}
```

`updateMechanism: "external"` is the correct, honest value for a Nix-managed install.

### 2.2 What Nix already owns (on `main`)

`modules/aspects/server/hermes/hermes-agent.nix` (den aspect `server.hermes-agent`) currently declares:

| Surface | Declared? | Where |
|---|---|---|
| The package | ✅ | `inputs.hermes-agent.packages.<system>.minimal.override { extraDependencyGroups = ["messaging" "anthropic"]; version = "0.21.7"; }` |
| `hermes` on system PATH | ✅ | `environment.systemPackages = [ hermes-pkg ]` |
| `hermes` user + group + subuid/subgid ranges | ✅ | `users.users.hermes`, `users.groups.hermes` |
| Secrets (per-secret sops declarations) | ✅ | host files, e.g. `modules/hosts/serenity/serenity.nix:167-200` |
| Secret → env-file rendering | ✅ (on `main`) | `sops.templates."hermes/sops-env"` + one template per extra profile; rendered to `/run/secrets/rendered/<name>` |
| Gateway user unit | ✅ | `systemd.user.services.hermes-gateway`, `ConditionUser = "hermes"` |
| Dashboard user unit | ✅ | `systemd.user.services.hermes-dashboard` |
| Per-profile gateway units | ✅ | `hermes-gateway-salem`, generated from `extraHermesProfiles` |
| Linger | ✅ (indirectly) | `systemd.tmpfiles.rules = [ "f /var/lib/systemd/linger/hermes 0644 root root - -" ]` |
| State directories | ✅ | `system.activationScripts."hermes-seed"` (mkdir/chown/chmod 2770) |
| Migration cleanup | ✅ | `system.activationScripts."hermes-unit-cleanup"` |
| `config.yaml` | ❌ | fully agent-owned on disk |
| `.env` | ❌ | hand-managed file, 1403 bytes, 22 keys |
| Cron jobs, skills, memory, kanban, sessions | ❌ | runtime state |

### 2.3 What is hand-managed outside Nix

* **`~/.hermes/config.yaml`** — 21 138 bytes, 563 lines, 39 top-level keys, `_config_version: 50`. Six `config.yaml.bak-*` files sit beside it, the newest from today. It is written by the agent (`hermes config set`, TUI settings panes, plugin install) and by humans.
* **`~/.hermes/.env`** — 1403 bytes, 22 keys (`TELEGRAM_BOT_TOKEN`, `MINIMAX_API_KEY`, `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`, `STANDARD_COMPUTE_KEY`, `SEARXNG_URL`, …), plus six `.env.bak*` files. **This is a second, hand-maintained secret store alongside the sops-rendered one.** Nothing in Nix knows its contents.
* **`~/.hermes/profiles/`** — `salem` (declared in `extraHermesProfiles`) and **`hiring` (not declared anywhere in Nix)**. `grep -rn hiring modules/ --include='*.nix'` matches only the unrelated `hr-bot` aspect. So `profiles/hiring` is an undeclared Hermes instance with its own `config.yaml`, `.env`, cron, sessions.
* **Transient units.** `pylon-cdp.service` and `pylon-webdev.service` are `systemd-run --user` transients created 2026-10-18 by the agent (loaded from `/run/user/976/systemd/transient/`). They die on reboot and are invisible to Nix. `pylon-webdev` runs a Gradle wasm dev server out of `/Storage/Git/Workspaces/hermes-pylon-…`; `pylon-cdp` runs headless Chromium on `127.0.0.1:9222` with `--user-data-dir` inside the scratch cache.
* **Erebus' gateway mask.** `modules/hosts/erebus/erebus.nix:10-11` *includes* `den.aspects.server.hermes-agent` and `hermes-webui`, so the units are declared there too — but on the host:
  ```
  $ ssh hermes@erebus 'systemctl --user is-enabled hermes-gateway.service; systemctl --user is-active hermes-gateway.service'
  masked
  failed
  ```
  The mask is a **runtime fact, not a declared one**. A rebuild that unmasks would silently start a second gateway on a host that is supposed to be edit-only.
* **The `.managed` marker is actively deleted.** `system.activationScripts."hermes-unit-cleanup"` (main, line 394) runs `rm -f /var/lib/hermes/.hermes/.managed`, and `ls -la /var/lib/hermes/.hermes/.managed` → *No such file or directory*. This is deliberate: it is what keeps `hermes config set` working, which `mkStandalone` depends on.
* **Nix drives the self-writing path.** `mkStandalone` (main, lines 145–155) runs, from an activation script:
  ```
  sudo -u hermes bash -c '… HERMES_HOME=<profile home> … hermes config set gateway.standalone true'
  ```
  i.e. Nix calls the CLI to write the app's own config. Also note this is a `sudo -u hermes` call from a **boot-time activation script** — the exact class of call the file's own comment (lines 323–328) says silently failed on every boot once before.

### 2.4 Runtime state inventory

```
5,3G  ~/.hermes/state.db          # SQLite session store, WAL mode
35M   ~/.hermes/sessions
57M   ~/.hermes/skills            # 30+ dirs, incl. .archive/, .curator_backups/, .curator_ledger.jsonl (257 KB)
16K   ~/.hermes/memories
2,0M  ~/.hermes/cron              # executions.db, deliveries.db, external-workers/, ~40 .fire-*.lock
284M  ~/.hermes/logs
105M  ~/.hermes/profiles
6,4M  ~/.hermes/plugins
482M  ~/.hermes/lazy-packages     # HERMES_LAZY_INSTALL_TARGET — runtime pip installs
```

`hermes doctor` also reports nine more SQLite DBs (`cron/executions.db`, `projects.db`, `response_store.db`, `verification_evidence.db`, `kanban.db`, and seven per-board `kanban/boards/<board>/kanban.db`).

**There is no backup unit for any of this.** `grep -rn backup modules/aspects/server/hermes/` → nothing. The only rollback artefacts are the ad-hoc `config.yaml.bak-*` / `.env.bak*` files and `.hermes/backups`, `.curator_backups`. The brief's Nextcloud version-history incident is the precedent: destructive state operations here have no rollback story.

### 2.5 Defects with evidence

**(a) `install out of sync` — issue #82 is cosmetic, but it is a real artifact/stamp disagreement.**

```
$ hermes doctor
⚠ install out of sync (ffmpeg: not installed or outdated; ripgrep: not installed or outdated)
   — this nix-managed install must rebuild the artifact to fix
```

Mechanism, read from `hermes_cli/venv_sync.py:check_runtime` → `pm.activate()`: the check reads the **`pmRuntime` bundle** named in the stamp. That bundle is a Python venv only:

```
$ ls /nix/store/k020ww31…-hermes-pm-runtime/bin/
activate  activate.csh  activate.fish  Activate.ps1  python  python3  python3.14  𝜋thon
```

But the *artifact* does ship both tools — via `makeWrapper --suffix PATH` on the wrapper (`nix/hermes-agent.nix:184-215`, `runtimeDeps = [ nodejs ripgrep git openssh ffmpeg tirith wl-clipboard xclip ]`). Verified on the live gateway process:

```
$ PID=$(systemctl --user show hermes-gateway -p MainPID --value)   # 2124855
$ tr '\0' '\n' < /proc/$PID/environ | grep '^PATH=' | tr ':' '\n' | grep -iE 'ripgrep|ffmpeg'
/nix/store/vli6118fdbngwy46j1w741ansmrzfszr-ripgrep-15.2.0/bin
/nix/store/jzmlspv69xcby6bi634lj8xqfwavdjy8-ffmpeg-9.0.1-bin/bin
```

So ripgrep and ffmpeg **are** on the agent's PATH; `search_files` (ripgrep-backed) works from this very session. Two separate ripgrep store paths also exist in the store (`m6qxk1vl…`, `vli6118f…`), so `rg` resolves through the wrapper rather than the store root — which is why `command -v rg` in a bare shell fails.

**Verdict:** the warning is a false negative from `pm.activate()` for `updateMechanism: "external"` installs. Fix is upstream-side (skip the tool check when the stamp says external, or put the tools in `pmRuntime`); the fleet can only silence it locally. **Do not "rebuild the artifact to fix" — there is nothing to fix.**

**(b) Two secret stores.** `~/.hermes/.env` (hand-managed, 22 keys) and `/run/secrets/rendered/hermes/sops-env` (sops-rendered) both feed the gateway. The rendered file is the *last* `EnvironmentFile` loaded, so it wins on collisions — silently. The file's own comment (main, lines 46–54) records that this exact "blank wins" behaviour cost Telegram ~11 h on 2026-10-14.

**(c) Linger without ordering.** The repo creates `/var/lib/systemd/linger/hermes` via tmpfiles. Upstream's module instead sets `users.users.<u>.linger` **and** orders the gateway `after/wants linger-users.service`, **and** waits for `/run/user/<uid>/bus` in `preStart`, because:

> *"`loginctl enable-linger` returns before logind has finished starting `user@<uid>.service`, and `run_gateway()` resolves `XDG_RUNTIME_DIR` / `DBUS_SESSION_BUS_ADDRESS` exactly once at startup — so a bus that appears after `ExecStart` is a bus this process never sees, for its whole lifetime."*
> — `nix/nixosModules.nix:585-603`

The repo has the tmpfiles rule and no ordering. Cron's `systemd-run --user --scope` dispatch needs that bus (`checks.nix` documents the v2026.9.21 upstream fix for the cached-probe failure mode).

**(d) `sudo -u hermes` inside activation scripts.** `hermes-seed` (podman migrate) and `mkStandalone` (`hermes config set`) both call `sudo -u hermes` at boot. The file's own comment says boot-time activation runs before PAM/sudo-as-user works.

**(e) Undeclared `hiring` profile**, and an undeclared Erebus mask — both §2.3.

---

## 3. Q1 — Upstream packaging

**Yes. Upstream ships a flake, a NixOS module, and a Home Manager module — and we already consume the flake.**

Authoritative sources, read from the pinned flake source in the store (`nix flake archive` → `/nix/store/pd9xh4kl9gx2724qqy52kgy311hzz3qx-source`, rev `f97608f1…`, matching `flake.lock`):

`flake.nix` outputs:

```nix
imports = [ ./nix/packages.nix ./nix/overlays.nix ./nix/nixosModules.nix
            ./nix/homeManagerModules.nix ./nix/checks.nix ./nix/devShell.nix ];
systems = [ "x86_64-linux" "aarch64-linux" "aarch64-darwin" ];
```

`nix flake show` confirms the surface:

```
nixosModules.default
homeManagerModules
packages.x86_64-linux.{minimal,messaging,tui,web,desktop,default,sandbox,configKeys,node-gyp}
checks.x86_64-linux.{build-package,package-contents,entry-points-sync,cli-commands,
                     managed-guard,bundled-skills,bundled-locales,bundled-mcps,
                     bundled-plugins,bundled-tui,config-roundtrip,cron-worker-user-scope,…}
overlays.default
```

The official doc is `website/docs/getting-started/nix-setup.md` (1235 lines). It opens with an explicit support caveat:

> **Tier 2 platform.** *"The flake and NixOS module documented here are maintained on a best-effort basis only. Commits to `main` may break these packages at any point in time. For a supported setup, use one of the standard installation paths — either Docker or an FHS environment."*
> — `nix-setup.md:9-13`

and then:

> *"Hermes Agent ships a Nix flake, a NixOS module, and a Home Manager module."* — `nix-setup.md:15`

| Level | Audience | What you get |
|---|---|---|
| `nix run` / `nix profile install` | any Nix user | pre-built binary, standard CLI workflow |
| Home Manager module | one person, any distro | declarative config + user service, no root |
| NixOS module (native) | NixOS servers | declarative config, hardened systemd service, managed secrets |
| NixOS module (container) | agents needing self-modification | + persistent Ubuntu container for `apt`/`pip`/`npm` |

**What the fleet does today:** consumes `packages.<system>.minimal` and `overlays`-free `.override`, and **does not import `nixosModules.default`**. So the answer to "is there nothing official?" is: there is something official, and we are using half of it.

**Third-party packaging:** none needed — upstream's own flake is the answer, and it is the one already pinned. (Community patterns are summarised in §4.) A delegated search of nixpkgs and the wider flake ecosystem found **no** third-party `hermes-agent` package, overlay, or module; every hit traces back to `NousResearch/hermes-agent` itself.

**Relevant extras the flake provides that we do not use:**
* `packages.<system>.configKeys` — "run `nix build .#configKeys && cat result` to see every leaf config key extracted from Python's `DEFAULT_CONFIG`" (`nix-setup.md:260`). Directly useful for §11 stage 2.
* `checks.*.managed-guard`, `checks.*.config-roundtrip` — build-time guards for the two mechanisms in §4.
* `checks.*.cron-worker-user-scope` — the cron/linger contract from §2.5(c).
* **Container mode** (`container.enable = true`) — a persistent Ubuntu container with `/nix/store` bind-mounted, identity-hash-based recreation, and GC-root protection. The docs position it as the option for *"agents that need self-modification"*. **This is upstream's answer to our 482 MB `lazy-packages/`** (§6): native mode is locked to the Nix-built PATH, so runtime `pip`/`npm`/`apt` installs have nowhere sanctioned to go. Worth an explicit decision rather than letting `lazy-packages/` keep growing.
* **`manageLingering` / `users.users.<u>.linger`** — see §2.5(c) and §9.

**Upstream is one minor ahead of the pin.** The latest published release is **v0.22.2 (2026-10-15T08:21:32Z)**; the fleet pins **v2026.9.24**. The docs' own NixOS upgrade recipe is:

```
cd /etc/nixos && nix flake update hermes-agent && sudo nixos-rebuild switch
```

which matches §8's flow, minus the repo's extra dry-build + VM smoke gate.

---

## 4. Q2 — The core tension: declarative vs self-writing config

### 4.1 What upstream actually does

Upstream does **not** make `config.yaml` a read-only store symlink, and it says why:

> *"config.yaml: merge the Nix settings into the file on disk. Hermes writes this file at runtime. A read-only symlink to the Nix store breaks each save from the application. The Nix keys replace the keys on disk, and the module keeps all other keys."*
> — `nix/moduleCommon.nix:842-845`

The merge is a real deep merge, run at every activation (`nix/configMergeScript.nix`, 33 lines):

```python
existing = yaml.safe_load(config_path) if config_path.exists() else {}
def deep_merge(base, override):
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result
merged = deep_merge(existing, nix)          # Nix wins on leaves, others preserved
```

The option contract, verbatim (`moduleCommon.nix:270-289`):

> *"The merge into the config.yaml on disk is also a deep merge. These keys replace the keys on disk. The module keeps all other keys, which includes the keys that `hermes config set` and the settings panes of the TUI and the desktop app write at runtime."*

Then a second, independent guard for interactive shells — because the env var does not reach them (`moduleCommon.nix:855-858`):

```
${inst} -m ${modes.managed} ${pkgs.writeText "hermes-managed" managedSystem} ${hermesHome}/.managed
```

Two signals, and the refusal names the right rebuild command (`nix-setup.md:587-592`):

| Blocked | Why |
|---|---|
| `hermes setup` | config is declarative |
| `hermes config edit` | config is generated from `settings` |
| `hermes config set <key> <value>` | config is generated from `settings` |
| `hermes gateway install` / `uninstall` | the systemd service is managed by NixOS |

**Verified locally** (scratch `HERMES_HOME`, no writes to live state):

```
$ HERMES_HOME=$T HERMES_MANAGED=true hermes config set model.default zzz
Cannot set configuration values: this Hermes installation is managed by nixos.
Use your package manager to upgrade or reinstall Hermes.

$ HERMES_HOME=$T hermes config set model.default zzz
✓ Set model.default = zzz in …/config.yaml
```

So the guard is real and it works. Note what that implies for **this repo**: `mkStandalone` calls `hermes config set gateway.standalone true`. **Adopting the managed marker would break salem's gateway opt-out** — the extra-profile unit would refuse to start. That is a concrete, verified coupling, and it is the reason §0's decision #2 is ordered after #1.

There is also an escape hatch for people who want none of this (`nix-setup.md:327-335`):

```nix
services.hermes-agent.configFile = /etc/hermes/config.yaml;   # copied as-is, no merge
```

### 4.2 The options

| | Option A — module-merged config | Option B — `configFile`, Nix-owned read-only | Option C — seed + mutable overlay | Option D — status quo, tracked |
|---|---|---|---|---|
| `config.yaml` becomes | Nix-declared keys merged in at each activation | the declared file, copied verbatim | Nix baseline written once, runtime deltas on top | unchanged, agent-owned |
| `hermes config set` | **blocked** (managed guard) | **blocked** | allowed | allowed |
| Runtime-written keys (`cron_jobs`, `_config_version`, `onboarding.seen`, `known_plugin_toolsets`, `custom_providers`, `platform_toolsets`) | preserved | **destroyed on every activation** | preserved | preserved |
| Drift between declared and live | impossible for declared keys | impossible | **the failure mode** — two writers, no arbiter | total |
| Blast radius of a bad edit | one `nixos-rebuild` revert | one `nixos-rebuild` revert | silent, unbounded | unbounded |
| Per-profile support | **not provided** (module is a singleton) | same | same | already hand-rolled |
| Effort | high — 563 lines of YAML → attrset | high + loses runtime keys | low | none |

**Failure modes, concretely:**

* **A — the silent revert.** Declaring a key the agent writes does *not* stop `hermes config set`; it lets the write succeed and then **reverts it at the next activation**, with no warning, no error, and no diff. That is strictly worse than "requires a deploy" — it is a setting that disappears. Verified that model switching writes `config.yaml` (`hermes_cli/cli_model_switch_mixin.py` → `save_config` with a `persist_callback`; `model_switch_providers.py:66`, `auth_model_picker.py:303` also call `save_config`). Upstream itself classifies these as transient: `hermes_cli/backup.py:1102` lists `("model","provider")`, `("model","default")`, `("model","base_url")`, `("model","api_key")` among the keys a config-repair pass **strips** because they get "pinned to a transient composer pick".
* **A (continued)** — it also breaks `mkStandalone` (verified: `HERMES_MANAGED=true hermes config set …` is refused), breaks plugin/skin/persona changes if those keys are declared, and costs a rebuild for every preference tweak.
* **B — destroys `cron_jobs`.** `config.yaml` today carries `cron_jobs:` and `_config_version: 50`. A verbatim copy on every activation would drop every scheduled job at the next rebuild. **Do not use `configFile` here.** (Upstream's own docs frame `configFile` as "I'd rather manage config.yaml entirely outside Nix" — i.e. for a file you generate yourself, not for one the app writes.)
* **C — two writers, no arbiter.** Whoever writes last wins and neither side can tell. This is close to what the fleet has now, minus the "Nix baseline" half.
* **D — nothing prevents the drift that already happened**: an undeclared `hiring` profile, a hand-managed 22-key `.env` next to a sops-rendered one, an Erebus mask nobody declared.

### 4.3 Other self-writing surfaces

Beyond `config.yaml`, the agent writes and Nix does not own: `plugins.enabled` / `plugins.entries`, `mcp_servers` (added via `hermes mcp add`, tokens in `~/.hermes/mcp-tokens/`), `custom_providers` (one present: `NeuralWatt`), skins/pets, `skills/` (57 MB with a curator ledger), `lazy-packages/` (482 MB of runtime pip installs), `auth.json` (OAuth, self-refreshing).

Upstream's module covers four of these declaratively: `extraPlugins`, `extraPythonPackages`, `mcpServers`, `extraDependencyGroups`, plus `authFile` with an explicit "seed once, then Hermes owns it" contract (`authFileForceOverwrite = false` default). It has no story for skills, memory, cron, or lazy-packages — those are runtime state (§6).

---

## 5. Q3 — Secrets

**Hard invariant to preserve: secrets in `.env`/env files, settings in `config.yaml`. Never a Nix path literal.** Upstream encodes this in the *types*:

```nix
environmentFiles = mkOption {
  # The type is `str` and not `path` for a reason. A Nix path literal
  # copies the secret into the Nix store, which all users can read. Use
  # a runtime path from sops-nix or agenix instead, for example
  # `config.sops.secrets."x".path`.
  type = types.listOf types.str;
```
— `moduleCommon.nix:292-297` (same reasoning repeated for `backend.sessionTokenFile`, lines 623-627)

The module's contract (`nix-setup.md:369`): `environment` (non-secret) + `environmentFiles` (secret) are **merged into `$HERMES_HOME/.env` at activation**, and Hermes reads that file on every start via `load_hermes_dotenv()`. It warns explicitly that `environment` values land in the world-readable store.

**Where the fleet stands:**

* sops-nix per-secret declarations in the host files ✅
* `sops.templates` rendering secret + allow-listed literal lines into `/run/secrets/rendered/hermes/sops-env`, `owner = "hermes"`, `mode = "0600"` ✅ (this is *better* than the module's `.env` merge in one respect: the template content is asserted to contain only placeholders and allow-listed literals, so a literal secret fails the build — main, lines 262–281)
* A **second**, hand-managed `~/.hermes/.env` with 22 keys ❌
* Nothing declares the `hiring` profile's env ❌

**Recommendation:** keep `sops.templates` (it is strictly stronger than the module's `.env` merge), and *collapse the two stores*: the rendered file is the only source the services consume; `~/.hermes/.env` shrinks to values the agent is allowed to write at runtime. Add a check that no key appears in both — because the rendered file is loaded last and wins **silently**.

The two approaches are not in conflict: the module's `environmentFiles` semantics (list of runtime paths, merged at activation) and `sops.templates` (sops-nix renders the file itself, atomically, ordered after the secrets) achieve the same end. The fleet's version has the stronger guarantee, so **adopting the module must not mean adopting its `.env` merge** — pass the rendered path through `environmentFiles` if you import the module, or keep `EnvironmentFile=` on the units as today.

---

## 6. Q4 — State that must NOT be declarative

| Path | Size | Verdict | Why |
|---|---|---|---|
| `state.db` | **5.3 GB** | runtime state, **back it up** | SQLite session store; the agent's whole history |
| `sessions/` | 35 MB | runtime state, back up | transcripts |
| `logs/` | 284 MB | runtime state, rotate | already growing; `disk-cleanup` plugin exists |
| `cron/` | 2.0 MB | **mixed** | `executions.db` + locks are state; *job definitions* live in `config.yaml:cron_jobs` |
| `skills/` | 57 MB | runtime state + **semi-config** | `.bundled_manifest` tracks store-provided skills; the rest is agent-authored/curated (`.curator_ledger.jsonl`) |
| `memories/` | 16 KB | runtime state, back up | agent memory |
| `plugins/` | 6.4 MB | **config-ish** | enabled list lives in `config.yaml:plugins.enabled`; sources are runtime |
| `lazy-packages/` | 482 MB | runtime state, **disposable** | runtime pip installs; rebuilding is cheap |
| `profiles/` | 105 MB | runtime state; **instance list is config** | which profiles exist *is* a declared fact; their contents are not |
| `mcp-tokens/`, `auth.json` | small | runtime state | OAuth; upstream's `authFile` = seed-once contract |
| `kanban/`, `kanban.db` | small | runtime state | 7 boards |

Rule of thumb that matches upstream's own split: **the module owns directories, ownership, modes, and the declared subset of files inside them; it never owns the contents of the DBs.** Upstream's `stateSubdirs = [ "cron" "sessions" "logs" "memories" "plugins" ]` (`moduleCommon.nix:1135-1141`) is exactly this.

**Backups — currently absent.** Recommendation:

* `sqlite3 state.db ".backup"` into a staging file before copying (never copy a live WAL DB), then restic/borg to a remote. Include `config.yaml`, `.env`, `profiles/*/config.yaml`, `cron/`, `memories/`.
* Exclude `lazy-packages/` (482 MB, reproducible), `logs/`, `cache/`, `audio_cache/`, `image_cache/`, `backups/`.
* Add a **restore test** to CI or to the smoke gate. The Nextcloud version-history incident is the precedent for why "we have backups" without a restore drill is not a rollback story.
* Explicitly: no `nix-collect-garbage`-style pruning of `state.db`, and no `rm` of a profile directory, without a verified restore point.

---

## 7. Q5 — Multi-host and profiles

**Hosts:**

| Host | hermes-agent aspect | Reality |
|---|---|---|
| serenity | ✅ + hermes-webui | the live agent (gateway, dashboard, salem gateway) |
| erebus | ✅ + hermes-webui | gateway **masked + failed** at runtime, not declared |
| traversal | — | off-tailnet, nothing pulls |
| poweredge | — | not a hermes host today |

**The module is a singleton — verified, not inferred.** Direct evidence from the pinned source:

```
$ grep -rn 'HERMES_PROFILE' nix/          # → no matches
$ grep -rn 'profiles' nix/                # → one match, a comment about "NixOS profiles" (Nix profiles, not Hermes ones)
$ grep -n 'systemd.services' nix/nixosModules.nix
566: systemd.services.hermes-agent = {     # native mode
617: systemd.services.hermes-backend = {   # backend
640: systemd.services.hermes-agent = {     # container mode (same unit name, mkIf-gated)
```

`services.hermes-agent` is a single option attrset — there is no `instances` or `profiles` option, and one `stateDir` → one `HERMES_HOME` → one unit. The Hermes profile concept (`~/.hermes/profiles/<name>/`) has **no representation** in either the NixOS or the Home Manager module.

The one nuance: the **Home Manager** module is scoped per-*user* (`hermesHome` defaults to `${config.home.homeDirectory}/.hermes`), so N OS users give N instances. That is a different axis — it changes the Unix user, not the Hermes profile. This fleet runs `default`, `salem` and `hiring` as profiles under **one** `hermes` user, which no upstream option expresses today.

Consequences:

1. **Full module adoption would either drop profiles or require a wrapper.** The honest options: (a) keep profile units hand-rolled in an aspect layered over the module; (b) write a small `lib` function that instantiates the module's *shared* pieces per profile — but `moduleCommon.nix` is not exported as a flake output, so this means vendoring it; (c) drop to one profile.
   **A cleaner expression exists than the current hand-generated unit names**: systemd *template units* — declare `hermes-gateway@.service` once with `ExecStart = "… %i …"` and `StateDirectory = "hermes/%i"`, then one `systemd.services."hermes-gateway@<name>" = { overrideStrategy = "asDropin"; … }` per profile. This became possible in NixOS when `overrideStrategy = "asDropin"` landed (nixpkgs PR #186314); before that, instantiating `foo@bar.service` from a module needed a `systemd.packages` symlink hack. The repo's current programmatic names work and are defensible — but if §11 stage 3 introduces a base unit anyway, templates are the smaller surface. Caveat: `overrideStrategy` errors if the base unit is not itself declared.
2. **Erebus' mask should be declared.** The cleanest expressions: `systemd.user.services.hermes-gateway.enable = false` on erebus, or a `hostGate` list in the aspect (`extraHermesProfiles`-style). Either way the *fact* "erebus does not run a gateway" becomes reviewable instead of a `systemctl mask` someone remembers.
3. **`hiring` must be declared or retired.** It exists on disk with its own `config.yaml`, `.env`, cron and sessions. Either add it to `extraHermesProfiles` (which also requires sops declarations for its token and API key) or move it out and document why.
4. **Per-profile sops templates already scale** (`sopsTemplates` maps over `extraHermesProfiles`), so secret wiring is not the blocker — unit generation is not either. The blocker is `config.yaml` per profile.

---

## 8. Q6 — Upgrades and pinning

**Current pin:**

```nix
# modules/defaults/inputs.nix:59-62  (declared once — the file warns against re-declaring)
hermes-agent = {
  url = "github:NousResearch/hermes-agent/v2026.9.24";
  inputs.nixpkgs.follows = "nixpkgs";
};
```

`flake.lock` resolves it to `rev f97608f178d1ffeca59860195ab7da295f7c8e5f`, `lastModified 1790244527`. The pin is a **tag** (`v2026.9.24`), not a branch — correct. The inputs file also records a floor (`do not pin below v2026.9.21`) with a check enforcing it (`checks.hermes-cron-dispatch-fix`).

**Two version facts worth keeping:**

1. **The `0.0.0` stamp.** Upstream v0.21.7 moved to stamp-based versioning: `pyproject.toml` carries `0.0.0` and the CLI reads `baseVersion` from `install-stamp.json`. Nix sources keep no `.git`, so upstream's flake stamps `0.0.0` (upstream #130070, open). The repo passes `version = "0.21.7"` explicitly, with a comment demanding it stay in sync with the input tag — **enforced by nothing.** A `checks.*` assertion comparing the packaged `baseVersion` to the pinned tag would catch the next mismatch mechanically.
2. **A nixpkgs bump changes the kernel** (6.18.49 → 6.18.55 in the 2026-10-06 bump). `switch` activates userspace only; the running kernel cannot load the new module tree (nvidia, ZFS), so the box is half-state until reboot. Prefer `nixos-rebuild boot` + reboot, or bump **only** the input you need (`nix flake update hermes-agent`) and leave nixpkgs pinned — userspace-only changes take effect on switch. The VM smoke gate validates the fresh-boot path; a switch does not.

**Recommended upgrade flow:** `nix flake update hermes-agent` → `nix build .#checks.x86_64-linux.{hermes-cron-dispatch-fix,hermes-imports,hermes-version-stamp}` → dry-build → `nix run .#serenity-smoke` → push → detached `systemd-run` switch (per `AGENTS.md`) → reboot if nixpkgs moved.

---

## 9. Q7 — Service supervision

**Declared (NixOS user units, on `main`):**

| Unit | Notes |
|---|---|
| `hermes-gateway.service` | `ConditionUser=hermes`, `after/wants sops-install-secrets.service`, `Restart=always`, `EnvironmentFile=/run/secrets/hermes/env` + rendered sops-env |
| `hermes-dashboard.service` | same ordering + env pattern, `--host 0.0.0.0 --port 9119 --no-open` |
| `hermes-gateway-salem.service` | generated per extra profile; `after/wants sops-install-secrets.service` **and** `hermes-gateway.service` (to remove the exit-75/TEMPFAIL race) |
| `graphiti-mcp.service` | separate aspect |
| `hermes-webui.service` | `webui.nix`, upstream `services.hermes-webui` module |
| `hr-bot.service` | system unit, separate aspect |

Plus `systemd.tmpfiles.rules = [ "f /var/lib/systemd/linger/hermes 0644 root root - -" ]`.

**Observations:**

* The `after/wants sops-install-secrets.service` lines are load-bearing and well-commented: without them the unit starts in parallel with the renderer, opens an empty `EnvironmentFile`, and `Restart=always` masks the failure. (2026-10-15 14:02:41 incident.)
* `ConditionUser = "hermes"` on every unit means the *same* NixOS config produces no-op units for other users. That is a reasonable idiom but it means "the unit exists" ≠ "the unit runs" — and on erebus it is combined with a runtime mask (§2.3).
* **Linger has no ordering** (§2.5c). Upstream's `preStart` bus wait is the missing piece.
* **Transient `systemd-run --user` helpers.** `pylon-cdp` (headless Chromium, CDP on 9222) and `pylon-webdev` (Gradle wasm dev server) are legitimate *for what they are*: interactive, session-scoped, throwaway dev processes that should not survive a reboot. The failure mode is not that they exist — it is that they are indistinguishable from state the fleet depends on. Policy recommendation:
  * Session-scoped dev helpers: keep transient, and **document the rule** ("transient = dies on reboot by design").
  * Anything a *service* or another host depends on (a CDP endpoint a test suite needs, an embedder, a proxy): make it a real Nix unit. `quadlet-nix` is already an input if containers are the right shape.
  * Note that `pylon-cdp`'s `--user-data-dir` sits in `.hermes/cache/scratch/`, which is **pruned after 24 h idle** — so the profile is disposable even though the process is long-lived.
* **Nix-declared and transient units coexist without colliding.** Nix units use full names (`hermes-gateway.service`); `systemd-run` transients use the `run-r<hex>` prefix. There is no shadowing hazard — the two sets are disjoint by construction. The hazard is *visibility*, not collision: nothing in Nix or in a rebuild tells you a transient is running.
* **PATH matters for the cron scope probe.** A separate upstream report (#105365) documents `systemd-run --user --scope` availability probes failing on NixOS because the probe hardcodes `/bin/true` and NixOS has no FHS `/bin`. This is a *distinct* bug from the cached-probe fix the repo already guards (`checks.hermes-cron-dispatch-fix`, upstream #111484): one is the probe's binary path, the other is the probe's caching. On this host the deployed gateway unit gets the systemd user default `PATH`, which includes `/run/current-system/sw/bin`, so `true` resolves — but that is an accident of the unit's environment, not a guarantee. `checks.cron-worker-user-scope` upstream is the place to pin it.

---

## 10. Q8 — What "done" looks like

| Surface | End state | How it changes |
|---|---|---|
| Package | Nix, upstream flake input, tag-pinned | already true |
| `config.yaml` | Nix-declared **policy** keys merged in at activation; runtime keys preserved | add `hermesSettings` + merge step |
| `hermes config set` | works for runtime keys; refused for declared keys | adopt `.managed` + `HERMES_MANAGED` **after** removing the CLI call from `mkStandalone` |
| Secrets | one rendered env file per profile, from `sops.templates`; `.env` holds only agent-written values | collapse the two stores; add a duplicate-key check |
| Units | declared user units, with linger ordering | add `linger-users.service` ordering + bus wait |
| Erebus | gateway disabled **in Nix** | replace the runtime mask |
| Profiles | the declared list is the whole list | declare or retire `hiring` |
| State | untouched, but **backed up and restorable** | add a backup unit + a restore drill |
| Transients | transient = by design; anything durable is a unit | document the rule; promote what must survive |
| Verification | one command answers "does the host match the declared state?" | a `hermes-audit` app/check |

**The change flow, end to end:** edit the aspect → `nix build .#nixosConfigurations.serenity.config.system.build.toplevel --dry-run` → `nix run .#serenity-smoke` → `jj bookmark set dev -r @ && jj git push --all` → detached `sudo systemd-run --collect --unit=nixos-rebuild-serenity …` → verify with `hermes-audit` and `systemctl --user status hermes-gateway`. Restarting the gateway remains **the user's action**, never an agent's (the cgroup hazard in `AGENTS.md`).

**The verification command** — recommended shape:

```
nix run .#hermes-audit        # exits non-zero on drift
  · packaged baseVersion == pinned tag
  · no key present in both the rendered env and ~/.hermes/.env
  · every profile dir under ~/.hermes/profiles is declared, and vice versa
  · units declared == units enabled (catches the erebus mask)
  · every key Nix declares in settings is present and equal on disk
  · /run/user/<uid>/bus exists while the gateway is active
  · state.db backup younger than N days
```

That list is the definition of done: each line is a fact someone currently has to remember.

---

## 11. Recommendation and migration path

### 11.0 In plain terms — what moves, and what does not

Day-to-day use does not change: the same `hermes config set` keeps working, the gateway keeps behaving the same, and salem stays a separate process.

**Bucket 1 — already declared, no change:** the hermes binary; the `hermes` user; the gateway unit; the dashboard unit; salem's gateway unit; secrets → rendered env files; state directories; linger.

**Bucket 2 — moves to declared (new):** *policy* settings only — API ports/listeners; which platforms are enabled + the webhook port; which plugins and MCP servers exist; `security.*` and `compression`. Editing one of these becomes "edit Nix + deploy" (~15 min, no reboot unless nixpkgs moved).

**Bucket 3 — stays agent-owned, unchanged:** `model.default`/`model.provider`, `stt.*`, `display.*`, skins/pets, `cron_jobs`, sessions, memory, skills, `state.db`, and the values the agent writes into `.env`. `hermes config set` keeps working here and **survives** deploys.

**Profiles stay separate processes.** `default` (likivik) and `salem` remain two independent gateways — separate unit, separate `HERMES_HOME`, separate port (8642 / 8643), separate bot token and API key, separate socket, separate restart. Restarting one cannot affect the other. Nix declares both units and continues to. The only change is that salem's `gateway.standalone: true` moves from a boot-time `hermes config set` call into the Nix declaration (step 2.3) — required, because that CLI call is exactly what the managed guard blocks (step 2.4).

**Multi-*user* is not needed and is not proposed.** Upstream's module offers only one instance per OS *user*; this fleet runs one `hermes` user with N *profiles*. That shape difference is the sole reason for keeping our own per-profile unit generation instead of importing upstream's module whole.

### 11.1 Why this shape

**Recommended: Option A restricted to policy keys, plus adoption of upstream's mechanisms — phased, each stage independently revertible.**

Reasoning:

1. Upstream's deep-merge is the *only* design in §4.2 that reconciles the two writers without lying about it, and it is the design upstream already tests (`checks.config-roundtrip` covers 7 merge scenarios).
2. The alternative — keep config imperative and "track" it — is what the fleet has now, and it has already produced four undeclared facts (§2.3) in a setup that is only weeks old.
3. Full module adoption is blocked by the singleton limitation (§7), so the module cannot simply be dropped in.
4. The `.managed` guard is valuable but is currently *impossible*: `mkStandalone` needs `hermes config set`. So the order matters — fix the writer, then close the door.

### Stage 0 — preconditions (no behaviour change)

| Step | Change | Verify |
|---|---|---|
| 0.1 | Reconcile the workspace: `jj edit main` (or a fresh workspace from `main`) before touching hermes files | `git merge-base --is-ancestor main HEAD` → true |
| 0.2 | Add `checks.hermes-version-stamp`: packaged `install-stamp.json.baseVersion` == the tag in `inputs.nix` | `nix build .#checks.x86_64-linux.hermes-version-stamp` |
| 0.3 | Snapshot before anything: `sqlite3 state.db ".backup …"` + copy `config.yaml`, `.env`, `profiles/*/config.yaml` | files exist, non-zero, restore into a scratch dir opens cleanly |

### Stage 1 — make drift visible (read-only, safe)

| Step | Change | Verify |
|---|---|---|
| 1.1 | Add `hermes-audit` with the §10 checks; start with the ones that need no new declaration (profiles declared↔present, duplicate env keys, version stamp, bus presence) | the check fails on today's state, listing `hiring` and the duplicate keys |
| 1.2 | Decide and *write down* the `.managed` policy. Today the activation deletes the marker, which is an undocumented decision | comment + check assert the intended state |

**Risk:** none — stage 1 adds a read-only check.

### Stage 2 — move policy into Nix (the core change)

| Step | Change | Verify |
|---|---|---|
| 2.1 | Split `config.yaml` into **policy** keys (Nix owns: API ports, `API_SERVER_*`, `platform_toolsets`, `plugins.enabled`, `mcp_servers`, `security.*`, `compression`, `cron.model*`) and **runtime** keys (leave undeclared: `model.*`, `stt.*`, `session_reset`, `display.*`, skins, `cron_jobs`, `_config_version`, `onboarding.seen`, `known_plugin_toolsets`, `custom_providers`) | `nix build .#configKeys` + a diff of the two sets; record the classification in the file |
| 2.2 | Add `hermesSettings` (attrset) + the deep-merge activation step. Reuse upstream's `configMergeScript.nix` verbatim — it is 33 lines and MIT-licensed — rather than writing a second one | dry-build; then `hermes config get` for each declared key equals the declared value; then `grep cron_jobs config.yaml` still present |
| 2.3 | Replace `mkStandalone`'s `hermes config set gateway.standalone true` with a declared key in that profile's own merge | salem's `config.yaml` contains `gateway.standalone: true` **and** no activation script calls the CLI |
| 2.4 | **Only now** adopt the `.managed` marker + `HERMES_MANAGED` for the default profile | `HERMES_HOME=/var/lib/hermes/.hermes hermes config set model.default x` is refused; salem's unit still starts |

**The rule for 2.1: declare policy, never preference.** The test is "would I want this reviewed in a diff, and would a silent revert of it be acceptable?" A declared key is a key whose value the agent will try to change and then lose at the next activation (§4.2, failure mode A). So:

* **Declare** things that describe the *deployment*: ports, listeners, which platforms are enabled, which plugins/MCP servers exist, security and compression policy.
* **Never declare** things the agent writes during normal use: `model.default`/`model.provider` (written by the model picker and `/model`), `stt.provider` (written by `hermes tools`), `session_reset`, `display.*`, skins/pets, `cron_jobs`, `_config_version`, `onboarding.seen`, `custom_providers`, `platform_toolsets` if the settings pane touches it.

Changing a declared key means a deploy (dry-build → smoke → switch ≈ 10–20 min, no reboot unless nixpkgs moved). Changing an undeclared key stays a `hermes config set` that survives. Getting this split wrong is the one way to make the migration *worse* than the status quo.

**Risk — highest in the plan.** Mitigations: dry-build + `serenity-smoke` before every switch; do 2.2 and 2.3 in separate commits so a revert is surgical; keep 0.3's snapshot; verify `cron_jobs` survives the merge explicitly (it is the one key whose loss is silent and expensive). **Do not** use `configFile` (§4.2, option B) — it would delete every scheduled job.

### Stage 3 — decide module adoption

| Option | Gain | Cost |
|---|---|---|
| 3a. Keep the hand-rolled aspect | nothing new | maintain a parallel implementation of §4.1 |
| 3b. Import `nixosModules.default` for the **default profile only**; keep `hermes-gateway-<name>` hand-rolled | state dirs, linger ordering, bus wait, `.env` rendering, `documents`/`hermesHomeFiles`, upstream's own checks | two config sources for two profile kinds; must pass the rendered sops path through `environmentFiles` to avoid a third env store |
| 3c. Vendor `moduleCommon.nix` and instantiate per profile | one mechanism for all profiles | vendoring an upstream file that changes on `main` — the Tier-2 warning applies |

**Recommendation: 3b**, with 3c revisited only if upstream adds a profile option. 3b deletes the most hand-written code (§2.5c, §2.5d, and the state-dir part of `hermes-seed`) for the smallest behavioural change.

### Stage 4 — secrets consolidation

Collapse to one source per profile. Keep `sops.templates` (stronger than the module's `.env` merge). Shrink `~/.hermes/.env` to agent-written values. Verify with the 1.1 duplicate-key check.

### Stage 5 — backups and a restore drill

Add the backup unit (§6) with a pre-copy `sqlite3 .backup`. **Verify by restoring `state.db` into a scratch dir and opening it** — not by reading the backup job's exit code.

### Stage 6 — host and profile expression

Declare Erebus' gateway-off in Nix. Declare or retire `hiring`. Verify with 1.1.

### Stage 7 — transient-helper policy

Write the rule down. Promote anything durable to a real unit; leave session-scoped dev helpers transient.

### What each stage must not do

* Restart the gateway from an agent's cgroup (`AGENTS.md`).
* Create git worktrees — jj only.
* Put a secret or a key literal in the Nix store (the `permittedLiteralLines` assertion already guards this; keep it).
* Delete `state.db`, a profile dir, or `cron_jobs` without a verified restore point.

---

## 12. What I could not determine

| # | Open question | What I'd need |
|---|---|---|
| 1 | Whether the upstream module can be instantiated more than once (profiles) — I read `nixosModules.nix` and `moduleCommon.nix` in full and found no profile concept, but I did not test a second instantiation | a throwaway eval: two `services.hermes-agent` definitions with different `stateDir`, or a read of upstream's issue tracker |
| 2 | Whether `hermes plugins install` / `hermes mcp add` write to keys Nix would declare — i.e. exactly which keys must stay undeclared | run each mutating CLI against a scratch `HERMES_HOME` and diff `config.yaml` before/after |
| 3 | Whether the fleet's `config.yaml` would survive a deep merge unchanged (no key currently disagrees with an intended declaration) | a dry merge against a candidate `hermesSettings` |
| 4 | The `hiring` profile's owner and purpose | not in the repo; only `hr-bot.nix` mentions "hiring", and it uses the profile's sops-env, not the profile |
| 5 | Whether `lazy-packages/` (482 MB) is load-bearing for the langfuse plugin or reproducible from the store | inspect `HERMES_LAZY_INSTALL_TARGET` contents vs the plugin's declared deps |
| 6 | Whether the `install out of sync` warning can be silenced locally (stamp manipulation) without lying to the update machinery | upstream #82 is filed; a fix belongs upstream |
| 7 | Whether `serenity-smoke` currently asserts the linger/bus contract — `checks.cron-worker-user-scope` exists upstream but I did not confirm it is wired into the gate | read `tests/` and the smoke app |
| 8 | Whether `profiles/salem/config.yaml`'s `gateway.standalone: true` was written by the CLI or by hand | no audit trail; `gateway-starts.log` shows only start times |

---

## 13. From scratch: a greenfield design for "one agent per person, many people, many machines"

Researched 2026-10-18 (upstream docs + community deployment patterns; sources in Appendix C). This section answers: if we started today with the requirement "me, mom, dad, friends, work — each with their own agent, possibly on different machines", what would we build?

### 13.1 The one rule upstream is explicit about

> *"Hermes Agent is a single-tenant personal agent… Within the authorized set, all callers are equally trusted. Hermes Agent does not model per-caller capabilities inside a single adapter. Operators who need capability separation should run separate agent instances with separate allowlists."* — SECURITY.md

> *"The only security boundary against an adversarial LLM is the operating system. Nothing inside the agent process constitutes containment — not the approval gate, not output redaction, nor any pattern scanner, nor any tool allowlist."* — SECURITY.md

Hermes profiles give **state** isolation (own `HERMES_HOME`, `state.db`, sessions, cron, secret scope, session namespace `agent:<profile>:…`) but **not** **security** isolation: every profile under one OS user shares one UID, one process, one file namespace. Mom's agent can read your files and vice versa.

**Therefore, from scratch: one person = one OS user = one Hermes instance.** Not N profiles under `hermes`.

### 13.2 A second finding that forces the same conclusion

Our salem setup relies on `gateway.standalone: true`. Upstream's own docs (multi-profile-gateways) say:

> *"`gateway.multiplex_profiles: false` is retired and was rewritten to true… A per-profile gateway is `gateway.standalone: true` in that profile's config (**temporary shim, not a supported topology**…) it will be removed."*

So the mechanism salem depends on is explicitly scheduled for removal. The direction of travel is: **one gateway per host serves every profile under that user** — i.e. per-person separation is only clean *between* OS users. This also means §11 stage 2.3 (moving the standalone flag into Nix) is right for *today* but should be tagged as temporary; the durable fix for a person who needs their own gateway is their own OS user.

### 13.3 The greenfield shape

One shared role, parameterized per person — the `attrsOf submodule` pattern used by `services.zeroclaw.instances`, `services.agent-box.users`, `services.restic.backups`:

```nix
# fleet.people (or den aspects, one per person — den's { host, user }: parametric form)
people.mom = {
  osUser = "hermes-mom";            # isSystemUser, linger = true, StateDirectory
  host = "serenity";                 # or any host; the aspect travels
  botTokenSecret = "people/mom/telegram-bot-token";
  apiKeySecret     = "people/mom/api-key";
  telegramAllowedUsers = [ "<mom's tg id>" ];   # THE access control
  graphitiGroup = "mom";             # memory partition — already how the plugin scopes
};
```

Each entry materializes, from one declaration site:

| Concern | What it becomes |
|---|---|
| OS identity | `users.users.<name>` (`isSystemUser`, `linger = true`, own group) — the only real security boundary |
| Home/state | `StateDirectory`/home per person; own `state.db`, sessions, memory |
| Unit | one gateway unit per person (`systemd` system or user unit with `User=<name>`) |
| Secrets | sops-nix per-host file: bot token + API key, `owner = <name>` |
| Access control | `TELEGRAM_ALLOWED_USERS` = that person's Telegram ID — per-profile allowlists are read from the owning profile's env, so this is already first-class |
| Memory | graphiti `group_id = <person>` — the partition scheme in `profile-groupid-scoping.md`, unchanged |
| Backups | trivially separable per person; each person's `state.db` is small enough to snapshot independently |

Adding a person = one entry + one sops secret. Adding a *machine* for that person = the same aspect on another host; **state does not sync** — upstream's cross-machine story is deliberately profile-shaped:

- **Profile distribution**: author a profile in a git repo (secrets/sessions/state.db excluded), `hermes profile install <repo>` on each box. *"Memories stay per-machine — the laptop remembers its own conversations."*
- **One-time migration**: `hermes profile export/import`, or `hermes backup`/`hermes import` for a full move.
- **Federation, not clustering**: the Desktop app registers N independent backends side by side. There is no shared-`state.db`/active-active topology; the N-peers-over-Tailnet pattern (issue #32397) and the Hermes Mesh RFC (#94363) are the open directions, unshipped.

### 13.4 What the current setup got right and wrong, judged from scratch

| Current choice | Verdict |
|---|---|
| Parameterized `extraHermesProfiles` list | ✅ right instinct — it is exactly the `attrsOf`/list-materialization pattern |
| graphiti `group_id` derived from profile name, no hardcoded literals | ✅ right — and it transfers unchanged to per-person users |
| salem on a separate gateway | ✅ right instinct (per-person separation), ❌ wrong mechanism — `gateway.standalone` is a documented temporary shim |
| Everything under one `hermes` OS user | ❌ wrong from scratch for *people* — fine for one human's multiple personas, wrong the moment mom and dad join |
| `hiring` profile undeclared | ❌ the drift §2.3 already flags |
| One 5.3 GB `state.db` with no backups | ❌ from scratch, per-person users make per-person backup units natural |

The dividing line that was never written down: **profiles are for one person's multiple personas; OS users are for multiple people.** The repo used profiles for both, because at the time there was one person. That is the "why" that should have been a design doc.

### 13.5 Migration bridge from here

Nothing in §11 is invalidated — stages 0–2 (policy keys, managed guard, secrets consolidation) apply per *instance* and carry over unchanged to a per-person world. What changes:

1. Stage 3 ("module adoption") gets a new best answer for *people*: **upstream's NixOS module per OS user** — the module is singleton per user, so one person per user is not a workaround, it is the upstream shape. Import it N times, one per person's user, and the per-profile hand-rolling disappears.
2. salem (if salem is a *persona of yours*, not another human) can stay a profile — but then its natural home is the multiplexed gateway once `standalone` is removed, and stage 2.3 should be written as a stopgap.
3. If salem is effectively *another person*, the from-scratch answer is: promote salem to an OS user via the `people` shape above, and the standalone-shim problem dissolves.

## Appendix A — commands used

## 14. Open decision (started 2026-10-18, not concluded): the memory system

Status: research complete, decision pending. Owner's position: Graphiti is not the best system — per-LLM-cost and space+machinery (Achiyon research concluded memory consolidation is the cost centre of any LLM product). Salem is another **person** (girlfriend, not a persona) — the per-person OS-user design in §13 is confirmed as the target shape for her.

Full research saved at: `/var/lib/hermes/.hermes/cache/delegation/subagent-summary-0-20261018_195821_976471.txt` (25k chars, all citations). Headline findings:

- **Graphiti's write path is the cost**: 4–6+ LLM calls per episode (entity extraction, dedup, edge extraction, contradiction resolution, summaries) + embedding per node/edge (Pinakes deep-dive on graphiti-core 0.29.x). Community report: **41M tokens / 24k API calls ingesting one docs site in 2 h** (graphiti issue #290, GPT-4o). Maintainer baseline (2k PDF pages ≈ $1) assumes GPT-4o-mini and simple content.
- **Benchmarks are noise**: LoCoMo full-context baseline (72.9) beats Mem0 (66.9) and Mem0g (68.4); Letta's plain-filesystem agent hit 74.0 — *"memory is more about how agents manage context than the exact retrieval mechanism used."* A zero-LLM-write system scored 67.3. Nobody's numbers are third-party replicated.
- **Practitioner reality for personal/small-fleet agents is plain files**: Claude Code's MEMORY.md, Letta's filesystem agent, Hermes' own built-in (MEMORY.md + USER.md, 0-token writes, always active alongside any provider).
- **Hermes-native options** (only one external provider active at a time): built-in files (free, capped), Honcho (Hermes-blessed, cadence-gated LLM cost, self-hostable), Mem0 (same write-side LLM cost class as Graphiti), Hindsight (measured most expensive of its peer group, ~$0.24/100 turns), Holographic (local SQLite+FTS5, free), OpenViking, Supermemory, ByteRover, RetainDB.
- **Graphiti is not an official Hermes provider** — the fleet's is a custom plugin + patched graphiti-core 0.29.x + FalkorDB container + sync loop, all self-maintained (NousResearch/hermes-agent#70067 open, unreleased).

Research ranking for this fleet (1–3 instances → one per person): **1)** built-in plain-file memory (+ optionally FTS5/sqlite-vec for long-history recall), **2)** Honcho if more than files is wanted, **3)** file + small vector layer, 4) Letta self-hosted, 5) Mem0/Hindsight, 6) keep Graphiti (hard-budgeted: GPT-4o-mini pinned, no community summaries, token spend metered in Langfuse). **Not yet decided by the owner.**



```bash
hostname -s; date -Is
hermes --version; readlink -f "$(which hermes)"; hermes doctor
sed -n 's/^\([A-Za-z0-9_]*\)=.*/\1/p' /var/lib/hermes/.hermes/.env      # key names only
du -sh /var/lib/hermes/.hermes/{state.db,sessions,skills,cron,logs,profiles,plugins,lazy-packages}
systemctl --user list-units --all --type=service
systemctl --user status pylon-cdp.service pylon-webdev.service
systemctl --user cat hermes-gateway
PID=$(systemctl --user show hermes-gateway -p MainPID --value); tr '\0' '\n' < /proc/$PID/environ | grep '^PATH='
loginctl show-user hermes -p Linger
ssh hermes@erebus 'systemctl --user is-enabled hermes-gateway.service; systemctl --user is-active hermes-gateway.service'

# upstream sources (pinned rev, read from the store)
nix flake archive --json github:NousResearch/hermes-agent/v2026.9.24   # -> /nix/store/pd9xh4kl9…-source
nix flake show github:NousResearch/hermes-agent/v2026.9.24
# then: nix/nixosModules.nix, nix/moduleCommon.nix, nix/configMergeScript.nix,
#       nix/hermes-agent.nix, website/docs/getting-started/nix-setup.md

# managed-guard behaviour, on a scratch HERMES_HOME (no writes to live state)
T=$(mktemp -d); HERMES_HOME=$T HERMES_MANAGED=true hermes config set model.default zzz
rm -rf "$T"

# repo state (note: read from main, not the working copy)
git show main:modules/aspects/server/hermes/hermes-agent.nix
git merge-base --is-ancestor main HEAD
```

## Appendix B — external research consulted

Two delegated research tasks fed §3, §4, §7 and §9. Their findings are folded in above; the primary sources are listed here so the claims are checkable.

**Upstream packaging (corroborates §3):** `https://github.com/NousResearch/hermes-agent/{flake.nix,flake.lock,nix/packages.nix,nix/overlays.nix,nix/nixosModules.nix,nix/homeManagerModules.nix,nix/devShell.nix,nix/checks.nix,.github/workflows/nix.yml}`, `https://hermes-agent.nousresearch.com/docs/{getting-started/nix-setup,getting-started/installation,getting-started/updating}`, `https://hermes-agent.nousresearch.com/install.sh`. Nix-path development confirmed by merged PRs #20 (initial flake), #15953 (declarative plugin install), #48883 (hashless npm deps); open issues #5514 (nixos-24.11 input is EOL) and #69465 (flake input refresh). Non-Nix default path for contrast: `install.sh` clones to `$HERMES_HOME/hermes-agent`, builds a uv venv, publishes `~/.local/bin/hermes`, and runs `hermes gateway install --if-missing` — i.e. **the imperative gateway unit the repo's `hermes-unit-cleanup` now deletes**, which is the concrete history behind §2.3.

**Pattern catalogue (corroborates §4, §7, §9):** nixpkgs `nixos/modules/system/etc/etc.nix`, `nixos/doc/manual/{development/activation-script,administration/service-mgmt,administration/systemd-state}.section.md`, `nixos/modules/system/boot/systemd/user.nix`; wiki.nixos.org `Systemd/User_Services`, `Systemd/Hardening`, `Impermanence`; `NixOS/nixpkgs#{issues/108054, pull/186314}` (template-unit instantiation); `Mic92/sops-nix` README + `modules/sops/{default,templates/default}.nix` + `modules/home-manager/templates.nix`; freedesktop `systemd-run(1)` / `systemd.exec(5)`; upstream `NousResearch/hermes-agent#105365` and commit `ec30eefec9` (linger required for cron worker scope).

Two of the catalogue's findings changed the text above: the template-unit option in §7, and the distinction between the two cron-probe bugs in §9. The rest of the catalogue (impermanence, home-manager variants, `mkOutOfStoreSymlink` seeding) is **not** adopted here — home-manager is deliberately out of scope for this repo, and seed-once patterns are strictly weaker than the deep merge for the specific problem in §4.1.
