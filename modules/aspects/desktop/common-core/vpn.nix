{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.vpn = {
    nixos =
      { config, pkgs, lib, ... }:
      {
        services.mullvad-vpn.enable = true;
        services.mullvad-vpn.enableExcludeWrapper = true;
        services.mullvad-vpn.package = pkgs.mullvad-vpn;

        services.tailscale.enable = true;
        services.tailscale.useRoutingFeatures = "both";
        services.tailscale.extraUpFlags = [
          "--operator=$USER"
          "--accept-routes=false"
        ];

        environment.systemPackages = with pkgs; [
          ktailctl
          mullvad-compass
        ];

        boot.kernel.sysctl = {
          "net.ipv4.conf.all.forwarding" = true;
          "net.ipv6.conf.all.forwarding" = true;
        };

        # Exclude Tailscale traffic from Mullvad to prevent routing loops
        systemd.services.mullvad-vpn.postStart = ''
          sleep 2
          ${pkgs.mullvad-vpn}/bin/mullvad exclude add 100.64.0.0/10
          ${pkgs.mullvad-vpn}/bin/mullvad exclude add 41641/udp
        '';
      };
  };
}

/* ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
  Testing dual VPN (Mullvad + Tailscale) on NixOS:

  1. Rebuild & apply config
     ```bash
     sudo nixos-rebuild switch
     ```

  2. Verify services are active
     ```bash
     systemctl status mullvad-vpn.service
     systemctl status tailscale.service
     ```

  3. Confirm Mullvad tunnel up
     ```bash
     mullvad status
     # should show “Connected” and your location
     ```

  4. Confirm Tailscale up & device listed
     ```bash
     tailscale status
     # should list this host and any peers
     ```

  5. Check routing tables – Mullvad should have default route, Tailscale should have subnet routes only:
     ```bash
     ip route show table main
     ip route show table tailscale0   # if using tailscale routing
     ```

  6. Verify Tailscale‑only traffic bypasses Mullvad:
     - Ping a Tailscale peer (replace <peer-ip> with a peer’s Tailscale IP)
       ```bash
       ping -c 3 <peer-ip>
       ```
     - Ensure response works; if it fails, check `tailscale ping <peer-ip>`.

  7. Verify internet traffic still goes through Mullvad:
     ```bash
     curl -s https://ifconfig.co
     # IP should belong
  ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ */