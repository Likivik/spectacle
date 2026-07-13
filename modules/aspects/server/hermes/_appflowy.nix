{ config, pkgs, lib }: let
  appflowy-dir = "/var/lib/appflowy-cloud";
in {
  systemd.services.appflowy-cloud = {
    description = "AppFlowy Cloud (Self-hosted)";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];

    preStart = ''
      mkdir -p ${appflowy-dir}
      cp -n ${./appflowy-compose/.env.example} ${appflowy-dir}/.env 2>/dev/null || true
    '';

    serviceConfig = {
      WorkingDirectory = appflowy-dir;
      ExecStart = "${pkgs.docker-compose}/bin/docker-compose up --remove-orphans";
      ExecStop = "${pkgs.docker-compose}/bin/docker-compose down";
      Restart = "on-failure";
      RestartSec = 10;
    };
  };

  # Seed the AppFlowy Cloud compose files and .env
  system.activationScripts."appflowy-cloud-seed" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    mkdir -p ${appflowy-dir}

    # Copy docker-compose.yml if not present
    if [ ! -f ${appflowy-dir}/docker-compose.yml ]; then
      cp ${./appflowy-compose/docker-compose.yml} ${appflowy-dir}/docker-compose.yml
    fi

    # Copy .env.example as base if .env doesn't exist
    if [ ! -f ${appflowy-dir}/.env ]; then
      cp ${./appflowy-compose/.env.example} ${appflowy-dir}/.env
    fi

    chown -R root:root ${appflowy-dir}
  '';
}
