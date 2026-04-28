{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [ pkgs.just ];
  # Optional: set JUST_CONFIG or other env vars
  # shellHook = ''
  #   export JUST_CONFIG="$PWD/justfile"
  # '';
}