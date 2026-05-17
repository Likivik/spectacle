{ inputs, den, ... }:
{
  # user aspect
  den.aspects.likivik = {
    includes = [
      den.provides.primary-user
      (den.provides.user-shell "bash")
      den.aspects.firefox
    ];

    homeManager =
      { pkgs, ... }:
      {
        programs.opencode = {
          enable = true;
          enableMcpIntegration = true;
          settings = {
            model = "anthropic/claude-sonnet-4-20250514";
            autoshare = false;
            autoupdate = true;
          }
        };
      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos = { pkgs, user, ... }: {
      home-manager.useGlobalPkgs = true;
      home-manager.useUserPackages = true;

      environment.systemPackages = with pkgs; [
        opencode-desktop
      ];



      users.users.${user.userName}.extraGroups = [
        "wheel" # to use `sudo`
        "networkmanager" # ethernet/wifi access
        "adbusers" # access to Android Debug Bridge
        "syncthing"
        "libvirtd"
        "docker"
        "podman"
        "input"
        "ydotool"
        "scanner"
        "lp"
        "pipewire"
      ];
    };
  };
}
