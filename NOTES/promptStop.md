## Goal
- Refactor NixOS configuration to replace `den.aspects.core._` usage with Den-native composition patterns

## Constraints & Preferences
- Eliminate `den.aspects.core._` pattern
- Prefer Den-native patterns: policies, quirks, pipes, or equivalent framework constructs

## Progress
### Done
- Analyzed 4 core aspect files (`bootloader.nix`, `determinate.nix`, `locale.nix`, `nix.nix`)
- Traced `den.aspects.core._` references across codebase
- Mapped current `nixos` module definitions to Den composition structures

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- (none)

## Next Steps
- Evaluate Den's policy, quirk, and pipe APIs against the 4 existing module definitions
- Draft migration plan mapping each core aspect to the chosen Den pattern
- Update `modules/hosts/serenity/serenity.nix` to use the new composition pattern

## Critical Context
- Each core file exports a single aspect via `den.aspects.core.<name>` wrapping a `nixos` module definition
- `bootloader.nix`: systemd-boot, max console mode, 50 gen limit, EFI variable touch, /tmp cleanup
- `determinate.nix`: imports `inputs.determinate.nixosModules.default`, adds Determinate cache URL & public key
- `locale.nix`: en_DK.UTF-8 default, default fonts, ru_RU for LC_* vars, Europe/Moscow timezone
- `nix.nix`: flakes/nix-command enabled, allow unfree, stateVersion 25.11, nh with 356d/30-gen retention, auto nix optimization
- `den.aspects.core._` is auto-synthesized by Den's `mergeWithAspectMeta` to collect all child aspects of `core` into a single includes list
- `modules/hosts/serenity/serenity.nix` currently relies on `[den.aspects.core._]` for host configuration

## Relevant Files
- `/Storage/Git/spectacle/modules/aspects/core/bootloader.nix`
- `/Storage/Git/spectacle/modules/aspects/core/determinate.nix`
- `/Storage/Git/spectacle/modules/aspects/core/locale.nix`
- `/Storage/Git/spectacle/modules/aspects/core/nix.nix`
- `/Storage/Git/spectacle/modules/hosts/serenity/serenity.nix`
- `/Storage/Git/spectacle/NOTES/DEN.md`
