{ config, pkgs, lib }: let
  caSecretPath = lib.attrByPath [ "sops" "secrets" "hermes-mitmproxy/mitmproxy-ca" "path" ] null config;

  mitmproxyAddon = pkgs.writeText "mitmproxy-addon.py" ''
    import os, sys, base64
    from mitmproxy import http

    # GitHub hosts by auth scheme (from tend project pattern)
    # Git smart-HTTP uses Basic auth; REST API uses Bearer/token
    GITHUB_BASIC_HOSTS = {"github.com", "codeload.github.com"}
    GITHUB_TOKEN_HOSTS = {"api.github.com", "uploads.github.com", "raw.githubusercontent.com"}

    # Other services (all use Bearer)
    BEARER_SERVICES = [
        ("openrouter.ai", "OPENROUTER_API_KEY"),
        ("opencode.ai", "OPENCODE_GO_API_KEY"),
    ]

    class Injector:
        def __init__(self):
            # Pre-compute GitHub Basic auth header
            gh_token = os.environ.get("GITHUB_TOKEN", "")
            if gh_token:
                self._gh_basic = "Basic " + base64.b64encode(
                    f"x-access-token:{gh_token}".encode()
                ).decode()
                self._gh_token = gh_token
            else:
                self._gh_basic = None
                self._gh_token = None

        def request(self, f):
            host = f.request.host.lower()

            # GitHub: inject based on host
            if host in GITHUB_BASIC_HOSTS:
                if self._gh_basic:
                    f.request.headers["Authorization"] = self._gh_basic
                    sys.stderr.write(f"MITMPROXY: injected GITHUB_BASIC for {host}\n")
                else:
                    sys.stderr.write("MITMPROXY: MISSING_ENV GITHUB_TOKEN\n")
            elif host in GITHUB_TOKEN_HOSTS:
                if self._gh_token:
                    f.request.headers["Authorization"] = f"token {self._gh_token}"
                    sys.stderr.write(f"MITMPROXY: injected GITHUB_TOKEN for {host}\n")
                else:
                    sys.stderr.write("MITMPROXY: MISSING_ENV GITHUB_TOKEN\n")
            else:
                # Other services: Bearer auth
                for pattern, env_key in BEARER_SERVICES:
                    if pattern in host:
                        v = os.environ.get(env_key)
                        if v:
                            # Anthropic Messages endpoint needs x-api-key header
                            # (e.g. OpenCode Go: qwen3.7-max, qwen3.7-plus)
                            # vs chat/completions which uses Authorization: Bearer
                            if f.request.path.endswith("/v1/messages"):
                                f.request.headers["x-api-key"] = v
                                # Also set anthropic-version for Discover API compliance
                                f.request.headers["anthropic-version"] = "2023-06-01"
                                sys.stderr.write(f"MITMPROXY: injected {env_key} as x-api-key for {host}{f.request.path}\n")
                            else:
                                f.request.headers["Authorization"] = f"Bearer {v}"
                                sys.stderr.write(f"MITMPROXY: injected {env_key} for {host}\n")
                        else:
                            sys.stderr.write(f"MITMPROXY: MISSING_ENV {env_key}\n")
                        break

    addons = [Injector()]
  '';
in {
  users.users.hermes-mitmproxy = {
    isSystemUser = true;
    group = "hermes-mitmproxy";
    home = "/var/lib/hermes-mitmproxy";
    createHome = true;
    shell = pkgs.bash;
  };
  users.groups.hermes-mitmproxy = { };

  system.activationScripts."hermes-mitmproxy-ca" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    MITM_DIR="/var/lib/hermes-mitmproxy/.mitmproxy"
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
        "$COREUTILS/chown" -R hermes-mitmproxy:hermes-mitmproxy "$MITM_DIR"
        "$COREUTILS/cat" "$MITM_DIR/mitmproxy-ca-cert.pem" >> "$COMBINED"
      fi
    ''}
  '';

  systemd.services.hermes-mitmproxy = {
    description = "Hermes MITM Credential Proxy";
    after = [ "network-online.target" ];
    wants = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];

    serviceConfig = {
      User = "hermes-mitmproxy";
      Group = "hermes-mitmproxy";
      Restart = "always";
      RestartSec = 5;
      UMask = "0077";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectSystem = "full";
      ProtectHome = false;
      ReadWritePaths = [ "/var/lib/hermes-mitmproxy" ];
    };

    script = ''
      OPENROUTER_API_KEY=$(cat /run/secrets/hermes-mitmproxy/llm-providers/openrouter/api-key)
      GITHUB_TOKEN=$(cat /run/secrets/hermes-mitmproxy/github/pat-hermes-full)
      OPENCODE_GO_API_KEY=$(cat /run/secrets/hermes-mitmproxy/llm-providers/opencode/api-key2)
      export OPENROUTER_API_KEY GITHUB_TOKEN OPENCODE_GO_API_KEY

      exec ${pkgs.mitmproxy}/bin/mitmdump \
        -s ${mitmproxyAddon} \
        --listen-port 7899 \
        --set block_global=false
    '';
  };
}
