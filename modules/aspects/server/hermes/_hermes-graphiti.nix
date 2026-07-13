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
    chmod -R a+rX "$PLUGIN_DIR"

    if ! grep -qE "^memory\.provider:" /var/lib/hermes/.hermes/config.yaml 2>/dev/null; then
      ${pkgs.sudo}/bin/sudo -u hermes bash -c '
        export HOME=/var/lib/hermes
        export HERMES_HOME=/var/lib/hermes/.hermes
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
        export PATH=/run/current-system/sw/bin:/etc/profiles/per-user/hermes/bin
        /run/current-system/sw/bin/hermes config set memory.provider graphiti
      '
    fi
  '';
}
