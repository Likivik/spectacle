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
      # Blessed pkgsCuda scope — cache-friendly (see core/nix.nix substituters)
      llama-cpp-cuda = pkgs.pkgsCuda.llama-cpp;
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
      # Models come from the store: immutable inputs, GC-tracked, and readable by
      # the DynamicUser units. They used to be downloaded by an activation script
      # into the unit's StateDirectory; a later rename (llama-cpp ->
      # llama-cpp-embedder) orphaned them behind /var/lib/private (mode 700), so
      # llama-server could no longer open them and both units crash-looped.
      bgeM3 = pkgs.fetchurl {
        url = "https://huggingface.co/groonga/bge-m3-Q4_K_M-GGUF/resolve/main/bge-m3-q4_k_m.gguf";
        hash = "sha256-RGIP2wqNI7XtV/5euPOELrljK0wTY91gIkasJL1tG+Q=";
      };
      bgeReranker = pkgs.fetchurl {
        url = "https://huggingface.co/TheOSExplorer/bge-reranker-v2-m3-Q2_K-GGUF/resolve/main/bge-reranker-v2-m3-q2_k.gguf";
        hash = "sha256-YFnPAktxpOR4SNosFGhGyZFvHbfWokzKhQ4rxHLElbg=";
      };
    in lib.mkMerge [
      # ── Serenity: 3 llama.cpp systemd units + ollama-compat proxy ───────
      (lib.mkIf (config.networking.hostName == "serenity") {
        # 4 slots = MCP's 3 indexer workers (VECTOR_SYNC_PROCESSOR_WORKERS
        # default on poweredge) + 1 headroom. Without --parallel llama.cpp
        # defaults to a single slot, the 3 workers contend, requests queue,
        # ollama_proxy.py returns 502s, and indexing drops to ~8.5 chunks/min.
        # ctx-size 8192 / 4 = 2048 tokens per slot, enough for the ~2048-char
        # chunks the MCP emits (200-char overlap included).
        #
        # --batch-size 8192 / -ub 8192 raises llama.cpp's logical and PHYSICAL
        # batch from the default 512 to 8192 (matches --ctx-size 8192 and bge-m3's
        # 8192-token max input). The upstream 502 body literally says
        # "increase the physical batch size" (current: 512); -ub is what actually
        # lifts the limit, --batch-size is set to the same value so they cannot
        # disagree. Without this, any single Cyrillic chunk >512 tokens makes
        # llama.cpp return 500 → ollama_proxy.py re-emits 502, and the MCP burns
        # its 5-retry backoff (2+4+8+16s) on every dense chunk. Dominant failure.
        systemd.services.llama-embedder = {
          description = "llama.cpp bge-m3 embedder";
          after = [ "network.target" ]; wantedBy = [ "multi-user.target" ];
          path = [ pkgs.curl ];
          serviceConfig = gpuServiceCfg // {
            Type = "exec";
            ExecStart = ''
              ${llama-server} --host 0.0.0.0 --port 8081 \
                -m ${bgeM3} \
                --embedding --ctx-size 8192 -ngl 99 --threads 4 \
                --parallel 4 --batch-size 8192 -ub 8192
            '';
            Restart = "on-failure"; RestartSec = 5;
            DynamicUser = true; StateDirectory = "llama-cpp-embedder";
          };
        };
        # 2 slots so concurrent searches at query time do not serialise.
        # ctx-size 8192 / 2 = 4096 tokens per slot; reranker inputs are short
        # (query + candidate passage pair), well inside that budget.
        #
        # --batch-size 8192 / -ub 8192 matches the embedder. Reranker submits
        # whole documents/chunks and is exposed to the same 512-token
        # physical-batch ceiling. -ub is the actual fix; --batch-size is set
        # to match so they cannot disagree.
        systemd.services.llama-reranker = {
          description = "llama.cpp bge-reranker-v2-m3";
          after = [ "network.target" ]; wantedBy = [ "multi-user.target" ];
          path = [ pkgs.curl ];
          serviceConfig = gpuServiceCfg // {
            Type = "exec";
            ExecStart = ''
              ${llama-server} --host 0.0.0.0 --port 8082 \
                -m ${bgeReranker} \
                --embedding --pooling rank --reranking -ngl 99 \
                --ctx-size 8192 --parallel 2 --batch-size 8192 -ub 8192
            '';
            Restart = "on-failure"; RestartSec = 5;
            DynamicUser = true; StateDirectory = "llama-cpp-reranker";
          };
        };
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
      })
    ];
  };
}