{ den, inputs, lib, ... }:
{
  den.aspects.opencode = {
    maid = { user, ... }: {
      file.xdg_config."opencode".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/opencode";
    };

    nixos =
      { pkgs, ... }: {
        environment.localBinInPath = true;
        environment.sessionVariables.OPENCODE_ENABLE_EXA = "1";
        environment.systemPackages = with pkgs; [
          opencode
          opencode-desktop

          # These are for documents/tables access
          pandoc
          python313Packages.python-docx
          python313Packages.openpyxl
          python313Packages.odfpy
          python313Packages.markitdown
        ];
      };
  };
}
