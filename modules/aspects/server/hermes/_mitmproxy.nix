{ config, pkgs, lib }: let
  caSecretPath = lib.attrByPath [ "sops" "secrets" "hermes-mitmproxy/mitmproxy-ca" "path" ] null config;

  mitmproxyAddon = pkgs.writeText "mitmproxy-addon.py" ''
    import os, sys, re
    from mitmproxy import http

    CREDS = [
        (re.compile(r'openrouter\.ai'), 'authorization', 'OPENROUTER_API_KEY', 'Bearer {}'),
        (re.compile(r'api\.github\.com'), 'authorization', 'GITHUB_TOKEN', 'Bearer {}'),
        (re.compile(r'github\.com'), 'authorization', 'GITHUB_TOKEN', 'Bearer {}'),
        (re.compile(r'opencode\.ai'), 'authorization', 'OPENCODE_GO_API_KEY', 'Bearer {}'),
    ]

    class Injector:
        def request(self, f):
            u = f.request.pretty_url
            for p, h, k, fmt in CREDS:
                if p.search(u):
                    v = os.environ.get(k)
                    if v:
                        f.request.headers[h] = fmt.format(v)
                        sys.stderr.write('MITMPROXY: injected ' + k[:12] + ' for ' + u[:50] + '\n')
                    else:
                        sys.stderr.write('MITMPROXY: MISSING_ENV ' + k + '\n')
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
