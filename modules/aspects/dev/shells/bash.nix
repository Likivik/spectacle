{ den, lib, ... }:
{
  den.aspects.bash = {

    maid = { ... }: {
      file.home.".bash_aliases".text = ''
        # Nix helpers
        nix-eval-host() {
            local host="''${1:-$(hostname -s)}"
            nix eval .#nixosConfigurations."$host".config.networking.hostName
        }

        nixos-switch-cn() {
            local host="''${1:-$(hostname -s)}"
            NIX_CONFIG='substituters = https://mirrors.ustc.edu.cn/nix-channels/store https://mirrors.tuna.tsinghua.edu.cn/nix-channels/store https://mirror.sjtu.edu.cn/nix-channels/store https://cache.nixos.org' \
              nh os switch .#"$host"
        }

        # Shortcuts
        alias ll='ls -l'
        alias ..='cd ..'
      '';
    };

    nixos = { pkgs, ... }: {
      environment.localBinInPath = lib.mkDefault true;
      programs.bash.completion.enable = true;
      programs.bash.interactiveShellInit = ''
        if [[ "$TERM" =~ xterm|vte|gnome ]]; then
          . ${pkgs.vte}/etc/profile.d/vte.sh
        fi
      '';
    };

  };
}