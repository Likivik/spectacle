# Den Framework Skill

Aspect-oriented, context-driven Dendritic Nix configurations.
Repo: github:denful/den
Documentation: den.denful.dev



## Core Concepts
- **Aspects** (`den.aspects.<name>`): Reusable config units returning modules per class (`nixos`, `homeManager`, `darwin`, etc.).
- **Classes**: Config domains. Built-in: `nixos`, `darwin`, `homeManager`, `user`. Custom via `den.batteries.forward`.
- **Context Pipeline**: `den.policies` traverse entities (host→users→homes); aspects applied at resolution.
- **Zero Dependencies**: `den.lib` is domain-agnostic; framework layer optional for NixOS/nix-Darwin/HM.

## Entity Declaration
```nix
# Hosts + Users + Homes (one-liners)
den.hosts.x86_64-linux.lap.users.vic = {};
den.homes.x86_64-linux."vic@lap" = {};

# With schema extensions
den.schema.user = { user, lib, ... }: {
  config.classes = lib.mkDefault [ "homeManager" ];
  options.mainGroup = lib.mkOption { default = user.userName; };
};
```

## Aspect Definition
```nix
den.aspects.workstation = {
  includes = [ den.batteries.hostname den.aspects.vpn ];
  nixos = { pkgs, ... }: { imports = [ inputs.disko.nixosModules.disko ]; };
  darwin = { pkgs, ... }: { imports = [ inputs.nix-homebrew.darwinModules.nix-homebrew ]; };
  provides.to-users.homeManager = { pkgs, ... }: { programs.vim.enable = true; };
};
```

## Policies & Pipes
Policies control config forwarding between entities. Declared via `den.schema.host.includes`.

```nix
# Pipe: forward from source to target class
pipe = { host, user, ... }: {
  pipe.from "source-key" [ "target-class" ];
  pipe.collect ({ host, ... }: true);  # gather matching aspects
};

# Quirks: conditional behavior flags
den.quirks.impermanence = { description = "Enable persist mounts"; };
```
Source: `modules/options.nix:236` (quirks), `nix/lib/policy-*.nix` (constructors), `templates/fleet-demo/modules/policies/pipes.nix` (usage).

## Custom Classes (Forward Battery)
```nix
roleClass = { host, user }: { class, aspect-chain }:
  den.batteries.forward {
    each = lib.intersectLists (host.roles or []) (user.roles or []);
    fromClass = lib.id; intoClass = _: host.class;
    intoPath = _: [ ]; fromAspect = _: lib.head aspect-chain;
  };
den.schema.user.includes = [ roleClass ];
```
Guard variant: add `guard = { pkgs, ... }: platform: lib.mkIf pkgs.stdenv."is${platform}";`

## Batteries (Built-in)
| Battery | Purpose |
|---------|---------|
| `hostname` | Sets `networking.hostName` from host key |
| `primary-user` | Marks first user as primary |
| `user-shell "<shell>"` | Sets default shell |
| `tty-autologin "<user>"` | Console autologin |
| `forward { ... }` | Core class forwarding engine |
| `define-user` | Auto-creates user from declaration |
| `mutual-provider` | Bidirectional host↔user config |

## Resolution & Manual Use
```nix
# Manual resolution outside pipeline
aspect = den.lib.aspects.resolve "nixos"
  (den.aspects.my-aspect { host = den.hosts.x86_64-linux.my-laptop; });
nixosConfigurations.my-laptop = lib.nixosSystem { modules = [ aspect ]; };
```

## Key Source Paths
- `nix/lib/policy-*.nix` — Policy effect constructors
- `nix/lib/aspects/policy-type.nix` — Policy type definitions
- `nix/lib/aspects/fx/handlers/policy.nix` — Effect handlers
- `modules/options.nix` — `den.quirks`, core options
- `templates/fleet-demo/` — Full policy/pipe examples
