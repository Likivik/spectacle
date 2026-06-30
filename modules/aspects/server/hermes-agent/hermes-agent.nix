{ inputs, den, lib, ... }:
{
  flake-file.inputs = {
    hermes-agent = {
      url = "github:NousResearch/hermes-agent";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.server.hermes-agent = {
    nixos =
      { config, ... }:
      {
        imports = [ inputs.hermes-agent.nixosModules.default ];

        services.hermes-agent = {
          enable = true;
          addToSystemPackages = true;
          extraDependencyGroups = [ "messaging" ];
          restart = "always";
          restartSec = 5;
        };
      };
  };
}
