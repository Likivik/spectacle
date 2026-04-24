{ config, pkgs, ... }: {

# Enable a basic set of fonts providing several styles and families and reasonable coverage of Unicode.
fonts.enableDefaultPackages = true;
fonts.packages = with pkgs; [

	# Dev/Markdown
		source-code-pro
		monaspace
		input-fonts
		maple-mono.NF
		camingo-code
		cascadia-code # https://github.com/microsoft/cascadia-code
		nerd-fonts.caskaydia-mono #Nerd Fonts: Like Cascadia Code but without any ligatures
		jetbrains-mono



	## Microsoft Fonts - to show some .doc/.docx better
		#corefonts # Trying to live without

	# Office Suite
			#liberation_ttf # - favorite for libreoffice, substitute for Microsoft Fonts
			#liberation-sans-narrow # Liberation_v2 doesn't come with narrow fonts by default

];

nixpkgs.config.input-fonts.acceptLicense = true;


}
