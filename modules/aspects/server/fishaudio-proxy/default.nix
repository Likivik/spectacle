{ den, lib, pkgs, ... }:

let
  proxySrc = builtins.readFile ../../../../pkgs/fishaudio-proxy/proxy.js;
in
{
  den.aspects.server.fishaudio-proxy = {
    nixos = { config, lib, pkgs, ... }: {
      sops.secrets = {
        "hermes-mitmproxy/llm-providers/fishaudio/api-key" = {
          sopsFile = ../../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0600";
          path = "/run/secrets/fishaudio-api-key";
        };
      };

      systemd.services.fishaudio-proxy = {
        description = "Fish Audio API proxy — translates OpenAI TTS shape to Fish native /v1/tts";
        wantedBy = [ "multi-user.target" ];
        after = [ "network.target" ];

        serviceConfig = {
          Type = "simple";
          User = "hermes";
          Group = "hermes";
          Restart = "always";
          RestartSec = "5s";
          Environment = [ "FISH_API_KEY_FILE=/run/secrets/fishaudio-api-key" ];
          ExecStart = lib.getExe (pkgs.writeTextFile {
            name = "fishaudio-proxy";
            executable = true;
            destination = "/bin/fishaudio-proxy";
            text = ''
              #!${lib.getExe pkgs.nodejs}
              ${proxySrc}
            '';
          });
        };
      };

      networking.firewall.interfaces.tailscale0.allowedTCPPorts = [ 8099 ];
      networking.firewall.interfaces.lo.allowedTCPPorts = [ 8099 ];
      networking.firewall.interfaces.podman0.allowedTCPPorts = [ 8099 ];
    };
  };
}
