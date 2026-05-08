{
  inputs,
  den,
  lib,
  ...
}:

let
  mkProvides =
    path:
    let
      contents = builtins.readDir path;

      # Process files into aspects
      files = lib.filterAttrs (
        n: v: v == "regular" && lib.hasSuffix ".nix" n && n != "default.nix"
      ) contents;

      aspects = lib.mapAttrs' (
        n: _: lib.nameValuePair (lib.removeSuffix ".nix" n) (import (path + "/${n}"))
      ) files;

      # Process sub-directories into sub-namespaces
      dirs = lib.filterAttrs (n: v: v == "directory") contents;
      subNamespaces = lib.mapAttrs (n: _: mkProvides (path + "/${n}")) dirs;

      thisLevel = aspects // subNamespaces;
    in
    thisLevel
    // {
      # This allows you to do: includes = [ den.ful.core.all ]
      all = {
        includes = lib.collect (attr: attr ? nixos || attr ? homeManager || attr ? includes) thisLevel;
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
