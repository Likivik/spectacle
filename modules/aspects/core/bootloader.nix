{ inputs, den, ... }:
{
  den.aspects.core.bootloader = {
    nixos =
      { config, pkgs, ... }:
      {
        boot = {
          loader = {
            systemd-boot = {
              enable = true;
              consoleMode = "max";
              configurationLimit = 50;
            };
            efi.canTouchEfiVariables = true;
          };

          tmp.cleanOnBoot = true;
        };
      };
  };
}