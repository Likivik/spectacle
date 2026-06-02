# Den Framework Debugging Skill

Debug den-based NixOS fleet configs: broken class wiring, missing aspects,
host-aspects projection, maid/HM class issues.

Repo: `github:denful/den` (rev `18e0d1c1`). Docs: `den.denful.dev`.

## Quick mental model

- **Entities** (`den.hosts.*`, `den.homes.*`): typed data records declaring
  what exists. Each has a `class`, `aspect`, and freeform attrs.
- **Aspects** (`den.aspects.<name>`): composable config units bundling modules
  for multiple classes (`nixos`, `maid`, `homeManager`, etc.) in one attrset.
  DAG via `includes`. Pipeline auto-creates one per entity.
- **Classes**: eval domains — `nixos`, `darwin`, `homeManager`, `maid`, `hjem`.
  Each has its own module system instance. User entities declare participation
  via `classes`.
- **Batteries** (`den.batteries.*`): reusable pre-built aspects. Some
  auto-activate (register classes), others require explicit `includes`.
- **Policies**: directed edges between entity kinds (host→user→hm-host→hm-user).
  Built-in policies wire the default pipeline.

## Debug workflows

### W1: maid/home-manager config not applying to user
```
User-level maid block has no effect
```
1. `nix eval --json '.#den.classes.maid'` — class registered?
   - No → check `inputs.nix-maid` in `modules/defaults/inputs.nix`
   - Yes → next step
2. `nix eval --json '.#den.schema.user.classes'` — `"maid"` in list?
   - No → check `den.schema.user.classes` in `modules/defaults/defaults.nix`
3. `nix eval --json '.#nixosConfigurations.<host>.config.users.users.<user>.maid.file'`
   — targeted query to see resolved maid files
4. Still empty? User entity may override `classes` without `mkDefault`.

### W2: host-level block silently no-op
```
den.aspects.serenity.maid = { file.home."test".text = "x"; };
# user likivik doesn't see it
```
Fix: `den.schema.user.includes` is missing `den.provides.host-aspects`.
Add to `modules/defaults/defaults.nix`:
```nix
den.schema.user.includes = [ den.provides.host-aspects ];
```

### W3: `nix eval --json` fails with "cannot convert a function to JSON"
```
error: cannot convert a function to JSON
```
Cause: class module contains lambdas (e.g., gsettings `testScript`).
Fix: query a sub-path instead of the whole class:
```bash
nix eval --json '.#nixosConfigurations.<host>.config.users.users.<u>.maid.file'
```

### W4: flake eval error after adding input
```
error: undefined variable 'nix-maid'
```
Fix: regenerate flake.nix + update lock:
```bash
nix run .#write-flake && nix flake update
```

### W5: `nix flake check` fails — "attribute '<host>' missing"
Check host exists:
```bash
nix eval --json '.#den.hosts.x86_64-linux.<host>'
```
Check host aspect: `den.aspects.<host>` exists and has a `nixos` key.
Check `host.class` is `"nixos"` (auto from `x86_64-linux`).

### W6: trace "Skipping unsatisfied args: user" in aspect include
Cause: include function requests `{ user, ... }` but no user in scope.
Fix: use optional arg or conditional:
```nix
({ host, user ? null }: if user != null then { ... } else { })
```

## Battery inventory (locked rev 18e0d1c1)

| Battery | Type | What it does | Required input |
|---------|------|-------------|----------------|
| `hostname` | opt-in | `networking.hostName` from `host.hostName` | none |
| `define-user` | opt-in | Creates `users.users.<name>` with `isNormalUser` + home dir | none |
| `primary-user` | opt-in | wheel+networkmanager groups, Darwin primaryUser | none |
| `user-shell "<sh>"` | opt-in | Sets login shell at OS+HM level | none |
| `host-aspects` | opt-in | Projects `user.classes` keys from host → each user | none |
| `tty-autologin "<u>"` | opt-in | getty TTY1 auto-login | none |
| `vm-autologin "<u>"` | opt-in | Same, scoped to `virtualisation.vmVariant` | none |
| `unfree [...]` | opt-in | `nixpkgs.config.allowUnfreePredicate` | none |
| `insecure [...]` | opt-in | `nixpkgs.config.permittedInsecurePackages` | none |
| `flake-scope` | opt-in | Exposes `lib`, `inputs`, `den` as pipeline args | none |
| `inputs'`, `self'` | opt-in | Flake-parts system-pre-selected inputs/self | flake-parts |
| `forward { ... }` | opt-in | Generic class forwarding primitive | none |
| `import-tree` | opt-in | Recursively imports `_<class>/` dirs | `inputs.import-tree` |
| `os-class` | **auto** | `os` class → both `nixos` and `darwin` | none |
| `os-user` | **auto** | `user` class → `users.users.<user>` at OS level | none |
| `home-manager` | **auto** | HM integration, merges `home-manager.users.<name>` | `inputs.home-manager` |
| `hjem` | **auto** | hjem integration | `inputs.hjem` |
| `maid` | **auto** | nix-maid integration, merges `users.users.<name>.maid` | `inputs.nix-maid` |
| `wsl` | **auto** (when `host.wsl.enable`) | NixOS-WSL integration | `inputs.nixos-wsl` |

