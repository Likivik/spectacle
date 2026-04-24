{ config, pkgs, lib, ... }:

{

  environment.systemPackages = [ pkgs.flatpak-builder ]; # build/create flatpak packages

}