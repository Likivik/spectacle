{ config, pkgs, lib }: {
  environment.systemPackages = [ pkgs.playwright ];

  system.activationScripts."hermes-playwright-browsers" = lib.stringAfter (
    lib.optional (config.system.activationScripts ? setupSecrets) "setupSecrets"
  ) ''
    # Install Playwright browsers (Chromium, Firefox, WebKit)
    # Runs as hermes user so browsers go in hermes' cache
    ${pkgs.sudo}/bin/sudo -u hermes ${pkgs.bash}/bin/bash -c '
      export HOME=/var/lib/hermes
      export PLAYWRIGHT_BROWSERS_PATH=/var/lib/hermes/.cache/ms-playwright
      mkdir -p /var/lib/hermes/.cache/ms-playwright
      chown -R hermes:hermes /var/lib/hermes/.cache/ms-playwright
      /run/current-system/sw/bin/playwright install --with-deps chromium 2>&1 || true
    '
  '';

  # NOTE: the old `hermes-browser-config` activation snippet was removed.
  # browser.cdp_url is persisted in hermes' config.yaml, and its flat-string
  # guard never matched the multiline YAML, so it re-ran `hermes config set`
  # on every boot — which fails during boot-time activation (no PAM yet).
}
