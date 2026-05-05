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

    }

  }
}