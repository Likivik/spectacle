{ den, inputs, lib, ... }:

let
  # den's aspect wrapper does not forward `pkgs` to module/nixos args,
  # so resolve it from the nixpkgs input directly (always present).
  pkgs = inputs.nixpkgs.legacyPackages.x86_64-linux;

  # mcp-email-server (Wh1isper) + aioimaplib/filelock overrides live in
  # pkgs/mcp-email-server.nix so the hermetic `email-mcp-roundtrip` check can
  # boot the same binary without duplicating the build. (doCheck=false on
  # aioimaplib is documented there.)
  mcp-email-server = import ../../../../pkgs/mcp-email-server.nix { inherit pkgs lib; };

  cfgDir = "/var/lib/email";

  # TOML config template. Placeholders __EMAIL__ / __PASSWORD__ are substituted
  # at activation from sops-decrypted values (never baked into the store).
  # account2 (second gmail) intentionally omitted — add a second [[emails]]
  # table here when the user actually needs it.
  configToml = pkgs.writeText "email-config.toml" ''
    credential_storage = "plaintext"
    enable_attachment_download = true
    allowed_recipients = []
    allowed_senders = []
    report_blocked_mutations = false

    [[emails]]
    account_name = "default"
    full_name = "Кирилл Липский"
    email_address = "__EMAIL__"
    save_to_sent = true

    [emails.incoming]
    user_name = "__EMAIL__"
    password = "__PASSWORD__"
    host = "imap.gmail.com"
    port = 993
    use_ssl = true
    start_ssl = false
    verify_ssl = true

    [emails.outgoing]
    user_name = "__EMAIL__"
    password = "__PASSWORD__"
    host = "smtp.gmail.com"
    port = 465
    use_ssl = true
    start_ssl = false
    verify_ssl = true
  '';
in
{
  den.aspects.server.email = {
    nixos = { config, lib, ... }:
      let
        emailAddrPath = lib.attrByPath [ "sops" "secrets" "email/gmail/account1/adress" "path" ] null config;
        emailPassPath = lib.attrByPath [ "sops" "secrets" "email/gmail/account1/app-password" "path" ] null config;
      in {
        users.users.email = {
          isSystemUser = true;
          group = "email";
          home = cfgDir;
          createHome = true;
          extraGroups = [ "hermes" ];
        };
        users.groups.email = {};

        systemd.tmpfiles.rules = [
          "d ${cfgDir} 0750 email email -"
        ];

        # Streamable HTTP on loopback — Hermes connects via url (no caller auth).
        systemd.services.email-mcp = {
          description = "mcp-email-server (Wh1isper) — IMAP/SMTP MCP over streamable HTTP";
          after = [ "network-online.target" "sops-nix.service" ];
          wants = [ "network-online.target" ];
          wantedBy = [ "multi-user.target" ];

          # Generate config.toml here (preStart), NOT in an activation script:
          # activation-script ordering vs sops-nix decryption is fragile — the
          # secrets landed in /run/secrets AFTER the activation script ran on the
          # first switch, so `cat` saw empty and no config was written. preStart
          # runs right before ExecStart, after sops-nix.service has decrypted
          # into /run/secrets, so the values are guaranteed present.
          preStart = ''
            EMAIL_ADDR=$(cat ${emailAddrPath} 2>/dev/null || true)
            EMAIL_PASS=$(cat ${emailPassPath} 2>/dev/null || true)
            if [ -n "$EMAIL_ADDR" ] && [ -n "$EMAIL_PASS" ]; then
              ${pkgs.gnused}/bin/sed \
                -e "s|__EMAIL__|$EMAIL_ADDR|g" \
                -e "s|__PASSWORD__|$EMAIL_PASS|g" \
                ${configToml} > ${cfgDir}/config.toml
              chmod 0600 ${cfgDir}/config.toml
            fi
          '';

          serviceConfig = {
            User = "email";
            Group = "email";
            Restart = "on-failure";
            RestartSec = 5;
            WorkingDirectory = cfgDir;
            NoNewPrivileges = true;
            ProtectSystem = "strict";
            ProtectHome = true;
            PrivateTmp = true;
            ReadWritePaths = [ cfgDir ];
          };

          environment = {
            MCP_EMAIL_SERVER_CONFIG_PATH = "${cfgDir}/config.toml";
          };

          script = ''
            exec ${mcp-email-server}/bin/mcp-email-server streamable-http --host 127.0.0.1 --port 9557
          '';

          restartTriggers = [ "${cfgDir}/config.toml" ];
        };
      };
  };
}
