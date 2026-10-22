{ den, inputs, lib, ... }:
{
  den.aspects.opencode = {
    maid =
      { user, host, ... }:
      let
        gitRoot = import ../../../lib/git-root.nix host;
      in
      {
        file.xdg_config."opencode".source = "${gitRoot}/spectacle/modules/users/likivik/dotfiles/opencode";
      };

    nixos =
      { pkgs, ... }: {
        environment.localBinInPath = true;
        environment.sessionVariables.OPENCODE_ENABLE_EXA = "1";
        programs.nix-ld.enable = true;
        environment.systemPackages = with pkgs; [
          opencode
          opencode-desktop

          # These are for documents/tables access
          pandoc
          python313Packages.python-docx
          python313Packages.openpyxl
          python313Packages.odfpy
        ];
      };
  };
}
