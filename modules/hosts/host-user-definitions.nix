# defines all hosts + users
{ inputs, ... }:

{

  den.hosts.x86_64-linux = {

    serenity = {
      description = "Likivik's Desktop";
      users = {
        likivik = { };
      };
    };

     traversal = {
       description = "Likivik's Laptop";
       users = {
         likivik = {
         };
       };
     };

    spectacle = {
      description = "Small box connected to TV to watch shows, movies and use browser";
      users = {
        watcher = { };
        likivik = { };
      };
    };

    salembox = {
      description = "Salem's Laptop";
      users = {
        salem = { };
      };
    };

    homelab01-poweredge = {
      description = "homelab01";
      users = {
        likivik = { };
      };
    };

    devbox01 = {
      description = "Devbox01";
      users = {
        likivik = { };
      };
    };

    nixosrouter = {
      description = "Router";
      users = {
        likivik = { };
      };
    };

  };

}
