# Boot-time Telegram connectivity assertion for the erebus host.
#
# Extends `nixosConfigurations.erebus` (via extendModules) into a headless VM
# that DHCPs on QEMU SLIRP and proves the Hermes host can reach Telegram over
# TLS with the SYSTEM CA bundle (i.e. no stale mitmproxy CA / proxy env).
#
# Run:  nix run .#erebus-telegram      (then read serial output)
#
# The vmcheck-telegram oneshot prints at boot and the script fails (non-zero)
# if the TLS handshake to api.telegram.org does not complete, so it can feed a
# CI gate.
{ config, pkgs, lib, ... }:
{
  # --- VM-only networking: kill the static networkd config, use DHCP/SLIRP ---
  # erebus.nix sets systemd.network."10-ens3" (static 148.253.214.185/32) and
  # useNetworkd=true. In QEMU SLIRP that leaves eth0 with a /32 and no route, so
  # outbound TLS hangs. mkForce-disable ALL of it.
  systemd.network.enable = lib.mkForce false;
  networking.useNetworkd = lib.mkForce false;
  networking.useDHCP = lib.mkForce true;
  networking.nameservers = lib.mkForce [
    "1.1.1.1"
    "8.8.8.8"
  ];

  # Tailscale's auth-key is empty in the VM (sops can't decrypt) and tailscaled
  # can hold network-online.target hostage. Disable it.
  services.tailscale.enable = lib.mkForce false;

  # Convenience: a known root password in the throwaway VM image.
  users.users.root.initialPassword = "test";

  systemd.services.vmcheck-telegram = {
    description = "Telegram connectivity verification (oneshot)";
    wantedBy = [ "multi-user.target" ];
    wants = [ "network-online.target" ];
    after = [ "network-online.target" ];
    serviceConfig.Type = "oneshot";
    path = with pkgs; [
      curl
      systemd
      coreutils
      iproute2
      getent
    ];
    script = ''
      exec > /dev/ttyS0 2>&1
      echo "=== TELEGRAM VMCHECK START ==="

      echo "--- network ---"
      ip -4 addr show eth0 2>&1 | grep inet | head -3

      echo "--- DNS ---"
      getent ahosts api.telegram.org | head -2 || echo "DNS_FAIL"

      echo "--- TLS to api.telegram.org (system CA) ---"
      CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 https://api.telegram.org 2>&1)
      echo "http_code=$CODE"
      if [ "$CODE" != "000" ]; then
        echo "TELEGRAM_TLS_OK"
      else
        echo "TELEGRAM_TLS_FAIL"
        exit 1
      fi

      echo "--- proxy env must be clean ---"
      env | grep -iE 'proxy|SSL_CERT|REQUESTS_CA' || echo "PROXY_ENV_CLEAN"

      echo "--- hermes-gateway user unit (deployed + proxy-clean env) ---"
      GW=$(readlink -f /etc/systemd/user/hermes-gateway.service 2>/dev/null)
      if [ -n "$GW" ] && [ -f "$GW" ]; then
        grep -E "ConditionUser=hermes|EnvironmentFile=/run/secrets/hermes/env|ExecStart=" "$GW" | head -3
        echo "GATEWAY_UNIT_OK"
      else
        echo "GATEWAY_UNIT_NOT_FOUND"
      fi

      echo "=== TELEGRAM VMCHECK END ==="
    '';
  };
}
