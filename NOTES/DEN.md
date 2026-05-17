# Den Framework — How it works

## What is Den?

Den is an **aspect-oriented framework** for NixOS/darwin/home-manager configurations. Instead of organizing configs by host (imperative: "this host has these settings"), you organize by **aspect** (declarative: "this set of functionality needs these configs"). Hosts are just the union of relevant aspects.

## Core concepts

### 1. Aspects

An aspect is a self-contained unit of configuration, potentially spanning multiple **classes** (NixOS, home-manager, etc.):

```nix
den.aspects.my-feature = {
  # Dependencies: other aspects this one needs
  includes = [ den.aspects.core._ ];

  # System-level config (nixos or darwin class)
  nixos = { pkgs, ... }: {
    environment.systemPackages = with pkgs; [ my-package ];
  };

  # User-level config (homeManager class)
  homeManager = { pkgs, ... }: {
    home.packages = with pkgs; [ my-package ];
  };
};
```

Classes are **evaluation domains** — each class maps to a module system invocation (nixos evalModules, home-manager homeManagerConfiguration, etc.).

### 2. The `_` wildcard

`den.aspects.core._` is **auto-synthesized** — you don't create `_.nix` files. Den's aspect type system (`mergeWithAspectMeta` in `types.nix`) generates it automatically. It collects all child aspects of `core` (bootloader, determinateNix, defaultLocale, nix) into a single includes list.

So `den.aspects.core._` === `[bootloader, determinateNix, defaultLocale, nix]` as includes.

### 3. Entities

Entities are the "subjects" of configuration — hosts, users, homes, flake, etc. Each entity kind is registered in `den.schema`.

**Host entity** (`nix/lib/entities/host.nix`):
- Has a `class` (nixos/darwin), `system`, `name`
- Has `users` — an attrset of user entities
- Has `aspect` — auto-resolved from `den.aspects.<name>` (the host-specific aspect)
- Has `instantiate` — default: `nixpkgs.lib.nixosSystem`
- Has `intoAttr` — e.g., `["nixosConfigurations", "serenity"]`

**User entity** (nested under host):
- Has `classes` — list of home management classes (`["homeManager"]`, `["user"]`, etc.)
- Has `aspect` — auto-resolved from `den.aspects.<name>`
- Has `host` — back-reference to parent host

### 4. Resolution pipeline

When you write `den.lib.aspects.resolve "nixos" (den.lib.resolveEntity "host" ctx)`:

1. **Entity resolution** (`resolveEntity`): creates the root aspect from schema entry, injecting `den.default`, schema includes, self-provide wrapper

2. **Effects pipeline** (`fx/pipeline.nix`): an algebraic effects system with 37 handlers:
   - Walks the aspect DAG via `includes`, deduplicating by identity and context
   - Classifies freeform keys into: class keys (nixos/homeManager), nested aspects, pipe keys
   - Resolves parametric includes (`{ host, ... }`) against available context
   - Dispatches policies (registered policies fire based on context)
   - Handles fan-out: policy effects like `resolve { inherit user; }` create new scopes
   - Collects class modules: each aspect's `nixos` block → emitted as `nixos` class module in the current scope

3. **Post-pipeline assembly** (`fx/resolve.nix`):
   - **Phase 1**: Wrap collected class modules per scope, apply context args
   - **Phase 2**: Apply `provide` effects — inject modules across classes
   - **Phase 3**: Apply `route` effects — move content between scope/class partitions
   - **Phase 4**: Apply `instantiate` effects — per-host subtree assembly → `nixosConfigurations.<name>`

### 5. Scopes

Scopes are the pipeline's way of partitioning evaluation by context. A scope is identified by `mkScopeId ctx` — a string like `"host=serenity,user=likivik"`.

Pipeline state is partitioned by scope:
- `scopedClassImports` — modules emitted in each scope
- `scopedAspectPolicies` — policies registered in each scope
- `scopedRoutes` — routing directives per scope

Scope tree: `flake → flake-system → host → user`

The `host-to-users` policy (core.nix) creates user scopes as children of the host scope. Each user scope has `user = { name = "likivik"; userName = "likivik"; classes = ["homeManager"]; aspect = den.aspects.likivik; ... }` in context, enabling user-specific class modules.

### 6. Policies

Policies are functions `ctx → [effects]` that run at specific points in the pipeline:

```nix
den.policies.host-to-users =
  { host, ... }:
  map (user: resolve.shared { inherit user; }) (attrValues host.users);
```

