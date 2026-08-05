{ den, inputs, lib, pkgs, ... }: {
  den.aspects.poweredge = {
    includes = [
      den.aspects.server.core
      den.aspects.server.sops
      den.aspects.server.nextcloud
      den.aspects.server.immich
      den.aspects.server.obsidian-collab
      den.aspects.server.nc-rag
    ];

    nixos = { config, lib, pkgs, ... }: {
      imports = [
        inputs.disko.nixosModules.disko
        ./_disko.nix
        ./_hardware-configuration.nix
      ];
      nix.settings.trusted-users = [ "likivik" ];

      services.openssh = {
        enable = true;
        settings = {
          PermitRootLogin = "no";
          PasswordAuthentication = false;
        };
      };

      users.users.likivik = {
        isNormalUser = true;
        extraGroups = [ "wheel" ];
        hashedPassword = "$y$j9T$CflOiBqf7adw8VPM1HjjD0$I.UH24kDyF8m75kAe3c4pO87oujxnUah7vBIDuTetR9";
        openssh.authorizedKeys.keys = [
          # hermes@erebus
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
          # likivik@traversal
          "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
          # likivik@serenity
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
        ];
      };

      # Rootless podman was attempted (per-service users, subuid/subgid,
      # linger, sdnotify) but rootless has known issues with pasta port
      # forwarding on podman 5.x — connections accepted but immediately
      # dropped. Reverted to rootful: simpler, works. Containers run as
      # root on this single-tenant host.

      security.sudo.extraRules = [{
        users = [ "likivik" ];
        commands = [{ command = "ALL"; options = [ "NOPASSWD" ]; }];
      }];

      sops.secrets."nextcloud/admin-password" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud";
        group = "nextcloud";
        mode = "0600";
      };

      sops.secrets."resend/api-key" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "nextcloud";
        group = "nextcloud";
        mode = "0600";
      };

      sops.secrets."tailscale/auth-key" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
      };

      sops.secrets."cloudflare/poweredge-tunnel-token" = {
        sopsFile = ../../../secrets/poweredge/secrets.yaml;
        owner = "root";
        group = "root";
        mode = "0400";
      };

      services.tailscale.authKeyFile =
        config.sops.secrets."tailscale/auth-key".path;
      services.tailscale.extraUpFlags = lib.mkAfter [
        "--advertise-tags=tag:server,tag:exit-node"
        "--advertise-exit-node"
        "--advertise-routes=192.168.0.100/32"
        "--accept-routes"
        "--exit-node=100.80.80.98"
      ];

      systemd.services.tailscale-serve = {
        description = "Tailscale Serve — HTTPS proxy to Nextcloud + Immich";
        after = [ "tailscaled.service" "tailscaled-autoconnect.service" ];
        wants = [ "tailscaled.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          ${lib.getExe pkgs.tailscale} serve --bg --https=443 http://127.0.0.1:80
          ${lib.getExe pkgs.tailscale} serve --bg --https=8443 http://127.0.0.1:3001
          ${lib.getExe pkgs.tailscale} serve --bg --https=5984 http://127.0.0.1:5984
          ${lib.getExe pkgs.tailscale} serve --bg --https=8787 http://127.0.0.1:8787
        '';
      };

      services.fail2ban = {
        enable = true;
        jails.nextcloud = {
          filter = {
            Definition = {
              failregex = "^.*\"remoteAddr\":\"<HOST>\".*Login failed.*$";
              ignoreregex = "";
            };
          };
          settings = {
            enabled = true;
            backend = "auto";
            port = "80,443";
            protocol = "tcp";
            maxretry = 5;
            bantime = "86400";
            findtime = "43200";
            logpath = "/tank/nextcloud/data/nextcloud.log";
          };
        };
      };

      # Disable the legacy NixOS cloudflared binary service —
      # the podman container in aspects/server/cloudflare-tunnel/default.nix
      # is its replacement. Both would conflict on the same tunnel token.
      systemd.services.cloudflared-poweredge = {
        enable = false;
        wantedBy = [];
        serviceConfig = { ExecStart = "/bin/true"; };
      };

      # Podman 0.0.0.0:X:X publishes work; 127.0.0.1:X:X silently drops
      # packets after DNAT on this NixOS+podman. Firewall restricts the
      # published ports to loopback only (not exposed to LAN).
      # Compare erebus kokoro-tts (works, 0.0.0.0) vs falkordb (broken, 127.0.0.1).
      networking.firewall.interfaces.eno1.allowedTCPPorts = lib.mkForce [ ];
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = lib.mkForce [ ];
      networking.firewall.interfaces.lo.allowedTCPPorts = lib.mkForce [ 2000 6333 6334 8000 ];
      # 8GB swapfile on root SSD
      swapDevices = [{
        device = "/swapfile";
        size = 8192; # 8GB
      }];

      boot.supportedFilesystems = [ "zfs" ];
      boot.zfs.forceImportRoot = false;
      boot.zfs.extraPools = [ "tank" ];
      networking.hostId = "5a099923";

      services.zfs.autoScrub.enable = true;

      services.zfs.autoSnapshot = {
        enable = true;
        frequent = 0;
        hourly = 36;
        daily = 30;
        weekly = 4;
        monthly = 3;
      };

      services.postgresqlBackup = {
        enable = true;
        startAt = "*-*-* 04:00:00";
        databases = [ "nextcloud" "immich" ];
        location = "/tank/backups/postgresql";
        compression = "gzip";
      };
    };
  };
}