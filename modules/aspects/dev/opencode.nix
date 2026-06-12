{ den, inputs, lib, pkgs, ... }:
{
  den.aspects.opencode = {
    maid = { user, ... }: {
      packages = [ pkgs.opencode ];
      file.xdg_config."opencode".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/opencode";
    };

    nixos =
      { pkgs, ... }:
      {
        environment.systemPackages = with pkgs; [
          opencode-desktop
        ];
      };
  };
}
