{ den, ... }:
{
  den.aspects.zsh = {
    homeManager = { pkgs, ... }: {
      programs.zsh = {
        enable = true;
        enableCompletion = true;
        syntaxHighlighting.enable = true;
        enableVteIntegration = true; # Blackbox and Gnome terminal use it at least, maybe others
        history.extended = true; # Save timestamp into the history file.
        autocd = true; # Automatically enter into a directory if typed directly into shell.
        initContent = ''
          ${builtins.readFile ./zsh/.zshrc}
          ${builtins.readFile ./zsh/.p10k-color.zsh}
        '';
        antidote = {
          enable = true;
          useFriendlyNames = true;
          plugins = [
            ''
              ${builtins.readFile ./zsh/.zsh_plugins.txt}
            ''
          ];
        };
      };
    };
  };
}