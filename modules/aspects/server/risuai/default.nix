{ den, lib, inputs, pkgs, ... }:

{
  den.aspects.server.risuai = {
    nixos = { config, lib, pkgs, ... }:
    let
      port = 9099;
      dataDir = "/var/lib/risuai";
      image = "ghcr.io/kwaroran/risuai:latest";
      podman = "${lib.getExe pkgs.podman}";
    in {
      virtualisation.podman.enable = true;

      # Writable storage for RisuAI saves (chars, lorebooks, plots)
      systemd.tmpfiles.rules = [
        "d ${dataDir} 0755 root root -"
      ];

      # Pre-pull image on activation
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

      # Long-running container (system podman, NOT rootless — avoids subuid mess)
      systemd.services.risuai = {
        description = "RisuAI — AI chat client (system podman)";
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" "risuai-prepull.service" ];
        wants = [ "network-online.target" ];

        serviceConfig = {
          Type = "simple";
          Restart = "always";
          RestartSec = "10s";
          TimeoutStartSec = "300s";
          # Force-stop the container, then re-run with --rm so cleanup happens
          ExecStop = "${podman} rm -f risuai 2>/dev/null || true";
          ExecStart = "${podman} run \
            --name risuai \
            --rm \
            --publish ${toString port}:6001 \
            --volume ${dataDir}:/app/save \
            ${image}";
        };
      };

      # Tailscale-only exposure (matches ST aspect pattern)
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ port ];
    };
  };
}