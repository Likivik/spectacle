{ config, pkgs, ... }:
{

  den.aspects.bootloader = {
    nixos =
    { ... }:
    {

      /* ---------------------------- Bootloader ---------------------------- */
      boot = {

        loader = {

          systemd-boot = {
            enable = true; # enable systemd-boot
            consoleMode = "max"; # resolution
            configurationLimit = 25; # Maximum number of latest generations in the boot menu.
            
            /* -----------------------------------------------------------------------
              Whether to allow editing the kernel command-line before boot.             
              It is recommended to set this to false, as it allows gaining root access  
              by passing init=/bin/sh as a kernel parameter.                            
              However, it is enabled by default for backwards compatibility.            
              ------------------------------------------------------------------------ */
            editor = false; # basically a security imporvement :shrugs
            
          };

          /* ---------------------------------------------------------------------------
            allow system to edit motherboard's NVRAM to make sure it finds                
            nixos's boot partition. Only for UEFI obviously. Extra helpful for dual-boot  
            ---------------------------------------------------------------------------- */
          efi.canTouchEfiVariables = true;
        };

        
        tmp.cleanOnBoot = true; # Cuz I like it clean (first step to ephemeral systems? :lol :trollface)

    };

  };
  
}
     
