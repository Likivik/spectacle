{
  inputs,
  den,
  lib,
  pkgs,
  ...
}:

let
mkProvides = path:
    let
      contents = builtins.readDir path;
      dirName = baseNameOf path;

      # If there is a file named "foldername.nix" inside "foldername/", use it directly
      shortcutFile = path + "/${dirName}.nix";
      hasShortcut = contents ? "${dirName}.nix";
    in
    if hasShortcut then shortcutFile else
    let
      files = lib.filterAttrs (n: v: v == "regular" && lib.hasSuffix ".nix" n && n != "default.nix") contents;
      aspects = lib.mapAttrs' (n: _: lib.nameValuePair (lib.removeSuffix ".nix" n) (path + "/${n}")) files;
      dirs = lib.filterAttrs (n: v: v == "directory") contents;
      subNamespaces = lib.mapAttrs (n: _: mkProvides (path + "/${n}")) dirs;
      thisLevel = aspects // subNamespaces;
    in
    thisLevel // {
      all = {
        includes = lib.collect (attr: builtins.isPath attr || (lib.isAttrs attr && (attr ? nixos || attr ? homeManager || attr ? includes))) thisLevel;
      };
    };
in

{

  imports = [
    (inputs.den.namespace "core" false)
    (inputs.den.namespace "desktop" false)
    (inputs.den.namespace "dev" false)
    (inputs.den.namespace "server" false)
  ];

  # Dynamically map the folder structure to the den namespaces
  den.ful.core = mkProvides ../aspects/core;
  den.ful.desktop = mkProvides ../aspects/desktop;
  den.ful.dev = mkProvides ../aspects/dev;
  den.ful.server = mkProvides ../aspects/server;

  # this line enables den angle brackets syntax in modules.
  _module.args.__findFile = den.lib.__findFile;
}
