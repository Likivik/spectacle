{ den, inputs, lib, pkgs, ... }:

# ─── NC-RAG stack (Serenity only) ─────────────────────────────────────────
# Den registers this folder as den.aspects.server.nc-rag. Internally gated by
# hostname via lib.mkIf (deferred config eval — do NOT compute hostName in a
# `let`; that forces `config` during module collection → infinite recursion).
#   serenity  → bge-m3 embedder + bge-reranker + gemma-3 vision (1660, CUDA)
#   poweredge → Qdrant + pi0n00r nextcloud-mcp quadlets (in poweredge.nix)
#
# VRAM (1660 = 6GB): embedder 1.2 + reranker 0.4 + gemma 2.9 ≈ 4.5 GB hot.
# allowUnfree = true (core/nix.nix) → CUDA override permitted.
# Secrets (poweredge/secrets.yaml): nextcloud/mcp-app-password
# Gemma GGUF URL verified 2026-08-05.
#
# Lesson from poweredge deploy (2026-08): podman/netavark bridge+DNAT
# is broken on this NixOS. Poweredge quadlets use --network=host
# (see poweredge.nix + NOTES/poweredge-nc-rag-port-forwarding.md).
# Serenity uses native systemd → no podman involvement.
#
# Semantic-search bridge: nc-mcp's Ollama client hardcodes /api/{tags,embed}
# (Ollama-native API). llama.cpp reverted /api/tags in PR #22165 (Apr 2026).
# Solution: small FastAPI proxy from deposist/llama.cpp-Control-Deck —
# translates /api/{tags,embed,chat} → llama.cpp's OpenAI endpoints. Bypass
# Ollama entirely (Ollama itself has unpatched CVE-2026-7482 CVSS 9.1).

