{ den, lib, ... }:
{
  den.aspects.hindsight = {
    nixos = { config, pkgs, ... }: {
      environment.sessionVariables = {
        HINDSIGHT_DYNAMIC_BANK_ID = "true";
      };

      virtualisation.oci-containers = {
        backend = "podman";
        containers = {
          ollama = {
            image = "ollama/ollama";
            autoStart = false;
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
            autoStart = false;
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

      # Auto-start/stop containers based on AC power state
      systemd.services.hindsight-power-watcher = {
        description = "Start/stop hindsight services based on AC power";
        wantedBy = [ "multi-user.target" ];
        path = [ config.virtualisation.podman.package ];
        script = ''
          for f in /sys/class/power_supply/*/type; do
            [ "$(cat "$f")" = "Mains" ] || continue
            online="$(cat "$(dirname "$f")"/online)"
            if [ "$online" = "1" ]; then
              ${pkgs.systemd}/bin/systemctl start podman-ollama podman-hindsight
              exit 0
            fi
          done
          ${pkgs.systemd}/bin/systemctl stop podman-ollama podman-hindsight
        '';
        serviceConfig.Type = "oneshot";
      };

      services.udev.extraRules = ''
        SUBSYSTEM=="power_supply", ATTR{online}=="*", RUN+="${pkgs.systemd}/bin/systemctl start hindsight-power-watcher"
      '';
    };
  };
}
