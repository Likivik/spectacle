{ config, pkgs, ... }:
{
	# Supported Filesystems List --------------------------------------------------
	boot.supportedFilesystems =
	[
		"fat32" "exfat" "ntfs"
	];
 
 services.fstrim.enable = true;
 

	# TOOLS -----------------------------------------------------------------------
	environment.systemPackages = with pkgs;
	[
		# FAT and VFAT tools (for gparted and others)
			dosfstools # Utilities for creating and checking FAT and VFAT file systems
			mtools # Utilities to access MS-DOS disks
	];
}
