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

        # Full-stack MCP roundtrip: boot the real graphiti-mcp-server against a
        # fresh FalkorDB, seed an episode (direct write, no model), then read it
        # back over streamable-HTTP (init + list_tools + get_episodes). Regresses
        # the mcp 1.x->2.0 transport break + config/FalkorDB/tenant wiring in one.
        mcp-roundtrip =
          let
            rt-py = inputs.graphiti-mcp-workspace.envs.${pkgs.system}.runtime;
            gmc = inputs.graphiti-mcp-workspace.packages.${pkgs.system}.graphiti-mcp;
            driver = ../../pkgs/hermes-tests/graphiti/mcp_roundtrip_driver.py;
            gmcp-config = pkgs.writeText "graphiti-mcp-config.yaml" ''
              llm:
                provider: "openai"
                model: "graphiti-primary"
                structured_output_mode: "tool_calling"
                providers:
                  openai:
                    api_url: "http://127.0.0.1:4000/v1"
                    api_key: "sk-dummy"

              embedder:
                provider: "openai"
                model: "bge-m3"
                dimensions: 1024
                providers:
                  openai:
                    api_url: "http://127.0.0.1:4000/v1"
                    api_key: "sk-dummy"

              graphiti:
                group_id: "likivik"

              database:
                providers:
                  falkordb:
                    database: "likivik"
            '';
            falkordb-image = pkgs.dockerTools.pullImage {
              imageName = "falkordb/falkordb-server";
              imageDigest = "sha256:e8bb6653262d9b58c99988de5ba6e4c8dc0f00a8c6056d3b111e35ee2253355d";
              sha256 = "sha256-/lRZHeUwjIUn3w4CoREyNgyXHwYCmKt+B6v7iCPehjA=";
              finalImageName = "falkordb/falkordb-server";
              finalImageTag = "edge-alpine";
            };
          in
          pkgs.testers.nixosTest {
            name = "mcp-roundtrip";
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
              systemd.services.graphiti-mcp = {
                wantedBy = [ "multi-user.target" ];
                after = [ "podman-falkordb.service" ];
                environment = {
                  OPENAI_API_KEY = "sk-dummy";
                  OPENAI_BASE_URL = "http://127.0.0.1:4000/v1";
                  NO_PROXY = "127.0.0.1,localhost";
                };
                serviceConfig = {
                  ExecStart = "${gmc}/bin/graphiti-mcp-server --config ${gmcp-config} --transport http --host 127.0.0.1 --port 8000";
                  Restart = "on-failure";
                  RestartSec = "2";
                };
              };
            };
            testScript = ''
              start_all()
              machine.wait_for_unit("podman-falkordb.service")
              machine.wait_for_open_port(6379)
              machine.wait_for_unit("graphiti-mcp.service")
              machine.wait_for_open_port(8000)
              machine.succeed(
                "${rt-py}/bin/python3 ${driver} 127.0.0.1 6379 likivik http://127.0.0.1:8000/mcp"
              )
            '';
          };

        # MCP handshake roundtrip for himalaya-mcp (Rust himalaya + TS wrapper):
        # spawn the real `node dist/index.js` over MCP stdio, run initialize +
        # list_tools, assert the confirm-gated surface (send/compose/draft + read
        # + attachments). list_tools is static (no IMAP dial), so this is
        # hermetic. Regresses: TS bundle builds, stdio MCP handshake, registry.
        email-mcp-roundtrip =
          let
            himalaya-mcp = import ../../pkgs/himalaya-mcp.nix {
              inherit pkgs;
              lib = pkgs.lib;
            };
            # The 2.1.0 override (same as the aspect deploys) — NOT pkgs.himalaya
            # (nixpkgs 2.0.0, which dies mid-exchange with EAGAIN on large APPEND,
            # himalaya #731/#732). The test must exercise what actually ships.
            himalaya = pkgs.callPackage ../../pkgs/himalaya.nix { };
            driver-py = pkgs.python3.withPackages (p: [ p.mcp ]);
            driver = ../../pkgs/hermes-tests/email/email_mcp_roundtrip.py;
          in
          pkgs.testers.nixosTest {
            name = "email-mcp-roundtrip";
            nodes.machine = { ... }: {
              environment.systemPackages = [ himalaya pkgs.nodejs ];
            };
            testScript = ''
              start_all()
              machine.wait_for_unit("multi-user.target")
              # CLI smoke: binary runs and is the 2.1.0 override (transport retry),
              # guarding against silent drift back to nixpkgs 2.0.0.
              machine.succeed("${himalaya}/bin/himalaya --version | grep -q 'v2.1.0'")
              machine.succeed(
                "${driver-py}/bin/python3 ${driver} ${himalaya-mcp}/dist/index.js ${himalaya}/bin/himalaya"
              )
            '';
          };

        # MiniMax tool-calling schema fidelity — hermetic unit on the real
        # _coerce_for_schema ({item:"0"} collapse + str->number repair) under
        # the graphiti runtime venv (needs graphiti_core/openai/pydantic).
        minimax-coerce =
          let
            rt-py = inputs.graphiti-mcp-workspace.envs.${pkgs.system}.runtime;
          in
          pkgs.runCommand "minimax-coerce" { } ''
            ${rt-py}/bin/python3 ${../../pkgs/hermes-tests/graphiti/minimax_coerce.py} \
              ${../../pkgs/graphiti/mcp-workspace/src/services/minimax_client.py}
            touch "$out"
          '';

        # Every litellm model must resolve cost (exact price-map key OR explicit
        # per-token cost) — otherwise gen_ai.usage.cost never fires and Langfuse
        # records totalCost=0. Regresses the openai/MiniMax-M3 -> None-cost bug.
        litellm-cost-map = pkgs.runCommand "litellm-cost-map" { } ''
          ${pkgs.python3}/bin/python3 ${../../pkgs/hermes-tests/graphiti/litellm_cost_map.py} \
            ${../../modules/aspects/server/hermes/_litellm.nix} ${pkgs.litellm}
          touch "$out"
        '';

        # litellm's langfuse_otel path must emit OpenInference span attributes
        # llm.cost.total + llm.model_name (fed by response_cost + model) — else
        # Langfuse v4 drops cost (totalCost=0) and model (modelId=null).
        langfuse-otel-attrs = pkgs.runCommand "langfuse-otel-attrs" { } ''
          ${pkgs.python3}/bin/python3 ${../../pkgs/hermes-tests/graphiti/langfuse_otel_attrs.py} \
            ${pkgs.litellm}
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
          # `program` must be a string; writeShellScript emits a single file at $out.
          program =
            "${pkgs.writeShellScript "erebus-telegram" ''
              exec ${run-vm} -nographic "$@"
            ''}";
        };
    };
}
