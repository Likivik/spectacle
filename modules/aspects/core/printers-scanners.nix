{ inputs, den, ... }:
{
  den.aspects.printersScanners = {
    nixos = { config, pkgs, ... }: {
      hardware.bluetooth = {
        enable = true;
        powerOnBoot = true;
        settings.General = {
          experimental = true;
          Privacy = "device";
          JustWorksRepairing = "always";
          Class = "0x000100";
          FastConnectable = true;
        };
      };

      hardware.xpadneo.enable = true;
      boot = {
        extraModulePackages = with config.boot.kernelPackages; [ xpadneo ];
        extraModprobeConfig = ''
          options bluetooth disable_ertm=Y
        '';
      };

      services.pipewire = {
        enable = true;
        alsa.enable = true;
        alsa.support32Bit = true;
        pulse.enable = true;
        jack.enable = true;
      };

      services.printing = {
        enable = true;
        drivers = with pkgs; [
          gutenprint
          gutenprintBin
        ];
      };

      services.avahi = {
        enable = true;
        nssmdns4 = true;
        openFirewall = true;
      };

      hardware.sane.enable = true;
      services.saned.enable = true;
      services.ipp-usb.enable = true;

      hardware.sane.extraBackends = [
        pkgs.hplipWithPlugin
        pkgs.sane-airscan
      ];
      environment.systemPackages = with pkgs; [
        simple-scan
      ];

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
    };
  };
}