# Things to do
  - remove "the daragons" and other fluffy stuf from agents.md - it works shittily, make less verbose!

## Big Goals

### Deployment

- [ ] Build on strong box, push to weak box
- [ ] Autoupdate
- [ ] Change config from remote box (Desktop)

## Agents Setup

- [oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode)
- [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim)
- https://github.com/hffmnnj/opencode-goopspec
- https://github.com/vtemian/micode
- https://github.com/kdcokenny/opencode-workspace

### Agent UI / sidebar

- https://github.com/AnganSamadder/opentmux
- https://github.com/Mark1708/opencode-agents-sidebar
- https://github.com/IgorWarzocha/opencode-planning-toolkit — more general perhaps
- https://github.com/malhashemi/opencode-sessions

## nix-maid migration

- [ ] Move remaining HM-managed items to nix-maid
- [x] tray.target HM/NixOS conflict — fixed via `home-manager.sharedModules` override in `defaults.nix`

## dms-shell

### Phone connectivity

- [x] Evaluate kdeconnect vs Valent — picked Valent (lighter, GTK4, same protocol)
  - [x] Research kdeconnect features + dms-shell compatibility
  - [x] Research Valent features + dms-shell compatibility
  - [x] Pick one → Valent
- [x] Install & configure Valent
  - [x] Added `programs.kdeconnect` with `package = pkgs.valent` to DMS aspect
  - [x] Firewall ports 1714-1764 opened (included in programs.kdeconnect)
- [x] Test: `dankKDEConnect` plugin + Valent compatibility on traversal — working!

## Streaming Box

### Voice control — it does exist

- [ ] Where do we start?

### Stremio

- [ ] Where do we start?

## OpenCode Tools

### Done

- [x] **Dynamic Context Pruning** — `@tarquinen/opencode-dcp` registered in global plugin array
- [x] **Token Tracker** — TUI sidebar footer plugin at `~/.config/opencode/plugins/token-tracker.tsx`, registered in tui.jsonc
- [x] **Direnv** — `@simonwjackson/opencode-direnv` registered in global plugin array
- [x] **Shell Strategy** — cloned to `~/.config/opencode/plugin/shell-strategy/`, referenced in config instructions
- [x] Context7 — library docs MCP

## Onboarding

- [x] Find & Watch dendritic video — vimjoyer and not much more found
- [x] Find & watch den.lib video — didn't find any
- [x] Asking gemini for explanations — meh usefulness
- [x] **Reading through documentation for den** — useful part
- [x] **Roaming through other people's configs** — also really useful
