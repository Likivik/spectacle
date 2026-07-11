{ inputs, den, lib, ... }:
{
  flake-file.inputs = {
    hermes-agent = {
      url = "github:NousResearch/hermes-agent";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.server.hermes-agent = {
    nixos = { config, pkgs, lib, ... }:
      let
        caSecretPath = lib.attrByPath [ "sops" "secrets" "hermes-credproxy/mitmproxy-ca" "path" ] null config;

        credproxyAddon = pkgs.writeText "mitmproxy-credproxy.py" ''
          from mitmproxy import http
          import os
          import re

          CREDENTIALS = [
              (r"openrouter\.ai", "Authorization", "OPENROUTER_API_KEY", "Bearer {}"),
              (r"api\.github\.com", "Authorization", "GITHUB_TOKEN", "Bearer {}"),
              (r"github\.com", "Authorization", "GITHUB_TOKEN", "Bearer {}"),
              (r"opencode\.ai", "Authorization", "OPENCODE_GO_API_KEY", "Bearer {}"),
          ]

          class CredentialInjector:
              def request(self, flow: http.HTTPFlow) -> None:
                  url = flow.request.pretty_url
                  for pattern, header, env_var, value_format in CREDENTIALS:
                      if re.search(pattern, url):
                          value = os.environ.get(env_var)
                          if value:
                              flow.request.headers[header] = value_format.format(value)
                          break

          addons = [CredentialInjector()]
        '';
      in
      {
        imports = [ inputs.hermes-agent.nixosModules.default ];

        services.hermes-agent = {
          enable = true;
          addToSystemPackages = true;
          extraDependencyGroups = [ "messaging" ];
          restart = "always";
          restartSec = 5;
          environment = {
            OPENROUTER_API_KEY = "hermes-proxy://openrouter";
            GITHUB_TOKEN = "hermes-proxy://github";
            OPENCODE_GO_API_KEY = "hermes-proxy://opencode";
            HTTPS_PROXY = "http://127.0.0.1:7899";
            SSL_CERT_FILE = "/etc/ssl/certs/hermes-with-proxy-ca.crt";
          };
        };

        users.users.hermes-credproxy = {
          isSystemUser = true;
          group = "hermes-credproxy";
          home = "/var/lib/hermes-credproxy";
          createHome = true;
          shell = pkgs.bash;
        };
        users.groups.hermes-credproxy = { };

        system.activationScripts."hermes-credproxy-ca" = lib.stringAfter (
          lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
        ) ''
          MITM_DIR="/var/lib/hermes-credproxy/.mitmproxy"
          COMBINED="/etc/ssl/certs/hermes-with-proxy-ca.crt"
          AWK="${pkgs.gawk}/bin/awk"
          COREUTILS="${pkgs.coreutils}/bin"

          "$COREUTILS/cat" "${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt" > "$COMBINED"
          "$COREUTILS/chmod" 0644 "$COMBINED"

          ${lib.optionalString (caSecretPath != null) ''
            if [ -f "${caSecretPath}" ]; then
              "$COREUTILS/mkdir" -p "$MITM_DIR"
              CERT=$("$AWK" '/^-----BEGIN CERTIFICATE-----/{p=1} p; /^-----END CERTIFICATE-----/{p=0}' "${caSecretPath}")
              KEY=$("$AWK" '/^-----BEGIN.*PRIVATE KEY-----/{p=1} p; /^-----END.*PRIVATE KEY-----/{p=0}' "${caSecretPath}")
              printf '%s\n%s\n' "$CERT" "$KEY" > "$MITM_DIR/mitmproxy-ca.pem"
              "$COREUTILS/chmod" 0600 "$MITM_DIR/mitmproxy-ca.pem"
              printf '%s\n' "$CERT" > "$MITM_DIR/mitmproxy-ca-cert.pem"
              "$COREUTILS/chmod" 0644 "$MITM_DIR/mitmproxy-ca-cert.pem"
              "$COREUTILS/chown" -R hermes-credproxy:hermes-credproxy "$MITM_DIR"
              "$COREUTILS/cat" "$MITM_DIR/mitmproxy-ca-cert.pem" >> "$COMBINED"
            fi
          ''}
        '';

        systemd.services.hermes-credproxy = {
          description = "Hermes Credential Proxy Daemon";
          after = [ "network-online.target" ];
          wants = [ "network-online.target" ];
          wantedBy = [ "multi-user.target" ];

          serviceConfig = {
            User = "hermes-credproxy";
            Group = "hermes-credproxy";
            Restart = "always";
            RestartSec = 5;
            UMask = "0077";
            NoNewPrivileges = true;
            PrivateTmp = true;
            ProtectSystem = "full";
            ProtectHome = false;
            ReadWritePaths = [ "/var/lib/hermes-credproxy" ];
          };

          script = ''
            OPENROUTER_API_KEY=$(cat /run/secrets/hermes-credproxy/llm-providers/openrouter/api-key)
            GITHUB_TOKEN=$(cat /run/secrets/hermes-credproxy/github/pat-spectacle)
            OPENCODE_GO_API_KEY=$(cat /run/secrets/hermes-credproxy/llm-providers/opencode/api-key2)
            export OPENROUTER_API_KEY GITHUB_TOKEN OPENCODE_GO_API_KEY

            exec ${pkgs.mitmproxy}/bin/mitmdump \
              -s ${credproxyAddon} \
              --listen-port 7899 \
              --set block_global=false
          '';
        };
      };
  };
}
