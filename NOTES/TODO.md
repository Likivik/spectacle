
# Things to do

### Done

* [x] Find & Watch dendritic video - vimjoyer and not much more found
* [x] find & watch den.lib video - didn’t find any
* [x] asking gemini for explanations - meh usefulness
* [x] **reading through documentation for den** - useful part
* [x] **roaming through other people’s configs** - also really useful

### Big Goals

#### Deployment

What do we want:
- Build on strontg box, push to weak box
- Autoupdate
- Change config from remote box (Desktop)

### Agents Setup
- [ ] Compare
    * [oh-my-opencode](https://github.com/code-yeongyu/oh-my-opencode)
    * [oh-my-opencode-slim](https://github.com/alvinunreal/oh-my-opencode-slim)
    * https://github.com/hffmnnj/opencode-goopspec
    * https://github.com/vtemian/micode
    * https://github.com/kdcokenny/opencode-workspace
    *
    #### Agent - agecent stuff
        * https://github.com/AnganSamadder/opentmux
        * https://github.com/Mark1708/opencode-agents-sidebar
        * https://github.com/IgorWarzocha/opencode-planning-toolkit - more general perhaps
        * https://github.com/malhashemi/opencode-sessions
        * 


### Migration off home-manager

- [ ] Move remaining HM-managed items to nix-maid (tray.target fixed via NixOS level, rest needs auditing)

### OpenCode Tools

- [x] **opencode-snip** — snip v0.18.0 at `~/.local/bin`, plugin registered in global config
- [x] **Dynamic Context Pruning** — `@tarquinen/opencode-dcp` registered in global plugin array
- [x] **Token Tracker** — TUI sidebar footer plugin at `~/.config/opencode/plugins/token-tracker.tsx`, registered in tui.jsonc
- [x] **Direnv** — `@simonwjackson/opencode-direnv` registered in global plugin array
- [x] **Shell Strategy** — cloned to `~/.config/opencode/plugin/shell-strategy/`, referenced in config instructions
- [x] Context7 — library docs MCP
- [] https://github.com/ramarivera/opencode-model-announcer


### Streaming Box:

#### Control linux with voice - it does exist
- [ ] Where do we start?
- [ ]

#### Stremio
- [ ] Where do we start?



## Possible hosts

### serenity

desc: Main Desktop PC.

### traversal

desc: Main Laptop

### spectacle

desc: small box connected to TV to watch shows, movies and use browser from.

### homelab01-poweredge

desc: Backups aggregator from all other machines, has probably mirrored zfs pool (which does bit-rot prevention) and sends backups off-site.

###  devbox01

desc: to mess with and host stuffs like local torrent server (for .iso files ofc), media server, Nextcloud, Notes, and every other thing I wanna try that has a server component, after messing with it here can be moved to “prod” server.

### nixosrouter

desc: nixos based router + wifi, nftables based (probably)

### salembox

desc: desktop for salem user

## Possible Users

### likivik

desc: desktop, laptop, spectacle user, development, office work, my main

### likiviks

desc: server administrator, also me, but setup for server administration as opposed to gui desktop, laptop use (better to combine with likivik, configured based on host)

### salem

desc: desktop user on

### watcher

desc: default user for spectacle
