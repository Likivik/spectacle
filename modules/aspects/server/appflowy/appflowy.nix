{ inputs, den, lib, ... }: {
  den.aspects.server.appflowy = {
    nixos = { config, pkgs, lib, ... }: let
      appflowy-dir = "/var/lib/appflowy-cloud";
    in {
      # Podman runtime for containers
      systemd.sockets.podman = {
        description = "Podman Socket";
        wantedBy = [ "sockets.target" ];
        socketConfig = {
          ListenStream = "/run/podman/podman.sock";
          SocketUser = "root";
          SocketMode = "0660";
        };
      };

      systemd.services.podman = {
        description = "Podman API Service";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          ExecStart = "${pkgs.podman}/bin/podman system service --time=0";
          Restart = "always";
          RestartSec = 5;
        };
      };

      # AppFlowy Cloud stack
      systemd.services.appflowy-cloud = {
        description = "AppFlowy Cloud (Self-hosted)";
        after = [ "network-online.target" "podman.service" ];
        wants = [ "network-online.target" "podman.service" ];
        wantedBy = [ "multi-user.target" ];

        preStart = ''
          ${pkgs.coreutils}/bin/mkdir -p ${appflowy-dir}
          ${pkgs.coreutils}/bin/cp -n ${./appflowy-compose/.env.example} ${appflowy-dir}/.env 2>/dev/null || true
        '';

        serviceConfig = {
          WorkingDirectory = appflowy-dir;
          ExecStart = "${pkgs.docker-compose}/bin/docker-compose up --remove-orphans";
          ExecStop = "${pkgs.docker-compose}/bin/docker-compose down";
          Environment = [
            "PATH=${pkgs.podman}/bin:${pkgs.docker-compose}/bin:${pkgs.coreutils}/bin:${pkgs.gnugrep}/bin:${pkgs.findutils}/bin:${pkgs.bash}/bin:${pkgs.gnused}/bin"
            "DOCKER_HOST=unix:///run/podman/podman.sock"
          ];
          Restart = "on-failure";
          RestartSec = 10;
        };
      };

      # Seed compose files
      system.activationScripts."appflowy-cloud-seed" = lib.stringAfter (
        lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
      ) ''
        ${pkgs.coreutils}/bin/mkdir -p ${appflowy-dir}

        if [ ! -f ${appflowy-dir}/docker-compose.yml ]; then
          ${pkgs.coreutils}/bin/cp ${./appflowy-compose/docker-compose.yml} ${appflowy-dir}/docker-compose.yml
        fi

        if [ ! -f ${appflowy-dir}/.env ]; then
          ${pkgs.coreutils}/bin/cp ${./appflowy-compose/.env.example} ${appflowy-dir}/.env
        fi

        ${pkgs.coreutils}/bin/chown -R root:root ${appflowy-dir}
      '';
    };
  };
}
