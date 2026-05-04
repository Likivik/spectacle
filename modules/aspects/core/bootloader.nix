{ inputs, den, ... }:
{
  den.aspects.bootloader = {
    nixos =
      { config, pkgs, ... }:
      {
        boot = {
          loader = {
            systemd-boot = {
              enable = true;
              consoleMode = "max";
              configurationLimit = 25;
            };
            efi.canTouchEfiVariables = true;
          };

          tmp.cleanOnBoot = true;
        };
      };
  };
}