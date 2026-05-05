{
  inputs,
  den,
  user,
  ...
}:
{
  # user aspect
  den.aspects.desktop-core = {
    includes = [

    ];

    homeManager =
      { pkgs, ... }:
      {



      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos =
      { pkgs, ... }:
      {



      };
  };
}
