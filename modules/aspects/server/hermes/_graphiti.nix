{ config, pkgs, lib, ... }:

# graphiti-mcp-server, built as a proper Nix derivation via uv2nix.
#
# All version pinning + PR #1500 patching happens inside the mcp-workspace
# sub-flake (pkgs/graphiti/mcp-workspace/), driven by uv.lock. No git clone,
# no uv sync, no sentinel files — the Nix store contains a hermetically
# built Python environment with graphiti-core[falkordb]==0.29.3 patched.
#
# To bump graphiti-core or falkordb:
#   1. Edit pkgs/graphiti/mcp-workspace/uv.lock (version + sha256)
#   2. Commit
#   3. Rebuild — service is automatically redeployed on next switch.
{
  # FalkorDB via NixOS-managed OCI container (pulls image at activation,
  # survives rebuild/prune — replaces the hand-rolled podman run user service
  # that died when the image left the local store).
  virtualisation.oci-containers = {
    backend = "podman";
    containers.falkordb = {
      # Fully-qualified registry prefix required: erebus podman has no
      # unqualified-search-registries, so bare "falkordb/..." fails to pull.
      image = "docker.io/falkordb/falkordb-server:edge-alpine";
      autoStart = true;
      ports = [ "127.0.0.1:6379:6379" ];
      volumes = [ "/var/lib/hermes/falkordb-data:/var/lib/falkordb/data" ];
      # RDB persistence so the graph survives container restarts.
      cmd = [ "--save" "900" "1" "--save" "300" "10" "--save" "60" "10000" "--dir" "/var/lib/falkordb/data" ];
    };
  };

  systemd.user.services.graphiti-mcp = {
    description = "Graphiti MCP Server (uv2nix-built)";
    after = [ "podman-falkordb.service" ];
    wantedBy = [ "default.target" ];

    unitConfig.ConditionUser = "hermes";

    serviceConfig = {
      Environment = [
        # graphiti_core's default OpenAIRerankerClient constructs an
        # AsyncOpenAI client at init time. Without OPENAI_API_KEY it fails
        # to start. Our reranker is never invoked (bge-reranker on serenity
        # does it) so a dummy value is fine. Reranker calls would route via
        # OPENAI_BASE_URL — pointed at our local litellm so any stray call
        # lands on the proxy instead of api.openai.com. The LLM and embedder
        # still read api_key from config.yaml (seeded from
        # /var/lib/litellm/master-key.txt), not from this env var.
        "OPENAI_API_KEY=«redacted:sk-…»"
        "OPENAI_BASE_URL=http://127.0.0.1:4000/v1"
        "NO_PROXY=127.0.0.1,localhost,127.0.0.1:4000"
      ];
      ExecStart = "${pkgs.graphiti-mcp}/bin/graphiti-mcp-server --config /var/lib/hermes/.config/graphiti-mcp/config.yaml --transport http --host 127.0.0.1 --port 8000";
      Restart = "on-failure";
      RestartSec = 5;
      StandardOutput = "append:/var/lib/hermes/.hermes/logs/graphiti-mcp.log";
      StandardError = "append:/var/lib/hermes/.hermes/logs/graphiti-mcp.log";
    };
  };

  # Generate config.yaml in /var/lib/hermes/.config/graphiti-mcp/ — the
  # service reads $CONFIG_PATH or ./config/config.yaml. We point it at the
  # canonical location via --config below.
  system.activationScripts."hermes-graphiti-config" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
    ++ lib.optional (config.system.activationScripts ? "hermes-litellm-seed") "hermes-litellm-seed"
  ) ''
    mkdir -p /var/lib/hermes/falkordb-data
    chown hermes:hermes /var/lib/hermes/falkordb-data

    mkdir -p /var/lib/hermes/.config/graphiti-mcp
    cat > /var/lib/hermes/.config/graphiti-mcp/config.yaml << CONFIGEOF
llm:
  provider: "openai"
  model: "graphiti-primary"
  structured_output_mode: "tool_calling"
  providers:
    openai:
      api_url: "http://127.0.0.1:4000/v1"
      api_key: "$(cat /var/lib/litellm/master-key.txt 2>/dev/null || echo sk-missing)"

embedder:
  provider: "openai"
  model: "bge-m3"
  dimensions: 1024
  providers:
    openai:
      api_url: "http://127.0.0.1:8081/v1"
      api_key: "$(cat /var/lib/litellm/master-key.txt 2>/dev/null || echo sk-missing)"

graphiti:
  group_id: "likivik"
CONFIGEOF
    chown -R hermes:hermes /var/lib/hermes/.config/graphiti-mcp
  '';
}
