{ den, ... }:
{
  den.aspects.jujutsu = {
    nixos = { pkgs, ... }: {
      environment.systemPackages = [ pkgs.jujutsu ];
    };
  };
}
