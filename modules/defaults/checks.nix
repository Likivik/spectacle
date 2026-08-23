# flake-parts `checks` + `apps` — CI guards + VM test for the Hermes deployment.
{ inputs, ... }:
{
  perSystem =
    { pkgs, ... }:
    {
      checks = {
        # Config still evaluates + builds (the "won't break Hermes on deploy" guard).
        erebus-build = inputs.self.nixosConfigurations.erebus.config.system.build.toplevel;

        # No-VM dependency-contract smoke against the *sealed* hermes venv.
        # Catches mcp 1.x->2.0 rename, otel<1.42 (RANDOM_TRACE_ID), and the
        # langfuse PYTHONPATH-layering regression — all in seconds, no VM.
        hermes-imports =
          let
            hermes-pkg = (inputs.hermes-agent.packages.${pkgs.system}.minimal).override {
              extraDependencyGroups = [ "messaging" "observability" ];
            };
          in
          pkgs.runCommand "hermes-imports" { } ''
            ${hermes-pkg.hermesVenv}/bin/python3 ${../../pkgs/hermes-tests/venv_imports.py}
            touch "$out"
          '';

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

        # VM roundtrip: boots a fresh FalkorDB + runs the graphiti-core driver
        # write->read path against the tenant graph (regresses the count:0 bug
        # where reads hit the empty default_db). No model/embedder (driver-level).
        graphiti-roundtrip =
          let
            rt-py = inputs.graphiti-mcp-workspace.envs.${pkgs.system}.runtime;
            rt-script = ../../pkgs/hermes-tests/graphiti/roundtrip_driver.py;
            falkordb-image = pkgs.dockerTools.pullImage {
              imageName = "falkordb/falkordb-server";
              imageDigest = "sha256:e8bb6653262d9b58c99988de5ba6e4c8dc0f00a8c6056d3b111e35ee2253355d";
              sha256 = "sha256-/lRZHeUwjIUn3w4CoREyNgyXHwYCmKt+B6v7iCPehjA=";
              finalImageName = "falkordb/falkordb-server";
              finalImageTag = "edge-alpine";
            };
          in
          pkgs.testers.nixosTest {
            name = "graphiti-roundtrip";
            nodes.machine = { ... }: {
              virtualisation.oci-containers = {
                backend = "podman";
                containers.falkordb = {
                  image = "falkordb/falkordb-server:edge-alpine";
                  imageFile = falkordb-image;
                  autoStart = true;
                  ports = [ "127.0.0.1:6379:6379" ];
                };
              };
            };
            testScript = ''
              start_all()
              machine.wait_for_unit("podman-falkordb.service")
              machine.wait_for_open_port(6379)
              machine.succeed("${rt-py}/bin/python3 ${rt-script} 127.0.0.1 6379 likivik")
            '';
          };
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
          # `program` must be a string; writeShellScript emits a single file at $out.
          program =
            "${pkgs.writeShellScript "erebus-telegram" ''
              exec ${run-vm} -nographic "$@"
            ''}";
        };
    };
}
