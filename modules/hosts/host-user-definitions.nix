# defines all hosts + users
{ inputs, ... }:

{
  den.hosts.x86_64-linux.serenity = {
    description = "Desktop";
    users = {
      likivik = { };
    };
  };

  # den.hosts.x86_64-linux.traversal = {
  #   description = "Laptop";
  #   users = {
  #     likivik = { };
  #   };
  # };

  den.hosts.x86_64-linux.spectacle = {
    description = "Small box connected to TV to watch shows, movies and use browser";
    users = {
      watcher = { };
    };

  };


}
