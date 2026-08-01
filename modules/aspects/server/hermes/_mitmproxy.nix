{ config, pkgs, lib }: let
  caSecretPath = lib.attrByPath [ "sops" "secrets" "hermes-mitmproxy/mitmproxy-ca" "path" ] null config;

  mitmproxyAddon = pkgs.writeText "mitmproxy-addon.py" ''
    import base64, sys
    from mitmproxy import http

    SECRETS = "/run/secrets/hermes-mitmproxy"

    # GitHub hosts by auth scheme (from tend project pattern)
    # Git smart-HTTP uses Basic auth; REST API uses Bearer/token
    GITHUB_BASIC_HOSTS = {"github.com", "codeload.github.com"}
    GITHUB_TOKEN_HOSTS = {"api.github.com", "uploads.github.com", "raw.githubusercontent.com"}

    # Other services (all use Bearer)
    OPENROUTER_KEY_FILE = f"{SECRETS}/llm-providers/openrouter/api-key"
    # Shared rotation pool for both OpenCode Go and Zen
    OPENCODE_POOL = [
        f"{SECRETS}/llm-providers/opencode/api-key1",
        f"{SECRETS}/llm-providers/opencode/api-key2",
        f"{SECRETS}/llm-providers/opencode/api-key3",
    ]

    # OpenCode Go routes under /zen/go/, Zen under /zen/v1/ (same host opencode.ai)
    GO_PATH_PREFIX = "/zen/go/"
    ZEN_PATH_PREFIX = "/zen/v1/"


    def _read(path):
        try:
            with open(path) as fh:
                return fh.read().strip()
        except OSError as e:
            sys.stderr.write(f"MITMPROXY: MISSING_SECRET {path}: {e}\n")
            return None


    def _inject_auth(f, service, value):
        if value:
            # Anthropic Messages endpoint needs x-api-key header
            # (e.g. OpenCode Go: qwen3.7-max, qwen3.7-plus)
            # vs chat/completions which uses Authorization: Bearer
            if f.request.path.endswith("/v1/messages"):
                f.request.headers["x-api-key"] = value
                # Also set anthropic-version for Discover API compliance
                f.request.headers["anthropic-version"] = "2023-06-01"
            else:
                f.request.headers["Authorization"] = f"Bearer {value}"
            sys.stderr.write(f"MITMPROXY: injected {service} for {f.request.host}{f.request.path}\n")


    class Injector:
        def __init__(self):
            # Pre-compute GitHub Basic auth header
            gh_token = _read(f"{SECRETS}/github/pat-hermes-full")
            if gh_token:
                self._gh_basic = "Basic " + base64.b64encode(
                    f"x-access-token:{gh_token}".encode()
                ).decode()
                self._gh_token = gh_token
            else:
                self._gh_basic = None
                self._gh_token = None

            self._openrouter = _read(OPENROUTER_KEY_FILE)
            self._opencode_pool = [k for k in (_read(p) for p in OPENCODE_POOL) if k]
            self._go_idx = 0
            self._zen_idx = 0

        def _opencode_service(self, f):
            path = f.request.path
            if path.startswith(GO_PATH_PREFIX):
                return "go"
            if path.startswith(ZEN_PATH_PREFIX):
                return "zen"
            return None

        def _opencode_key(self, service):
            if not self._opencode_pool:
                return None
            idx = self._go_idx if service == "go" else self._zen_idx
            return self._opencode_pool[idx % len(self._opencode_pool)]

        def _rotate_opencode(self, service):
            if not self._opencode_pool:
                return
            n = len(self._opencode_pool)
            if service == "go":
                self._go_idx = (self._go_idx + 1) % n
            else:
                self._zen_idx = (self._zen_idx + 1) % n
            sys.stderr.write(
                f"MITMPROXY: rotated {service} key to index "
                f"{self._go_idx if service == 'go' else self._zen_idx} ({n} keys)\n"
            )

        def request(self, f):
            host = f.request.host.lower()

            # GitHub: inject based on host
            if host in GITHUB_BASIC_HOSTS:
                if self._gh_basic:
                    f.request.headers["Authorization"] = self._gh_basic
                    sys.stderr.write(f"MITMPROXY: injected GITHUB_BASIC for {host}\n")
                else:
                    sys.stderr.write("MITMPROXY: MISSING_SECRET github/pat-hermes-full\n")
            elif host in GITHUB_TOKEN_HOSTS:
                if self._gh_token:
                    f.request.headers["Authorization"] = f"token {self._gh_token}"
                    sys.stderr.write(f"MITMPROXY: injected GITHUB_TOKEN for {host}\n")
                else:
                    sys.stderr.write("MITMPROXY: MISSING_SECRET github/pat-hermes-full\n")
            elif "opencode.ai" in host:
                service = self._opencode_service(f)
                if service:
                    _inject_auth(f, f"OPENCODE_{service.upper()}", self._opencode_key(service))
            elif "openrouter.ai" in host:
                _inject_auth(f, "OPENROUTER", self._openrouter)

        def response(self, f):
            host = f.request.host.lower()
            if "opencode.ai" in host and f.response.status_code in (401, 429):
                service = self._opencode_service(f)
                if service:
                    self._rotate_opencode(service)

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
      exec ${pkgs.mitmproxy}/bin/mitmdump \
        -s ${mitmproxyAddon} \
        --listen-port 7899 \
        --mode regular \
        --set block_global=false
    '';
  };
}
