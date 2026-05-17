---
name: den-framework
description: Deep reference for the Den Nix framework (github:denful/den) — aspects, effects pipeline, policies, entity resolution, class assembly. Verified against pinned rev aee486b.
---

## Den pinned version
Pinned in flake.lock: `aee486b` (denful/den). Source clones to `/tmp/den-pinned` for reference.

> **Keep updated**: when `nix flake update den` bumps the lock, re-clone the new rev and re-read key files to refresh this skill. Run:
> ```bash
> rev=$(nix eval '.#den.sourceInfo.rev' 2>/dev/null | jq -r '.rev')
> rm -rf /tmp/den-pinned
> git clone --depth 1 https://github.com/denful/den /tmp/den-pinned
> cd /tmp/den-pinned && git fetch --depth 1 origin "$rev" && git checkout "$rev"
> ```

## Architecture

Den is a **library** for composing Nix configurations via **aspect-oriented programming** and a **framework** for NixOS/Darwin/home-manager. Built on algebraic effects via `nix-effects`.

```
nix/default.nix       ← entry point: exposes lib, flakeModules, templates
nix/lib/              ← core lib
nix/lib/aspects/      ← aspect types, pipeline, resolution
nix/lib/aspects/fx/   ← effects pipeline + handlers (37 handlers)
nix/lib/entities/     ← host/home entity schemas
nix/lib/aspects/fx/policy/  ← schema resolve processing
nix/lib/policy-*.nix  ← policy effect constructors + introspection
modules/              ← NixOS module tree (auto-imported by flakeModule)
modules/options.nix   ← `den.*` option declarations
modules/aspects/      ← built-in aspects (batteries)
modules/aspects/batteries.nix ← wires den.provides → den.batteries alias
modules/policies/     ← built-in policies (core, flake, flake-parts)
modules/context/      ← flake-level modules (hasAspect, perHost/perUser, flake-schema)
```

## Key: `_` wildcard convention

`den.aspects.<namespace>._` is **auto-synthesized** — no `_.nix` file needed.

From `nix/lib/aspects/types.nix` lines 113-132:
- **Each** aspect namespace entry gets a synthetic `_` attribute via `mergeWithAspectMeta`
- `_` collects all child keys (non-structural, non-class, non-pipe) into a single aspect whose `includes` contains all children
- Also: `_` is an alias for `provides` via `lib.mkAliasOptionModule [ "_" ] [ "provides" ]` in `aspectSubmodule` (line 580)
- So `den.aspects.core._` = all children of `den.aspects.core` = `bootloader + determinate + locale + nix`

This enables:
```nix
den.aspects.serenity.includes = [ den.aspects.core._ ]
# equivalent to:
den.aspects.serenity.includes = [
  den.aspects.core.bootloader
  den.aspects.core.determinateNix
  den.aspects.core.defaultLocale
  den.aspects.core.nix
]
```

## `den.provides.*` alias

`den.provides` is an alias for `den.batteries` (via `modules/aspects/batteries.nix` line 6):
```nix
(lib.mkAliasOptionModule [ "provides" ] [ "batteries" ])
```
So `den.provides.define-user` === `den.batteries.define-user`.

## Aspect system

Defined in `nix/lib/aspects/types.nix`.

### Aspect structural options
| Option | Type | Description |
|--------|------|-------------|
| `name` | `str` | auto from location |
| `description` | `str` | human-readable |
| `meta` | submodule | handleWith, provider (path tracking), collisionPolicy |
| `includes` | `listOf providerType` | DAG dependencies |
| `excludes` | `listOf unspecified` | aspects/policies to exclude |
| `provides` | submodule with freeform providerType | sub-aspects for other aspects to include |
| `policies` | lazyAttrsOf policyType | named policy functions (activated by placing in includes) |
| `classes` | lazyAttrsOf raw | class schemas declared by this aspect |

### Freeform key dispatch

Aspect freeform keys are classified by `nix/lib/aspects/fx/key-classification.nix`:
1. **Structural keys** — `name`, `meta`, `includes`, `excludes`, `provides`, `policies`, `classes`, `__fn`, `__args`, `__functor`, `_module`, `_`, etc.
2. **Class keys** — keys matching a registered class in `den.classes` (e.g., `nixos`, `homeManager`, `darwin`, `packages`, `apps`, `checks`)
3. **Pipe keys** — keys matching `den.quirks`
4. **Nested aspect keys** — attrsets with recognized sub-keys (recursive check up to 3 levels)
5. **Provided/forwarded keys** — keys forwarded from `provides.<name>`, tagged with `__providesForwarded`

