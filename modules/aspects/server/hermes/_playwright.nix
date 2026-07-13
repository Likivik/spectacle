{ config, pkgs, lib }: {
  environment.systemPackages = [ pkgs.playwright ];

  system.activationScripts."hermes-playwright-browsers" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    # Install Playwright browsers (Chromium, Firefox, WebKit)
    # Runs as hermes user so browsers go in hermes' cache
    ${pkgs.sudo}/bin/sudo -u hermes bash -c '
      export HOME=/var/lib/hermes
      export PLAYWRIGHT_BROWSERS_PATH=/var/lib/hermes/.cache/ms-playwright
      mkdir -p /var/lib/hermes/.cache/ms-playwright
      chown -R hermes:hermes /var/lib/hermes/.cache/ms-playwright
      /run/current-system/sw/bin/playwright install --with-deps chromium 2>&1 || true
    '
  '';

  # Configure Hermes to use Playwright browser
  system.activationScripts."hermes-browser-config" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    if ! ${pkgs.gnugrep}/bin/grep -q "browser.cdp_url" /var/lib/hermes/.hermes/config.yaml 2>/dev/null; then
      ${pkgs.sudo}/bin/sudo -u hermes ${pkgs.bash}/bin/bash -c '
        export HOME=/var/lib/hermes
        export HERMES_HOME=/var/lib/hermes/.hermes
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
        export PATH=/run/current-system/sw/bin:/etc/profiles/per-user/hermes/bin
        /run/current-system/sw/bin/hermes config set browser.cdp_url "http://127.0.0.1:9222" 2>&1 || true
      '
    fi
  '';
}
