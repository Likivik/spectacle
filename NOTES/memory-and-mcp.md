# Memory & MCP notes

## Mnemosyne
- DB: `~/.hermes/mnemosyne/data/mnemosyne.db`
- MCP server runs via pipx (ad-hoc, not in systemPackages)
- Install path: `~/.local/pipx/venvs/mnemosyne-memory/`
- Binary symlink: `~/.local/bin/mnemosyne`

### TODO — sync strategy
- [ ] Live `.db` not git-tracked (binary, corruption risk)
- [ ] Consider: `mnemosyne export > backup.json` + git commit, or `mnemosyne sync` between machines
- [ ] Could add automated export as pre-commit hook

## Adding a new MCP server
1. Define in `opencode.jsonc` under `"mcp"` — see existing entries for pattern
2. General patterns:
   - **Node.js MCPs**: `nix shell nixpkgs#nodejs -c npx -y <npm-package>`
   - **Python MCPs**: `nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c bash -c '... pipx install <pypi-package> && exec <command>'`
   - **Nix-packaged MCPs**: `nix shell <flake-ref> -c <command>`
3. If adding a nix-packaged MCP, add it to `environment.systemPackages` in the relevant aspect module
