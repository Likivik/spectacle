{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.immich = {
    nixos = { config, lib, pkgs, ... }: {
      services.immich = {
        enable = true;
        mediaLocation = "/tank/data/immich";
        host = "0.0.0.0";
        port = 3001;

        machineLearning.enable = true;

        database.createDB = true;
        redis.createLocally = true;
      };

      services.immich.openFirewall = false;

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 3001 ];
    };
  };
}
