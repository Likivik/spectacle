{ config, pkgs, lib }: let
  sopsFile = ../../../../secrets/poweredge/secrets.yaml;

   mcpAuthToken = config.sops.secrets."obsidian/obsidian-sync-mcp/mcp-auth-token".path;
   e2ePassphrase = config.sops.secrets."obsidian/obsidian-sync-mcp/e2e-passphrase".path;
  couchdbUser = config.sops.secrets."obsidian/couchdb/adminUser".path;
  couchdbPass = config.sops.secrets."obsidian/couchdb/adminPass".path;
in {
  systemd.tmpfiles.rules = [
    "d /var/lib/obsidian-sync-mcp 0755 root root - -"
  ];

  sops.secrets."obsidian/obsidian-sync-mcp/mcp-auth-token" = {
    inherit sopsFile;
    owner = "root";
    group = "root";
    mode = "0600";
  };
  sops.secrets."obsidian/obsidian-sync-mcp/e2e-passphrase" = {
    inherit sopsFile;
    owner = "root";
    group = "root";
    mode = "0600";
  };

  systemd.services.obsidian-sync-mcp = {
    description = "Obsidian Sync MCP server — AI agent access to LiveSync vault";
    wantedBy = [ "multi-user.target" ];
    after = [ "couchdb.service" ];
    requires = [ "couchdb.service" ];
    serviceConfig = {
      Type = "exec";
      Restart = "on-failure";
      RestartSec = 5;
      User = "root";
      Group = "root";
      ExecStart = "${pkgs.writeShellScript "obsidian-sync-mcp-run" ''
        set -euo pipefail
        COUCHDB_USER=$(${pkgs.coreutils}/bin/cat ${couchdbUser})
        COUCHDB_PASSWORD=$(${pkgs.coreutils}/bin/cat ${couchdbPass})
        MCP_AUTH_TOKEN=$(${pkgs.coreutils}/bin/cat ${mcpAuthToken})
        COUCHDB_PASSPHRASE=$(${pkgs.coreutils}/bin/cat ${e2ePassphrase})
        export COUCHDB_USER COUCHDB_PASSWORD MCP_AUTH_TOKEN COUCHDB_PASSPHRASE
        exec ${pkgs.podman}/bin/podman run --rm \
          --name obsidian-sync-mcp \
          --network host \
          -e COUCHDB_URL=http://127.0.0.1:5984 \
          -e COUCHDB_USER="$COUCHDB_USER" \
          -e COUCHDB_PASSWORD="$COUCHDB_PASSWORD" \
          -e COUCHDB_DATABASE=obsidiannotes \
          -e COUCHDB_PASSPHRASE="$COUCHDB_PASSPHRASE" \
          -e VAULT_NAME=obsidian \
          -e MCP_AUTH_TOKEN="$MCP_AUTH_TOKEN" \
          -e HOST=127.0.0.1 \
          -e PORT=8787 \
          -e MCP_REFRESH_DAYS=14 \
          -v /var/lib/obsidian-sync-mcp:/data \
          ghcr.io/es617/obsidian-sync-mcp:latest
      ''}";
    };
  };
}