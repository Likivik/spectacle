# Peripherals
{ den, ... }:

{
  den.aspects.peripherals-base = {
    nixos =
      { config, ... }:
      {
        /*
          ------------------------------------------------------------------------
                                          Bluetooth
          -------------------------------------------------------------------------
        */

        # Enable Bluetooth
        hardware.bluetooth = {
          enable = true;
          powerOnBoot = true;
          settings.General = {
            experimental = true; # show battery

            # https://www.reddit.com/r/NixOS/comments/1ch5d2p/comment/lkbabax/
            # for pairing bluetooth controller
            Privacy = "device";
            JustWorksRepairing = "always";
            Class = "0x000100";
            FastConnectable = true;
          };
        };

        # services.blueman.enable = true;

        hardware.xpadneo.enable = true; # Enable the xpadneo driver for Xbox One wireless controllers

        boot = {
          extraModulePackages = with config.boot.kernelPackages; [ xpadneo ];
          extraModprobeConfig = ''
            options bluetooth disable_ertm=Y
          '';
          # connect xbox controller

        };

        /*
          ---------------------------------------------------------------------------
                                            Audio
          ----------------------------------------------------------------------------
        */

        # security.rtkit.enable = true; # temporary :TODO disabled bc of this https://github.com/NixOS/nixpkgs/issues/392992#issuecomment-2799867278

        services.pipewire = {
          enable = true;
          alsa.enable = true;
          alsa.support32Bit = true;
          pulse.enable = true;
          jack.enable = true; # If you want to use JACK applications, uncomment this
        };

        /*
          ------------------------------------------------------------------------
                                          Touchpad
          -------------------------------------------------------------------------
        */

        # Prolly not needed, since gets auto enabled when there is a gui session

        # services.libinput = {
        #   enable = true; # enable touchpad support
        #   # additionalOptions = '' Option "libinput Tapping Drag Lock Enabled" 0 ''; # disable drag lock option
        #   # Relevant links:
        #   # https://wayland.freedesktop.org/libinput/doc/latest/tapping.html#tap-and-drag (official documentation)
        #   # https://wiki.archlinux.org/index.php/Libinput#Via_xinput (howto figure out commands)
        #   # https://nixos.org/nixos/options.html#libinput (example of additionalOptions)
        # };

      };
  };
}
