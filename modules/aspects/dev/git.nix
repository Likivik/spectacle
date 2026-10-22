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

    maid =
      { user, host, ... }:
      let
        gitRoot = import ../../../lib/git-root.nix host;
      in
      {
        file.xdg_config."git".source =
          "${gitRoot}/spectacle/modules/users/likivik/dotfiles/git";
        file.xdg_config."gh".source =
          "${gitRoot}/spectacle/modules/users/likivik/dotfiles/gh";
      };
  };
}
