{ inputs, determinate, ... }: {

  flake-file.inputs = {
    determinate.url = "https://flakehub.com/f/DeterminateSystems/determinate/*";
  };

  # imports = [ inputs.determinate.nixosModules.default ];

  den.aspects.determinate = {
    nixos = { ... }: {
      imports = [ inputs.determinate.nixosModules.default ];
    };
  };

}