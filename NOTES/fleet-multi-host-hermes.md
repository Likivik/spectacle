# Fleet Multi-Host Hermes Architecture

## Problem
Hermes runs on erebus. User works on spectacle repo across multiple devices:
- **erebus** (VPS) — Hermes lives here, runs commands, manages fleet
- **traversal** (laptop) — local dev, nixos-rebuild
- **serenity** (desktop) — local dev, nixos-rebuild
- **Pixel9a** (phone) — Telegram only

Need Hermes to access files/commands on traversal and serenity without duplicating the full setup.

## Solutions Evaluated

### 1. SSH terminal backend (built-in)
Single remote, all-or-nothing. Can't mix local + remote.
```yaml
terminal:
  backend: ssh
  ssh_host: "100.108.207.39"
  ssh_user: "likivik"
```
**Verdict:** Too rigid. Loses local execution entirely.

### 2. Multi-backend terminal (proposed, not merged)
GitHub issue [#1855](https://github.com/NousResearch/hermes-agent/issues/1855).
```yaml
terminal:
  default_backend: local
  backends:
    traversal:
      type: ssh
      host: traversal.tailnet
    serenity:
      type: ssh
      host: serenity.tailnet
```
**Verdict:** Perfect design, but not available yet.

### 3. Remote Hosts Plugin ✅ (available now)
[hermes-plugin-remote-hosts](https://github.com/donovan-yohan/hermes-plugin-remote-hosts)

Adds per-command remote targeting while keeping local as default:
- `remote_terminal(host="serenity", command="sudo nixos-rebuild switch")`
- `remote_read_file(host="traversal", path="/etc/nixos/configuration.nix")`
- `remote_write_file(host="traversal", path="...", content="...")`

Config:
```yaml
remote_hosts:
  hosts:
    traversal:
      host: 100.98.71.80
      user: likivik
      workdir: ~/spectacle
      enabled: true
    serenity:
      host: 100.108.207.39
      user: likivik
      workdir: ~/spectacle
      enabled: true
```

**Verdict:** Best option available now. Install on erebus.

## What Needs to Happen
1. Add hermes@erebus SSH key to traversal + serenity authorized_keys
2. Install remote-hosts plugin on erebus
3. Configure host aliases in config.yaml
4. Test remote file read/write/execute

## SSH Keys Status
- ✅ erebus host key generated
- ✅ hermes@erebus user key generated (`~/.ssh/id_ed25519`)
- ❌ hermes key NOT in serenity authorized_keys yet
- ❌ hermes key NOT in traversal authorized_keys yet
- ❌ remote-hosts plugin NOT installed yet
