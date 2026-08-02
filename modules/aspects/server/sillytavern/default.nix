{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.sillytavern = {
    nixos = { config, lib, pkgs, ... }:
    let
      pkg = pkgs.sillytavern;
      defaultConfig = "${pkg}/lib/node_modules/sillytavern/default/config.yaml";
    in {
      services.sillytavern = {
        enable = true;
        port = 8001;
        # DON'T set listen here — module stringifies `true` → `--listen=1`,
        # which ST parses as FALSE (still binds 127.0.0.1). Env vars below.
      };

      systemd.services.sillytavern = {
        # nixpkgs#455581: module tmpfiles symlinks config.yaml → read-only store,
        # ST dies with EROFS writing missing config keys. Replace with a real
        # writable file seeded from package defaults (no sed needed).
        preStart = lib.mkAfter ''
          if [ -L /var/lib/SillyTavern/config.yaml ]; then
            rm /var/lib/SillyTavern/config.yaml
          fi
          if [ ! -f /var/lib/SillyTavern/config.yaml ]; then
            cp ${defaultConfig} /var/lib/SillyTavern/config.yaml
            chmod 0600 /var/lib/SillyTavern/config.yaml
          fi
          # Bake in thumbnail settings (idempotent — guard against re-append on rebuild).
          grep -q '^thumbnails:' /var/lib/SillyTavern/config.yaml || cat >> /var/lib/SillyTavern/config.yaml <<'YAML'

thumbnails:
  enabled: true
  format: png
  quality: 100
  dimensions:
    bg:
      - 240
      - 135
    avatar:
      - 864
      - 1280
YAML
          # Whitelist mode stays ON (erebus has a public IP) — allow the tailnet
          # subnet so phones on Tailscale can connect, everyone else is refused.
          grep -q '100.64.0.0/10' /var/lib/SillyTavern/config.yaml || \
            sed -i '/^whitelist:/a\  - 100.64.0.0/10' /var/lib/SillyTavern/config.yaml

          # Idempotent extension install — clone third-party repos if missing.
          # Extensions persist across rebuilds via the BindPaths mount.
          if [ ! -d "/var/lib/SillyTavern/extensions/Horae" ]; then
            git clone --depth 1 https://github.com/SenriYuki/SillyTavern-Horae.git \
              /var/lib/SillyTavern/extensions/Horae 2>/dev/null || true
          fi
          if [ ! -d "/var/lib/SillyTavern/extensions/SillyTavern-Tracker" ]; then
            git clone --depth 1 https://github.com/kaldigo/SillyTavern-Tracker.git \
              /var/lib/SillyTavern/extensions/SillyTavern-Tracker 2>/dev/null || true
          fi
          if [ ! -d "/var/lib/SillyTavern/extensions/sillytavern-inventory" ]; then
            git clone --depth 1 https://github.com/nyxkrage/sillytavern-inventory.git \
              /var/lib/SillyTavern/extensions/sillytavern-inventory 2>/dev/null || true
          fi
        '';

        # ST natively reads SILLYTAVERN_* env vars (override config.yaml, proper bool parse).
        # The module's `listen = true` flag stringifies to `--listen=1` which ST
        # mishandles (still binds 127.0.0.1) — env vars are the reliable path.
        environment = {
          SILLYTAVERN_LISTEN = "true";
          SILLYTAVERN_LISTEN_ADDRESS_IPV4 = "0.0.0.0";
        };
      };

      # Security boundary: Tailscale-only, not ST whitelist
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 8001 ];
    };
  };
}
