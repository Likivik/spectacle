## Project
NixOS config repo. Uses **Den framework** (dendritic patterns) — aspects, not hosts, are the primary unit.

Flake uses `github:denful/den`. Docs: https://den.denful.com/

## Repo structure
```
modules/
├── aspects/          # Den aspects
│   ├── core/         # bootloader, determinate, locale, nix
│   ├── desktop/
│   │   ├── apps/firefox/
│   │   ├── common-core/    # desktopInbox, filesystems, networking, package-sources, peripherals-base, printers-scanners, remote-desktops, vpn
│   │   ├── common-extra/   # gaming, peripheralsExtra
│   │   └── desktopManagers/ # Cosmic, GNOME, Hyprland, KDE (7 files)
│   ├── dev/          # android, audiobookshelf, dev-fonts, direnv, docker, Flatpak-build, qt-inspection, shell-commands, shells (bash/elvish/zsh), ssh, stash, virtualization
│   └── server/torrserver/
├── defaults/         # inputs.nix, defaults.nix, topAspectDefinitions.nix, shell.nix, vm.nix
├── hosts/            # host-user-definitions.nix, serenity (desktop), spectacle (TV box), traversal (laptop, disabled)
└── users/            # likivik.nix, watcher.nix
```

## Hosts
| Host       | Description                          | Users   | Desktop       |
|------------|--------------------------------------|---------|---------------|
| serenity   | Desktop (active)                     | likivik | KDE           |
| spectacle  | TV box (active)                      | watcher | GNOME         |
| traversal  | Laptop (disabled)                    | likivik | —             |

## First setup (one-time, when inputs changed)
```bash
nix run .#write-flake
nix flake update
```

## Dev workflow (daily)
```bash
# 1. Check validity
nix flake check

# 2. Build & run VM for a host
nix run .#serenity     # or .#spectacle
```

## Rebuild on real hardware
```bash
nh os switch .#hostname
nh os boot .#hostname   # staged for next reboot
```

## Den patterns used
- `den.aspects.*` — aspect definitions with `.includes` (DAG) and `.provides`
- `den.hosts.*` — host declarations with users
- `den.default.*` — global defaults (includes Den batteries like `hostname`, `define-user`, `mutual-provider`)
- `den.provides.*` — built-in batteries (`primary-user`, `user-shell`, `tty-autologin`)
- `den.schema.*` — schema extensions (e.g., `user.classes`)
- Per-class blocks: `nixos`, `homeManager`, `darwin`
- Context args flow automatically: `{ host, user, config, pkgs, ... }`

## Conventions
- New file → `git add` before any builds or VM runs (flake-file expects tracked files); `nix run .#write-flake` only needed for inputs changes
- State version: NixOS 25.11, HM 25.11
- Default user class: `homeManager` (via `den.schema.user.classes`) — TODO: doesn't actually work, needs debug
- Firewall enabled globally

## Workflow
- If ambiguous about next steps, stop and ask — do NOT decide alone.

## Validation
- Do not ignore failing tests/checks, even if seemingly unrelated.

## Response style
- Terse, technical, no fluff. Fragments OK. Arrows for causality (X → Y).
- For code/commits/PRs: write normally, properly, eloquently.
- Errors quoted exactly.
