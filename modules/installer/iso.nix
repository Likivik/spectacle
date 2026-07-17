{
  perSystem =
    { pkgs, ... }:
    let
      eval = import (pkgs.path + "/nixos/lib/eval-config.nix") {
        system = "x86_64-linux";
        modules = [ ./_fleet-installer.nix ];
      };
    in
    {
      packages.installer = eval.config.system.build.isoImage;
    };
}
