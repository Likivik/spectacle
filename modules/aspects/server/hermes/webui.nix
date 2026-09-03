{ den, inputs, lib, ... }:
{
  flake-file.inputs = {
    hermes-webui = {
      url = "github:nesquena/hermes-webui";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  den.aspects.server.hermes-webui = {
    nixos = { config, pkgs, lib, ... }:
      let
        # The fork's agent env (messaging + observability extras) — same package
        # the gateway units run with. passthru.hermesVenv survives the override;
        # run_agent.py sits at that env's site-packages root.
        hermes-pkg = (inputs.hermes-agent.packages.${pkgs.system}.minimal).override {
          extraDependencyGroups = [ "messaging" "observability" ];
        };
        agent-site-packages = "${hermes-pkg.passthru.hermesVenv}/lib/python3.12/site-packages";
      in
      {
        imports = [ inputs.hermes-webui.nixosModules.default ];

        services.hermes-webui = {
          enable = true;
          host = "127.0.0.1";
          port = 8787;
          # Run as the hermes service account so shared ~/.hermes state
          # (sessions, logs, workspace) is readable without chown.
          user = "hermes";
          group = "hermes";
          hermesHome = "/var/lib/hermes/.hermes";
          stateDir = "/var/lib/hermes/.hermes/webui-state";
          agent.package = hermes-pkg;
          agent.dir = agent-site-packages;
          # Password auth — required before any tailscale exposure.
          environmentFiles = [ "/run/secrets/hermes/webui-password" ];
        };

        # tailscale serve exposes 8444 → 127.0.0.1:8787 (node-local state,
        # deliberately not in nix — same treatment as pocketrisu on :443).

        sops.secrets."hermes/webui-password" = {
          sopsFile = ../../../../secrets/erebus/secrets.yaml;
          owner = "hermes";
          group = "hermes";
          mode = "0400";
          # KEY=value content, consumed directly as an EnvironmentFile.
          # NOTE: sops-nix reloadUnits sends a signal the python server
          # ignores — secret changes need `systemctl restart hermes-webui`.
          restartUnits = [ "hermes-webui.service" ];
        };
      };
  };
}
