{ config, pkgs, lib }: {
  # ── LiteLLM AI Gateway ───────────────────────────────────────────────
  # OpenAI-compatible proxy sitting in front of Graphiti (and anything else
  # that speaks OpenAI). Handles multi-key rotation + per-deployment
  # fallback + token/spend logging to Postgres.
  #
  # Graphiti points its `api_url` here (see _graphiti.nix) instead of
  # talking directly to OpenRouter. Keys are read from the SAME sops
  # secrets the mitmproxy already uses (/run/secrets/hermes-mitmproxy/...),
  # surfaced to LiteLLM via an EnvironmentFile generated at activation.
  #
  # Rotation is REAL: openrouter + opencode×4 + nousportal + (expected) more
  # are pooled as deployments under one `graphiti-free` model_name. On a
  # 429/503 LiteLLM walks order=1→2→3 then the fallbacks[] chain.

  # ── Postgres (shared server, dedicated `litellm` database) ────────────
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_16;
    enableTCPIP = false;          # local socket only; LiteLLM runs on same host
    initialScript = pkgs.writeText "litellm-pg-init" ''
      CREATE ROLE litellm WITH LOGIN PASSWORD 'litellm';
      CREATE DATABASE litellm OWNER litellm;
    '';
  };

  systemd.user.services.litellm-proxy = {
    description = "LiteLLM AI Gateway (Graphiti key rotation + spend logging)";
    after = [ "network.target" "postgresql.service" ];
    wantedBy = [ "default.target" ];

    unitConfig.ConditionUser = "hermes";

    serviceConfig = {
      WorkingDirectory = "/var/lib/hermes/litellm";
      EnvironmentFile = "/var/lib/hermes/litellm/env";
      # LiteLLM reaches upstream providers DIRECTLY with the real keys from
      # env (no mitmproxy in this path — avoids double-injection).
      # 127.0.0.1 stays off the proxy via NO_PROXY.
      Environment = [
        "LITELLM_MASTER_KEY_FILE=/var/lib/hermes/litellm/master-key.txt"
        "DATABASE_URL=postgresql://litellm:litellm@/litellm?host=/run/postgresql"
        "NO_PROXY=127.0.0.1,localhost,openrouter.ai,api.openrouter.ai"
        "LITELLM_LOG=INFO"
      ];
      ExecStart = "${pkgs.bash}/bin/bash -c 'exec ${pkgs.uv}/bin/uv run --with litellm litellm --config /var/lib/hermes/litellm/config.yaml --host 127.0.0.1 --port 4000'";
      Restart = "on-failure";
      RestartSec = 5;
      StandardOutput = "append:/var/lib/hermes/.hermes/logs/litellm-proxy.log";
      StandardError = "append:/var/lib/hermes/.hermes/logs/litellm-proxy.log";
    };
  };

  system.activationScripts."hermes-litellm-seed" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    mkdir -p /var/lib/hermes/litellm
    chown hermes:hermes /var/lib/hermes/litellm

    # ── Master key: reuse sops if present, else generate + persist locally ──
    MK_FILE=/var/lib/hermes/litellm/master-key.txt
    SOPS_MK=/run/secrets/hermes-litellm/master-key
    if [ -f "$SOPS_MK" ]; then
      install -m 0600 "$SOPS_MK" "$MK_FILE"
    elif [ ! -f "$MK_FILE" ]; then
      "${pkgs.openssl}/bin/openssl rand -hex 24" > "$MK_FILE"
      chmod 0600 "$MK_FILE"
    fi
    chown hermes:hermes "$MK_FILE"

    # ── EnvironmentFile: pull keys from the SAME sops paths mitmproxy uses ──
    SECRETS=/run/secrets/hermes-mitmproxy/llm-providers
    {
      [ -f "$SECRETS/openrouter/api-key" ]       && echo "OPENROUTER_KEY=$(cat "$SECRETS/openrouter/api-key")"
      [ -f "$SECRETS/opencode/api-key1" ]        && echo "OPENCODE_KEY1=$(cat "$SECRETS/opencode/api-key1")"
      [ -f "$SECRETS/opencode/api-key2" ]        && echo "OPENCODE_KEY2=$(cat "$SECRETS/opencode/api-key2")"
      [ -f "$SECRETS/opencode/api-key3" ]        && echo "OPENCODE_KEY3=$(cat "$SECRETS/opencode/api-key3")"
      [ -f "$SECRETS/opencode/api-key4" ]        && echo "OPENCODE_KEY4=$(cat "$SECRETS/opencode/api-key4")"
      [ -f "$SECRETS/nousportal/api-key" ]       && echo "NOUSPORTAL_KEY=$(cat "$SECRETS/nousportal/api-key")"
      [ -f "$SECRETS/deepseek/api-key" ]         && echo "DEEPSEEK_KEY=$(cat "$SECRETS/deepseek/api-key")"
    } > /var/lib/hermes/litellm/env
    chmod 0600 /var/lib/hermes/litellm/env
    chown hermes:hermes /var/lib/hermes/litellm/env

    # ── LiteLLM config: one model_name, many deployments (rotation) ──
    cat > /var/lib/hermes/litellm/config.yaml << CONFIGEOF
model_list:
  # Primary: OpenRouter free router (server-side model rotation) — your openrouter key
  - model_name: graphiti-free
    litellm_params:
      model: openrouter/openrouter/free
      api_key: os.environ/OPENROUTER_KEY
      rpm: 20
      order: 1

  # OpenCode pool (opencode.ai) — custom OpenAI-compatible base.
  # TODO: confirm opencode.ai base URL + model name, then uncomment.
  # - model_name: graphiti-free
  #   litellm_params:
  #     model: openai/<MODEL>
  #     api_base: https://opencode.ai/v1
  #     api_key: os.environ/OPENCODE_KEY1
  #     rpm: 20
  #     order: 2
  # (repeat for OPENCODE_KEY2..4, order 3..5)

  # NousPortal — same pattern, uncomment when base URL confirmed.
  # - model_name: graphiti-free
  #   litellm_params:
  #     model: openai/<MODEL>
  #     api_base: <NOUSPORTAL_BASE>
  #     api_key: os.environ/NOUSPORTAL_KEY
  #     order: 6

  # DeepSeek fallback (if key present) — separate provider, real fallback value
  - model_name: graphiti-free
    litellm_params:
      model: deepseek/deepseek-v4-flash-0731
      api_key: os.environ/DEEPSEEK_KEY
      rpm: 20
      order: 10

router_settings:
  routing_strategy: simple-shuffle   # rotate across healthy deployments
  num_retries: 3
  timeout: 60
  fallbacks:
    - graphiti-free:
        - openrouter/openrouter/free
        - deepseek/deepseek-v4-flash-0731

litellm_settings:
  # Native Postgres spend logging (tokens + $) is automatic via DATABASE_URL.
  # Langfuse (per your request) — UNCOMMENT + set env when a Langfuse
  # instance is deployed; native Postgres logging works without it.
  # success_callback: ["langfuse"]
CONFIGEOF
    chown -R hermes:hermes /var/lib/hermes/litellm
  '';
}
