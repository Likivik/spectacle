{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.trilium = {
    nixos = { config, lib, pkgs, ... }: {
      services.trilium-server = {
        enable = true;
        host = "0.0.0.0";
        port = 8090;
      };

      systemd.tmpfiles.rules = [
        "d /var/lib/trilium 0750 trilium trilium - -"
      ];
    };
  };
}
