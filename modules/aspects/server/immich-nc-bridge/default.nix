{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.immich-nc-bridge = {
    nixos = { config, lib, pkgs, ... }:
    let
      immichNcbPlugin = pkgs.buildNpmPackage {
        pname = "immich-nc-bridge";
        version = "0.1.0";
        src = ../../../../pkgs/immich-nc-bridge;
        npmInstallFlags = [ "--omit=dev" ];
        installPhase = ''
          mkdir -p $out/dist
          cp -r node_modules $out/node_modules
          cp dist/index.js dist/index.d.ts $out/dist/
        '';
        npmDepsHash = lib.fakeSha256;  # TODO: real hash on first build
      };
    in
    {
      # Drop compiled plugin into immich's plugin dir.
      environment.etc."immich/plugins/immich-nc-bridge/dist/index.js".source =
        "${immichNcbPlugin}/dist/index.js";
      environment.etc."immich/plugins/immich-nc-bridge/dist/index.d.ts".source =
        "${immichNcbPlugin}/dist/index.d.ts";

      # sops-encrypted secrets for NC credentials + immich API key
      sops.secrets."immich/nc-bridge/nc-user" = {
        owner = "root";
        group = "root";
        mode = "0440";
      };
      sops.secrets."immich/nc-bridge/nc-password" = {
        owner = "root";
        group = "root";
        mode = "0440";
      };
      sops.secrets."immich/nc-bridge/immich-api-key" = {
        owner = "root";
        group = "root";
        mode = "0440";
      };
    };
  };
}