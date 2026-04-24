{config, packages, lib, ... }:

let
	# Creates a list of files in this folder
	#-> [ "2test.nix" "3test.nix" "test.txt" ]
	listOfFilesFromDir = (dirPath:
		lib.collect lib.isString (
			lib.mapAttrsRecursive (path: type:
				lib.concatStringsSep "/" path
			)(
				builtins.readDir dirPath # <-
			)
		)
	);

	# Filter out everything but .nix files and exclude default.nix
	#-> [ "2test.nix" "3test.nix" ]
	listOfValidFilesFromDir = (dir:
		lib.filter (file:
			lib.hasSuffix ".nix" file &&
			file != "default.nix"
		)(
			listOfFilesFromDir dir
		)
	);
	# Nix requires absolute path (I believe so)
	makePathsAbsolute = (listOfFiles:
		map (fileName:
			./. + "/${fileName}" # `./.` is an absolute path to current folder
		)(
			listOfFiles
		)
	);

	#-> [ /mnt/storage/Code/2test.nix /mnt/storage/Code/3test.nix]
	nixFilesInThisFolder = (dirPath:
		makePathsAbsolute (listOfValidFilesFromDir dirPath)
	);

in

{

	imports = nixFilesInThisFolder ./.;

}
