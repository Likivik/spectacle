
# Issues I have/had/solved


## New inputs are not being added with `nix flake update`!?

**Solution:**
- After adding new inputs you need to regenerate flake.nix (with flake-file)!

**How exactly?**
- If you add new source to `flake-file.inputs = []` - you HAVE to execute `nix run .#write-flake` to regenerate the flake.nix and only then execute `nix flake update` to update and pull newly added sources.

**Question:**
- Can this be automated?


## How to add determinate?
* https://github.com/jasperro/dotfiles/blob/3926333fae3deab4bcad12aff531a0d3154e3c69/modules/nixos/determinate.nix
* https://github.com/blessuselessk/determinate-OCD/blob/main/modules/community/ocd/determinate.nix
* https://github.com/mbainter/nix-den/blob/main/modules/aspects/determinate.nix
* https://github.com/loystonpais/lunar/blob/c4cc251fc6c9ba0034be0f3cf502bc257769d21f/modules/lunar/determinate.nix



