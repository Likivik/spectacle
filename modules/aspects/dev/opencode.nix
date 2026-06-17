{ den, inputs, lib, ... }:
{
  den.aspects.opencode = {
    maid = { user, ... }: {
      file.xdg_config."opencode".source = "/Storage/Git/spectacle/modules/users/likivik/dotfiles/opencode";
    };

    nixos =
      { pkgs, ... }:
      let
        mnemosyne-pkg = pkgs.python3Packages.buildPythonPackage rec {
          pname = "mnemosyne-memory";
          version = "3.8.0";
          src = pkgs.fetchFromGitHub {
            owner = "AxDSan";
            repo = "mnemosyne";
            rev = "v${version}";
            hash = "sha256-P+NG+jb7Q/INcAH8XUmd/FUIqPFc+Pdj319JqV9YjAE=";
          };
          pyproject = true;
          nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ];
          propagatedBuildInputs = with pkgs.python3Packages; [
            mcp anyio fastembed sqlite-vec
          ];
        };
      in {
        environment.systemPackages = with pkgs; [
          opencode
          opencode-desktop

          pandoc
          python313Packages.python-docx
          python313Packages.openpyxl
          python313Packages.odfpy
          python313Packages.markitdown

          mnemosyne-pkg
        ];
      };
  };
}
