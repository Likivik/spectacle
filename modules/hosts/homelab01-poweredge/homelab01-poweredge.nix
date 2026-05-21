{ den, inputs, ... }: {
  den.aspects.homelab01-poweredge = {
    includes = [ den.aspects.core ];
    nixos = {
      fileSystems."/" = {
        device = "tmpfs";
        fsType = "tmpfs";
        options = [ "mode=0755" ];
      };
      fileSystems."/boot" = {
        device = "tmpfs";
        fsType = "tmpfs";
        options = [ "mode=0755" ];
      };
    };
  };
}
