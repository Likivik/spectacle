{ config, pkgs, lib }: let
  model_path = "/var/lib/hermes/llama/models/bge-m3-q4_k_m.gguf";
in {
  services.llama-cpp = {
    enable = true;
    settings = {
      host = "127.0.0.1";
      port = 8081;
      model = model_path;
      embedding = true;
      ctx-size = 8192;
      threads = 4;
    };
    openFirewall = false;
  };

  system.activationScripts."hermes-llama-model" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    mkdir -p /var/lib/hermes/llama/models

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
