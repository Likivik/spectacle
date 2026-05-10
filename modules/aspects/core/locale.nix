{ inputs, den, ... }:
{


	den.aspects.defaultLocale = {

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

					"en_US.UTF-8/UTF-8"
					"en_US/ISO-8859-1"
					"en_DK.UTF-8/UTF-8"
					"ru_RU.UTF-8/UTF-8"
					"ru_RU.KOI8-R/KOI8-R"
					"ru_RU/ISO-8859-5"

				];
				extraLocaleSettings = {

					LC_CTYPE = "en_DK.UTF-8";
					LC_ADDRESS = "en_DK.UTF-8";
					LC_MEASUREMENT = "ru_RU.UTF-8";
					LC_MESSAGES = "ru_RU.UTF-8";
					LC_MONETARY = "ru_RU.UTF-8";
					LC_NAME = "ru_RU.UTF-8";
					LC_NUMERIC = "ru_RU.UTF-8";
					LC_PAPER = "ru_RU.UTF-8";
					LC_TELEPHONE = "ru_RU.UTF-8";
					LC_TIME = "ru_RU.UTF-8";
					LC_IDENTIFICATION = "ru_RU.UTF-8";
					LC_COLLATE = "ru_RU.UTF-8";

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
