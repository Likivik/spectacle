{ inputs, den, ... }:
{


	den.aspects.core.default-locale = {

		nixos =
		{ ... }:
		{
			# Enable a basic set of fonts providing several styles and families and reasonable coverage of Unicode.
			# for: display other languages (even in terminal)
			fonts.enableDefaultPackages = true;
			# Locate Settings ---------------------------------------------------------
			i18n ={

				defaultLocale = "en_DK.UTF-8";
				extraLocales = [

					"en_DK.UTF-8/UTF-8"

				];
				extraLocaleSettings = {

					LC_CTYPE = "en_DK.UTF-8";
					LC_ADDRESS = "en_DK.UTF-8";
					LC_MEASUREMENT = "en_DK.UTF-8";
					LC_MESSAGES = "en_DK.UTF-8";
					LC_MONETARY = "en_DK.UTF-8";
					LC_NAME = "en_DK.UTF-8";
					LC_NUMERIC = "en_DK.UTF-8";
					LC_PAPER = "en_DK.UTF-8";
					LC_TELEPHONE = "en_DK.UTF-8";
					LC_TIME = "en_DK.UTF-8";
					LC_IDENTIFICATION = "en_DK.UTF-8";
					LC_COLLATE = "en_DK.UTF-8";

				};

			};

			time =
			{

				timeZone = "Europe/Moscow";

			};

			# console =
			# {
			# 	font = "Lat2-Terminus16";
			# 	keyMap = "us";
			# };

		};

	};

}