This is included in `den.schema.host.includes`, so when a host entity is resolved, the policy fires: for each user, it creates a new shared scope with `user` in context.

Policy effects:
- `resolve { bindings }` — fan out to new scope
- `include aspect` — include an aspect
- `route { fromClass; intoClass; path; }` — route modules between classes
- `instantiate entity` — request entity instantiation
- `provide { class; module }` — inject module into a class
- `when predicate policy` — gate policy by condition
- `for entity policy` — gate policy to specific entities

### 7. Batteries (den.provides)

`den.provides.*` is an alias for `den.batteries.*` (via `lib.mkAliasOptionModule` in `batteries.nix`). These are pre-built aspects for common tasks.

**`define-user`**: Creates OS user accounts + home directories. Included via `den.default.includes`.

**`hostname`**: Auto-sets `networking.hostName` from the host entity's `hostName` option. Included via `den.default.includes`. (Your question: yes, it's automatic via the schema, but `den.provides.hostname` provides the actual config module that reads `host.hostName` and sets the NixOS option.)

**`mutual-provider`**: Sets up `${user}.provides.${host}` and `${host}.provides.${user}` for cross-referencing. Needed when aspects need to reference both host and user contexts. The exact mechanism: it creates parametric wrappers so `user.provides.host` resolves to the host aspect and vice versa.

**`primary-user`**: Designates a user as primary (used for autologin, etc.).

**`user-shell "bash"`**: Sets the user's shell.

### 8. Class system

`den.classes` is the registry of evaluation domains. Built-in:
- `nixos` — NixOS system evaluation
- `darwin` — nix-darwin system evaluation
- `packages`, `apps`, `checks`, `devShells`, `legacyPackages` — flake output classes
- `homeManager` — home-manager evaluation (registered by `home-manager.nix` battery)

Each class has a `description` and optional `forwardTo`.

**How `homeManager` class wiring works:**
1. `home-manager.nix` battery registers `homeManager` in `den.classes`
2. Adds `host-to-hm-users` policy to `den.schema.host.includes`
3. During host resolution, the policy checks each user's `classes`:
   - If `"homeManager"` ∈ `user.classes`, creates a user scope + includes a `forward` aspect
   - The forward routes `homeManager` class modules into `nixos.home-manager.users.<userName>`
4. `user.classes` defaults to `["user"]` on the user entity
5. `den.schema.user.classes = lib.mkDefault ["homeManager"]` tries to override to `["homeManager"]`

### 9. Scope widening / context args

Aspects can request context args:
```nix
den.aspects.my-aspect = { host, user, ... }: {
  nixos.networking.hostName = host.hostName;
};
```

The fx pipeline's `compileParametricHandler` extracts arg names from the function, checks if they're available in scope context, and if not, defers. The `bindHandler` resolves them against scope handlers.

Available context args depend on scope level:
- `flake` scope: none
- `flake-system` scope: `{ system }`
- `host` scope: `{ host, system }`
- `user` scope: `{ host, user, system }`

## How your config maps to Den concepts

### Hosts → Entities

```
hosts/host-user-definitions.nix
  den.hosts.x86_64-linux.serenity → Host entity (nixos/x86_64-linux)
    users.likivik → User entity
  den.hosts.x86_64-linux.spectacle → Host entity (nixos/x86_64-linux)
    users.watcher → User entity
```

### Nix/self modules → Aspects

```
aspects/core/*.nix               → den.aspects.core.{bootloader, determinateNix, defaultLocale, nix}
aspects/desktop/managers/gnome   → den.aspects.desktop.desktopManagers.gnome
aspects/desktop/managers/kde     → den.aspects.desktop.desktopManagers.kde
aspects/desktop/common-core/*    → den.aspects.desktop.common-core.{...}
aspects/dev/*                    → den.aspects.dev.{...}
hosts/serenity/serenity.nix      → den.aspects.serenity (host-specific aspect)
hosts/spectacle/spectacle.nix    → den.aspects.spectacle (host-specific aspect)
users/likivik.nix                → den.aspects.likivik (user-specific aspect)
```

### Resolution flow for `nix run .#serenity`

