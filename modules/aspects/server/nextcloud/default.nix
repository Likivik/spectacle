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
          overwritehost = "nextcloud.filepath.ru";
          "overwrite.cli.url" = "https://nextcloud.filepath.ru";
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
          allow_local_remote_servers = true;
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
            # ssl.termination=true: Tailscale-serve terminates TLS, Collabora
            # receives plaintext HTTP from Nextcloud php-fpm over loopback.
            # alias_groups.mode=groups: allow both filepath.ru (public) and
            # the tailnet host (poweredge.oryx-galaxy.ts.net) to open docs.
            # 'domain' sets the WOPI host allowlist regex; pipe-separates
            # multiple hosts per Collabora docs.
            extra_params = "--o:ssl.enable=false --o:ssl.termination=true --o:alias_groups.mode=groups";
            domain = "nextcloud\\.filepath\\.ru|poweredge\\.oryx\\-galaxy\\.ts\\.net";
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
        "opcache.jit" = "tracing";
        "opcache.jit_buffer_size" = "128M";
      };

      # Ensure opcache + JIT enabled in FPM pool
      services.phpfpm.pools.nextcloud.phpOptions = ''
        opcache.enable=1
        opcache.enable_cli=0
        opcache.interned_strings_buffer=16
        opcache.max_accelerated_files=10000
        opcache.memory_consumption=256
        opcache.revalidate_freq=1
        opcache.fast_shutdown=1
        opcache.jit=tracing
        opcache.jit_buffer_size=128M
      '';

      # Nginx: brotli compression + HTTP/2
      services.nginx = {
        additionalModules = [ pkgs.nginxModules.brotli ];
        appendHttpConfig = ''
          brotli on;
          brotli_comp_level 6;
          brotli_types
            text/plain
            text/css
            text/javascript
            application/javascript
            application/json
            application/xml
            application/xml+rss
            image/svg+xml
            font/woff
            font/woff2;
        '';
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

      # Configure Nextcloud Office (richdocuments) WOPI bridge to local
      # Collabora container. Idempotent — occ config:app:set overwrites
      # the same key on every deploy. Runs after install so app:enable
      # for richdocuments has already happened via extraApps.
      systemd.services.nextcloud-configure-richdocuments = {
        description = "Configure richdocuments WOPI bridge to Collabora";
        after = [ "nextcloud-setup.service" "podman-collabora-code.service" ];
        wants = [ "nextcloud-setup.service" "podman-collabora-code.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig.Type = "oneshot";
        serviceConfig.RemainAfterExit = true;
        script = ''
          ${config.services.nextcloud.occ}/bin/nextcloud-occ \
            config:app:set richdocuments wopi_url \
            --value="http://127.0.0.1:9980"
          ${config.services.nextcloud.occ}/bin/nextcloud-occ \
            config:app:set richdocuments wopi_allow_list \
            --value="127.0.0.1"
          ${config.services.nextcloud.occ}/bin/nextcloud-occ \
            config:app:set richdocuments public_wopi_url \
            --value="https://poweredge.oryx-galaxy.ts.net"
        '';
      };

      services.zfs.autoScrub.enable = true;
    };
  };
}
