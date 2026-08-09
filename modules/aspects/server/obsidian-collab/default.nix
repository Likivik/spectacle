{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.obsidian-collab = {
    nixos = { config, lib, pkgs, ... }:
    let
      sopsFile = ../../../../secrets/poweredge/secrets.yaml;

      liveShareRepo = pkgs.applyPatches {
        name = "obsidian-live-share-src";
        src = inputs.obsidian-live-share;
        patches = [ ./liveshare-bind.patch ];
      };
      liveShareSrc = "${liveShareRepo}/server";

      liveShareServer = pkgs.buildNpmPackage {
        pname = "obsidian-live-share-server";
        version = "0.1.0";
        src = liveShareSrc;
        npmDepsHash = "sha256-duURSD3FBADhysJaJPMCI5e4sBjeaD8Yf/sPmaLc6eU=";
        nodejs = pkgs.nodejs_22;
      };
      syncMcpConfig = import ./_obsidian-sync-mcp.nix { inherit config pkgs lib; };
    in lib.mkMerge [
      {
      virtualisation.podman.enable = lib.mkDefault true;

      users.users.obsidian-live-share = {
        isSystemUser = true;
        group = "obsidian-live-share";
      };
      users.groups.obsidian-live-share = {};
      users.users.obsidian-publish = {
        isSystemUser = true;
        group = "obsidian-publish";
      };
      users.groups.obsidian-publish = {};

      systemd.tmpfiles.rules = [
        "d /var/lib/obsidian-live-share 0755 obsidian-live-share obsidian-live-share - -"
        "d /var/lib/obsidian-vault-db 0755 obsidian-publish obsidian-publish - -"
        "d /var/lib/obsidian-vault 0755 obsidian-publish obsidian-publish - -"
        "d /var/www/obsidian-publish 0755 obsidian-publish obsidian-publish - -"
      ];

      # ── A. CouchDB — LiveSync backend ─────────────────────────────
      sops.secrets."obsidian/couchdb/adminUser" = {
        inherit sopsFile;
        owner = "couchdb";
        group = "couchdb";
        mode = "0600";
      };
      sops.secrets."obsidian/couchdb/adminPass" = {
        inherit sopsFile;
        owner = "couchdb";
        group = "couchdb";
        mode = "0600";
      };
      sops.templates."couchdb-local.ini" = {
        owner = "couchdb";
        group = "couchdb";
        mode = "0600";
        content = ''
          [admins]
          ${config.sops.placeholder."obsidian/couchdb/adminUser"} = ${config.sops.placeholder."obsidian/couchdb/adminPass"}
        '';
      };

      services.couchdb = {
        enable = true;
        bindAddress = "127.0.0.1";
        port = 5984;
        extraConfigFiles = [ config.sops.templates."couchdb-local.ini".path ];
      };

      systemd.services.couchdb-init = {
        description = "CouchDB init — Obsidian LiveSync (cluster, CORS, DB)";
        after = [ "couchdb.service" ];
        requires = [ "couchdb.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        environment = {
          COUCHDB_INTERNAL_URL = "http://127.0.0.1:5984";
          COUCHDB_DATABASE = "obsidiannotes";
        };
        path = [ pkgs.curl ];
        script = ''
          COUCHDB_USER=$(${pkgs.coreutils}/bin/cat ${config.sops.secrets."obsidian/couchdb/adminUser".path})
          COUCHDB_PASSWORD=$(${pkgs.coreutils}/bin/cat ${config.sops.secrets."obsidian/couchdb/adminPass".path})
          export COUCHDB_USER COUCHDB_PASSWORD
          ${./couchdb-init.sh}
        '';
      };

      # ── B. LiveShare relay — public via CF tunnel ─────────────────
      sops.secrets."obsidian/obsidian-live-share/server-password" = {
        inherit sopsFile;
        owner = "obsidian-live-share";
        group = "obsidian-live-share";
        mode = "0600";
      };
      sops.secrets."obsidian/obsidian-live-share/jwt-secret" = {
        inherit sopsFile;
        owner = "obsidian-live-share";
        group = "obsidian-live-share";
        mode = "0600";
      };

      systemd.services.obsidian-live-share = {
        description = "Obsidian Live Share relay server";
        wantedBy = [ "multi-user.target" ];
        after = [ "network.target" ];
        serviceConfig = {
          ExecStart = "${pkgs.nodejs_22}/bin/node ${liveShareServer}/lib/node_modules/obsidian-live-share-server/dist/index.js";
          WorkingDirectory = "/var/lib/obsidian-live-share";
          User = "obsidian-live-share";
          Group = "obsidian-live-share";
          Restart = "on-failure";
          RestartSec = 5;
          EnvironmentFile = [
            config.sops.secrets."obsidian/obsidian-live-share/server-password".path
            config.sops.secrets."obsidian/obsidian-live-share/jwt-secret".path
          ];
        };
        environment = {
          PORT = "3000";
        };
      };

      # ── C. Publish — vault mirror + nginx basic auth ──────────────
      sops.secrets."obsidian/htpasswd" = {
        inherit sopsFile;
        owner = "nginx";
        group = "nginx";
        mode = "0640";
      };

      services.nginx.virtualHosts."obsidian.filepath.ru" = {
        listen = [{ addr = "127.0.0.1"; port = 8080; }];
        root = "/var/www/obsidian-publish";
        locations."/".extraConfig = ''
          auth_basic "Restricted";
          auth_basic_user_file ${config.sops.secrets."obsidian/htpasswd".path};
        '';
      };

      systemd.services.obsidian-publish = {
        description = "Obsidian publish — LiveSync CLI mirror + render";
        serviceConfig = {
          Type = "oneshot";
          User = "root";
          Group = "root";
          ReadWritePaths = [ "/run/secrets/obsidian/couchdb" ];
        };
        path = [ pkgs.podman pkgs.pandoc ];
        environment = {
          LIVESYNC_IMAGE = "ghcr.io/vrtmrz/livesync-cli";
          LIVESYNC_DB = "/var/lib/obsidian-vault-db";
          LIVESYNC_VAULT = "/var/lib/obsidian-vault";
          PUBLISH_DIR = "/var/www/obsidian-publish";
        };
        script = ''
          set -euo pipefail
          mkdir -p "$LIVESYNC_DB" "$LIVESYNC_VAULT" "$PUBLISH_DIR"

          CONNSTR="sls+http://$(${pkgs.coreutils}/bin/cat ${config.sops.secrets."obsidian/couchdb/adminUser".path}):$(${pkgs.coreutils}/bin/cat ${config.sops.secrets."obsidian/couchdb/adminPass".path})@127.0.0.1:5984/obsidiannotes"

          # add remote if missing (idempotent: first run), then sync + mirror
          podman run --rm -v "$LIVESYNC_DB:/data" "$LIVESYNC_IMAGE" remote-add main "$CONNSTR" || true
          podman run --rm -v "$LIVESYNC_DB:/data" "$LIVESYNC_IMAGE" sync
          podman run --rm -v "$LIVESYNC_DB:/data" -v "$LIVESYNC_VAULT:/vault" "$LIVESYNC_IMAGE" mirror /vault

          # render publish/ folder
          rm -f "$PUBLISH_DIR"/*.html
          for f in "$LIVESYNC_VAULT"/publish/*.md; do
            [ -f "$f" ] || continue
            ${pkgs.pandoc}/bin/pandoc --standalone "$f" -o "$PUBLISH_DIR/$(basename "$f" .md).html"
          done
        '';
      };

       systemd.timers.obsidian-publish = {
         description = "Obsidian publish timer";
         wantedBy = [ "timers.target" ];
         timerConfig = {
           OnCalendar = "*-*-* *:0/10:00";
           Persistent = true;
         };
       };
     } syncMcpConfig
    ];
   };
 }
