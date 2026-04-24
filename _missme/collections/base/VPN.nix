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
  # if you use ipv4, this is all you need
  "net.ipv4.conf.all.forwarding" = true;

  # If you want to use it for ipv6
  "net.ipv6.conf.all.forwarding" = true;
	};
}
