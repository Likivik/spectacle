{ den, lib, ... }: let
  cfg = "gov-browser";
in {
  den.aspects.${cfg} = {
    nixos = { pkgs, ... }: let
      govBrowser = pkgs.callPackage ../../../../../pkgs/gov-browser-wrap {
        chromium-gost = pkgs.callPackage ../../../../../pkgs/chromium-gost { };
      };
    in {
      environment.systemPackages = [ govBrowser ];
    };
  };
}
