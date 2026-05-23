## Project

NixOS fleet config repo.
Flake uses `github:denful/den`. Docs: https://den.denful.com/



## Workflow
- Create plan -> ask user
- Never invent new steps without confirming with user.
- never take new direction without confirming with user.
- ALWAYS ask user before next steps or sub-steps!
- stop and ask — do NOT decide alone.
- ALWAYS ask to confirm a commit message.
- Never commit without explicit permission
- CONFIRM EVERY STEP WITH USER - DON'T TRY TO DO SEVERAL TASKS AT ONCE.

## Response style (IMPORTANT!!!)
- Terse, technical, no fluff. Fragments OK. Arrows for causality (X → Y).
- Conserve tokens, answer shortly, laconically.

## Noctalia keybind wallpaper
- Wallpaper lives at `modules/users/likivik/dotfiles/noctalia/wallpapers/keybinds.png`
- Generated from `config.kdl` by `modules/users/likivik/dotfiles/noctalia/gen-keybind-wallpaper.sh`
- After changing keybinds, regenerate: `nix-shell -p imagemagick iosevka --run "FONT_PATH=\$(nix-build -E '(import <nixpkgs> {}).iosevka' --no-out-link 2>/dev/null)/share/fonts/truetype/Iosevka-Regular.ttf bash modules/users/likivik/dotfiles/noctalia/gen-keybind-wallpaper.sh"`

## After making changes
```bash

# only if inputs changed, binary cache was added or flake.nix needs to be rebuilt for some reason:
nix run .#write-flake && nix flake update

# if needed - Check validity
nix flake check
```

## If asked to switch to new config (applies changes to hardware)
```bash
nh os switch .#hostname
nh os boot .#hostname   # staged for next reboot
```

## Conventions
- Special case: modules/defaults/topAspectDefinitions.nix - don't include new sub aspects into .desktopManager.includes (they are always used only one at a time)
- user dotfiles live in modules/users/{username}/dotfiles/{program-name}/

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


