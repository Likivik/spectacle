{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.immich = {
    nixos = { config, lib, pkgs, ... }: {
      services.immich = {
        enable = true;
        mediaLocation = "/tank/immich";
        host = "0.0.0.0";
        port = 3001;

        "machine-learning".enable = true;

        database.createDB = true;
        redis.enable = true;
      };

      services.immich.openFirewall = false;

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 3001 ];
    };
  };
}
