{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.nextcloud = {
    nixos = { config, lib, pkgs, ... }: {
      virtualisation.podman.enable = lib.mkDefault true;

      services.nextcloud = {
        enable = true;
        hostName = lib.mkDefault "nextcloud.likivik.com";
        home = "/var/lib/nextcloud";
        datadir = "/tank/data/nextcloud";

        https = true;
        configureRedis = true;

        database.createLocally = true;

        config = {
          dbtype = lib.mkDefault "pgsql";
          adminuser = "admin";
          adminpassFile = config.sops.secrets."nextcloud/admin-password".path;
        };

        appstoreEnable = true;

        extraAppsEnable = true;
        extraApps = {
          inherit (pkgs.nextcloud32Packages.apps) calendar contacts notes tasks richdocuments;
        };

        autoUpdateApps.enable = true;
        autoUpdateApps.startAt = "*-*-* 04:00:00";
      };

      virtualisation.oci-containers = {
        backend = lib.mkDefault "podman";
        containers.collabora-code = {
          image = "collabora/code:latest";
          autoStart = true;
          ports = [ "127.0.0.1:9980:9980" ];
          extraOptions = [ "--cap-add=MKNOD" ];
          environment = {
            extra_params = "--o:ssl.enable=false --o:ssl.termination=true";
            domain = "nextcloud\\.likivik\\.com";
            dictionaries = "ru en";
          };
        };
      };

      services.nextcloud.phpOptions = {
        "memory_limit" = "1024M";
        "upload_max_filesize" = "16G";
        "post_max_size" = "16G";
        "max_execution_time" = "3600";
        "max_input_time" = "3600";
        "opcache.enable" = "1";
        "opcache.interned_strings_buffer" = "16";
        "opcache.max_accelerated_files" = "10000";
        "opcache.memory_consumption" = "256";
        "opcache.revalidate_freq" = "1";
        "opcache.fast_shutdown" = "1";
      };

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 80 443 ];

      services.zfs.autoScrub.enable = true;
    };
  };
}
