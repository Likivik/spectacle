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
# Gemma GGUF URL TODO-verify before deploy.
#
# Lesson from poweredge deploy (2026-08): podman/netavark bridge+DNT
# is broken on this NixOS. Poweredge quadlets use --network=host
# (see poweredge.nix + NOTES/poweredge-nc-rag-port-forwarding.md).
# Serenity uses native systemd → no podman involvement → no lesson to
# apply here; this just listens on host's 0.0.0.0:8081/8082 directly.

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
    in lib.mkMerge [
      # ── Serenity: 3 llama.cpp systemd units (CUDA) ──────────────────────
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
        # On-demand OCR — Restart=no so it unloads after a batch.
        systemd.services.llama-gemma-vision = {
          description = "llama.cpp gemma-3-4b-it vision (on-demand OCR)";
          after = [ "network.target" ];
          path = [ pkgs.curl ];
          serviceConfig = gpuServiceCfg // {
            Type = "exec";
            ExecStart = ''
              ${llama-server} --host 127.0.0.1 --port 8083 \
                -m ${modelsDir}/gemma-3-4b-it-q2_k.gguf \
                --mmproj ${modelsDir}/mmproj-gemma-3-4b-it-f16.gguf \
                -ngl 99 --ctx-size 4096
            '';
            Restart = "no";
            DynamicUser = true; StateDirectory = "llama-cpp-gemma";
          };
        };
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