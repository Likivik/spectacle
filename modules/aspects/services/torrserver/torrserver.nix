# Peripherals
{ den, ... }:

{
  flake-file.inputs = {
    torrserver.url = "github:YouROK/TorrServer";
  };

  den.aspects.torrserver = {
    nixos =
      { config, ... }:
      {
        # "https://github.com/YouROK/TorrServer/blob/master/nix/modules/nixos.nix"
        services.torrserver = {
          enable = true;
          maxCacheSize = "5GB";
          enableDLNA = true;
        };
      };
  };
}
