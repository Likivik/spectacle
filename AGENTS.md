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
- New file → immediately `git add`;
- Special case: modules/defaults/topAspectDefinitions.nix - don't include new sub aspects into .desktopManager.includes (they are always used only one at a time)

## Commit messages
- Examples (always ask user to confirm)
  - feat: add noctalia desktop shell aspect, replace KDE on serenity
  - fix: ...
  - or suggest new words before :