### Aspect type coercion

Functions/attrsets can be coerced to aspects:
- **NixOS submodule fns** (`{ lib, config, options, ... }`) → treated as NixOS submodule directly
- **Bare parametric fns** (`{ host, user, ... }`) → coerced to `{ includes = [fn] }`
- **Functor attrsets** (`{ __functor = self: ... }`) → wrapper preserved
- **Plain attrsets** → merged through aspect submodule

## Effects pipeline (fx)

The core pipeline lives in `nix/lib/aspects/fx/pipeline.nix`. It's an **algebraic effects** system using nix-effects.

### Pipeline initialization
```nix
fxResolve { class; self; ctx; }
```
- `class` — target class name to extract (`"nixos"`, `"homeManager"`, `"flake"`, etc.)
- `self` — the root aspect (resolved entity)
- `ctx` — scope context (host, user, etc.)

### Boot sequence
1. `fx.send "resolve" { aspect = self; identity; ctx; gated = true; }` — kick off resolution
2. `fx.handle { handlers = composeHandlers rootHandlers extraHandlers; state = defaultState; }` — install handlers
3. Trampoline: effects dispatched to handlers, each returns `{ resume, state }`

### Handler order (37 handlers, install order matters)
From `pipeline.nix` defaultHandlers (lines 34-81):
1. `constantHandler` — injects static context values
2. `classCollectorHandler` — collects per-class output
3. `constraintRegistryHandler` — tracks constraint registrations
4. `chainHandler` — manages include chain dedup
5. `includeHandler` — processes `includes` list
6. `checkDedupHandler` — dedup by identity key
7. `ctxSeenHandler` — dedup by (ctx, identity)
8. `pathSetHandler` — builds resolved path set (for hasAspect)
9. `collectPathsHandler` — records resolved paths
10. `registerAspectPolicyHandler` — registers policy effects
11. `registerRouteHandler` — registers routing directives
12. `registerInstantiateHandler` — registers entity instantiation
13. `provideHandler` — processes `provide` effects
14. `registerPipeEffectHandler` — registers pipe transformations
15. `resolveEntityHandler` — resolves sub-entities (calls `den.lib.resolveEntity`)
16. `pushScopeHandler` — creates new scope (fan-out)
17. `restoreScopeHandler` — restores parent scope
18. `propagateRoutesHandler` — forwards routes to parent scope
19. `recordFiredHandler` — tracks fired policies
20. `widenContextHandler` — enriches scope context
21. `resolveSchemaEntityHandler` — resolves schema-tracked entities
22. `gateHandler` — processes meta.guard (conditional aspects)
23. `resolveHandler` — dispatches `resolve` effects
24. `compileHandler` — dispatches to compile sub-handlers
25. `compileForwardHandler` — handles `provides` forwarding
26. `compileConditionalHandler` — handles guarded aspects
27. `deferConditionalHandler` — defers unresolved conditionals
28. `drainConditionalsHandler` — re-processes deferred conditionals
29. `compileParametricHandler` — resolves parametric (`{host, ...}`) includes
30. `compileStaticHandler` — resolves static includes, classifies, emits classes
31. `bindHandler` — resolves binding args via `fx.bind.fn`
32. `deferHandler` — defers includes with unsatisfied args
33. `drainHandler` — re-processes deferred includes
34. `scopeWidenHandler` — widens scope context
35. `classifyHandler` — classifies freeform keys
36. `emitClassesHandler` — emits classified modules into state
37. `resolveChildrenHandler` — resolves nested aspects
38. `dispatchPoliciesHandler` — dispatches policy effects
39. `emitPolicyEffectsHandler` — processes policy effect results

### Scope identity
`mkScopeId` produces an injective string from context: `"host=serenity,user=likivik"`. Used as scope partition key throughout the pipeline state.

