# flake-parts `checks` — CI-able guards for the Hermes deployment.
#
# NOTE on the boot nixosTest: den only re-exports `nixosConfigurations.erebus`
# (evaluated), not importable per-host modules (`nixosModules` is empty), so a
# clean `pkgs.nixosTest` that re-imports the host isn't wired yet. The
# `erebus-build` check below covers the "config still compiles" half; the full
# boot+assert remains the manual `nix run .#erebus` VM procedure for now.
{ inputs, ... }:
{
  perSystem =
    { pkgs, ... }:
    {
      checks = {
        # Config still evaluates + builds (the "won't break Hermes on deploy" guard).
        erebus-build = inputs.self.nixosConfigurations.erebus.config.system.build.toplevel;

        # Hermetic hermes-tests (gateway proxy-removal guard + graphiti wiring).
        # Reads the repo's .nix source via conftest, so copy the tree in.
        hermes-tests =
          let
            py = pkgs.python3.withPackages (p: [ p.pytest ]);
          in
          pkgs.runCommand "hermes-tests" { buildInputs = [ py ]; } ''
            cp -r ${../..} repo
            cd repo/pkgs/hermes-tests
            HOME=$(mktemp -d) ${py}/bin/python -m pytest -m "not live" -q
            touch "$out"
          '';
      };
    };
}
