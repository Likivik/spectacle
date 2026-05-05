{ den, ... }:
{
  den.aspects.direnv = {

    homeManager =
    { pkgs, ... }:
    {

      programs.direnv = {
        enable = true;
        enableZshIntegration = true;
        enableBashIntegration = true; # see note on other shells below
        enableNushellIntegration = true;
        enableFishIntegration = true;
        nix-direnv.enable = true;
      };

    }

  }
}