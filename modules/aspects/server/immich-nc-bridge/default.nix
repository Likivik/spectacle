{ den, inputs, lib, pkgs, ... }:

let
  # Build the TypeScript plugin via pnpm/npm in a Node sandbox.
  # immich loads /usr/share/immich/plugins/<name>/dist/index.js
  immichNcbPlugin = pkgs.buildNpmPackage {
    pname = "immich-nc-bridge";
    version = "0.1.0";
    src = ./.;
    npmInstallFlags = [ "--omit=dev" ];
    installPhase = ''
      mkdir -p $out/dist
      cp -r node_modules $out/node_modules
      cp dist/index.js dist/index.d.ts $out/dist/
    '';
    # Use offline npm cache if available
    npmDepsHash = lib.fakeSha256;  # TODO: real hash on first build
  };
in
{
  den.aspects.server.immich-nc-bridge = {
    nixos = { config, lib, pkgs, ... }: {
      # Drop compiled plugin into immich's plugin dir.
      # Immich reads plugins from /usr/share/immich/plugins/ on container start.
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
