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

      swapDevices = [ { device = "/swapfile"; size = 4096; } ];

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

      sops.age.keyFile = "/var/lib/sops/age-key.txt";

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

      users.users.likivik.openssh.authorizedKeys.keys = [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
      ];

      security.sudo.extraRules = [{
        users = [ "likivik" ];
        commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
      }];

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
