# COSMIC DESKTOP
{ lib, pkgs, ... }:
{

  services.desktopManager.cosmic.enable = true;
  services.displayManager.cosmic-greeter.enable = true;
  services.displayManager.defaultSession = "cosmic";
  environment.cosmic.excludePackages = with pkgs; [
    # gcr_4
  ];
  #
  # services.gnome.gcr-ssh-agent.enable = lib.mkForce false;

}
