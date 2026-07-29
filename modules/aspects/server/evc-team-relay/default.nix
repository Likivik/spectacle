{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.evc-team-relay = {
    nixos = { config, lib, pkgs, ... }: {
      # Ensure Podman is available (Collabora already uses it)
      virtualisation.podman.enable = lib.mkDefault true;
      virtualisation.podman.dockerCompat = lib.mkDefault true;

      # Clone repo, setup data dirs, copy override + .env on activation
      system.activationScripts.evc-team-relay = lib.stringAfter [ "var" ] ''
        # Clone repo if not present
        if [ ! -d /opt/evc-team-relay ]; then
          ${pkgs.git}/bin/git clone https://github.com/entire-vc/evc-team-relay.git /opt/evc-team-relay
        fi

        # Copy docker-compose.override.yml from Nix store
        cp ${./docker-compose.override.yml} /opt/evc-team-relay/infra/docker-compose.override.yml

        # Create data directories on ZFS dataset
        mkdir -p /tank/evc-team-relay/{minio,uploads,backups,relay,caddy,caddy_config}
        mkdir -p /opt/evc-team-relay/data/postgres

        # Copy .env from sops-nix
        mkdir -p /etc/evc-team-relay
        if [ -f /etc/evc-team-relay/.env ]; then
          cp /etc/evc-team-relay/.env /opt/evc-team-relay/infra/.env
        fi
      '';

      # sops-nix secrets for EVC
      sops.secrets."evc-team-relay/.env" = {
        sopsFile = ../../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
        path = "/etc/evc-team-relay/.env";
      };

      # Systemd service to manage the compose stack
      systemd.services.evc-team-relay = {
        description = "EVC Team Relay - Obsidian collaboration";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = pkgs.writeShellScript "evc-start" ''
            cd /opt/evc-team-relay/infra
            ${pkgs.docker-compose}/bin/docker-compose up -d --build
          '';
          ExecStop = pkgs.writeShellScript "evc-stop" ''
            cd /opt/evc-team-relay/infra
            ${pkgs.docker-compose}/bin/docker-compose down
          '';
          Restart = "on-failure";
          RestartSec = 30;
        };
      };

      # Firewall
      networking.firewall.allowedTCPPorts = [ 80 443 8080 8444 ];
    };
  };
}
