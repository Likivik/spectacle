{ inputs, den, ... }:
{
  den.aspects.audiobookshelf = {
    nixos = { config, pkgs, lib, ... }: {
      services.audiobookshelf = {
        enable = true;
        port = 8234;
        user = "likivik";
        group = "users";
      };

      systemd.user.services.tailscale_serve_audiobookshelf = {
        enable = true;
        restartIfChanged = true;
        description = "tailscale_serve_audiobookshelf";
        script = ''
          tailscale serve 8234
        '';
        wantedBy = [ "multi-user.target" ];
      };
    };
  };
}