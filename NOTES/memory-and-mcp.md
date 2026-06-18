# Memory & MCP notes

## Mnemosyne (MCP-based, ad-hoc)

**Key point: mnemosyne is NOT in the NixOS closure.** It runs ad-hoc via `nix shell` + `pipx run` to avoid bloating the system closure with Python packages.

### DB location
- `~/.hermes/mnemosyne/data/mnemosyne.db`

### MCP config (`opencode.jsonc`)
```json
"mnemosyne": {
  "type": "local",
  "enabled": true,
  "command": [
    "nix", "shell",
    "nixpkgs#python3",
    "nixpkgs#python313Packages.pipx",
    "-c",
    "pipx", "run", "--spec", "mnemosyne-memory[mcp]", "--with", "mnemosyne-hermes", "mnemosyne", "mcp"
  ]
}
```

**Why `--with` and not another `--spec`:** `--with` adds an extra package alongside the main spec. Using `--spec` twice causes pipx/uv to treat the second package as the primary app, losing the `[mcp]` extras from the first.

### How it works
1. `nix shell` provides `python3` + `pipx` without installing them system-wide
2. `pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes` installs both packages into a temporary uv-managed venv
3. `mnemosyne mcp` starts the MCP server over stdio
4. The MCP server exposes ~25 tools: `mnemosyne_remember`, `mnemosyne_recall`, `mnemosyne_stats`, `mnemosyne_sleep`, scratchpad, graph, triples, canonical facts, sync, etc.

**`mnemosyne-hermes` is required** — the tool definitions (`ALL_TOOL_SCHEMAS`) live in the hermes package, not in `mnemosyne-memory`. Without it, the server registers 0 tools.

### CLI usage (outside MCP)
```bash
nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes mnemosyne stats
nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec mnemosyne-memory[mcp] --with mnemosyne-hermes mnemosyne recall "query"
```

## Other MCP servers

### General patterns
| Language | Command |
|---|---|
| Node.js | `nix shell nixpkgs#nodejs -c npx -y <npm-pkg>` |
| Python | `nix shell nixpkgs#python3 nixpkgs#python313Packages.pipx -c pipx run --spec <pypi-pkg> --with <extra-pkg> <command>` |
| Nix-packaged | `nix shell <flake-ref> -c <command>` |

### Adding a new MCP server
1. Define in `opencode.jsonc` under `"mcp"` — see existing entries for pattern
2. Test the command manually first
3. No NixOS rebuild needed for ad-hoc MCPs (they run via `nix shell`)

## TODO — sync strategy
- [ ] Live `.db` not git-tracked (binary, corruption risk)
- [ ] Consider: `mnemosyne export > backup.json` + git commit, or `mnemosyne sync` between machines
- [ ] Could add automated export as pre-commit hook
