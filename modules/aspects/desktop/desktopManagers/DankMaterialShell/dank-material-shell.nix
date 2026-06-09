{ den, lib, pkgs, ... }: {
  den.aspects.desktop.desktopManagers.dank-material-shell = {
    includes = [
      den.aspects.desktop.desktopManagers.niri
    ];

    nixos = { ... }: {
      programs.dms-shell.enable = true;
    };

    maid = { user, ... }: {
      file.xdg_config."DankMaterialShell".source = ./../../../../../users/likivik/dotfiles/dms;
    };
  };
}
