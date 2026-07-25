{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.immich = {
    nixos = { config, lib, pkgs, ... }: {
      services.immich = {
        enable = true;
        mediaLocation = "/tank/immich";
        host = "127.0.0.1";
        port = 3001;

        "machine-learning".enable = true;

        database.createDB = true;
        redis.enable = true;
      };

      services.immich.openFirewall = false;
    };
  };
}
