{ config, pkgs, ... }:
{
  # TODO: Android ADB - put it in it's own file
  # TODO: find way to add user group from there?
  environment.systemPackages = [ pkgs.android-tools ];
  
}
