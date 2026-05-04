{ inputs, den, ... }:
{
  den.aspects.fixes = {
    nixos = { config, pkgs, ... }: {
      services.envfs.enable = true;

      xdg.portal = {
        enable = true;
        extraPortals = with pkgs; [
          kdePackages.xdg-desktop-portal-kde
        ];
      };

      services.tarsnap.enable = true;

      networking.firewall = {
        allowedUDPPortRanges = [
          {
            from = 9278;
            to = 9279;
          }
        ];
        allowedTCPPortRanges = [
          {
            from = 9278;
            to = 9279;
          }
        ];
      };

      programs.thunderbird.enable = true;
    };
  };
}