# flake-parts `checks` + `apps` — CI guards + VM test for the Hermes deployment.
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

      # Boot the erebus host headless and assert Telegram TLS connectivity.
      # `nix run .#erebus-telegram` — reads serial for TELEGRAM_TLS_OK.
      apps.erebus-telegram =
        let
          vm = inputs.self.nixosConfigurations.erebus.extendModules {
            modules = [ (import ../../tests/erebus-telegram.nix) ];
          };
          run-vm = "${vm.config.system.build.vm}/bin/run-erebus-vm";
        in
        {
          type = "app";
          program =
            pkgs.writeShellScript "erebus-telegram" ''
              exec ${run-vm} -nographic "$@"
            '';
        };
    };
}
