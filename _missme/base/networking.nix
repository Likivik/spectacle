{ config, pkgs, ... }:
{
  # Networking --------------------------------------------------------------
  networking.networkmanager = {
    enable = true;
    plugins = [
      pkgs.networkmanager-l2tp
    ];
  };

  # remember to add users to the networkmanager group
  networking.firewall = {
    enable = true;
    # allowedTCPPorts = [ 80 443 6568]; # for anydesk
    # allowedUDPPorts = [ 50001 50002 50003 ]; # for anydesk
  };

  # boot.kernel.sysctl."net.ipv4.ip_forward" = 1;
  # boot.kernel.sysctl."net.ipv6.conf.all.forwarding" = 1;

}
