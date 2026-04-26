
nixos = { config, pkgs, ... }: {

  hardware.graphics.enable32Bit = true; # TODO: Test if this is needed

  environment.systemPackages = with pkgs; [
    bottles
  ];

};