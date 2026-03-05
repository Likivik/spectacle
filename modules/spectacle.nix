{
  # host aspect
  den.aspects.spectacle = {
    # host NixOS configuration
    nixos =
      { pkgs, ... }:
      {
        environment.systemPackages = [ pkgs.hello ];
      };

    # host provides default home environment for its users
    homeManager =
      { pkgs, ... }:
      {
        home.packages = [ pkgs.micro ];
      };
  };
}
