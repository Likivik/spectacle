# Always apply these rules

1. Ask before committing, pushing, or switching
2. Check eval with `nix eval .#nixosConfigurations.<hostname>.config.networking.hostName`
3. Run `nix flake check --no-build --keep-going` after any changes
4. Never add secrets, API keys, or credentials to tracked files
5. Understand existing codebase conventions before making changes
6. Prefer existing patterns over introducing new ones
7. Keep configuration DRY — prefer symlinks over duplication
8. `opencode.jsonc` MCP definitions should reference `shared-mcp.jsonc` (NOT duplicated inline)
