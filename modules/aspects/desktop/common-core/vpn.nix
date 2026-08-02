{ inputs, den, ... }:
{
  den.aspects.desktop.common-core.vpn = {
    nixos =
      { config, pkgs, lib, ... }:
      {

        services.mullvad-vpn.enable = true;
        services.mullvad-vpn.enableExcludeWrapper = true;
        services.mullvad-vpn.gui.enable = true;

        environment.systemPackages = with pkgs; [
          mullvad-compass

          ktailctl
        ];

         # v2raya replaced by xray-vless (TUN-mode VLESS Reality service below)
         services.v2raya.enable = true;





         boot.kernel.sysctl = {
          "net.ipv4.conf.all.forwarding" = true;
          "net.ipv6.conf.all.forwarding" = true;
        };

        # Exclude Tailscale traffic from Mullvad to prevent routing loops
        systemd.services.mullvad-vpn.postStart = ''
          sleep 2
          ${pkgs.mullvad}/bin/mullvad exclude add 100.64.0.0/10
          ${pkgs.mullvad}/bin/mullvad exclude add 41641/udp
        '';
      };
  };
}