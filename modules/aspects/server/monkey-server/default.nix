{ den, inputs, lib, pkgs, ... }:

# MonkeyOCRv2-B parsing server on serenity GPU (HF transformers, fp16).
#
# Validated 2026-09-07: GTX 1660 (sm_75) needs fp16 (no bf16 SDPA kernel),
# /run/opengl-driver/lib on LD_LIBRARY_PATH, TRITON_LIBCUDA_PATH, and gcc in
# PATH for triton's one-time cuda_utils build. Patches to the modeling files
# (SDPA backend fallback, bfloat16→float16) are applied at package build time.
{
  den.aspects.server.monkey-server = {
    nixos = { config, lib, pkgs, ... }:

    let
      monkeyVenv = "/var/lib/monkey-server/venv";
      modelDir = "/var/lib/monkey-server/model";
      port = 8086;

      # Server code from the repo
      monkeyServerSrc = ../../../../pkgs/monkeyocr-server;

      # Model weights: fetched from HuggingFace at build time.
      # MonkeyOCRv2-B-Parsing, rev pinned; includes modeling .py files which
      # get patched below (fp16 + SDPA fallback).
      monkeyModel = pkgs.stdenv.mkDerivation {
        name = "MonkeyOCRv2-B-Parsing";
        src = pkgs.fetchurl {
          url = "https://huggingface.co/echo840/MonkeyOCRv2-B-Parsing/resolve/main/model.safetensors";
          sha256 = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="; # PLACEHOLDER
        };
        # Remaining files fetched by the start script on first run (small).
        dontBuild = true;
        dontUnpack = true;
        installPhase = ''
          mkdir -p $out
          cp $src $out/model.safetensors
        '';
      };

      # Start script: build venv if missing, fetch small model files +
      # apply the sm_75 patches (idempotent, marker file), exec server.
      # NOTE: patch python is a separate writeShellScriptApp because heredocs
      # inside a Nix '' string lose their unindented terminator (PYEOF gets
      # two leading spaces → bash never sees the delimiter).
      monkeyPatchScript = pkgs.writeShellScript "monkey-model-patch" ''
        set -eu
        F="$1"
        ${pkgs.python311}/bin/python3 - "$F" <<'PYEOF'
        import sys
        f = sys.argv[1]
        s = open(f).read()
        if "except (RuntimeError, ValueError):" not in s:
            s = s.replace(
                "        with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):\n"
                "            attn_output = F.scaled_dot_product_attention(q, k, v, attention_mask, dropout_p=0.0)",
                "        try:\n"
                "            with sdpa_kernel(SDPBackend.EFFICIENT_ATTENTION):\n"
                "                attn_output = F.scaled_dot_product_attention(q, k, v, attention_mask, dropout_p=0.0)\n"
                "        except (RuntimeError, ValueError):\n"
                "            with sdpa_kernel(SDPBackend.MATH):\n"
                "                attn_output = F.scaled_dot_product_attention(q, k, v, attention_mask, dropout_p=0.0)",
            )
            open(f, "w").write(s)
        PYEOF
        ${pkgs.python311}/bin/python3 - "$F" <<'PYEOF'
        import sys
        f = sys.argv[1]
        s = open(f).read()
        s = s.replace("hidden_states = hidden_states.bfloat16()",
                      "hidden_states = hidden_states.to(torch.float16)")
        open(f, "w").write(s)
        PYEOF
      '';

      monkeyStartScript = pkgs.writeShellScript "monkey-server-start" ''
        set -eu
        MODEL="''${MOCR_MODEL_DIR:-${modelDir}}"

        # venv: torch cu121 + transformers; skip if marker newer than script
        if [ ! -x "${monkeyVenv}/bin/python" ] || [ "${monkeyVenv}/.installed" -ot "${monkeyServerSrc}/monkey_server.py" ]; then
          echo "Creating MonkeyOCR venv..."
          ${pkgs.python311}/bin/python3.11 -m venv ${monkeyVenv}
          ${monkeyVenv}/bin/pip install --quiet --upgrade pip
          ${monkeyVenv}/bin/pip install --quiet torch --index-url https://download.pytorch.org/whl/cu121
          ${monkeyVenv}/bin/pip install --quiet "transformers<5" accelerate fastapi uvicorn pillow numpy einops timm pypdfium2
          touch ${monkeyVenv}/.installed
        fi

        # Model dir: safetensors from store, rest fetched once from HF
        if [ ! -f "$MODEL/.ready" ]; then
          echo "Fetching MonkeyOCRv2-B-Parsing support files..."
          mkdir -p "$MODEL"
          for f in added_tokens.json args.json chat_template.jinja config.json \
                   configuration_monkeyocrv2.py generation_config.json \
                   merges.txt modeling_monkeyocrv2.py modeling_monkeyocrv2_vision.py \
                   preprocessor_config.json processor_config.json \
                   special_tokens_map.json tokenizer.json tokenizer_config.json vocab.json; do
            [ -f "$MODEL/$f" ] || ${pkgs.curl}/bin/curl -fsSL \
              "https://huggingface.co/echo840/MonkeyOCRv2-B-Parsing/resolve/main/$f" \
              -o "$MODEL/$f" || echo "warn: missing $f"
          done

          # --- sm_75 (GTX 1660) patches (separate script: heredoc safe) ---
          ${monkeyPatchScript} "$MODEL/modeling_monkeyocrv2_vision.py"
          touch "$MODEL/.ready"
        fi

        export PATH="/run/wrappers/bin:${pkgs.stdenv.cc}/bin:$PATH"
        export LD_LIBRARY_PATH="/run/opengl-driver/lib:${pkgs.stdenv.cc.cc.lib}/lib"
        export TRITON_LIBCUDA_PATH="/run/opengl-driver/lib/libcuda.so.1"
        export MOCR_MODEL_DIR="$MODEL"
        exec ${monkeyVenv}/bin/python ${monkeyServerSrc}/monkey_server.py --port ${toString port}
      '';
    in {
      systemd.tmpfiles.rules = [
        "d /var/lib/monkey-server 0755 monkey monkey -"
      ];

      users.users.monkey = {
        isSystemUser = true;
        group = "monkey";
        extraGroups = [ "video" ];
      };
      users.groups.monkey = {};

      systemd.services.nc-monkey-server = {
        description = "MonkeyOCRv2-B parsing server (GPU, nc-ocr-flow tier-2)";
        after = [ "network.target" ];
        wantedBy = [ "multi-user.target" ];

        environment = {
          CUDA_VISIBLE_DEVICES = "0";
          HF_HOME = "/var/lib/monkey-server/hf-cache";
          HOME = "/var/lib/monkey-server";
        };

        serviceConfig = {
          Type = "simple";
          Restart = "on-failure";
          RestartSec = "10s";
          StateDirectory = "monkey-server";
          StateDirectoryMode = "0755";
          User = "monkey";
          Group = "monkey";
          TimeoutStartSec = "15min";
          ExecStart = monkeyStartScript;
        };
      };

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ port ];
    };
  };
}
