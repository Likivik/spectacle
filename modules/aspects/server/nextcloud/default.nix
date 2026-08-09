{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.nextcloud = {
    nixos = { config, lib, pkgs, ... }:
    let
      ncVersion = builtins.head (builtins.split "\\." config.services.nextcloud.package.version);
      ncApps = pkgs."nextcloud${ncVersion}Packages".apps;
    in {
      virtualisation.podman.enable = lib.mkDefault true;

      services.nextcloud = {
        enable = true;
        hostName = lib.mkDefault "nextcloud.filepath.ru";
        home = "/var/lib/nextcloud";
        datadir = "/tank/nextcloud";

        package = pkgs.nextcloud34;

        https = true;
        configureRedis = true;

        database.createLocally = true;

        maxUploadSize = "16G";

        imaginary.enable = true;

        poolSettings = {
          "pm" = "dynamic";
          "pm.max_children" = "120";
          "pm.start_servers" = "12";
          "pm.min_spare_servers" = "6";
          "pm.max_spare_servers" = "18";
          "pm.max_requests" = "500";
        };

        config = {
          dbtype = lib.mkDefault "pgsql";
          adminuser = "admin";
          adminpassFile = config.sops.secrets."nextcloud/admin-password".path;
        };

        appstoreEnable = true;

        settings = {
          default_phone_region = "RU";
          trusted_proxies = [ "127.0.0.1" "::1" ];
          forwarded_for_headers = [ "HTTP_CF_CONNECTING_IP" "HTTP_X_FORWARDED_FOR" ];
          overwriteprotocol = "https";
          maintenance_window_start = 3;
          twofactor_enforced = "true";
          log_type = "file";
          mail_smtpmode = "smtp";
          mail_smtphost = "smtp.resend.com";
          mail_smtpport = 587;
          mail_smtpsecure = "";
          mail_smtpauth = true;
          mail_smtpname = "resend";
          mail_from_address = "nextcloud";
          mail_domain = "filepath.ru";
          server_id = "poweredge";
          trusted_domains = [
            "poweredge.oryx-galaxy.ts.net"
            "nextcloud.filepath.ru"
          ];
          allowed_admin_ranges = [ "100.64.0.0/10" "fd7a:115c:a1e0::/48" ];
          loglevel = 2;
          logfile = "/tank/nextcloud/data/nextcloud.log";
          logfilemode = "0640";
          logtimezone = "Europe/Moscow";
          enable_previews = true;
          enabledPreviewProviders = [
            "OC\\Preview\\PNG"
            "OC\\Preview\\JPEG"
            "OC\\Preview\\GIF"
            "OC\\Preview\\BMP"
            "OC\\Preview\\XBitmap"
            "OC\\Preview\\MP3"
            "OC\\Preview\\TXT"
            "OC\\Preview\\MarkDown"
          ];
          "auth.bruteforce.protection.enabled" = true;
        };

        secrets.mail_smtppassword = config.sops.secrets."resend/api-key".path;

        extraAppsEnable = true;
        extraApps = {
          inherit (ncApps) calendar contacts notes tasks richdocuments
            deck collectives mail news bookmarks;
        };

        autoUpdateApps.enable = false;
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
            domain = "nextcloud\\.filepath\\.ru";
            dictionaries = "ru en";
          };
        };
      };

      services.nextcloud.phpOptions = {
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

      systemd.services.nextcloud-phpfpm.serviceConfig = {
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;
        NoNewPrivileges = true;
        LockPersonality = true;
        ReadWritePaths = [ "/tank/nextcloud" "/var/lib/nextcloud" ];
      };

      systemd.services.nextcloud-disable-app-api = {
        description = "Disable AppAPI — unnecessary bundled app";
        after = [ "nextcloud-setup.service" ];
        wants = [ "nextcloud-setup.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig.Type = "oneshot";
        serviceConfig.RemainAfterExit = true;
        script = ''
          ${config.services.nextcloud.occ}/bin/nextcloud-occ app:disable app_api 2>&1
        '';
      };

      services.zfs.autoScrub.enable = true;
    };
  };
}
