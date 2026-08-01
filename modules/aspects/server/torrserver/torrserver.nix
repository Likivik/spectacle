# Peripherals
{ den, inputs, ... }:

{
  flake-file.inputs = {
    torrserver.url = "github:YouROK/TorrServer";
  };

  den.aspects.torrserver = {
    # TODO: make user management dynamic instead of hardcoding likivik+watcher
    # (user block causes Den to evaluate nixos block per-user, duplicating
    #  option declarations from the torrserver flake module import)
    nixos =
      { config, ... }:
      {
        imports = [ inputs.torrserver.nixosModules.default ];
        services.torrserver = {
          enable = true;
          maxCacheSize = "5GB";
          enableDLNA = true;
          torrentsDir = "/Storage/Torrents";
        };
        users.users.likivik.extraGroups = [ "torrserver" ];
        users.users.watcher.extraGroups = [ "torrserver" ];
      };
  };
}
