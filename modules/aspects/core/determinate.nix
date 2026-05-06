{ inputs, den, ... }:
{

  # I think defining your own aspects goes like this:

  den.aspects.determinateNix = {
    nixos =
      { ... }:
      {
        imports = [ inputs.determinate.nixosModules.default ]; # this is how you import modules from external projects!
        nix.settings.substituters = [ "https://install.determinate.systems" ];
        nix.settings.trusted-public-keys = [
          "cache.flakehub.com-3:hJuILl5sVK4iKm86JzgdXW12Y2Hwd5G07qKtHTOcDCM="
        ];
      };
  };

  # and then in for example 'defaults.nix' we add:
  # den.default = {
  #   includes = [ den.aspects.determinateNix ];
  # };
}
