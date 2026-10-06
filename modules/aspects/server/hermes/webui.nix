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
        # Upstream agent env (messaging extra only — no observability extra
        # since we dropped the deps fork). Same package the gateway units
        # run with. passthru.hermesVenv survives the override; run_agent.py
        # sits at that env's site-packages root.
        hermes-pkg = (inputs.hermes-agent.packages.${pkgs.system}.minimal).override {
          extraDependencyGroups = [ "messaging" ];
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
          # The webui runs the agent IN-PROCESS, so it needs the same env the
          # gateway unit gets — otherwise model calls fail HTTP 401 "Invalid API
          # Key" (it only had the password file, so e.g. the MiniMax key was
          # missing while the gateway had it). sops-env is generated into the
          # agent's home by the hermes-agent aspect (0600 hermes), so it exists
          # wherever both aspects are enabled.
          environmentFiles = [
            "/run/secrets/hermes/webui-password"
            "/run/secrets/hermes/env"
            "/var/lib/hermes/.hermes/sops-env"
          ];
        };

        # tailscale serve exposes 8444 → 127.0.0.1:8787 (node-local state,
        # deliberately not in nix — served by a manually-managed listener).

        # `hermes/webui-password` is declared by the HOST, not here: the shared
        # server/sops aspect mkForce-nulls sops.defaultSopsFile on purpose, so a
        # shared aspect cannot point at one host's secrets file. This aspect only
        # consumes /run/secrets/hermes/webui-password.
        # Any host declaring it must keep restartUnits = [ "hermes-webui.service" ]:
        # sops-nix reloadUnits sends a signal the python server ignores.
      };
  };
}
