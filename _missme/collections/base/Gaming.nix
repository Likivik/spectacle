{ config, pkgs, ... }: {
  hardware.graphics.enable32Bit = true;



#   programs.steam = {
#   enable = true;
#   extraCompatPackages = with pkgs; [
#     proton-ge-bin
#   ];
# };


environment.systemPackages = with pkgs; [
  bottles

  # wineWowPackages.waylandFull # Wine
  # winetricks
  # protonup-qt # GUI for installing custom Proton versions like GE_Proton
];



#  programs.lutris = {
#     enable = true;
#     extraPackages = with pkgs; [
#       mangohud
#       protonup-qt
#       winetricks
#       gamescope
#       gamemode
#       umu-launcher
#     ];
#     protonPackages = with pkgs; [
#       proton-ge-bin
#     ];
#     winePackages = with pkgs; [
#       wineWowPackages.waylandFull
#     ];

}