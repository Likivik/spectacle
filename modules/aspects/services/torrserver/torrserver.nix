# Peripherals
{ den, inputs, ... }:

{
  flake-file.inputs = {
    torrserver.url = "github:YouROK/TorrServer";
  };

  den.aspects.torrserver = {
    user = { user, ... }: {
      nixos.users.users.${user.userName}.extraGroups = [ "torrserver" ];
      nixos.services.torrserver.torrentsDir = "/home/${user.userName}/Torrents";
    };

    nixos =
      { config, ... }:
      {
        imports = [ inputs.torrserver.nixosModules.default ]; # import torrserver flake, so that config options become available!
        # "https://github.com/YouROK/TorrServer/blob/master/nix/modules/nixos.nix"
        services.torrserver = {
          enable = true;
          maxCacheSize = "5GB";
          enableDLNA = true;
        };
      };
  };
}
