{ inputs, den, lib, ... }:
let
  # 1. Helper to find every .nix file recursively for the 'imports' list
  getNixFiles = path:
    let
      contents = builtins.readDir path;
      files = lib.mapAttrsToList (n: _: path + "/${n}")
        (lib.filterAttrs (n: v: v == "regular" && lib.hasSuffix ".nix" n && n != "default.nix") contents);
      dirs = lib.concatLists (lib.mapAttrsToList (n: _: getNixFiles (path + "/${n}"))
        (lib.filterAttrs (n: v: v == "directory") contents));
    in
    files ++ dirs;

  # 2. Helper to build the navigation tree (core.all, desktop.common-core.all)
  mkNavigationTree = path:
    let
      contents = builtins.readDir path;
      nixFiles = lib.filterAttrs (n: v: v == "regular" && lib.hasSuffix ".nix" n && n != "default.nix") contents;
      dirs = lib.filterAttrs (n: v: v == "directory") contents;

      # We use the file paths directly for 'includes'
      filePaths = lib.mapAttrsToList (n: _: path + "/${n}") nixFiles;

      # Recursively build sub-folders
      subTrees = lib.mapAttrs (n: _: mkNavigationTree (path + "/${n}")) dirs;

      # The 'all' aspect for this specific folder
      allAspect = {
        includes = filePaths ++ (lib.mapAttrsToList (n: v: v.all) subTrees);
      };
    in
    subTrees // { all = allAspect; };

in
{
  # Dynamically import every file so Den registers the aspects inside them
  imports = [
    (inputs.den.namespace "core" false)
    (inputs.den.namespace "desktop" false)
    (inputs.den.namespace "dev" false)
    (inputs.den.namespace "server" false)
  ]
  ++ (getNixFiles ../aspects/core)
  ++ (getNixFiles ../aspects/desktop)
  ++ (getNixFiles ../aspects/dev)
  ++ (getNixFiles ../aspects/server);

  # Expose the navigation objects as module arguments
  # This prevents the collision with den.ful
  _module.args = {
    core = mkNavigationTree ../aspects/core;
    desktop = mkNavigationTree ../aspects/desktop;
    dev = mkNavigationTree ../aspects/dev;
    server = mkNavigationTree ../aspects/server;

    # Keep the den findFile logic
    __findFile = den.lib.__findFile;
  };
}