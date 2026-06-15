{ den, ... }:
{
  den.aspects.git = {
    nixos = { pkgs, ... }: {
      environment.systemPackages = with pkgs; [
        git
        git-extras
        gh
      ];
    };

    maid = { user, ... }: {
      file.xdg_config."git".source =
        "/Storage/Git/spectacle/modules/users/likivik/dotfiles/git";
      file.xdg_config."gh".source =
        "/Storage/Git/spectacle/modules/users/likivik/dotfiles/gh";
    };
  };
}
