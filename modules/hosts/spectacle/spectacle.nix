                        



      
{ inputs, den, lib, ... }:
{

  den.aspects.spectacle = {
      includes = [
        den.aspects.gnome-desktop
        den.aspects.firefox
    ];

  };

}