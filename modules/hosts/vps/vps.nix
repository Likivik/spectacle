{ den, inputs, lib, pkgs, ... }:
let
  lockSshToTailscale = false;
in
{
  den.aspects.vps = {
    includes = [
      den.aspects.core
      den.aspects.core.tailscale
      den.aspects.server.hermes-agent
      den.aspects.server.sops
    ];

    nixos = { config, pkgs, lib, ... }: {
      imports = [
        inputs.disko.nixosModules.disko
        ./_disko.nix
        ./_hardware-configuration.nix
      ];

      services.openssh = {
        enable = true;
        openFirewall = true;
        settings = {
          PermitRootLogin = "no";
          PasswordAuthentication = false;
        };
      };

      networking.firewall = {
        enable = true;
        interfaces.tailscale0.allowedTCPPorts = [
          9119
          8642
        ];
        interfaces.tailscale0.allowedUDPPorts = [ 41641 ];
      } // (if lockSshToTailscale then {
        allowedTCPPorts = lib.mkForce [ ];
        interfaces.tailscale0.allowedTCPPorts = [ 22 9119 8642 ];
      } else {
        allowedTCPPorts = lib.mkForce [ 22 ];
      });

      systemd.tmpfiles.rules = [
        "d /var/lib/hermes/.hermes 0750 hermes hermes - -"
        "L+ /var/lib/hermes/.hermes/config.yaml - - - - /var/lib/spectacle/modules/hosts/vps/hermes-config.yaml"
      ];

      users.groups.hermes = { };
      users.users.hermes.extraGroups = [ "likivik" ];

      systemd.paths."hermes-config-watcher" = {
        pathConfig = {
          PathChanged = "/var/lib/spectacle/modules/hosts/vps/hermes-config.yaml";
        };
      };
      systemd.services."hermes-config-watcher" = {
        serviceConfig = {
          Type = "simple";
          ExecStart = "${pkgs.systemd}/bin/systemctl restart hermes-agent.service";
        };
      };

      systemd.services."hermes-config-autocommit" = {
        serviceConfig = {
          Type = "oneshot";
          User = "likivik";
          WorkingDirectory = "/var/lib/spectacle";
        };
        script = ''
          if ! git diff --quiet modules/hosts/vps/hermes-config.yaml; then
            git add modules/hosts/vps/hermes-config.yaml
            git -c user.name=hermes-agent \
               -c user.email=hermes-agent@vps.local \
               commit -m "hermes-agent: auto-save config edit"
          fi
        '';
      };
      systemd.timers."hermes-config-autocommit" = {
        wantedBy = [ "timers.target" ];
        timerConfig.OnCalendar = "daily";
      };

      sops.secrets = {
        "tailscale/auth-key" = {
          sopsFile = ../../../secrets/vps/secrets.yaml;
          key = "tailscale_auth_key";
          owner = "root";
          group = "root";
          mode = "0600";
        };
        "hermes/openrouter-api-key" = {
          sopsFile = ../../../secrets/vps/secrets.yaml;
          key = "hermes_openrouter_api_key";
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
      };

      services.tailscale.authKeyFile =
        config.sops.secrets."tailscale/auth-key".path;

      services.hermes-agent.environment = { };

      system.activationScripts."hermes-secrets-env" =
        lib.stringAfter [ "hermes-agent-setup" ] ''
          echo "OPENROUTER_API_KEY=$(${pkgs.coreutils}/bin/cat ${config.sops.secrets."hermes/openrouter-api-key".path})" \
            >> /var/lib/hermes/.hermes/.env
        '';
    };
  };
}
