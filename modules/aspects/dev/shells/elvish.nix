{ den, ... }:
{
  den.aspects.elvish = {

    nixos =
      { pkgs, ... }:
      {

        environment.systemPackages = [
          pkgs.elvish
        ];

      };

  };
}
