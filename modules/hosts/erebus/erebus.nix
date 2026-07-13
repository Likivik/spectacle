{ den, inputs, lib, pkgs, ... }:
let
  lockSshToTailscale = false;
in
{
  den.aspects.erebus = {
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

      boot.loader.grub = {
        enable = true;
        efiSupport = false;
      };
      boot.loader.systemd-boot.enable = lib.mkForce false;

      systemd.network.enable = true;
      networking.useNetworkd = true;

      systemd.network.networks."10-ens3" = {
        matchConfig.Name = "ens3";
        address = [ "148.253.214.185/32" ];
        routes = [
          { Gateway = "10.0.0.1"; }
          { Destination = "10.0.0.1/32"; }
        ];
        networkConfig.DNS = [ "8.8.8.8" "8.8.4.4" ];
      };

      nix.settings.trusted-users = [ "likivik" ];

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

      users.users.hermes.extraGroups = [ "likivik" ];

      sops.secrets = {
        "tailscale/auth-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "root";
          group = "root";
          mode = "0600";
        };
        "hermes/env" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
        };
        "hermes-mitmproxy/mitmproxy-ca" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        "hermes-mitmproxy/github/pat-hermes-full" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        "hermes-mitmproxy/llm-providers/openrouter/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        "hermes-mitmproxy/llm-providers/opencode/api-key2" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
      };

      users.users.likivik.initialHashedPassword = "$6$1FZNn7nnzCyHhgke$jyU9Ou3/5F2IHWLMGPc/bCDMQctvmKRXWCT6SAmUjhnHXmiOVFMhh4vVFxAoHZ8izk.QhQoyFZlvut6WOxXgb0";
      users.users.likivik.openssh.authorizedKeys.keys = [
        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
      ];

      security.sudo.extraRules = [
        {
          users = [ "likivik" ];
          commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
        }
        {
          users = [ "hermes" ];
          commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
        }
      ];

      services.tailscale.authKeyFile =
        config.sops.secrets."tailscale/auth-key".path;
      services.tailscale.extraUpFlags = lib.mkAfter [
        "--advertise-tags=tag:server,tag:exit-node"
        "--advertise-exit-node"
      ];

      systemd.services.fix-ts-gro = {
        description = "Fix UDP GRO forwarding for Tailscale exit node performance";
        wants = [ "network-online.target" ];
        after = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig.Type = "oneshot";
        script = ''
          ${pkgs.ethtool}/bin/ethtool -K ens3 rx-udp-gro-forwarding on rx-gro-list off
        '';
      };

      environment.systemPackages = [ pkgs.nodejs_22 ];

    };
  };
}
