{ den, lib, inputs, pkgs, ... }:

{
  den.aspects.server.pocketrisu = {
    nixos = { config, lib, pkgs, ... }:
    let
      port = 9099;
      dataDir = "/var/lib/pocketrisu";
      image = "ghcr.io/pocketrisu/pocketrisu:latest";
      podman = lib.getExe pkgs.podman;
      startScript = pkgs.writeShellScript "pocketrisu-start" ''
        exec ${podman} run \
          --name pocketrisu \
          --rm \
          --publish 127.0.0.1:${toString port}:6001 \
          --volume ${dataDir}:/app/save \
          ${image}
      '';
    in {
      virtualisation.podman.enable = true;

      systemd.tmpfiles.rules = [
        "d ${dataDir} 0755 root root -"
      ];

      systemd.services.pocketrisu-prepull = {
        description = "Pull PocketRisu container image";
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = "${podman} pull ${image}";
        };
      };

      systemd.services.pocketrisu = {
        description = "PocketRisu — self-hosted AI roleplay chat (system podman)";
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" "pocketrisu-prepull.service" ];
        wants = [ "network-online.target" ];

        serviceConfig = {
          Type = "simple";
          Restart = "always";
          RestartSec = "10s";
          TimeoutStartSec = "300s";
          ExecStart = "${startScript}";
          ExecStop = "${podman} rm -f pocketrisu 2>/dev/null || true";
        };
      };

    };
  };
}
