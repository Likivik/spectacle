{ den, inputs, lib, pkgs, ... }: {
  den.aspects.poweredge = {
    includes = [
      den.aspects.server.core
      den.aspects.server.sops
      den.aspects.server.nextcloud
      den.aspects.server.immich
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
          # erebus (VPS provider default)
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIEhOOKKg6lHLhp2x3lAIg6bFheG8SlN+vsnFeTtIRBLo root@bistre-prase24161"
          # hermes@erebus
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIECMxs9cBFN8Adq8AJ9I62gVNFTkgNkr0ikg+VkWbHx1 hermes@erebus"
          # traversal
          "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDLeI2EqFsNLBPNIi/neXss0yZ3Q0vLevkiK5gfF5Fc+Zo0i9Nf0JPPkq3ak+uc5wJvumSvMAgO+gUUxDbQ6ieMZKCU6HSEhcQvjiHKczyYx+mDxxz6TXnd9TQRUFwmM/u/5kocl9PIwzjDnEdC/84H4sKiv9tmCy6Lv97VpdTYwkYerNWPm3wiapfGROHcS1WjKFOTD7+S++SQLDzir07W509b15HzgiP0Mk7Jdcc3axfIVl/FykGUQeYEFCram0XHvlDIB4yCb9rFxVACQXvUFgXLLb942lvoKeg5d2HbOxLXRVFlJJCnJlYQB3aKis983zjNmZ18Pm21YYvG6vmH traversal-likivik-2024-07-rsa"
          # likivik@gmail.com
          "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPyWUPBV/fxkioRPFJ5ws3XQYwMX0hzo6SmQSJkLSV5w likivik@gmail.com"
        ];
      };

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

      sops.secrets."tailscale/auth-key" = {
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
      ];

      boot.kernelParams = [ "elevator=none" ];

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
    };
  };
}
