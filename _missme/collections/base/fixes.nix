{ config, pkgs, ... }:
{
  # populates contents of /bin and /usr/bin/ so that it contains all executables from the PATH of the requesting process.
  services.envfs.enable = true;

  # Screen sharing on Wayland requires enabling PipeWire and the appropriate XDG Desktop Portals.
  xdg.portal = {
    enable = true;
    # Add the portal for your compositor, e.g.:
    extraPortals = with pkgs; [
      kdePackages.xdg-desktop-portal-kde # For KDE
    ];
  };

  # TARSNAP
  services.tarsnap.enable = true;
  #tarsnap ports, #TODO do I need this?
  networking.firewall = {
    allowedUDPPortRanges = [
      {
        from = 9278;
        to = 9279;
      } # allow for tarsnap ports
    ];
    allowedTCPPortRanges = [
      {
        from = 9278;
        to = 9279;
      } # allow for tarsnap ports
    ];
  };

  programs.thunderbird.enable = true;
}
