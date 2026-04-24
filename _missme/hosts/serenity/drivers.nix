 
{ config, pkgs, lib, ... }:

{
    # Nvidia driver
    services.xserver.videoDrivers = [ "nvidia" ];
    #services.xserver.videoDrivers = [ "nouveau" ];
    hardware.nvidia.open = true; # kernel modules, support moves to foss

    hardware.graphics = {
      enable = true;
      enable32Bit = true;
      extraPackages = with pkgs;
      [
         intel-media-driver

      ];
    };

    boot = {
      blacklistedKernelModules = [
        "nouveau"
        #"i915"
      ]; 
      kernelParams = [ "nomodeset" ];
      
    };

    
}
