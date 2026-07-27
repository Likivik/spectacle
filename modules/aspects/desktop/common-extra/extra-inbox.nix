{ inputs, den, ... }:
{
  den.aspects.desktop.common-extra.extra-inbox = {
    nixos =
      { config, pkgs, ... }:
      {
        programs.thunderbird.enable = true;
        services.tarsnap.enable = true;

        environment.systemPackages = with pkgs; [
          typora
          obsidian
          joplin-desktop

          # Password Management --------------------------------------------------------------------------------
          #bitwarden-desktop
          # bws

          # System Information and Administration --------------------------------------------------------------------------------
          # Learning this
          netdata

          # Other
          steam-run
          qbittorrent
          contrast # Colorpicker - only one I found that works with wayland on kde6

          lite-xl
        ];

      };
  };
}
