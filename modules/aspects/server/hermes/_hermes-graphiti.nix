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
  # A profile can opt out (`graphiti = false`): installing the plugin and
  # forcing memory.provider would otherwise undo that choice on every switch.
  profiles = [ defaultProfile ] ++ builtins.filter (p: p.graphiti or true) extraProfiles;

  installFor = p: let
    user = p.user or "hermes";
    homeDir = if user == "hermes" then "/var/lib/hermes" else "/var/lib/${user}";
  in ''
    PLUGIN_DIR="${p.home}/plugins/graphiti"
    rm -rf "$PLUGIN_DIR" 2>/dev/null || true
    mkdir -p "${p.home}/plugins"
    ln -sf "${graphitiPlugin}/lib" "$PLUGIN_DIR"
    chown -h ${user}:${user} "$PLUGIN_DIR"

    if ! ${pkgs.gnugrep}/bin/grep -q "provider: graphiti" "${p.home}/config.yaml" 2>/dev/null; then
      ${pkgs.sudo}/bin/sudo -u ${user} ${pkgs.bash}/bin/bash -c ${lib.escapeShellArg ''
        export HOME=${homeDir}
        export HERMES_HOME=${p.home}
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
        export PATH=/run/current-system/sw/bin:/etc/profiles/per-user/${user}/bin
        /run/current-system/sw/bin/hermes config set memory.provider graphiti
      ''}
    fi
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