```
1. flake output → resolve "flake" entity
2. flake-to-systems policy → resolve "flake-system" { system = "x86_64-linux"; }
3. system-to-os-outputs policy → resolve "host" { host = den.hosts.x86_64-linux.serenity; }
4. resolveEntity "host" ctx → creates root aspect with:
   - Self-provide: den.aspects.serenity
   - Schema includes: den.default (hostname, define-user, mutual-provider)
   - Schema includes: host-to-users policy
5. Pipeline walks aspect DAG:
   - den.aspects.serenity.includes = den.aspects.core._ + common-core._ + kde + firefox + dev-fonts
   - Each included aspect also resolved → DAG traversal
6. host-to-users policy fires → resolve.shared { user = den.hosts.x86_64-linux.serenity.users.likivik; }
7. User scope created → include den.aspects.likivik
8. den.aspects.likivik includes primary-user + user-shell "bash" + firefox
9. All nixos blocks emitted as class modules in respective scopes
10. Post-pipeline: wrap → provides → routes → instantiate
11. Result: { imports = [all nixos modules from all scopes] } → nixpkgs.lib.nixosSystem
```

### Namespace aspect tree (from topAspectDefinitions.nix)

```
den.aspects
├── core           = {}  (namespace: allows core.bootloader, core.locale, etc.)
├── desktop        = {}  (namespace)
│   ├── apps       = {}
│   ├── common-core = {}
│   ├── common-extra = {}
│   └── desktopManagers = {}
└── dev            = {}  (namespace)
```

These empty `= {}` declarations register namespace prefixes. Without them, `den.aspects.desktop.desktopManagers.gnome` would fail because intermediate paths would be `_module` deferred.

## Open issues

### `den.schema.user.classes = lib.mkDefault [ "homeManager" ]` — doesn't work?

This attempts to change default user classes from `["user"]` to `["homeManager"]`. The mechanism:
- `den.schema.user.classes` sets `classes` on the `user` schema entry
- Schema entries are imported into entity submodules
- Should override user entity's `default = ["user"]`

But there may be a timing issue — the schema entry modules are processed through `schemaEntryType.merge`, and `classes` is a freeform key on the deferred module. The merge with the user entity's declared option depends on evaluation order.

The real question: **do you need this?** If you only have 2 users (likivik, watcher) and both should have HM, just set it per user aspect or explicitly. The HM battery's `host-to-hm-users` policy checks `user.classes` — if no user has `"homeManager"` in classes, HM integration won't fire for that host.

### `den.schema.hm-host` — commented out

This is for per-host HM overrides (e.g., `home-manager.useGlobalPkgs`). The HM battery in `home-manager.nix` checks `config.den.schema.hm-host.includes` and includes them under `policy.when hasHmUsers`. Uncommenting it with proper config should work.

Currently HM packages don't get included because `home-manager.nix` battery may not be properly included. Check: is the `home-manager` battery included anywhere in your schema? Looking at `defaults.nix`, you have `den.provides.hostname`, `define-user`, `mutual-provider` but NOT the `home-manager` battery.

**That's likely the issue!** The `home-manager` battery (which registers the `homeManager` class and the forwarding machinery) needs to be included. Without it:
1. `homeManager` class isn't registered in `den.classes`
2. No `host-to-hm-users` policy to route HM content into user scopes
3. `homeManager` blocks on aspects are collected but never reach a `homeManager` evalModules

Fix: add to `den.default.includes`:
```nix
den.provides.home-manager
```

This is separate from `den.schema.user.classes`. The battery registers the class + sets up forwarding. The user classes just tell the battery which users are HM-managed.

### `_` wildcards on serenity

`serenity.nix` uses `den.aspects.core._` and `den.aspects.desktop.common-core._` — these are the synthetic wildcards. They work because Den's `mergeWithAspectMeta` auto-generates `_` from all child keys. Since `topAspectDefinitions.nix` declares empty namespaces, these resolve correctly at evaluation time.

## Cheat sheet

| You write | Den does |
|-----------|----------|
| `den.hosts.x86_64-linux.serenity = { ... }` | Creates host entity, auto-resolves `den.aspects.serenity` |
| `den.aspects.serenity = { nixos = ...; includes = [...]; }` | Host aspect: collected during host resolution |
| `den.aspects.my-feature.nixos = { ... }` | Registers class module — emitted during pipeline |
| `den.default.includes = [...]` | Injected into all entity resolutions |
| `den.schema.host.includes = [ myPolicy ]` | Policy fires for every host |
| `den.provides.define-user` | Creates OS users from entity declarations |
| `includes = [ den.aspects.core._ ]` | Includes all child aspects of `core` namespace |
