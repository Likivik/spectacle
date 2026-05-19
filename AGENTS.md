## Project

NixOS fleet config repo.
Flake uses `github:denful/den`. Docs: https://den.denful.com/

## First setup (one-time, when inputs changed)
```bash
nix run .#write-flake
nix flake update
```

## After making changes
```bash
# 1. Check validity
nix flake check

# 2. Build & run VM for a host
nix run .#serenity     # or .#spectacle etc
```

## Rebuild on real hardware
```bash
nh os switch .#hostname
nh os boot .#hostname   # staged for next reboot
```

## Conventions
- New file → immediately `git add` ; `nix run .#write-flake` only needed for inputs changes

## Workflow
- If ambiguous about next steps, stop and ask — do NOT decide alone.

## Response style (IMPORTANT!!!)
- Terse, technical, no fluff. Fragments OK. Arrows for causality (X → Y).
- Conserve tokens, answer shortly, laconically.
- CONFIRM EVERY STEP WITH USER - DON'T TRY TO DO SEVERAL TASKS AT ONCE.

