# Clan.lol Integration with Den Framework

> **Status:** Research completed 2026-07-03
> **Finding:** No public examples of Den + Clan integration found. This is unexplored territory.

---

## Critical Understanding First

Before the three concepts, you need to understand one thing:

**Both Den and Clan want to define your machines.** They both call `nixosSystem` internally and produce `nixosConfigurations`. You can use BOTH frameworks in the same flake, but each host can only be defined by ONE of them.

You can think of it like food:
- **Den** is a recipe book (aspects + hosts → complete configs)
- **Clan** is a meal delivery service (configs → deployed machines with secrets)

You can use Den's recipes and Clan's delivery — but only one writes the shopping list (nixosConfigurations) for each host.

---

## The Three Key Concepts (Corrected)

### 1. Shares `nixosConfigurations` namespace (mergeable via `manySubmodule`)

Think of `nixosConfigurations` as a **shared address book** that stores all your machine configs.

- Den writes: `nixosConfigurations.traversal`, `nixosConfigurations.spectacle`, etc.
- Clan writes: `nixosConfigurations.server1`, `nixosConfigurations.server2`, etc.

The "mergeable" part means **they can use the same address book as long as they write on different pages** (different hostnames). Both Den and Clan can contribute entries to `nixosConfigurations` without conflict, as long as they don't both try to write the same hostname.

**What the original file got wrong:** It implied this meant both could define the SAME host. They can't. Two chefs can't both cook the same dish in the same kitchen.

### 2. Can coexist with Den's `den.hosts` without collision

This is true — but only if you define **different** hosts in each.

- `den.hosts.x86_64-linux.traversal` → `nixosConfigurations.traversal` ✅
- `clan.machines.server1` → `nixosConfigurations.server1` ✅
- `den.hosts.x86_64-linux.server1` + `clan.machines.server1` → ❌ COLLISION

**What the original file got wrong:** It made this sound like you could define a host in Den and then use Clan to deploy it. You can't — `clan machines update server1` requires `server1` to exist in `clan.machines`.

### 3. Import clan as flakeModule, keep Den owning hosts

**This is the most misleading claim in the original file.** You cannot keep a host only in `den.hosts` and then use `clan machines update` to deploy it. `clan machines update` reads machines from `clan.machines` — if a machine isn't there, Clan doesn't know it exists.

**You CAN** use `nixos-rebuild` directly (instead of `clan machines update`) on Den-defined hosts. Clan's own docs confirm `nixos-rebuild` works alongside Clan. But then you only get Clan's vars/secrets system, not its deployment CLI.

**The car analogy was also misleading.** A better one:

- **Den** = The architect (designs the house, makes blueprints)
- **Clan** = The contractor (builds the house, manages keys, handles delivery)

The architect and contractor need to agree on which house they're building. They can build different houses, or one designs and the other builds — but they can't both design the same house independently.

---

## The Bridge: Den → Clan without Migrating Hosts

**Core insight:** Each Den host already produces `mainModule` — the fully composed NixOS module from ALL aspects (includes, providers, policies, quirks, cross-entity delivery). This module is computed BEFORE `intoAttr` writes the host to `nixosConfigurations`. We can redirect it.

### How It Works

```
den.hosts.traversal = { ... }
  ↓ aspect resolution (includes, providers, policies, quirks — all preserved)
mainModule (the composed NixOS module, available as config.den.hosts...mainModule)
  ↓ imported into
clan.machines.traversal
  ↓ Clan's nixosSystem (adds clanCore modules on top)
nixosConfigurations.traversal
  ↓
clan machines update traversal ✅
nixos-rebuild --flake .#traversal ✅
```

### The Bridge Module

```nix
# modules/clan-bridge.nix
{ config, lib, den, ... }:
let
  hosts = config.den.hosts.x86_64-linux or {};
in
{
  # Create clan.machines entries from Den's host definitions
  clan.machines = lib.mapAttrs (name: cfg: {
    imports = [ cfg.mainModule ];   # Den's full aspect composition
    nixpkgs.hostPlatform = "x86_64-linux";
    clan.core.networking.targetHost =
      lib.mkDefault "root@${name}";
  }) hosts;

  # Prevent Den from ALSO calling nixosSystem for these hosts
  # intoAttr = [] tells Den: "don't write to nixosConfigurations"
  # This is the CORRECT way — NOT overriding instantiate
  config.den.hosts.x86_64-linux = lib.mapAttrs (name: cfg:
    cfg // { intoAttr = lib.mkDefault []; }
  ) hosts;
}
```

### Key: `intoAttr = []` vs `instantiate = _: {}`

| Approach | Safe? | Why |
|----------|-------|-----|
| **`intoAttr = []`** ✅ | **Yes** | Only gating site (`modules/policies/flake.nix:46`): `lib.optionals (host.intoAttr != []) [...]`. Empty array → the entire instantiate-registration block is skipped. No side effects anywhere else. |
| **`instantiate = _: {}`** ❌ | **No** | If `intoAttr` is non-empty, Den's pipeline calls `entry.spec.instantiate(mkArgs(entry.spec))` and writes the raw result to `flake.nixosConfigurations`. Returning `{}` produces a garbage empty attrset, silently breaking `nixos-rebuild` and `nix build`. |

