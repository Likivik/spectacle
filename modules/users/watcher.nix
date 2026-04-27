{ den, ... }:
{
  # user aspect
  den.aspects.watcher = {
    includes = [
      den.provides.primary-user
      (den.provides.user-shell "bash")
    ];

    homeManager =
      { pkgs, ... }:
      {
        home.packages = [ pkgs.htop ];
        # home.file.".config/fish/config.fish".force = true;

      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos = { pkgs, ... }: { 
      users.users.watcher.hashedPassword = "$y$j9T$Wx9St3q4EyI5cS5IXbgJy0$5Qc6bj/b5qeieEdaXXd4MdkkyvEM7ZC5GG3IA5HK99C";
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;
      environment.systemPackages = [ pkgs.trash-cli ];
      home-manager.backupCommand = "${pkgs.trash-cli}/bin/trash";
      home-manager.backupFileExtension = "hm-backup";
      home-manager.overwriteBackup = true;
    };
  };
}
