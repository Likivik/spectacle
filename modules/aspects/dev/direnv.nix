{ den, ... }:
{
  den.aspects.direnv = {

    nixos = { ... }: {
      # micro is a lightweight terminal editor safe for root contexts.
      # Programs that check $VISUAL first (like git, sops) use that;
      # $EDITOR is the safer fallback.
      environment.sessionVariables.EDITOR = "micro";
    };

    homeManager =
    { pkgs, ... }:
    {
      home.packages = with pkgs; [
        vscodium
      ];

      home.sessionVariables.VISUAL = "vscodium";

      programs.direnv = {
        enable = true;
        enableZshIntegration = true;
        enableBashIntegration = true; # see note on other shells below
        enableNushellIntegration = true;
        enableFishIntegration = true;
        nix-direnv.enable = true;
      };
    };

  };
}