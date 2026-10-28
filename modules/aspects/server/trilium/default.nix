{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.trilium = {
    nixos = { config, lib, pkgs, ... }: {
      services.trilium-server = {
        enable = true;
        host = "0.0.0.0";
        port = 8090;
      };

      # Frontend scripts (render-note calculators) call api.runOnBackend; it is
      # gated behind this option, which the server reads at startup. Set through
      # the environment so it survives config.ini being a store symlink.
      systemd.services.trilium-server.environment = {
        TRILIUM_SECURITY_BACKEND_SCRIPTING_ENABLED = "true";
      };

      systemd.tmpfiles.rules = [
        "d /var/lib/trilium 0750 trilium trilium - -"
      ];
    };
  };
}
