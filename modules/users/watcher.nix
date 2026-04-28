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

      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos = { pkgs, ... }: { 
      users.users.watcher.password = "stupid";
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;
      environment.systemPackages = [ pkgs.trash-cli ];
      home-manager.backupCommand = "${pkgs.trash-cli}/bin/trash";
      home-manager.backupFileExtension = "hm-backup";
      home-manager.overwriteBackup = true;
    };
  };
}
