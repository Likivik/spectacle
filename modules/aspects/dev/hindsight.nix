{ den, lib, ... }:
{
  den.aspects.hindsight = {
    nixos = { ... }: {
      virtualisation.oci-containers = {
        backend = "podman";
        containers = {
          ollama = {
            image = "ollama/ollama";
            ports = [ "11434:11434" ];
            volumes = [ "ollama-models:/root/.ollama" ];
            extraOptions = [
              "--pull=always"
              "--device" "/dev/kfd"
              "--device" "/dev/dri"
              "--group-add" "video"
            ];
          };

          hindsight = {
            image = "ghcr.io/vectorize-io/hindsight";
            ports = [ "4242:8888" "4243:9999" ];
            environment = {
              HINDSIGHT_API_LLM_PROVIDER = "ollama";
              HINDSIGHT_API_LLM_BASE_URL = "http://ollama:11434";
              HINDSIGHT_API_LLM_MODEL = "qwen2.5:7b";
              HINDSIGHT_API_WORKER_ID = "hindsight-traversal";
            };
            volumes = [ "hindsight-data:/home/hindsight/.pg0" ];
            dependsOn = [ "ollama" ];
            extraOptions = [ "--pull=always" ];
          };
        };
      };
    };
  };
}
