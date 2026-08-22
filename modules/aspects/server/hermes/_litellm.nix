{ config, pkgs, lib }: {
  # ── LiteLLM AI Gateway (upstream services.litellm module) ────────────
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_16;
    enableTCPIP = true;
    settings.listen_addresses = lib.mkForce "127.0.0.1";
    initialScript = pkgs.writeText "litellm-pg-init" ''
      CREATE ROLE litellm WITH LOGIN PASSWORD 'litellm';
      CREATE DATABASE litellm OWNER litellm;
    '';
  };

  services.litellm = {
    enable = true;
    host = "127.0.0.1";
    port = 4000;
    # NOTE: the upstream module runs the service as a DynamicUser (line 212 of
    # the nixpkgs litellm module). We therefore can NOT pin User/Group here
    # (services.litellm.serviceConfig does not exist). The generated env file
    # + master key are made world-readable (0644) below so the dynamic uid can
    # read them from the StateDirectory /var/lib/litellm.
    environmentFile = "/var/lib/litellm/env";

    settings = {
      # ── Model architecture ────────────────────────────────────────────
      # Each provider gets a unique model_name so LiteLLM can chain fallbacks
      # explicitly. Graphiti calls "graphiti-primary" (MiniMax-M3); on any
      # retryable error (404, 429, 5xx, timeout) LiteLLM falls through the
      # fallback chain to the free providers.
      #
      # To update a model name (e.g. Groq renames it again):
      #   1. Edit the `model =` field below
      #   2. jj bookmark set dev -r @ && jj git push --all
      #   3. sudo nixos-rebuild switch --flake .#erebus
      model_list = [
        # ── Primary (graphiti-primary): MiniMax-M3 (Token Plan, ~$0) ──
        {
          model_name = "graphiti-primary";
          litellm_params = {
            model = "openai/MiniMax-M3";
            api_base = "https://api.minimax.io/v1";
            api_key = "os.environ/MINIMAX_KEY";
            # C-plan: throttle locally so bursts queue instead of 429 upstream.
            rpm = 200;      # under MiniMax's 200 RPM
            tpm = 8000000;  # under MiniMax's 10M TPM
            allowed_fails = 4;
            cooldown_time = 30;
          };
        }
        # ── Fallback 1: Groq gpt-oss-120b (free, RPD-limited) ──
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "groq/openai/gpt-oss-120b";
            api_key = "os.environ/GROQ_KEY";
            # Free Groq: 30 RPM / 8K TPM / 1000 RPD — cap below each.
            # Per-deployment cooldown tuning: a single 429 must NOT bench the
            # deployment for 5 minutes while fallbacks are also rate-limited —
            # that combo produced RouterRateLimitError storms (Aug 15-22) and
            # silently dropped graphiti episodes.
            rpm = 28;
            tpm = 7000;
            rpd = 900;
            allowed_fails = 4;
            cooldown_time = 30;
          };
        }
        {
          model_name = "mistral-small-latest";
          litellm_params = {
            model = "openai/mistral-small-latest";
            api_base = "https://api.mistral.ai/v1";
            api_key = "os.environ/MISTRAL_KEY";
            rpm = 50;
            tpm = 200000;
          };
        }
        {
          model_name = "hf-gpt-oss-20b";
          litellm_params = {
            model = "openai/gpt-oss-20b:fastest";
            api_base = "https://router.huggingface.co/v1";
            api_key = "os.environ/HF_TOKEN";
            rpm = 20;
            rpd = 200;
          };
        }
        {
          model_name = "openrouter-free";
          litellm_params = {
            model = "openrouter/openrouter/free";
            api_key = "os.environ/OPENROUTER_KEY";
            rpm = 2;
            rpd = 40;
          };
        }
      ];
      router_settings = {
        routing_strategy = "simple-shuffle";
        # Retry once per request before falling through to the next model.
        num_retries = 1;
        timeout = 60;
        allowed_fails = 4;
        cooldown_time = 30;
        # graphiti-primary is the primary model_name (MiniMax-M3), with
        # free providers chained as fallbacks.
        # LiteLLM 1.89.0 doesn't support routing_groups as virtual models,
        # so we use model_name + fallbacks instead.
        fallbacks = [
          { "graphiti-primary" = [ "graphiti-free" "mistral-small-latest" "hf-gpt-oss-20b" "openrouter-free" ]; }
        ];
      };
      litellm_settings = {
        # Langfuse Cloud observability via OTel (tokens in/out + $ cost).
        # Uses langfuse_otel callback (not legacy "langfuse") — the legacy
        # path constructs Langfuse() directly and crashes on the nixpkg's
        # langfuse 4.0.2 SDK (sdk_integration kwarg removed). OTel path is
        # version-safe; opentelemetry deps are present in the nixpkg.
        callbacks = [ "langfuse_otel" ];
      };
    };
  };

  system.activationScripts."hermes-litellm-seed" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    mkdir -p /var/lib/litellm

    # ── Master key: reuse sops if present, else generate + persist locally ──
    MK_FILE=/var/lib/litellm/master-key.txt
    SOPS_MK=/run/secrets/hermes-litellm/master-key
    if [ -f "$SOPS_MK" ]; then
      install -m 0600 "$SOPS_MK" "$MK_FILE"
    elif [ ! -s "$MK_FILE" ]; then
      # Pure-bash master key (24 bytes hex). The activation env lacks
      # openssl on PATH, so avoid external binaries — use only bash builtins.
      mk=""; i=0
      while [ $i -lt 24 ]; do
        mk+=$(printf "%02x" $((RANDOM * 256 / 32768))); i=$((i + 1))
      done
      printf '%s' "$mk" > "$MK_FILE"
    fi
    chmod 0644 "$MK_FILE"

    # ── EnvironmentFile: pull keys from the SAME sops paths mitmproxy uses.
    #    Every var is ALWAYS emitted (empty fallback) so LiteLLM config-load
    #    never crashes on an absent os.environ/X — dead keys just mean dead
    #    deployments at request time, not a startup failure. ──
    SECRETS=/run/secrets/hermes-mitmproxy/llm-providers
    {
      echo "LITELLM_MASTER_KEY=$(cat "$MK_FILE")"
      # NOTE: no DATABASE_URL — litellm 1.89.0 nixpkg lacks Prisma engine
      # binaries, so setting DATABASE_URL crashes startup ("Unable to find
      # Prisma binaries"). Spend logging deferred to Langfuse (separate
      # service) per original plan.
      echo "NO_PROXY=127.0.0.1,localhost,openrouter.ai,api.openrouter.ai"
      echo "LITELLM_LOG=INFO"
      echo "OPENROUTER_KEY=$([ -f "$SECRETS/openrouter/api-key" ] && cat "$SECRETS/openrouter/api-key" || echo "")"
      echo "OPENCODE_KEY1=$([ -f "$SECRETS/opencode/api-key1" ] && cat "$SECRETS/opencode/api-key1" || echo "")"
      echo "OPENCODE_KEY2=$([ -f "$SECRETS/opencode/api-key2" ] && cat "$SECRETS/opencode/api-key2" || echo "")"
      echo "OPENCODE_KEY3=$([ -f "$SECRETS/opencode/api-key3" ] && cat "$SECRETS/opencode/api-key3" || echo "")"
      echo "OPENCODE_KEY4=$([ -f "$SECRETS/opencode/api-key4" ] && cat "$SECRETS/opencode/api-key4" || echo "")"
      echo "DEEPSEEK_KEY=$([ -f "$SECRETS/deepseek/api-key" ] && cat "$SECRETS/deepseek/api-key" || echo "")"
      echo "GROQ_KEY=$([ -f "$SECRETS/groq/api-key" ] && cat "$SECRETS/groq/api-key" || echo "")"
      echo "HF_TOKEN=$([ -f "$SECRETS/huggingface/api-key" ] && cat "$SECRETS/huggingface/api-key" || echo "")"
      echo "MISTRAL_KEY=$([ -f "$SECRETS/mistral/api-key" ] && cat "$SECRETS/mistral/api-key" || echo "")"
      echo "MINIMAX_KEY=$(cat /run/secrets/hermes/minimax-api-key 2>/dev/null || echo \"\")"
      LF=/run/secrets/hermes-mitmproxy/langfuse
      echo "LANGFUSE_PUBLIC_KEY=$([ -f "$LF/public-key" ] && cat "$LF/public-key" || echo "")"
      echo "LANGFUSE_SECRET_KEY=$([ -f "$LF/secret-key" ] && cat "$LF/secret-key" || echo "")"
      echo "LANGFUSE_HOST=https://cloud.langfuse.com"
      echo "LANGFUSE_OTEL_HOST=https://cloud.langfuse.com"
    } > /var/lib/litellm/env
    chmod 0644 /var/lib/litellm/env
  '';
}
