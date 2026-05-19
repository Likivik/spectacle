{ den, inputs, ... }: {

  den.aspects.homelab01-poweredge = {

    includes = [ den.aspects.core._ ];
  };

}
