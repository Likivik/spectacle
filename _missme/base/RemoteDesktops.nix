{ config, pkgs, ... }:
{
	environment.systemPackages = with pkgs; [
			anydesk
			remmina
  	];

}
