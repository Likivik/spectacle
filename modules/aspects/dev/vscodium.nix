{ den, ... }:
{
  den.aspects.vscodium = {
    # NOTE: ~/.config/VSCodium/ is intentionally NOT symlinked into dotfiles.
    # Cross-host sync is owned by Shan.code-settings-sync via a GitHub Gist.

    nixos = { pkgs, ... }: {
      environment.systemPackages = [ pkgs.vscodium ];
    };
  };
}
