{ den, lib, inputs, pkgs, ... }:

{
  den.aspects.server.risuai = {
    nixos = { config, lib, pkgs, ... }:
    let
      port = 9099;
      dataDir = "/var/lib/risuai";
    in {
      # RisuAI runs in a rootless podman container — see aspect `container`
      # for OCI backend wiring. Native systemd unit launches the container.

      # Image pulled on first activation
      virtualisation.podman.enable = true;

      # Storage path on host (persists across rebuilds)
      systemd.tmpfiles.rules = [
        "d ${dataDir} 0755 nobody nogroup -"
      ];

      # Systemd unit — run container rootless as 'nobody' since RisuAI binds
      # to a fixed port and writes to /app/save (mounted from dataDir).
      # Whitelist via firewall stays in Tailscale.
      systemd.services.risuai = {
        description = "RisuAI — AI chat client (rootless podman)";
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];

        serviceConfig = {
          Type = "simple";
          User = "nobody";
          Group = "nogroup";
          Restart = "always";
          RestartSec = "10s";
          ExecStartPre = "${lib.getExe pkgs.podman}/bin/podman pull ghcr.io/kwaroran/risuai:latest";
          ExecStart = lib.concatStringsSep " " [
            "${lib.getExe pkgs.podman}/bin/podman run"
            "--name risuai"
            "--rm"
            "--publish ${toString port}:6001"
            "--volume ${dataDir}:/app/save"
            "ghcr.io/kwaroran/risuai:latest"
          ];
          ExecStop = "${lib.getExe pkgs.podman}/bin/podman stop risuai";
        };
      };

      # Tailscale-only exposure (matches ST aspect pattern)
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ port ];
    };
  };
}