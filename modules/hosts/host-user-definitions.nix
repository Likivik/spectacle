# defines all hosts + users
{ inputs, determinate, ... }:

{
  den.hosts.x86_64-linux.serenity = {
    description = "Main Desktop";
    users = {
      likivik = { };
      salem = { };
    };
  };
  
  den.hosts.x86_64-linux.traversal = {
    description = "Main Laptop";
    users = {
      likivik = { };
    };
  };

  den.hosts.x86_64-linux.spectacle = {
    description = "Small box connected to TV to watch shows, movies and use browser";
    users = {
      likivik = { };
      watcher = { };
    };

  };


}
