{ den, inputs, lib, ... }:
{
  den.aspects.omp = {
    nixos = { pkgs, ... }: {
      environment.localBinInPath = true;
      programs.nix-ld.enable = true;
      environment.systemPackages = [
        inputs.llm-agents.packages.${pkgs.stdenv.hostPlatform.system}.omp
      ];
    };

    maid = { user, ... }: {
      file.home.".omp".source =
        /Storage/Git/spectacle/modules/users/likivik/dotfiles/omp;
    };
  };
}
