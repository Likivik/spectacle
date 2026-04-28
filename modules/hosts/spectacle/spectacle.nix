                        



      
{ inputs, den, lib, ... }:
{

  den.aspects.spectacle = {
  # Define the actual host 'spectacle'
  den.hosts.spectacle = { # Changed from den.aspects.spectacle to den.hosts.spectacle
      includes = [
        den.aspects.gnome-desktop
        den.aspects.firefox
    ];

  };

}