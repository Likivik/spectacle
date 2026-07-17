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

      boot.kernelParams = [ "elevator=none" ];

      services.zfs.autoScrub.enable = true;
    };
  };
}
