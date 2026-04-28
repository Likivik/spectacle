
{ inputs, lib, devshell, den, self, ... }:
{
flake.den = den;  # remove after debugging  
  flake-file.inputs = {
    devshell.url = "github:numtide/devshell";
  };

  # flake.den = den;  # remove after debugging
  
  perSystem =
    { pkgs, den, ... }:
    let
      host = inputs.self.nixosConfigurations.spectacle.config;
    in
    {
      
      devShells.default = pkgs.mkShell {
        buildInputs = [ pkgs.just ];
        shellHook = ''
          export JUST_CONFIG="$PWD/justfile"
          PS1="(just) $PS1"
          echo "Entering devShell with just on PATH"
          nix repl --expr '
          let 
            flake = builtins.getFlake (toString ./.);
          in 
            flake // { 
              lib = flake.inputs.nixpkgs.lib;
              
               }
            '
        '';
      };
    };
}

/* --------------------------------------------------------------------------------------------------------
  I've updated modules/shell.nix to automatically start a pre-configured nix repl when you run nix develop.  
                                                                                                             
  Instead of typing :lf . and importing <nixpkgs> manually, the repl is initialized with an expression that  
  automatically loads the current flake and mixes in lib. Since you are in a Flake environment, I used the   
  nixpkgs input from your flake (flake.inputs.nixpkgs.lib) to get lib. This is much better and cleaner than  
  importing <nixpkgs>, which relies on impure, stateful Nix channels.

  1. It will set up the environment and put just on your $PATH
  2. It will immediately drop you into the pre-loaded nix repl.
  3. If you ever need to use the just command or drop back to the standard terminal
  shell, just exit the repl (type `:q` or press `Ctrl+D`) and you'll be in the nix
  develop bash shell with just ready to use
  --------------------------------------------------------------------------------------------------------- */