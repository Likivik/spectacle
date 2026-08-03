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
      model_list = [
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openrouter/openrouter/free";
            api_key = "os.environ/OPENROUTER_KEY";
            rpm = 20;
            order = 1;
          };
        }
        # OpenCode Zen (pay-per-use; has 7 free models e.g. deepseek-v4-flash-free).
        # One key covers Zen + Go; only the base URL differs.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash-free";
            api_base = "https://opencode.ai/zen/v1";
            api_key = "os.environ/OPENCODE_KEY1";
            rpm = 20;
            order = 2;
          };
        }
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash-free";
            api_base = "https://opencode.ai/zen/v1";
            api_key = "os.environ/OPENCODE_KEY2";
            rpm = 20;
            order = 3;
          };
        }
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash-free";
            api_base = "https://opencode.ai/zen/v1";
            api_key = "os.environ/OPENCODE_KEY3";
            rpm = 20;
            order = 4;
          };
        }
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash-free";
            api_base = "https://opencode.ai/zen/v1";
            api_key = "os.environ/OPENCODE_KEY4";
            rpm = 20;
            order = 5;
          };
        }
        # OpenCode Go (subscription; open-source models only, no free tier).
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash";
            api_base = "https://opencode.ai/zen/go/v1";
            api_key = "os.environ/OPENCODE_KEY1";
            rpm = 20;
            order = 6;
          };
        }
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash";
            api_base = "https://opencode.ai/zen/go/v1";
            api_key = "os.environ/OPENCODE_KEY2";
            rpm = 20;
            order = 7;
          };
        }
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash";
            api_base = "https://opencode.ai/zen/go/v1";
            api_key = "os.environ/OPENCODE_KEY3";
            rpm = 20;
            order = 8;
          };
        }
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/deepseek-v4-flash";
            api_base = "https://opencode.ai/zen/go/v1";
            api_key = "os.environ/OPENCODE_KEY4";
            rpm = 20;
            order = 9;
          };
        }
        # NousPortal dropped: Hermes-4-405B is paid (404 on $0 free tier) and
        # Hermes-4 is tuned for chat, not rapid tool-calling — poor Graphiti fit.
        # Also redundant with OpenRouter (Nous is OpenRouter-powered).
        # Groq — permanent free tier (Llama 3.3 70B etc.), no card.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/llama-3.3-70b-versatile";
            api_base = "https://api.groq.com/openai/v1";
            api_key = "os.environ/GROQ_KEY";
            rpm = 30;
            order = 12;
          };
        }
        # Hugging Face — free tier (router.huggingface.co/v1, $0.10/mo credits, no card).
        # 200+ models; server-side provider selection. GitHub Models was retired 2026-07-30.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/gpt-oss-20b:fastest";
            api_base = "https://router.huggingface.co/v1";
            api_key = "os.environ/HF_TOKEN";
            rpm = 20;
            order = 13;
          };
        }
        # Mistral — free experimentation tier (La Plateforme), no card, permissive terms.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/mistral-small-latest";
            api_base = "https://api.mistral.ai/v1";
            api_key = "os.environ/MISTRAL_KEY";
            rpm = 20;
            order = 14;
          };
        }
        # DeepSeek fallback (if key present) — separate provider, real fallback value.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "deepseek/deepseek-v4-flash-0731";
            api_key = "os.environ/DEEPSEEK_KEY";
            rpm = 20;
            order = 20;
          };
        }
      ];
      router_settings = {
        routing_strategy = "simple-shuffle";
        num_retries = 3;
        timeout = 60;
        fallbacks = [
          { "graphiti-free" = [ "openrouter/openrouter/free" "deepseek/deepseek-v4-flash-0731" ]; }
        ];
      };
      litellm_settings = {
        # Native Postgres spend logging (tokens + $) via DATABASE_URL below.
        # Langfuse (per your request) — UNCOMMENT + set env when a Langfuse
        # instance is deployed; native Postgres logging works without it.
        # success_callback = [ "langfuse" ];
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
    elif [ ! -f "$MK_FILE" ]; then
      # Generate 24 bytes of hex from /dev/urandom (no openssl dependency —
      # the activation env lacks openssl/bash on PATH, so avoid external bins).
      head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n' > "$MK_FILE"
    fi
    chmod 0644 "$MK_FILE"

    # ── EnvironmentFile: pull keys from the SAME sops paths mitmproxy uses.
    #    Every var is ALWAYS emitted (empty fallback) so LiteLLM config-load
    #    never crashes on an absent os.environ/X — dead keys just mean dead
    #    deployments at request time, not a startup failure. ──
    SECRETS=/run/secrets/hermes-mitmproxy/llm-providers
    {
      echo "LITELLM_MASTER_KEY=$(cat "$MK_FILE")"
      echo "DATABASE_URL=postgresql://litellm:litellm@127.0.0.1:5432/litellm"
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
      echo "MISTRAL_KEY=$([ -f "$SECRETS/mistral/api-key" ] && cat "$SECRETS/mistral/api-key" || echo "")";
    } > /var/lib/litellm/env
    chmod 0644 /var/lib/litellm/env
  '';
}
