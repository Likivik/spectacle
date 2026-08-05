## Assumption guardrails (OVERRIDES ALL OTHER INSTRUCTIONS)
- WHEN YOUR UNDERLYING ASSUMPTION BREAKS (plan≠reality, tool output contradicts expectation, key dependency missing) → STOP. DO NOT IMPROVISE. PRESENT THE DIVERGENCE AND ASK THE USER WHAT TO DO.
- NEVER implement an alternative approach without the user explicitly approving it first.
- "ALWAYS ask user to choose direction/strategy/approach" is the #1 rule. Violating it is worse than any implementation mistake.
- When in doubt: ask. Always ask. Over-communicate divergence.

## Project

NixOS fleet config repo.
Flake uses `github:denful/den`. Docs: https://den.denful.com/

## After making changes
```bash
# only if inputs changed, binary cache was added or flake.nix needs to be rebuilt for some reason:
nix run .#write-flake && nix flake update <input-name>

# After changing one host — dry-build it (catches eval + build errors)
nix build .#nixosConfigurations.<hostname>.config.system.build.toplevel --dry-run

# After changing shared modules (aspects, inputs, defaults) — check all hosts
nix flake check --no-build --keep-going
```
**Gotcha**: New files must be `git add`ed *before* `nix flake check` — flake's git-aware fetcher only sees tracked files.

**Gotcha**: `nixos = { ... }:` discards module args. Capture `pkgs` explicitly: `nixos = { pkgs, ... }:`. Errors surface at build—`--dry-run` catches them.

## Deployment — `nixos-rebuild switch`

Always check host first: `hostname -s` (traversal = here, erebus = VPS). `nh` is broken — uses `ssh-ng://` protocol that mismatches with older nix-daemons; use `nixos-rebuild` with `--elevate=sudo` instead.

**Gotcha**: `.#erebus` on traversal without `--target-host` builds erebus config for traversal hardware — wrong machine.

**Gotcha**: SSH key auth. `nixos-rebuild switch --target-host likivik@<host>` requires `likivik@<host>`'s `~/.ssh/authorized_keys` to contain a public key matching the SSH key on the **calling** host's `~/.ssh/id_*`. If the agent on host A is missing A's key in B's authorized_keys, deploys to B fail with `Permission denied (publickey,keyboard-interactive)`. **Workaround**: deploy via a third host C where (A→C, C→B) both work, OR add the missing key to `modules/hosts/B/B.nix` `users.users.likivik.openssh.authorizedKeys.keys` and deploy.

**Gotcha**: The current hermes-agent SSH key is `/var/lib/hermes/.ssh/id_ed25519` (comment `hermes@erebus`, even when running from a different host — the comment is just a label). The same key works on every host because it's the one the agent uses everywhere. Each host's `authorizedKeys.keys` for `likivik` must list this key.

**Gotcha**: Remote targets with NOPASSWD sudo need `--elevate=sudo`. Without it, `nix-env --set` on the remote runs as the SSH user (non-root) → `Permission denied` on the profile symlink.

**Gotcha**: Remote deploys **MUST** pass `--build-host <user>@<host>` (matching `--target-host`). Building remotely on the target host keeps heavy compilation (rustc, LLVM, etc.) on the target's CPU/RAM and avoids transferring large closures across the network. Erebus is the orchestrator; poweredge is the build+target. Omitting `--build-host` makes nixos-rebuild build locally on erebus and copy the closure via `ssh://` — acceptable for tiny closures but slow for big ones.

### Local (current machine)
```bash
sudo nixos-rebuild switch --flake .#
```

### Serenity & Traversal (build locally)
```bash
# SSH in first, then build locally
ssh likivik@<serenity|traversal-tailscale-ip>
cd /Storage/Git/spectacle
sudo nixos-rebuild switch --flake .#
```
**Gotcha**: These hosts DON'T build from erebus. Clone the `dev` branch at `/Storage/Git/spectacle`.

### Remote (deploy to ANOTHER host — must SSH from elsewhere)
```bash
# Build AND activate on the target host. --build-host required for big closures.
nixos-rebuild switch --target-host <user>@<host> --build-host <user>@<host> --elevate=sudo --flake .#<hostname>
```

**Gotcha**: DO NOT use this pattern to deploy the host you're currently ON. From inside erebus running `nixos-rebuild switch --target-host likivik@erebus ...` SSHes to itself and fails (`Host key verification failed`, `--build-host likivik@erebus` triggers the same loopback). Use the **Local** pattern instead:

