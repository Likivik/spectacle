{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.olmocr-vision = {
    nixos = { config, lib, pkgs, ... }: {
      # Replace gemma-vision on serenity with olmOCR-v2 (Qwen2.5-VL-7B AWQ).
      # Exposes OpenAI-compatible /v1/chat/completions on 127.0.0.1:8083
      # for per-page VLM fallback from nc-ocr-flow on poweredge.
      #
      # Model: bartowski/allenai_olmOCR-2-7B-1025-GGUF (Q4_K_M, 4.68GB)
      #   URL: https://huggingface.co/bartowski/allenai_olmOCR-2-7B-1025-GGUF
      #   License: Apache-2.0 (Allen AI)
      #   Benchmark: 82.3 on olmOCR-bench (vs tesseract 70-80)
      # mmproj (vision encoder): mmproj-allenai_olmOCR-2-7B-1025-f16.gguf (1.35GB)
      #
      # VRAM budget on serenity 1660 (6GB):
      #   bge-m3 (1.2) + bge-reranker (0.4) + ollama-compat-proxy ≈ 1.6GB resident
      #   olmOCR-v2 (5.0GB exclusive) — on-demand via Restart=no
      #   When olmOCR-v2 loads, llama.cpp unloads cohabit models on demand.
      #
      # Invoke from nc-ocr-flow:
      #   POST http://serenity:8083/v1/chat/completions
      #   Body: OpenAI multimodal format (image_url data: URL, base64 PNG)
      #   Response: text completion with extracted text
      #
      # Build requirements:
      #   - llama-cpp-cuda with libmtmd (multimodal) support
      #   - nixpkgs llama-cpp-cuda may need overrides for libmtmd — see
      #     https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md

      environment.etc."llm/olmocr-v2-Q4_K_M.gguf".source =
        pkgs.fetchurl {
          url = "https://huggingface.co/bartowski/allenai_olmOCR-2-7B-1025-GGUF/resolve/main/allenai_olmOCR-2-7B-1025-Q4_K_M.gguf";
          sha256 = "sha256-NHk1/EwWgIz5fHrcVj2pLGetkO6wUEpGX/n6mNJ5Tz4=";
        };

      environment.etc."llm/olmocr-v2-mmproj.gguf".source =
        pkgs.fetchurl {
          # mmproj (vision encoder) — verified hash 2026-08-13
          url = "https://huggingface.co/bartowski/allenai_olmOCR-2-7B-1025-GGUF/resolve/main/mmproj-allenai_olmOCR-2-7B-1025-f16.gguf";
          sha256 = "sha256-eNFpCk2YBR9ScQTDN5a3n6oF8VjRRkXhnbkfrJm9GwQ=";
        };

      # Model storage dir (persistent across rebuilds)
      systemd.tmpfiles.rules = [
        "d /var/lib/llm 0755 likivik likivik -"
      ];

      # olmOCR-v2 llama-server: replaces gemma-vision.
      # On-demand via Restart=no — unloads after idle (matches gemma-vision pattern).
      # Port 8083 stays the same so nc-ocr-flow doesn't need config changes.
      systemd.services.llama-olmocr = {
        description = "llama.cpp olmOCR-v2 VLM (replaces gemma-vision, nc-ocr-flow per-page fallback)";
        after = [ "network.target" ];
        wantedBy = [ "multi-user.target" ];

        path = [ pkgs.curl ];

        serviceConfig = {
          Type = "exec";
          # Use llama-server with --hf flag for multimodal model auto-download.
          # Equivalent to: -m model.gguf --mmproj mmproj.gguf
          # See llama.cpp multimodal.md.
          ExecStart = let
            llamaCppCuda = pkgs.llama-cpp.override { cudaSupport = true; };
          in ''
            ${lib.getExe' llamaCppCuda "llama-server"} \
              --host 127.0.0.1 --port 8083 \
              -m /etc/llm/olmocr-v2-Q4_K_M.gguf \
              --mmproj /etc/llm/olmocr-v2-mmproj.gguf \
              -ngl 99 --ctx-size 8192 --threads 4 --batch-size 512 \
              --temp 0.0 --top-k 1 \
              --alias olmocr-v2
          '';
          Restart = "no";  # on-demand — load on first request, stay resident
          RestartSec = 5;
          DynamicUser = true;
          StateDirectory = "llama-cpp-olmocr";
          # Give llama-server enough time to load 5GB model
          TimeoutStartSec = "10min";
          # No timeout — VLM inference can take 30-90s per page on 1660
          TimeoutStopSec = "2min";
          # GPU access
          DeviceAllow = [ "char-nvidia*" "char-dri*" ];
          PrivateDevices = false;
        };
      };
    };
  };
}
