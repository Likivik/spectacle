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
        listen = true;
        port = 8001;
        # NOTE: don't set whitelist here — module stringifies bools to 1/0,
        # and ST treats "--whitelist=0" as truthy (JS "0" string). Use env var instead.
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
        '';

        # ST natively reads SILLYTAVERN_* env vars (override config.yaml, proper bool parse)
        environment = {
          SILLYTAVERN_WHITELIST = "false";
        };
      };

      # Security boundary: Tailscale-only, not ST whitelist
      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 8001 ];
    };
  };
}
