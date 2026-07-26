{ inputs, den, ... }:
{
  den.aspects.desktop.common-extra.extra-inbox = {
    nixos =
      { config, pkgs, ... }:
      {
        programs.thunderbird.enable = true;

      };
  };
}
