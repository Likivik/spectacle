# Plan: multi-profile hermes (parameterized extra profiles)

## Decision (user-confirmed)
Keep `default` gateway/plugin untouched. Parameterize **extra** profiles via a
list. salem = first extra profile. Bot token slot left empty (placeholder).
salem gets NeuralWatt (LLM) + MiniMax (via shared graphiti-mcp).

## Shape
```nix
extraHermesProfiles = [
  { name = "salem"; home = "/var/lib/hermes/.hermes/profiles/salem";
    botTokenSecret = "hermes/salem-bot-token"; }
];
```

## Changes
1. `hermes-agent.nix` — loop over `extraHermesProfiles` to emit:
   - `systemd.user.services.hermes-gateway-<name>` (own HERMES_HOME, own
     EnvironmentFile, `ExecStart = hermes gateway run`).
   - per-profile `sops-env` generation (bot token vs default's multi-var file).
2. `_hermes-graphiti.nix` — plugin install loop over `default + extras`
   (symlink + `memory.provider graphiti` per profile home).
3. `erebus.nix` — declare `sops.secrets."hermes/salem-bot-token"`.
4. `secrets/erebus/secrets.yaml` — add `hermes.salem-bot-token` empty slot.

## Shared (unchanged)
graphiti-mcp, litellm, FalkorDB, dashboard, llama/playwright/searxng.

## Out of nix scope (imperative, follow-up)
salem's model provider + key = `salem setup` / `hermes config set`
(NeuralWatt), graphiti memory auto-resolves to `salem` tenant.

## Verify
`nix build .#nixosConfigurations.erebus.config.system.build.toplevel --dry-run`
+ `nix flake check` (hermes-tests). No deploy without user go.
