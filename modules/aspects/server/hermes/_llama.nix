{ config, pkgs, lib }: let
  models_dir = "/var/lib/llama-cpp/models";
  model_path = "${models_dir}/bge-m3-q4_k_m.gguf";
in {
  services.llama-cpp = {
    enable = true;
    settings = {
      host = "0.0.0.0";
      port = 8081;
      model = model_path;
      embedding = true;
      ctx-size = 8192;
      # BGE-M3 natively supports up to 8192 tokens; llama.cpp defaults
      # ubatch-size to 512 which capped embeddings at 512 tokens (500 error
      # on longer episodes). Bump both to the model's native max.
      batch-size = 8192;
      ubatch-size = 8192;
      threads = 4;
    };
    openFirewall = false;
  };

  # Allow PocketRisu container (podman0 bridge) to reach the embedder
  networking.firewall.interfaces.podman0.allowedTCPPorts = [ 8081 ];

  system.activationScripts."hermes-llama-model" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    mkdir -p "${models_dir}"
    chmod 755 "${models_dir}"

    if [ ! -f "${model_path}" ]; then
      echo "Downloading BGE-M3 GGUF model..."
      ${pkgs.curl}/bin/curl -L --fail \
        -o "${model_path}.tmp" \
        "https://huggingface.co/groonga/bge-m3-Q4_K_M-GGUF/resolve/main/bge-m3-q4_k_m.gguf"
      mv "${model_path}.tmp" "${model_path}"
    fi
    chmod 644 "${model_path}"
  '';
}