### Pipeline state (defaultState)
Flat state: `seen`, `pathSet` (dedup across scopes)
Scoped state (partitioned by scopeId):
- `scopedClassImports` — collected class modules
- `scopedAspectPolicies` — per-scope policy registrations
- `scopedDeferredIncludes` — includes deferred for later resolution
- `scopedDeferredConditionals` — guarded aspects awaiting resolution
- `scopedIncludesChain` — include chain for cycle detection
- `scopedConstraintRegistry` / `scopedConstraintFilters` — constraint tracking
- `scopedRoutes` — routing directives
- `scopedInstantiates` — entity instantiation requests
- `scopedProvides` — provide effects
- `scopedPipeEffects` — pipe transformations
- `scopedEmittedLocs` — emitted module locations

## Post-pipeline assembly (resolve.nix)

From `nix/lib/aspects/fx/resolve.nix` — 4 phases:

### Phase 1: wrapPerScope
`wrapCollectedClasses` applies `wrapClassModule` to each raw class entry per scope. Deduplicates by module key across scopes (first wins). Each module gets wrapped with context args partially applied.

### Phase 2: applyProvides
Deduplicates `provide` effects by `policyName/class/path`. Wraps and injects into target classes.

### Phase 3: applyRoutes
Processes `route` effects — moves class content from one scope partition to another. Uses `route/` module with `buildForwardAspect`.

### Phase 4: applyInstantiates
For each entity with `intoAttr` (e.g., hosts), re-runs assembly per host subtree (host scope + all descendants, excluding siblings). Produces `flake.nixosConfigurations.<name>` etc.

Includes **post-assembly drain** of deferred includes (lines 520-598): pipe-arg deferred and enrichment-deferred includes are resolved after pipe assembly.

### wrapClassModule
From `class-module.nix`:
1. Extracts den context args from function signature (`{ host, user, ... }`)
2. Partially applies known args
3. Handles remaining args via wrapper function at evalModules time
4. Resolves collision policies (aspect meta → entity → global)
5. Handles pipe config thunks (`__configThunk`) — resolves within evalModules fixpoint
6. Tags with identity key for NixOS module dedup

## Entity system

Entity kinds are registered in `den.schema`. Built-in kinds:
- `flake`, `flake-system`, `flake-parts`, `default` (from `modules/context/flake-schema.nix`)
- `host`, `user`, `home`, `conf`, `fleet` (from `modules/options.nix` lines 251-257)

### Host entity (`nix/lib/entities/host.nix`)
- `name`, `hostName`, `system`, `class` (auto: nixos/darwin)
- `aspect` — auto-resolved from `den.aspects.<name>`
- `users` — `attrsOf userType`
- `instantiate` — defaults to `nixpkgs.lib.nixosSystem` / `darwin.lib.darwinSystem`
- `intoAttr` — flake output path (e.g., `["nixosConfigurations", name]`)
- `mainModule` — `den.lib.aspects.resolve config.class config.resolved`

### User entity (nested under host)
- `name`, `userName`
- `classes` — `listOf str` (default `[ "user" ]`), determines home management class
- `aspect` — auto-resolved from `den.aspects.<name>`
- `host` — back-reference to parent host

### Home entity (`nix/lib/entities/home.nix`)
- Standalone home-manager configurations (supports `user@host` naming)
- `class` defaults to `"homeManager"`
- Links back to parent `host` and `user` entities

### Schema entry type
From `modules/options.nix` `schemaEntryType`:
- Processes `includes`, `excludes` → stripped before module merge, appended to result
- `resolvedCtx` — adds `id_hash` (identity hash from primitive options), `resolved` (computed aspect), `collisionPolicy`
- `isEntity` — set when entity has content beyond just includes/excludes
- Entity schema entries get a `__functor` that returns `{ imports = [merged resolvedCtx] }`
- Used via `imports = [ den.schema.<kind> ]` in entity type definitions

## Entity identity hashing (`id_hash`)
From `modules/options.nix` lines 87-119:
- Reflects on all primitive-typed options (str/int/bool) to produce an `sha256` fingerprint
- Includes schema kind prefix to prevent cross-kind collisions
- Used for entity comparison (`a.id_hash != b.id_hash` instead of `a != b`)
- Avoids Nix deep structural recursion divergence

## Policy system

### Policy types (`policy-type.nix`)
```nix
{ __isPolicy = true; name = "..."; fn = ctx → [effects]; }
```

### Policy effects (`policy-effects.nix`)

