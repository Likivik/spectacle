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
            model = "";
            autoshare = false;
            autoupdate = false; # managed by flake
            compaction = {
              auto = false; # Disable automatic compaction
              prune = true; # Keep pruning old tool outputs to save tokens
            };

          };
        };
      };

    # user can provide NixOS configurations
    # to any host it is included on
    nixos =
      { pkgs, user, ... }:
      {
        environment.systemPackages = with pkgs; [
          opencode-desktop
        ];

        users.users.${user.userName} =
          {
            initialPassword = "vm";
            extraGroups = [
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
  };
}
