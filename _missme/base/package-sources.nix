{ config, pkgs, ... }:
{
	# Packages ----------------------------------------------------------------
	nixpkgs.config = { allowUnfree = true; }; # Open the gates!
	
	# Flatpak Stuff -----------------------------------------------------------
	services.flatpak.enable = true; # Open even more gates!
	
	# This is a fix for broken fonts and layout in flatpak apps
	# Apparently XDG is needed for links and D-bus related stuffs
	xdg.portal ={
		enable = true;
		config = {
			common = {
				default = [ /* I forget why this is here */
					"kde"
				];
				"org.freedesktop.impl.portal.Settings" = [ 
					"kde;gtk" /* I forget why this is here */
				];
			};
		};
		
		xdgOpenUsePortal = true; /* ->
		because this: https://github.com/NixOS/nixpkgs/issues/160923,
		opening links/mime-types permission issues when opening from other apps */
	};

	# Appimage Stuff -----------------------------------------------------------
	programs.appimage = { 
		enable = true;
		binfmt = true; /* ->
		Registers Appimages with the kernel to open them with appimage-run,
		meaning "just click on the icon and it works as normal.
		perhaps should be made default on "base-config" for new users =)
		This used to be much harder to achieve!*/

	}; # All the gates!


	# Only one gate remains... and we shall snap it closed!



}