| Effect | Description |
|--------|-------------|
| `resolve { bindings }` | Fan-out to new scope with bindings merged |
| `resolve.shared { bindings }` | Shared (non-isolated) fan-out |
| `resolve.to "kind" { bindings }` | Fan-out to explicit target kind (schema-driven) |
| `include aspect` | Include an aspect in current scope |
| `exclude aspect` | Gate/exclude an aspect |
| `route { fromClass; intoClass; path; }` | Route class content between scopes |
| `instantiate spec` | Request post-pipeline entity instantiation |
| `provide { class; module; path?; }` | Inject module into target class |
| `pipe.from name stages` | Attach pipe transformation stages |
| `for entity policy` | Gate policy to specific entities (by `id_hash`) |
| `when predicate policy` | Gate policy to contexts matching predicate |
| `pipelineOnly value` | Tag value with class-wins collision policy |
| `mkPolicy name fn` | Create a named policy record |

### Built-in policies

**core.nix** — `host-to-users`: fans out host scope to each user scope. Schema-included on `den.schema.host`.

**flake.nix** — Flake output wiring:
- `flake-to-systems`: fans out per system
- `system-to-os-outputs`: resolves hosts, instantiates
- `system-to-hm-outputs`: resolves homes, instantiates
- `packages-to-flake` / `apps-to-flake` / etc: route outputs to flake
- Registers `packages`, `apps`, `checks`, `devShells`, `legacyPackages` as classes

### Policy dispatch flow (policy/schema.nix)
1. Schema resolve effects are decomposed via `decomposeSchemaEffect`:
   - Resolve target kind, bindings, scoped context, entity class
2. `processSingleResolve` handles each resolve effect:
   - Checks ctx-seen dedup (by entity kind + scope key)
   - First visit → `resolve-schema-entity` effect
   - Subsequent → supplemental resolution of new aspect values
3. `lateDispatchPass` re-dispatches policies at sibling scopes (for late-registered policies from earlier siblings)
4. `processSchemaResolves` wraps it all, enabling late dispatch for fan-out scenarios

## Class system

### Class registration
- Built-in: `nixos`, `darwin` (from `options.nix`)
- Flake outputs: `packages`, `apps`, `checks`, `devShells`, `legacyPackages` (from `policies/flake.nix`)
- HM/other: `homeManager` (from `batteries/home-manager.nix` line 52), `hjem`, etc.
- Custom: via `den.aspects.<name>.classes.<className>` collected by `aspect-schema.nix`
- Runtime: `den.classes` is a `lazyAttrsOf classSchemaType`

### Class assignment to users
From `host.nix` user entity:
```nix
options.classes = lib.mkOption {
  type = lib.types.listOf lib.types.str;
  default = [ "user" ];
};
```

Classes determine home management integration:
- `home-manager.nix` battery checks `lib.elem "homeManager" user.classes`
- `mkIntoClassUsers` (home-env.nix) filters users by class
- `mkDetectHost` checks if any host user has the class

### How homeManager class works (home-manager.nix battery)
1. Declares `den.classes.homeManager`
2. Adds to `den.schema.host.includes`:
   - A policy (`host-to-hm-users`) that fires during host resolution
   - For each user with `"homeManager"` in classes: resolves user scope + includes `userForward` aspect
   - `userForward` routes `homeManager` class content into host class via `den.batteries.forward`
3. Adds to `den.schema.user.includes`:
   - A policy (`hm-user-detect`) that fires during user resolution
   - If user has `"homeManager"` class: includes `userForward` aspect + host module
4. Adds `den.schema.host.imports` with `hm-host-conf` — host options for HM (enable, module)

## Batteries (built-in providers)

Defined in `modules/aspects/batteries/`. Referenced as `den.provides.*` or `den.batteries.*`.