### Verified: No Impact on Den Internals

**The code path gated by `intoAttr`** (found in `modules/policies/flake.nix:46-49`):
```nix
lib.optionals (host.intoAttr != []) [
  (resolve.to "host" { inherit host; })
  (den.lib.policy.instantiate host)
]
```

This controls ONLY:
1. Creating a host scope for flake-level delivery
2. Registering the instantiate call (nixosSystem)

It does NOT control:
- Aspect resolution (happens in the host submodule, independent)
- `mainModule` computation (from `__resolveResult`, inside the host submodule)
- Quirks, policies, cross-entity delivery (part of aspect resolution)
- Providers, includes, context propagation (all inside the host submodule)

**No other code references `intoAttr`** beyond these two lines (confirmed by source audit across entire Den codebase).

### Clan's Extra Modules

Clan's `clanCore` module auto-includes:
- `clan.core.*` options (networking, sops, vars, backups, settings, state)
- sops-nix module
- disko module

These are **namespaced** under `clan.core.*` — they shouldn't conflict with Den aspects. If they do, you can disable per host:
```nix
clan.machines.traversal = {
  imports = [ cfg.mainModule ];
  clan.core.sops.enable = false;   # if Den handles sops
};
```

---

## Integration Paths

### Bridge Path (Recommended): Keep Den hosts, Clan deploys

**No migration needed.** Keep `den.hosts` as-is. Bridge module reads `mainModule` and creates `clan.machines` entries. Den retains full composability. Clan handles deployment.

```
# den.hosts stays as it is:
den.hosts.x86_64-linux.traversal = { };
den.hosts.x86_64-linux.spectacle = { };

# Bridge module auto-generates:
clan.machines.traversal = { imports = [ <mainModule> ]; targetHost = ...; }
clan.machines.spectacle  = { imports = [ <mainModule> ]; targetHost = ...; }
```

**Risk:** Low. No host definitions moved. `intoAttr = []` is safe — only skips nixosSystem call.

**`clan machines update`:** ✅ Works for all hosts

### Path A+ (Incremental bridge): One host at a time

Add Clan as flakeModule + bridge. Start by enabling the bridge on ONE new host (e.g., VPS). Then enable it on existing hosts one at a time.

Add a flag per host to opt into clan:
```nix
den.hosts.x86_64-linux.traversal = {
  clan.enable = true;  # bridge processes only this host
};
```

Bridge only processes hosts with the flag. All others stay Den-managed.

**Risk:** Very low. Each host individually opt-in.

### Path C (Alternative): Clan owns machines, Den provides modules

Define machines in `clan.machines` directly (not via bridge). Import Den's aspects as NixOS modules.

```
clan.machines.my-host = { config, pkgs, ... }: {
  imports = [
    # Reference the Den-composed module
    den.den.hosts.x86_64-linux.my-host.mainModule
    ./hardware-configuration.nix
  ];
  nixpkgs.hostPlatform = "x86_64-linux";
  clan.core.networking.targetHost = "root@my-host.local";
};
```

Only useful if you want a mixed fleet where SOME hosts don't use Den at all.

---

## Vars and Secrets

Clan's vars system (`clan vars generate <machine>`) requires the machine to be in `clan.machines`. Since the bridge creates those entries, vars work for all bridged hosts:

```
clan vars generate traversal     # ✅ works (machine exists in clan.machines)
clan vars upload traversal        # ✅ works
nixos-rebuild switch --flake .#traversal --target-host root@traversal  # ✅ works
clan machines update traversal    # ✅ works
```

---

## Migration Plan

```
Phase 0: Add clan-core + flakeModule    (5 min, zero risk)
  - Add clan-core to flake inputs
  - Import clan-core.flakeModules.default
  - Set clan.meta.name and clan.meta.domain
  - Verify: nix flake check still passes

Phase 1: Bridge for ONE new host         (30 min, isolated)
  - Create the bridge module
  - Enable on VPS only (host doesn't exist yet)
  - Verify: nix flake check passes
  - Test: nix build .#nixosConfigurations.vps.config.system.build.toplevel

Phase 2: Bridge for existing hosts        (1 hour each, opt-in)
  - Add clan.enable flag on traversal
  - Verify: nix flake check passes
  - nix build .#nixosConfigurations.traversal.config.system.build.toplevel (dry)
  - clan machines update traversal (live)

Phase 3: Clan services                    (as needed)
  - Add clan.core.* options (networking, backups, etc.)
  - Enable clan vars for secrets
  - Migrate from sops-nix to clan vars if desired
```

---

## Verdict

| Path | `clan machines update` | Secrets | Preserves Den | Risk |
|------|------------------------|---------|---------------|------|
| **Bridge (Recommended)** | ✅ All hosts | ✅ Full | ✅ Full (no migration) | Low |
| **A+ (Incremental bridge)** | ✅ Per host | ✅ Full | ✅ Full | Very low |
| **C (Direct clan.machines)** | ✅ Clan hosts | ✅ Full | ⚠️ Needs Den output modules | Low |
| **vars + nixos-rebuild only** | ❌ | ⚠️ Partial | ✅ Full | None |

**Bottom line:** The bridge approach gives us everything — full Den composability, full Clan deployment, no host migration. Add clan-core today, write the bridge module, and enable it one host at a time.
