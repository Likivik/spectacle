{ inputs, den, ... }:
{

# Look into defining your own aspects 
# I think it's just

den.aspects.determinateNix = {
  nixos = { pkgs, ... }: { 
    imports = [ inputs.determinate.nixosModules.default ];
    nix.settings.substituters = ["https://install.determinate.systems"];
    nix.settings.trusted-public-keys = ["cache.flakehub.com-3:hJuILl5sVK4iKm86JzgdXW12Y2Hwd5G07qKtHTOcDCM="];

    };
  };

# and then how do we include it in all systems by default?
# in den.default = { includes = [];}; 
}