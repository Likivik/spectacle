{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.sillybunny = {
    nixos = { config, lib, pkgs, ... }:
    let
      pkg = import ../../../../pkgs/sillybunny/default.nix { inherit pkgs; };
      defaultConfig = "${pkg}/lib/node_modules/sillybunny/default/config.yaml";
      dataDir = "/var/lib/SillyBunny";
      port = 8003;
      node = pkgs.nodejs_22;
    in {
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ port ];

      users.groups.sillybunny = { };
      users.users.sillybunny = {
        isSystemUser = true;
        group = "sillybunny";
        home = dataDir;
        createHome = false;
      };

      systemd.tmpfiles.rules = [
        "d ${dataDir} 0755 sillybunny sillybunny -"
        "f ${dataDir}/server.log 0644 sillybunny sillybunny -"
      ];

      systemd.services.sillybunny = {
        description = "SillyBunny — mobile-friendly SillyTavern fork (Bun runtime, custom nav, mobile-first layout)";
        wantedBy = [ "multi-user.target" ];
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];

        serviceConfig = {
          Type = "simple";
          User = "sillybunny";
          Group = "sillybunny";
          WorkingDirectory = dataDir;
          # SillyBunny's server.js runs process.chdir(serverDirectory) before
          # parsing CLI args, so WorkingDirectory=/var/lib/SillyBunny is ignored.
          # Pass --configPath and --dataRoot explicitly so the relative "./config.yaml"
          # default resolved against /nix/store... (read-only) doesn't apply.
          ExecStart = "${lib.getExe node} --no-warnings ${pkg}/lib/node_modules/sillybunny/server.js --listen --listenAddressIPv4=0.0.0.0 --port ${toString port} --enableIPv4 true --browserLaunchEnabled false --configPath ${dataDir}/config.yaml --dataRoot ${dataDir}/data";
          Restart = "always";
          RestartSec = "10s";
          TimeoutStartSec = "300s";
          Environment = [
            "NODE_ENV=production"
            "NPM_CONFIG_LOGLEVEL=warn"
          ];
          StandardOutput = "append:${dataDir}/server.log";
          StandardError = "append:${dataDir}/server.log";
        };

        preStart = ''
          # Drop NUL config from previous bad runs and re-seed from package default.
          if [ -L ${dataDir}/config.yaml ]; then
            rm ${dataDir}/config.yaml
          fi
          if [ ! -f ${dataDir}/config.yaml ] && [ -f ${defaultConfig} ]; then
            cp ${defaultConfig} ${dataDir}/config.yaml
            chmod 0600 ${dataDir}/config.yaml
          fi
          # Force listen/port so even if CLI args get dropped, server still binds.
          if [ -f ${dataDir}/config.yaml ]; then
            sed -i 's/^listen:.*/listen: true/' ${dataDir}/config.yaml
            sed -i 's/^port:.*/port: ${toString port}/' ${dataDir}/config.yaml
            # Whitelist the tailscale subnet so phones on tailnet can connect.
            grep -q '100.64.0.0/10' ${dataDir}/config.yaml || \
              sed -i '/^whitelist:/a\  - 100.64.0.0/10' ${dataDir}/config.yaml
          fi
        '';
      };
    };
  };
}
