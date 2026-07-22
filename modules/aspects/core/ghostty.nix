{ inputs, den, ... }: {
  den.aspects.core.ghostty-terminfo = {
    nixos = { pkgs, ... }: {
      environment.systemPackages = [ pkgs.ghostty.terminfo ];
    };
  };
}