{
  den.aspects.server.nc-rag = {
    includes = [ den.aspects.server.sops ];
    nixos = { config, lib, pkgs, ... }:
    let
      modelsDir = "/var/lib/llama-cpp";
      llama-cpp-cuda = pkgs.llama-cpp.override { cudaSupport = true; };
      llama-server = "${lib.getExe' llama-cpp-cuda "llama-server"}";
      gpuServiceCfg = {
        DeviceAllow = [ "char-nvidiactl" "char-nvidia-frontend" "char-nvidia-uvm" "char-dri" ];
        SupplementaryGroups = [ "video" "render" ];
        PrivateDevices = false;
      };
      # Control Deck ollama_proxy.py: translates Ollama /api/{tags,embed,chat}
      # to llama.cpp's OpenAI endpoints. Pinned to upstream commit
      # 87f531e5f7b868cbcd87a65ab54333f51d21dbdc (2026-07-25).
      # Source: https://github.com/deposist/llama.cpp-Control-Deck
      ollamaProxy = pkgs.stdenvNoCC.mkDerivation {
        name = "ollama-proxy-87f531e";
        src = pkgs.fetchurl {
          url = "https://raw.githubusercontent.com/deposist/llama.cpp-Control-Deck/87f531e5f7b868cbcd87a65ab54333f51d21dbdc/ollama_proxy.py";
          sha256 = "1nrrypq460csx2g0ph66p0xh255mjvvcicrylpffhkkdhwzsdd8i";
        };
        dontUnpack = true;
        installPhase = "install -Dm755 $src $out/bin/ollama_proxy.py";
      };
      pythonWithProxyDeps = pkgs.python3.withPackages (ps: with ps; [ fastapi uvicorn httpx ]);
    in lib.mkMerge [
      # ── Serenity: 3 llama.cpp systemd units + ollama-compat proxy ───────
      (lib.mkIf (config.networking.hostName == "serenity") {
        systemd.services.llama-embedder = {
          description = "llama.cpp bge-m3 embedder";
          after = [ "network.target" ]; wantedBy = [ "multi-user.target" ];
          path = [ pkgs.curl ];
          serviceConfig = gpuServiceCfg // {
            Type = "exec";
            ExecStart = ''
              ${llama-server} --host 0.0.0.0 --port 8081 \
                -m ${modelsDir}/bge-m3-q4_k_m.gguf \
                --embedding --ctx-size 8192 -ngl 99 --threads 4
            '';
            Restart = "on-failure"; RestartSec = 5;
            DynamicUser = true; StateDirectory = "llama-cpp-embedder";
          };
        };
        systemd.services.llama-reranker = {
          description = "llama.cpp bge-reranker-v2-m3";
          after = [ "network.target" ]; wantedBy = [ "multi-user.target" ];
          path = [ pkgs.curl ];
          serviceConfig = gpuServiceCfg // {
            Type = "exec";
            ExecStart = ''
              ${llama-server} --host 0.0.0.0 --port 8082 \
                -m ${modelsDir}/bge-reranker-v2-m3-q2_k.gguf \
                --embedding --pooling rank --reranking -ngl 99 --ctx-size 8192
            '';
            Restart = "on-failure"; RestartSec = 5;
            DynamicUser = true; StateDirectory = "llama-cpp-reranker";
          };
        };
        # gemma-vision DISABLED — replaced by olmocr-vision (port 8083).
        # Keep this stanza as a reference; new VLM lives in modules/aspects/server/olmocr-vision.
        #
        # systemd.services.llama-gemma-vision = {
        #   description = "llama.cpp gemma-3-4b-it vision (on-demand OCR)";
        #   after = [ "network.target" ];
        #   path = [ pkgs.curl ];
        #   serviceConfig = gpuServiceCfg // {
        #     Type = "exec";
        #     ExecStart = ''
        #       ${llama-server} --host 127.0.0.1 --port 8083 \
        #         -m ${modelsDir}/gemma-3-4b-it-q2_k.gguf \
        #         --mmproj ${modelsDir}/mmproj-gemma-3-4b-it-f16.gguf \
        #         -ngl 99 --ctx-size 4096
        #     '';
        #     Restart = "no";
        #     DynamicUser = true; StateDirectory = "llama-cpp-gemma";
        #   };
        # };
        # Ollama-compat proxy: enables nc-mcp semantic search by translating
        # /api/{tags,embed,chat} → llama.cpp's OpenAI endpoints.
        # Bound 127.0.0.1:11434 only (Tailscale + poweredge reach it via serenity DNS).
        # Starts after llama-embedder so 127.0.0.1:8081 is ready.
        systemd.services.llama-ollama-proxy = {
          description = "Ollama-compat proxy for llama.cpp (nc-mcp semantic search)";
          after = [ "llama-embedder.service" "network.target" ];
          wantedBy = [ "multi-user.target" ];
          path = [ pkgs.bash ];
          serviceConfig = {
            Type = "exec";
            ExecStart = ''
                      ${pythonWithProxyDeps}/bin/python ${ollamaProxy}/bin/ollama_proxy.py \
                        --host 0.0.0.0 --port 11434 \
                        --target-base-url http://127.0.0.1:8081/v1 \
                        --model bge-m3
                    '';
            Restart = "on-failure"; RestartSec = 5;
            DynamicUser = true; StateDirectory = "llama-ollama-proxy";
          };
        };
        # Open 11434 on tailscale0 only (loopback already reachable from poweredge
        # via Tailscale's magic DNS routing). 127.0.0.1 is implicit via Type=exec.
        networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 11434 ];
        system.activationScripts."nc-rag-models".text = ''
          mkdir -p "${modelsDir}"; chmod 755 "${modelsDir}"
          EMBED="${modelsDir}/bge-m3-q4_k_m.gguf"
          if [ ! -f "$EMBED" ]; then
            ${pkgs.curl}/bin/curl -L --fail -o "$EMBED.tmp" \
              "https://huggingface.co/groonga/bge-m3-Q4_K_M-GGUF/resolve/main/bge-m3-q4_k_m.gguf"
            mv "$EMBED.tmp" "$EMBED"
          fi; chmod 644 "$EMBED"
          RERANK="${modelsDir}/bge-reranker-v2-m3-q2_k.gguf"
          if [ ! -f "$RERANK" ]; then
            ${pkgs.curl}/bin/curl -L --fail -o "$RERANK.tmp" \
              "https://huggingface.co/TheOSExplorer/bge-reranker-v2-m3-Q2_K-GGUF/resolve/main/bge-reranker-v2-m3-q2_k.gguf"
            mv "$RERANK.tmp" "$RERANK"
          fi; chmod 644 "$RERANK"
          GEMMA="${modelsDir}/gemma-3-4b-it-q2_k.gguf"
          if [ ! -f "$GEMMA" ]; then
            # bartowski/google_gemma-3-4b-it-GGUF repo filenames DO use the
            # `google_` prefix (same as mmproj). Verified via
            # https://huggingface.co/api/models/bartowski/google_gemma-3-4b-it-GGUF/tree/main
            ${pkgs.curl}/bin/curl -L --fail -o "$GEMMA.tmp" \
              "https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/google_gemma-3-4b-it-Q2_K.gguf"
            mv "$GEMMA.tmp" "$GEMMA"
          fi; chmod 644 "$GEMMA"
          MMPROJ="${modelsDir}/mmproj-gemma-3-4b-it-f16.gguf"
          if [ ! -f "$MMPROJ" ]; then
            ${pkgs.curl}/bin/curl -L --fail -o "$MMPROJ.tmp" \
              "https://huggingface.co/bartowski/google_gemma-3-4b-it-GGUF/resolve/main/mmproj-google_gemma-3-4b-it-f16.gguf"
            mv "$MMPROJ.tmp" "$MMPROJ"
          fi; chmod 644 "$MMPROJ"
        '';
      })
    ];
  };
}