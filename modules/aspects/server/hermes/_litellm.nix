{ config, pkgs, lib }: {
  # ── LiteLLM AI Gateway (upstream services.litellm module) ────────────
  # OpenAI-compatible proxy in front of Graphiti. Pools openrouter +
  # opencode×4 + nousportal (+ DeepSeek fallback) as deployments under one
  # `graphiti-free` model_name, with order-based + fallback-chain rotation
  # on 429/503, and native Postgres token/spend logging.
  #
  # Graphiti points api_url -> http://127.0.0.1:4000/v1 (see _graphiti.nix).
  # Keys are read from the SAME sops secrets the mitmproxy already uses
  # (/run/secrets/hermes-mitmproxy/...), surfaced via an EnvironmentFile
  # generated at activation (services.litellm.environmentFile).
  #
  # Module runs as a hardened DynamicUser by default; we pin a static
  # `litellm` user so it can read the secret env file we generate.

  users.users.litellm = {
    isSystemUser = true;
    group = "litellm";
    home = "/var/lib/litellm";
    createHome = true;
    shell = pkgs.bash;
  };
  users.groups.litellm = { };

  # ── Postgres (shared server, dedicated `litellm` database) ────────────
  services.postgresql = {
    enable = true;
    package = pkgs.postgresql_16;
    enableTCPIP = true;
    settings.listen_addresses = "127.0.0.1";
    initialScript = pkgs.writeText "litellm-pg-init" ''
      CREATE ROLE litellm WITH LOGIN PASSWORD 'litellm';
      CREATE DATABASE litellm OWNER litellm;
    '';
  };

  services.litellm = {
    enable = true;
    host = "127.0.0.1";
    port = 4000;
    # Pin a static user (override module default DynamicUser) so the
    # generated secret env file is readable by the service.
    serviceConfig = {
      DynamicUser = false;
      User = "litellm";
      Group = "litellm";
      ReadWritePaths = [ "/var/lib/litellm" ];
    };
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
        # NousPortal — OpenAI-compatible inference API.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/Hermes-4-405B";
            api_base = "https://inference-api.nousresearch.com/v1";
            api_key = "os.environ/NOUSPORTAL_KEY";
            rpm = 20;
            order = 11;
          };
        }
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
        # NVIDIA NIM — permanent free API key, no card, 70-100+ models, separate vendor.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/meta/llama-3.3-70b-instruct";
            api_base = "https://integrate.api.nvidia.com/v1";
            api_key = "os.environ/NVIDIA_KEY";
            rpm = 20;
            order = 14;
          };
        }
        # Cerebras — free tier (Llama 3.3 70B etc.), no card, high throughput.
        {
          model_name = "graphiti-free";
          litellm_params = {
            model = "openai/llama-3.3-70b";
            api_base = "https://api.cerebras.ai/v1";
            api_key = "os.environ/CEREBRAS_KEY";
            rpm = 30;
            order = 15;
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
    chown litellm:litellm /var/lib/litellm

    # ── Master key: reuse sops if present, else generate + persist locally ──
    MK_FILE=/var/lib/litellm/master-key.txt
    SOPS_MK=/run/secrets/hermes-litellm/master-key
    if [ -f "$SOPS_MK" ]; then
      install -m 0600 "$SOPS_MK" "$MK_FILE"
    elif [ ! -f "$MK_FILE" ]; then
      "${pkgs.openssl}/bin/openssl rand -hex 24" > "$MK_FILE"
    fi
    chmod 0600 "$MK_FILE"
    chown litellm:litellm "$MK_FILE"

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
      echo "NOUSPORTAL_KEY=$([ -f "$SECRETS/nousportal/api-key" ] && cat "$SECRETS/nousportal/api-key" || echo "")"
      echo "DEEPSEEK_KEY=$([ -f "$SECRETS/deepseek/api-key" ] && cat "$SECRETS/deepseek/api-key" || echo "")"
      echo "GROQ_KEY=$([ -f "$SECRETS/groq/api-key" ] && cat "$SECRETS/groq/api-key" || echo "")"
      echo "HF_TOKEN=$([ -f "$SECRETS/huggingface/api-key" ] && cat "$SECRETS/huggingface/api-key" || echo "")"
      echo "NVIDIA_KEY=$([ -f "$SECRETS/nvidia/api-key" ] && cat "$SECRETS/nvidia/api-key" || echo "")"
      echo "CEREBRAS_KEY=$([ -f "$SECRETS/cerebras/api-key" ] && cat "$SECRETS/cerebras/api-key" || echo "")";
    } > /var/lib/litellm/env
    chmod 0600 /var/lib/litellm/env
    chown litellm:litellm /var/lib/litellm/env
  '';
}