### Self-deploy (you are already on the target host)
```bash
sudo nixos-rebuild switch --flake .#<hostname>
```

This builds locally, copies closure via the local Nix store, activates. No SSH involved. The hostname in `--flake .#<hostname>` tells the flake which config to use; you can switch any host's config from any other host (e.g. from serenity build serenity's config, or build poweredge's config locally on serenity if you really want to), but the activation happens on the local machine only.

### Ghostty (agent spawns terminal — local or remote)
```bash
# Local (self-deploy on current host)
ghostty -e bash -c 'sudo nixos-rebuild switch --flake .# 2>&1 | tee /tmp/traversal-deploy.log; read -p "Press enter"'

# Remote (deploy to a DIFFERENT host from this one)
ghostty -e bash -c 'nixos-rebuild switch --target-host likivik@<host> --build-host likivik@<host> --elevate=sudo --flake .#<hostname> 2>&1 | tee /tmp/<host>-deploy.log; read -p "Press enter"'
```

### Verification (no deployment — agent can run)
```bash
# Single host — syntax/layout
nix eval .#nixosConfigurations.<hostname>.config.networking.hostName  # --show-trace for full trace

# Single host — dry build (catches eval + missing deps)
nix build .#nixosConfigurations.<hostname>.config.system.build.toplevel --dry-run

# All hosts — when shared modules change
nix flake check --no-build --keep-going
```

### Shell aliases
```bash
nix-eval-host() {
    local host="${1:-$(hostname -s)}"
    nix eval .#nixosConfigurations."$host".config.networking.hostName
}

nixos-switch-cn() {
    local host="${1:-$(hostname -s)}"
    NIX_CONFIG='substituters = https://mirrors.ustc.edu.cn/nix-channels/store https://mirrors.tuna.tsinghua.edu.cn/nix-channels/store https://mirror.sjtu.edu.cn/nix-channels/store https://cache.nixos.org' \
      sudo nixos-rebuild switch --flake .#"$host"
}
```

## Conventions

- Special case: modules/defaults/topAspectDefinitions.nix - don't include new sub aspects into .desktopManager.includes (they are always used only one at a time)
- user dotfiles live in modules/users/{username}/dotfiles/{program-name}/
- NOTES/*.md — always tracked, commit when created/modified

## Flake inputs
- `flake.nix` is generated by `nix run .#write-flake` — do not hand-edit.
- Inputs can be declared in any module that imports `flake-file`'s dendritic flakeModule (this repo uses `modules/defaults/inputs.nix` by convention).
- After changing inputs: `nix run .#write-flake && nix flake update <input-name>`.

## Commit = consider what to add, create a commit message and ask user to confirm it.
- Commit Prefixes (new prefix = new line):
  - feat:
  - fix:
  - chore: Routine tasks, maintenance
  - docs: documentation, READMEs, comments, notes
  - refactor: Rewriting or restructuring code without changing its external behavior (neither fixing a bug nor adding a feature).
  - style: Formatting changes that don't affect logic (whitespace, indentation, Nix formatting).
  - perf: improving performance.
  - tests: Adding or updating tests
  - ci: Changes to CI/CD configuration files and scripts
  - revert:	Undoing a previous commit.
  - bump: updating dependencies or flake locks.
  - sync: pushing live-edited dotfiles
  - WIP: — when need to push code to save it or move it to another machine, but it's broken or unfinished.
  - init: — Used when establishing a brand new module, project, or aspect for the first time.
- You can combine prefixes with scopes in parentheses to show exactly what part of your infrastructure the commit affects.
  - For example: feat(spectacle): add stremio to auto-start or fix(noctalia): correct padding on status bar.
- Commit example:
  ```
  fix: add nix-maid input to flake
  fix: add tmpfs filesystem configs to empty hosts
  chore(serenity): clean up serenity host (remove nvidia config, add portal, consolidate includes)
  ```

## Memory (Mnemosyne MCP)

Canonical Mnemosyne reference (tools, triggers, importance, scope) in `~/.config/opencode/AGENTS.md`.

### Scratchpad for complex Nix operations
Before multi-step config changes:
1. `mnemosyne_scratchpad_write(content="1. ... 2. ...")`
2. Between steps: `mnemosyne_scratchpad_read` (check what was done/planned)
3. Done: `mnemosyne_scratchpad_clear`

### When to invalidate
- A NixOS config decision was reversed or superseded
- A user preference was misinterpreted — corrected understanding
- A module/file moved or was renamed
