# Peripherals
{ config, pkgs, ... }:
{
  # Bluetooth ----------------------------------------------------------------
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

  # Audio --------------------------------------------------------------------
  services.pulseaudio.enable = false;
  # security.rtkit.enable = false; # temporary :TODO disabled bc of this https://github.com/NixOS/nixpkgs/issues/392992#issuecomment-2799867278

  services.pipewire = {
    enable = true;
    alsa.enable = true;
    alsa.support32Bit = true;
    pulse.enable = true;
    jack.enable = true; # If you want to use JACK applications, uncomment this
  };

  # Touchpad ------------------------------------------------------------------
  services.libinput = {
    enable = true; # enable touchpad support
    #additionalOptions = '' Option "libinput Tapping Drag Lock Enabled" 0 ''; # disable drag lock option
    # Relevant links:
    # https://wayland.freedesktop.org/libinput/doc/latest/tapping.html#tap-and-drag (official documentation)
    # https://wiki.archlinux.org/index.php/Libinput#Via_xinput (howto figure out commands)
    # https://nixos.org/nixos/options.html#libinput (example of additionalOptions)
  };
  # Printing ------------------------------------------------------------------
  services.printing = {
    enable = true; # Enable CUPS backend
    drivers = with pkgs; [

      gutenprint
      gutenprintBin
      # hplip
      # hplipWithPlugin # can try ` sudo -E hp-setup ` to add the printer.
      # postscript-lexmark
      # samsung-unified-linux-driver
      # splix
      # brlaser
      # brgenml1lpr
      # brgenml1cupswrapper
      # cnijfilter2
      cups-bjnp
      canon-capt
      canon-cups-ufr2
      # epson-escpr2
      # epson-escpr

      # for avahi
      # cups-filters
      # cups-browsed
    ];
  };


  services.avahi = {
    enable = true;
    nssmdns4 = true; # enable mDNS for IPv4 (.local)
    openFirewall = true; # opens UDP/5353 if using NixOS firewall
  };

  # Scanning ------------------------------------------------------------------
  hardware.sane.enable = true; # Enable support for SANE scanners.
  # if the scanner is connected by USB, also set the following option:
  services.ipp-usb.enable = true;

  hardware.sane.extraBackends = [
    pkgs.hplipWithPlugin
    pkgs.sane-airscan
  ];
  services.saned.enable = true; # Enable saned network daemon for remote connection to scanners.
  environment.systemPackages = with pkgs; [
    simple-scan # main
    kdePackages.skanpage # backup





  ];

  #services.input-remapper.enable = true;


  # Keyboard ------------------------------------------------------------------
  hardware.keyboard.qmk.enable = true;
  services.udev.packages = with pkgs; [ via ];


   services.udev.extraRules = ''
# This rule was added by Solaar.
#
# Allows non-root users to have raw access to Logitech devices.
# Allowing users to write to the device is potentially dangerous
# because they could perform firmware updates.

ACTION == "remove", GOTO="solaar_end"
SUBSYSTEM != "hidraw", GOTO="solaar_end"

# USB-connected Logitech receivers and devices
ATTRS{idVendor}=="046d", GOTO="solaar_apply"

# Lenovo nano receiver
ATTRS{idVendor}=="17ef", ATTRS{idProduct}=="6042", GOTO="solaar_apply"

# Bluetooth-connected Logitech devices
KERNELS == "0005:046D:*", GOTO="solaar_apply"

GOTO="solaar_end"

LABEL="solaar_apply"

# Allow any seated user to access the receiver.
# uaccess: modern ACL-enabled udev
TAG+="uaccess"

# Grant members of the "plugdev" group access to receiver (useful for SSH users)
#MODE="0660", GROUP="plugdev"

LABEL="solaar_end"
# vim: ft=udevrules
    '';
  
}
