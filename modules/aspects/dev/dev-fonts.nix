{ inputs, den, ... }:
{

	den.aspects.dev-fonts = {

		nixos = 
			{ pkgs, ... }:
			{
				
				# Enable a basic set of fonts providing several styles and families and reasonable coverage of Unicode.
				# fonts.enableDefaultPackages = true; # --> MOVED TO defaults.nix

				fonts.packages = with pkgs; [
					/* ------------------------------ Dev/Markdown ------------------------------ */
						source-code-pro
						monaspace
						input-fonts
						maple-mono.NF
						camingo-code
						cascadia-code # https://github.com/microsoft/cascadia-code
						nerd-fonts.caskaydia-mono #Nerd Fonts: Like Cascadia Code but without any ligatures
						jetbrains-mono
						fira-code
				];

				nixpkgs.config.input-fonts.acceptLicense = true;

			};
	};

}
