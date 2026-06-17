{ den, inputs, lib, ... }:
{
  den.aspects.opencode = {
    maid = { user, ... }: {
      file.xdg_config."opencode".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/opencode";
    };

    nixos =
      { pkgs, ... }: {
        environment.systemPackages = with pkgs; [
          opencode
          opencode-desktop

          pandoc
          python313Packages.python-docx
          python313Packages.openpyxl
          python313Packages.odfpy
          python313Packages.markitdown
        ];
      };
  };
}
