{ inputs, den, ... }:
{
  den.aspects.vpn = {
    nixos =
      { config, pkgs, ... }:
      {
        services.mullvad-vpn.enable = true;
        services.mullvad-vpn.enableExcludeWrapper = true;
        services.mullvad-vpn.package = pkgs.mullvad-vpn;

        services.tailscale.enable = true;
        services.tailscale.useRoutingFeatures = "both";
        services.tailscale.extraUpFlags = [
          "--operator=$USER"
        ];

        environment.systemPackages = with pkgs; [
          ktailctl
          mullvad-compass
        ];

        boot.kernel.sysctl = {
          "net.ipv4.conf.all.forwarding" = true;
          "net.ipv6.conf.all.forwarding" = true;
        };
      };
  };
}