# rusty-imap-mcp: Security-first IMAP MCP server with PII redaction
# Fork of randomparity/rusty-imap-mcp with leakguard PII detection
#
# Binary: /var/lib/hermes/.local/bin/rusty-imap-mcp
# Config: /var/lib/hermes/rusty-imap/config.toml

{ config, lib, pkgs, ... }:

let
  cfg = config.services.rusty-imap;
  binary = "/var/lib/hermes/.local/bin/rusty-imap-mcp";
  configPath = "/var/lib/hermes/rusty-imap/config.toml";
  dataDir = "/var/lib/hermes/.local/share/rusty-imap-mcp";
in
{
  options.services.rusty-imap = {
    enable = lib.mkEnableOption "rusty-imap-mcp email MCP server with PII redaction";

    imap-password-env = lib.mkOption {
      type = lib.types.str;
      default = "RUSTY_IMAP_MCP_IMAP_PASSWORD";
      description = "Environment variable name for the IMAP password";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.rusty-imap-mcp = {
      description = "rusty-imap-mcp — security-first IMAP MCP server";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];

      serviceConfig = {
        Type = "simple";
        ExecStart = "${binary} --config ${configPath}";
        Restart = "on-failure";
        RestartSec = 5;

        # Hardening
        User = "hermes";
        Group = "hermes";
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = [ dataDir "/var/lib/hermes/rusty-imap" ];
        PrivateTmp = true;
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectControlGroups = true;

        # Network access (IMAP only — Gmail)
        IPAddressAllow = [
          "142.250.0.0/15"
          "172.217.0.0/16"
          "2607:f8b0:4004:c00::0/62"
        ];
        IPAddressDeny = "any";

        # Capabilities
        CapabilityBoundingSet = "";

        # System call filter
        SystemCallFilter = [ "@system-service" "~@privileged" ];
      };

      environment = {
        RUST_LOG = "info";
        RUSTY_IMAP_MCP_CONFIG = configPath;
      };
    };
  };
}
