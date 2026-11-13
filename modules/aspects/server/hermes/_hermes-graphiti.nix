{ config, pkgs, lib, extraProfiles }: let
  graphitiPlugin = pkgs.stdenv.mkDerivation {
    pname = "hermes-graphiti-plugin";
    version = "0.1.0";
    src = ./hermes-graphiti-plugin;
    phases = [ "installPhase" ];
    installPhase = ''
      mkdir -p $out/lib
      cp -r $src/* $out/lib/
    '';
  };

  defaultProfile = { name = "default"; home = "/var/lib/hermes/.hermes"; };
  # A profile can opt out (`graphiti = false`): the plugin symlink is the only
  # thing this module still manages. memory.provider is runtime config and is
  # set imperatively (`hermes config set`) — nix no longer touches it.
  profiles = [ defaultProfile ] ++ builtins.filter (p: p.graphiti or true) extraProfiles;

  installFor = p: let
    user = p.user or "hermes";
  in ''
    PLUGIN_DIR="${p.home}/plugins/graphiti"
    rm -rf "$PLUGIN_DIR" 2>/dev/null || true
    mkdir -p "${p.home}/plugins"
    ln -sf "${graphitiPlugin}/lib" "$PLUGIN_DIR"
    chown -h ${user}:${user} "$PLUGIN_DIR"

    # memory.provider is deliberately NOT set here: runtime config belongs to
    # the operator, not to activation. Set it imperatively if you want graphiti.
  '';
in {
  # Run after the salem home migration: installing into a home that does not
  # exist yet creates it as root, and the profile's own user then cannot init
  # its state (measured 2026-11-13: "Cannot initialize Hermes directory
  # /var/lib/salem/.hermes/cron: Permission denied").
  system.activationScripts."hermes-graphiti-plugin" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
    ++ lib.optional (config.system.activationScripts ? "hermes-graphiti-seed") "hermes-graphiti-seed"
    ++ lib.optional (config.system.activationScripts ? "hermes-salem-migrate") "hermes-salem-migrate"
  ) (lib.concatMapStringsSep "\n\n" installFor profiles);
}
