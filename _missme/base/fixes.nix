{ config, pkgs, ... }:
{
  # NixOS thing: virtual mapping of /bin and /usr/bin/ for better compatablility
  services.envfs.enable = true;

  # Screen sharing on Wayland requires enabling PipeWire and the appropriate XDG Desktop Portals.
  xdg.portal = {
    enable = true;
    # Add the portal for your compositor, e.g.:
    extraPortals = with pkgs; [
      kdePackages.xdg-desktop-portal-kde # For KDE
    ];
  };



  programs.thunderbird.enable = true;
}
