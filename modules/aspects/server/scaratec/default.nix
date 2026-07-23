{ den, inputs, lib, ... }:

let
  # den's aspect wrapper does not forward `pkgs` to module/nixos args,
  # so resolve it from the nixpkgs input directly (always present).
  pkgs = inputs.nixpkgs.legacyPackages.x86_64-linux;

  # ---- sc-imap-mcp: build from PyPI sdist (verified present, GPL-3.0) ----
  sc-imap-mcp = pkgs.python3Packages.buildPythonApplication {
    pname = "sc-imap-mcp";
    version = "2.0.1";
    # Wheel (zip) avoids the sdist's unsafe ".." tar member that breaks Nix unpackPhase
    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/70/3c/1eddaebc06e2f4836235f8f8343160101d37eeced15f57ab8e088e331bbc/sc_imap_mcp-2.0.1-py3-none-any.whl";
      sha256 = "23b6cf3ee8c83f380fc44109ad4d50eda10bde1ee14b6cf0048240d2d7baa5d7";
    };
    format = "wheel";
    propagatedBuildInputs = with pkgs.python3Packages; [
      aioimaplib
      aiosqlite
      mcp
      pydantic
      pyyaml
      structlog
      httpx
    ];
    nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ];
    pythonImportsCheck = [ "imap_mcp" ];
    meta = with lib; {
      description = "Security-focused MCP server mediating LLM access to IMAP mailboxes under auditable policy";
      homepage = "https://github.com/scaratec/imap-mcp";
      license = licenses.gpl3Plus;
      mainProgram = "imap-mcp";
    };
  };

  cfgDir = "/var/lib/scaratec/config";
  secretDir = "/var/lib/scaratec/secrets";
