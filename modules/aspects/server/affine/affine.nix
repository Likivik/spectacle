{ inputs, den, lib, ... }: {
  den.aspects.server.affine = {
    nixos = { config, pkgs, lib, ... }: let
      affine-dir = "/var/lib/affine";
    in {
      # Podman requires a containers policy to pull images from registries
      environment.etc."containers/policy.json".text = builtins.toJSON {
        default = [{ type = "insecureAcceptAnything"; }];
      };

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

      systemd.services.affine = {
        description = "AFFiNE Self-hosted";
        after = [ "network-online.target" "podman.service" ];
        wants = [ "network-online.target" "podman.service" ];
        wantedBy = [ "multi-user.target" ];

        preStart = ''
          ${pkgs.coreutils}/bin/mkdir -p ${affine-dir}
          ${pkgs.coreutils}/bin/cp -n ${./affine-compose/.env} ${affine-dir}/.env 2>/dev/null || true
        '';

        serviceConfig = {
          WorkingDirectory = affine-dir;
          ExecStart = "${pkgs.docker-compose}/bin/docker-compose up --remove-orphans";
          ExecStop = "${pkgs.docker-compose}/bin/docker-compose down";
          Environment = [
            "PATH=${pkgs.podman}/bin:${pkgs.docker-compose}/bin:${pkgs.coreutils}/bin:${pkgs.gnugrep}/bin:${pkgs.findutils}/bin:${pkgs.bash}/bin:${pkgs.gnused}/bin"
          ];
          EnvironmentFile = [ "${affine-dir}/docker-host.env" ];
          Restart = "on-failure";
          RestartSec = 10;
        };
      };

      system.activationScripts."affine-seed" = lib.stringAfter (
        lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
      ) ''
        ${pkgs.coreutils}/bin/mkdir -p ${affine-dir}

        if [ ! -f ${affine-dir}/docker-compose.yml ]; then
          ${pkgs.coreutils}/bin/cp ${./affine-compose/docker-compose.yml} ${affine-dir}/docker-compose.yml
        fi

        if [ ! -f ${affine-dir}/.env ]; then
          ${pkgs.coreutils}/bin/cp ${./affine-compose/.env} ${affine-dir}/.env
        fi

        # Create storage directories
        ${pkgs.coreutils}/bin/mkdir -p ${affine-dir}/storage
        ${pkgs.coreutils}/bin/mkdir -p ${affine-dir}/config
        ${pkgs.coreutils}/bin/mkdir -p ${affine-dir}/postgres/pgdata

        ${pkgs.coreutils}/bin/chown -R root:root ${affine-dir}

        # Ensure DOCKER_HOST is set for docker-compose
        ${pkgs.coreutils}/bin/echo "DOCKER_HOST=unix:///run/podman/podman.sock" > ${affine-dir}/docker-host.env
      '';
    };
  };
}
