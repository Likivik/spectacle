{ den, inputs, pkgs, ... }:

{
  flake-file.inputs = {
    noctalia = {
      url = "github:noctalia-dev/noctalia-shell/v5";
    };
  };

  den.aspects.desktop.desktopManagers.noctalia = {
    nixos = { config, pkgs, ... }: {
      nix.settings = {
        extra-substituters = [ "https://noctalia.cachix.org" ];
        extra-trusted-public-keys = [
          "noctalia.cachix.org-1:pCOR47nnMEo5thcxNDtzWpOxNFQsBRglJzxWPp3dkU4="
        ];
      };

      environment.systemPackages = [
        inputs.noctalia.packages.${pkgs.stdenv.hostPlatform.system}.default
      ];
    };

    maid = { user, ... }: {
      file.xdg_config."noctalia".source =
        "{{home}}/nixos-config/homes/${user.userName}/dotfiles/noctalia";
    };
  };
}
