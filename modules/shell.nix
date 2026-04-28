

{ inputs, den, devshell, ... }:

flake-file.inputs = {
  devshell.url = "github:numtide/devshell";
};

{

  perSystem =
    { pkgs, self', ... }:

    {

      devShells = {
        just = pkgs.mkShell {
          buildInputs = [ pkgs.just ];
          shellHook = ''
            export JUST_CONFIG="$PWD/justfile"
            PS1="(just) $PS1"
            echo "Entering devShell with just on PATH"
          '';
        };

      };

    };
}
