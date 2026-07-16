{
  perSystem = { pkgs, ... }: {
    packages.installer = (pkgs.nixos {
      imports = [ ./_fleet-installer.nix ];
    }).config.system.build.isoImage;
  };
}
