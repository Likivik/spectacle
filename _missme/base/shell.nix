{ config, pkgs, ... }:
{
	environment.systemPackages = with pkgs;
	[
		# Images
		# imagemagick # Create, edit, compose, convert bitmap images
		# Clipboard
		# xclip # Tool to access the X clipboard from a console application
		# Killing
		killall # kill all processes with name 'xxxx'
		# Compression
		# unzip # Open passworded zip: unzip -P PasswOrd filename.zip
		# unrar
		# unar
		
		# yazi
		# bat
		# eza
		#ov
	];
	
	# programs.zsh.enable = true;
	# users.defaultUserShell = pkgs.zsh;




}
