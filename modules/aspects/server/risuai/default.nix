{ den, lib, inputs, pkgs, ... }:

let
  cfg = pkgs.writeShellScript "risuai-start" ''
    exec ${lib.getExe pkgs.podman} run \
      --name risuai \
      --rm \
      --publish 9099:6001 \
      --volume /var/lib/risuai:/app/save \
      ghcr.io/kwaroran/risuai:latest
  '';
in
{
  den.aspects.server.risuai = {
    nixos = { config, lib, pkgs, ... }:
    let
      port = 9099;
      dataDir = "/var/lib/risuai";
      image = "ghcr.io/kwaroran/risuai:latest";
      podman = lib.getExe pkgs.podman;
    in {
      virtualisation.podman.enable = true;

      systemd.tmpfiles.rules = [
        "d ${dataDir} 0755 root root -"
      ];

      systemd.services.risuai-prepull = {
        description = "Pull RisuAI container image";
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = "${podman} pull ${image}";
        };
      };

      systemd.services.risuai = {
        description = "RisuAI — AI chat client (system podman)";
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" "risuai-prepull.service" ];
        wants = [ "network-online.target" ];

        script = ''
          exec ${cfg}
        '';

        serviceConfig = {
          Type = "simple";
          Restart = "always";
          RestartSec = "10s";
          TimeoutStartSec = "300s";
          ExecStop = "${podman} rm -f risuai 2>/dev/null || true";
        };
      };

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ port ];
    };
  };
}