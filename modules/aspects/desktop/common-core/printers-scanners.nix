{ inputs, den, ... }:
{
  den.aspects.printersScanners = {
    nixos = { config, pkgs, ... }: {

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


    };
  };
}