| Battery | Path | What it does |
|---------|------|-------------|
| `define-user` | `define-user.nix` | OS user creation + home dir setup for NixOS/Darwin and standalone HM |
| `hostname` | `hostname.nix` | Auto-sets hostname from entity name |
| `mutual-provider` | (in forward.nix?) | Cross-references user↔host provides |
| `primary-user` | `primary-user.nix` | Marks user as primary |
| `user-shell "<shell>"` | `user-shell.nix` | Sets user shell |
| `tty-autologin "<user>"` | `tty-autologin.nix` | Enables TTY autologin |
| `vm-autologin "<user>"` | `vm-autologin.nix` | Enables VM autologin |
| `forward` | `forward.nix` | Generic class forwarding (used by `home-manager.nix` to route HM→nixos) |
| `home-manager` | `home-manager.nix` | Home Manager class integration |
| `hjem` | `hjem.nix` | hjem class integration |
| `os-class` | `os-class.nix` | OS class utilities |
| `os-user` | `os-user.nix` | OS user class |
| `host-aspects` | `host-aspects.nix` | Host aspect utilities |
| `flake-scope` | `flake-scope.nix` | Flake scope integration |
| `import-tree` | `import-tree.nix` | Import tree support |
| `maid` | `maid.nix` | nix-maid integration |
| `insecure/*` | `insecure/` | Insecure package handling |
| `unfree/*` | `unfree/` | Unfree package handling |
| `wsl` | `wsl.nix` | WSL integration |
| `flake-parts/*` | `flake-parts/` | flake-parts integration |

## Key lib functions

From `nix/lib/aspects/default.nix`:

| Function | Description |
|----------|-------------|
| `aspects.resolve class aspect` | Resolve aspect tree → `{ imports = [...] }` |
| `aspects.resolveImports class aspect` | Like resolve but skip instantiation |
| `aspects.resolveWithState class aspect` | Full pipeline result including state |
| `aspects.normalizeRoot aspect` | Coerce raw fns/attrsets to standard aspect shape |
| `aspects.hasAspectIn ref aspect` | Check if ref is in aspect tree |
| `aspects.mkEntityHasAspect entity` | Build `hasAspect` for entity (forClass/forAnyClass) |
| `aspects.collectPathSet aspect` | Get resolved path set from tree |

From `nix/lib/default.nix`:
- `resolveEntity kind ctx` — create entity from schema + context
- `policy.*` — policy effect constructors (`resolve`, `include`, `route`, etc.)
- `policyInspect.*` — policy introspection utilities
- `synthesizePolicies.*` — policy arg checking
- `canTake.*` — function arg shape predicates
- `take.*` — function arg extraction
- `fx.*` — nix-effects library (effects runtime)
- `schemaUtil.*` — entity kind predicates (`schemaEntityKinds`, `schemaArgKinds`)
- `nsTypes.*` — namespace types for `den.ful`
- `diag.*` — resolution diagnostics/diagrams
- `forward.*` — class forwarding utilities
- `home-env.*` — home environment battery builder

## Den defaults wiring

`den.default` is injected as a schema include for `host`, `user`, and `home` entity kinds via `resolveEntity` (resolve-entity.nix line 48-52). It provides:
- `includes` — shared defaults across all entities
- Global config like `stateVersion`, `networking.firewall.enable`

## User API surface

```nix
# Host declaration
den.hosts.x86_64-linux.serenity = {
  description = "Desktop";
  users.likivik = { };
};

# Aspect with nixos + homeManager blocks
den.aspects.my-service = {
  nixos = { pkgs, ... }: { ... };
  homeManager = { pkgs, ... }: { ... };
};

# Aspect with context args (parametric)
den.aspects.my-aspect = { host, ... }: {
  nixos.networking.hostName = host.hostName;
};

# DAG via includes
den.aspects.my-aspect.includes = [
  den.aspects.core._
  (den.provides.user-shell "bash")
];

# Defaults (injected for all host/user entities)
den.default.includes = [
  den.provides.hostname
  den.provides.define-user
  den.provides.mutual-provider
];

# Schema extensions
den.schema.my-kind = {
  includes = [ myPolicies ];
  isEntity = true;
};

# Custom classes
den.classes.my-class.description = "Custom class domain";

# User class defaults (sets default classes for all users)
den.schema.user.classes = lib.mkDefault [ "homeManager" ];
```

## Known issues / caveats

1. `den.schema.user.classes` set via `lib.mkDefault` should override the user entity's `default = [ "user" ]`, but the interaction between schema entry freeform keys and entity option defaults can be fragile
2. `hm-host` schema (`den.schema.hm-host`) is used by `home-manager.nix` battery for per-host HM overrides via `hmHostSchemaIncludes`
3. Class modules wrap context args (host, user, etc.) via partial application; remaining args become wrapper functions evaluated at module system time
4. Pipe system (`den.quirks`) enables structured data flow between entities (cross-host config references, pipe transforms)
