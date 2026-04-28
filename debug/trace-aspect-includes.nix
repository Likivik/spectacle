let  
  inherit (den.lib.aspects) resolve adapters;  
  aspect = den.hosts.x86_64-linux.resolved;  
in

resolve.withAdapter adapters.trace "nixos" aspect