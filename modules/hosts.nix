# defines all hosts + users + homes.
# then config their aspects in as many files you want
{
  # tux user at igloo host.
  # den.hosts.x86_64-linux.igloo.users.tux = { };
  den.hosts.x86_64-linux.spectacle.users.watcher = { };

  # other hosts can also have user tux.
  # den.hosts.x86_64-linux.south = {
  #   wsl = { }; # add nixos-wsl input for this.
  #   users.tux = { };
  #   users.orca = { };
  # };
}