Auto-activated batteries register classes in `den.classes.*` and fire when the
required input is present. Opt-in batteries require explicit `includes`.

## Symptom → first-place-to-look

| Symptom | First file | Common cause |
|---------|-----------|-------------|
| Host-level `maid` silent no-op | `modules/defaults/defaults.nix:16` | Missing `den.provides.host-aspects` in `den.schema.user.includes` |
| User-level maid not applying | `modules/hosts/host-user-definitions.nix` | User entity missing `classes = [ "maid" ]` |
| "maid requires inputs.nix-maid" | `modules/defaults/inputs.nix` | nix-maid input not declared |
| "cannot convert function to JSON" | The class module itself | `nix eval --json` on attr with lambdas — use sub-path |
| Flake eval error after input change | Run `nix run .#write-flake && nix flake update` | flake.nix stale |
| "attribute '<host>' missing" | `modules/hosts/host-user-definitions.nix` | Host not declared, or aspect missing |
| Infinite recursion during eval | Any module with circular `includes` | Aspect DAG cycle |
| User HM config not applying | `modules/users/<user>/<user>.nix` | User entity missing `classes = [ "homeManager" ]` |
| "maid is not a recognized class" | `modules/defaults/inputs.nix` | nix-maid input missing (battery can't register class) |
| `os` class not reaching NixOS | `modules/aspects/batteries/os-class.nix` | os-class battery not imported (should be auto) |
| Divergent entity comparison | Use `id_hash`: `a.id_hash != b.id_hash` | Nix `==` fragile across module boundaries |
| `nix run .#write-flake` fails | `modules/defaults/inputs.nix` | flake-file URL malformed or missing |

## nix eval queries cheat sheet

```bash
# Check a class is registered
nix eval --json '.#den.classes.maid'                          # → { description: "nix-maid user environment", ... }

# Check schema defaults for user classes
nix eval --json '.#den.schema.user.classes'                   # → ["homeManager","maid"]

# Check a host entity
nix eval --json '.#den.hosts.x86_64-linux.serenity'           # → { class: "nixos", ... }

# Check resolved maid files for a user (targeted, avoids function-serialize error)
nix eval --json '.#nixosConfigurations.serenity.config.users.users.likivik.maid.file'

# Check resolved HM config for a user
nix eval --json '.#nixosConfigurations.serenity.config.home-manager.users.likivik'

# Overall validity
nix flake check

# Regen flake.nix + lock (after input changes)
nix run .#write-flake && nix flake update
```

For deep aspect resolution, use REPL (not `nix eval` — can't serialize functions):
```nix
:lf .
den.lib.aspects.resolve "nixos" den.aspects.<name>
```

## Error patterns

**"cannot convert a function to JSON"** — `nix eval --json` on maid/home-manager
class serializing the whole module. GSettings `testScript` lambdas are a common
source. Fix: query sub-attr (`maid.file`) instead.

**Host-level maid block no effect** — `den.schema.user.includes` missing
`den.provides.host-aspects`. The `host-aspects` battery projects
`user.classes` keys (maid, homeManager) from host → user.

**"den: maid battery requires inputs.nix-maid"** — nix-maid input absent from
`flake-file.inputs`. Add to `modules/defaults/inputs.nix` then
`nix run .#write-flake && nix flake update`.

**flake.nix regenerated but undefined variable** — edited inputs.nix without
`write-flake + flake update`. Always run both; `flake update` alone only
touches `flake.lock`.

**"Skipping unsatisfied args: user"** in trace — include function requests
`{ user, ... }` but no user in scope. Use optional param
(`{ host, user ? null }`) + conditional body.

**`user.classes` default not inherited** — user entity overrides `classes`
without `mkDefault`, wiping the schema default. Use `lib.mkDefault`:
```nix
den.schema.user.classes = lib.mkDefault [ "homeManager" "maid" ];
```

## Cross-references

- Upstream den-debugging skill (den-INTERNAL, contributor-targeted):
  `denful/den/.claude/skills/den-debugging.md`
- Den debug guide: https://den.denful.dev/guides/debug/
- Den entities: https://den.denful.dev/explanation/entities/
- Den aspects: https://den.denful.dev/explanation/aspects/
- Den class modules: https://den.denful.dev/explanation/class-modules/
- Den policies: https://den.denful.dev/explanation/policies/
- Den batteries reference: https://den.denful.dev/reference/batteries/
- nix-maid source: https://github.com/viperML/nix-maid
- nix-maid API docs: https://viperml.github.io/nix-maid/
