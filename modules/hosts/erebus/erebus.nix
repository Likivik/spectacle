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
      den.aspects.server.scaratec
      den.aspects.server.sillytavern
      den.aspects.server.sillybunny
      den.aspects.server.fishaudio-proxy
      den.aspects.server.pocketrisu
      den.aspects.server.n8n
      den.aspects.tts
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

      nix.settings = {
        trusted-users = [ "likivik" ];
        require-sigs = false;
      };

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
          3443
          8880
        ];
        interfaces.tailscale0.allowedUDPPorts = [ 41641 ];
      } // (if lockSshToTailscale then {
        allowedTCPPorts = lib.mkForce [ ];
        interfaces.tailscale0.allowedTCPPorts = [ 22 9119 8642 3443 8001 8003 8880 ];
      } else {
        allowedTCPPorts = lib.mkForce [ 22 ];
      });

      swapDevices = [ { device = "/swapfile"; size = 4096; } ];

      users.users.hermes.extraGroups = [ "users" ];

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
        "hermes-mitmproxy/llm-providers/opencode/api-key1" = {
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
        "hermes-mitmproxy/llm-providers/opencode/api-key3" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        # Added so LiteLLM (graphiti-free pool) can read them at runtime.
        # Keys already present in secrets/erebus/secrets.yaml (encrypted).
        "hermes-mitmproxy/llm-providers/groq/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        "hermes-mitmproxy/llm-providers/huggingface/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        "hermes-mitmproxy/llm-providers/mistral/api-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        # Langfuse Cloud (spend/observability dashboard) — keys already in secrets.yaml.
        "hermes-mitmproxy/langfuse/public-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        "hermes-mitmproxy/langfuse/secret-key" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "hermes-mitmproxy";
          group = "hermes-mitmproxy";
          mode = "0600";
        };
        "email/gmail/account1/adress" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "scaratec";
          group = "scaratec";
          mode = "0400";
        };
        "email/gmail/account1/app-password" = {
          sopsFile = ../../../secrets/erebus/secrets.yaml;
          owner = "scaratec";
          group = "scaratec";
          mode = "0400";
        };
      };

      users.users.likivik.initialHashedPassword = "$6$1FZNn7nnzCyHhgke$jyU9Ou3/5F2IHWLMGPc/bCDMQctvmKRXWCT6SAmUjhnHXmiOVFMhh4vVFxAoHZ8izk.QhQoyFZlvut6WOxXgb0";
      users.users.likivik.openssh.authorizedKeys.keys = [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
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
        "--advertise-tags=tag:server,tag:exit-node,tag:nix-binary-caches"
        "--advertise-exit-node"
        "--advertise-connector"
      ];

      # Tailscale app connector requires IP forwarding to route traffic
      # for the configured domains (install.determinate.systems,
      # cache.flakehub.com, nix-community.cachix.org, hyprland.cachix.org,
      # cache.nixos.org) through this host to the public internet.
      boot.kernel.sysctl."net.ipv4.ip_forward" = 1;
      boot.kernel.sysctl."net.ipv6.conf.all.forwarding" = 1;

      systemd.services.tailscale-serve-pocketrisu = {
        description = "Tailscale HTTPS serve for PocketRisu";
        after = [ "network-online.target" "tailscaled.service" "pocketrisu.service" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = "${config.services.tailscale.package}/bin/tailscale serve --bg http://localhost:9099";
          ExecStop = "${config.services.tailscale.package}/bin/tailscale serve off || true";
        };
      };
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

      systemd.services.xray-trojan = {
        description = "xray Trojan+REALITY HTTP CONNECT proxy";
        after = [ "network-online.target" ];
        wants = [ "network-online.target" ];
        serviceConfig = {
          Type = "simple";
          User = "root";
          ExecStartPre =
            "${pkgs.bash}/bin/bash -ec 'if [ ! -f /opt/trojan/config.json ]; then echo \"no /opt/trojan/config.json — create it\" >&2; exit 1; fi'";
          ExecStart = "${pkgs.xray}/bin/xray run -c /opt/trojan/config.json";
          Restart = "on-failure";
          RestartSec = 5;
          LimitNOFILE = "infinity";
        };
      };

      systemd.tmpfiles.rules = [
        "d /opt/trojan 0700 root root - -"
      ];

      system.activationScripts."trojan-config" = lib.stringAfter [ "var" ] ''
        mkdir -p /opt/trojan
        ${pkgs.coreutils}/bin/cat > /opt/trojan/config.json << 'TROJANEOF'
{
  "inbounds": [{
    "tag": "http-in",
    "protocol": "http",
    "listen": "127.0.0.1",
    "port": 1081
  }],
  "outbounds": [{
    "tag": "trojan-reality",
    "protocol": "trojan",
    "settings": {
      "servers": [{
        "address": "5.180.172.173",
        "port": 443,
        "password": "5812d9fb-9a4b-489a-a89c-c2fbb0828481",
        "flow": ""
      }]
    },
    "streamSettings": {
      "network": "tcp",
      "security": "reality",
      "realitySettings": {
        "serverName": "www.google.com",
        "fingerprint": "edge",
        "publicKey": "ZVTSHN3DJ8u3ph7NqjSGfyfv4pTjSa4pseAF19fasEo",
        "shortId": "80da64",
        "spiderX": "/"
      }
    }
  }],
  "routing": {
    "domainStrategy": "AsIs",
    "rules": [
      { "type": "field", "ip": ["10.0.0.0/8", "100.64.0.0/10", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8"], "outboundTag": "direct" },
      { "type": "field", "ip": ["geoip:private"], "outboundTag": "direct" }
    ]
  }
}
TROJANEOF
        ${pkgs.coreutils}/bin/chmod 0600 /opt/trojan/config.json
      '';

      environment.systemPackages = with pkgs; [
        nodejs_22 uv xray git gh pkgs.jujutsu
        # Office document skills (docx/xlsx/powerpoint): soffice + pandoc + poppler
        # npm helpers `docx` and `pptxgenjs` are installed by the skill on first require
        libreoffice
        pandoc
        poppler-utils
      ];



    };
  };
}
