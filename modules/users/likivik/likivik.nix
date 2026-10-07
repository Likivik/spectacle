{ inputs, den, ... }:
{
  # user aspect
  den.aspects.likivik = {
    includes = [
      den.provides.primary-user
      (den.provides.user-shell "bash")
    ];

    nixos =
      { pkgs, user, ... }:
      {
        # /Storage/Git is group-owned by this so the Forgejo/Gitea service
        # accounts (members of `users`) get no write into the repos, while the
        # agent user keeps access. Shared with the hermes user per host.
        users.groups.gitdev = { };

        users.users.${user.userName} =
          {
            extraGroups = [
              "wheel" # to use `sudo`
              "gitdev" # /Storage/Git repos, shared with the hermes agent
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
              "video"
            ];
          };
      };
  };
}
