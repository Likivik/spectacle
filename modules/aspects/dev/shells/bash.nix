{ den, ... }:
{
  den.aspects.bash = {

    homeManager =
    { pkgs, ... }:
    {

      programs.bash = {
        enable = true;
        enableCompletion = true;
        enableVteIntegration = true;
        shellAliases = {
          ll = "ls -l";
          ".." = "cd ..";
        };
        # initExtra = ''
        #   ssh-add /home/likivik/.ssh/id_rsa
        #   cdl ()
        #   {
        #     cd "$(dirname "$(readlink "$1")")";
        #   }
        #   eval "$(starship init bash)"
        # '';
      };

    };

    maid = { ... }: {
      file.home = {
        ".config/environment.d/10-local-bin-path.conf".text = ''
          # opencode-snip plugin needs snip binary (~/.local/bin/snip) on PATH
          # systemd-logind applies this to all user processes (covers desktop-launched opencode)
          PATH=/home/likivik/.local/bin:$PATH
        '';
        ".profile".text = ''
          # Same purpose as environment.d above but covers login-shell terminals
          case ":''${PATH:-}:" in
            *:"$HOME/.local/bin":*) ;;
            *) export PATH="$HOME/.local/bin:$PATH" ;;
          esac
        '';
      };
    };

  };
}