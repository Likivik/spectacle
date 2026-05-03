{ den, ... }:
den.lib.policyInspect.inspect {
  kind = "user";
  context = {
    # host = den.hosts.x86_64-linux.spectacle;
    user = den.hosts.x86_64-linux.spectacle.users.watcher;
  };
}
