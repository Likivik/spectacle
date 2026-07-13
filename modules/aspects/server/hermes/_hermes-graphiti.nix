{ config, pkgs, lib }: let
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
in {
  system.activationScripts."hermes-graphiti-plugin" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
    ++ lib.optional (config.system.activationScripts ? "hermes-graphiti-seed") "hermes-graphiti-seed"
  ) ''
    PLUGIN_DIR="/var/lib/hermes/.hermes/plugins/graphiti"
    rm -rf "$PLUGIN_DIR" 2>/dev/null || true
    mkdir -p "/var/lib/hermes/.hermes/plugins"
    ln -sf "${graphitiPlugin}/lib" "$PLUGIN_DIR"
    chown -h hermes:hermes "$PLUGIN_DIR"

    if ! ${pkgs.gnugrep}/bin/grep -q "provider: graphiti" /var/lib/hermes/.hermes/config.yaml 2>/dev/null; then
      ${pkgs.sudo}/bin/sudo -u hermes ${pkgs.bash}/bin/bash -c '
        export HOME=/var/lib/hermes
        export HERMES_HOME=/var/lib/hermes/.hermes
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
        export PATH=/run/current-system/sw/bin:/etc/profiles/per-user/hermes/bin
        /run/current-system/sw/bin/hermes config set memory.provider graphiti
      '
    fi
  '';
}