in
{
  den.aspects.server.scaratec = {
    nixos = { config, lib, ... }:
      # Safely access sops paths (sops module may load after this aspect)
      let
        emailAdressPath = lib.attrByPath [ "sops" "secrets" "email/gmail/account1/adress" "path" ] null config;
        emailPassPath = lib.attrByPath [ "sops" "secrets" "email/gmail/account1/app-password" "path" ] null config;
      in {
      # Isolated system user — owns secrets + runs the service
      users.users.scaratec = {
        isSystemUser = true;
        group = "scaratec";
        home = "/var/lib/scaratec";
        createHome = true;
        extraGroups = [ "hermes" ];
      };
      users.groups.scaratec = {};

      # Generate config tree from sops secrets at activation
      system.activationScripts.scaratec-config = lib.stringAfter ([ "var" ] ++ lib.optional (config.system.activationScripts ? sops) "sops") ''
        ${lib.optionalString (emailAdressPath != null && emailPassPath != null) ''
          EMAIL_ADDR=$(cat ${emailAdressPath} 2>/dev/null || true)
          EMAIL_PASS=$(cat ${emailPassPath} 2>/dev/null || true)

          if [ -n "$EMAIL_ADDR" ] && [ -n "$EMAIL_PASS" ]; then
            install -d -m 0750 -o scaratec -g scaratec ${cfgDir}
            install -d -m 0700 -o scaratec -g scaratec ${cfgDir}/policies
            install -d -m 0700 -o scaratec -g scaratec ${secretDir}/accounts/account1
            install -d -m 0700 -o scaratec -g scaratec ${secretDir}/callers/hermes
            install -d -m 0750 -o scaratec -g scaratec /var/lib/scaratec/audit

            # Account password (file_dir secret store resolves secret:// -> path)
            printf '%s' "$EMAIL_PASS" > ${secretDir}/accounts/account1/password
            chown scaratec:scaratec ${secretDir}/accounts/account1/password
            chmod 0400 ${secretDir}/accounts/account1/password

            # Caller bearer token (pinned, matches Hermes config.yaml)
            # Loopback-only (127.0.0.1); shared local secret, not in sops.
            TOKEN="56bfc654b67fcf2c75d06def149dc872d8fbc9584e4b66cee4abf19e7d8ea707"
            if [ ! -s ${secretDir}/callers/hermes/token ]; then
              printf '%s' "$TOKEN" > ${secretDir}/callers/hermes/token
              chown scaratec:scaratec ${secretDir}/callers/hermes/token
              chmod 0400 ${secretDir}/callers/hermes/token
            fi

            # accounts.yaml
            cat > ${cfgDir}/accounts.yaml <<ACCOUNTS_EOF
        accounts:
          - id: account1
            provider: google
            host: imap.gmail.com
            port: 993
            user: "$EMAIL_ADDR"
            auth:
              type: password
              secret_ref: secret://accounts/account1/password
        secret_store:
          backend: file_dir
          path: ${secretDir}
        audit:
          directory: /var/lib/scaratec/audit
          hot_days: 90
          warm_days: 275
          delete_after_days: 365
        wal:
          path: /var/lib/scaratec/wal.db
        ACCOUNTS_EOF
            chown scaratec:scaratec ${cfgDir}/accounts.yaml
            chmod 0640 ${cfgDir}/accounts.yaml

            # callers.yaml (Hermes connects over HTTP with shared_token)
            cat > ${cfgDir}/callers.yaml <<CALLERS_EOF
        callers:
          - id: hermes
            policy: hermes-policy
            auth:
              type: shared_token
              token_secret_ref: secret://callers/hermes/token
        CALLERS_EOF
            chown scaratec:scaratec ${cfgDir}/callers.yaml
            chmod 0640 ${cfgDir}/callers.yaml

            # policies/hermes-policy.yaml (default-deny: ENVELOPE + BODY on INBOX)
            cat > ${cfgDir}/policies/hermes-policy.yaml <<POLICY_EOF
        name: hermes-policy
        accounts:
          account1:
            - path: INBOX
              mode: blacklist
              default: ENVELOPE
              mark_seen: false
              rules: []
            - path: "[Gmail]/All Mail"
              mode: blacklist
              default: BODY
              mark_seen: false
              rules: []
        POLICY_EOF
            chown scaratec:scaratec ${cfgDir}/policies/hermes-policy.yaml
            chmod 0640 ${cfgDir}/policies/hermes-policy.yaml

            # Expose bearer token to Hermes (read by hermes user via hermes group)
            install -d -m 0750 -o scaratec -g hermes /run/secrets/scaratec
            install -m 0640 -o scaratec -g hermes ${secretDir}/callers/hermes/token /run/secrets/scaratec/hermes-token
          fi
        ''}
      '';

      # Ensure dirs exist pre-activation
      systemd.tmpfiles.rules = [
        "d /var/lib/scaratec 0750 scaratec scaratec -"
        "d /var/lib/scaratec/config 0750 scaratec scaratec -"
        "d /var/lib/scaratec/secrets 0700 scaratec scaratec -"
        "d /var/lib/scaratec/audit 0750 scaratec scaratec -"
      ];

      # Systemd service: scaratec over HTTP on 127.0.0.1:8080
      systemd.services.scaratec-mcp = {
        description = "sc-imap-mcp — security-focused IMAP MCP server (HTTP)";
        after = [ "network-online.target" "sops-nix.service" ];
        wants = [ "network-online.target" ];
        wantedBy = [ "multi-user.target" ];

        serviceConfig = {
          User = "scaratec";
          Group = "scaratec";
          Restart = "on-failure";
          RestartSec = 5;
          WorkingDirectory = "/var/lib/scaratec";
          NoNewPrivileges = true;
          ProtectSystem = "strict";
          ProtectHome = true;
          PrivateTmp = true;
          ReadWritePaths = [ "/var/lib/scaratec" ];
        };

        environment = {
          IMAP_MCP_CONFIG_DIR = cfgDir;
          IMAP_MCP_HTTP_HOST = "127.0.0.1";
          IMAP_MCP_HTTP_PORT = "8080";
        };

        script = ''
          exec ${sc-imap-mcp}/bin/imap-mcp --transport http
        '';
      };
    };
  };
}
