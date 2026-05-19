{ den, inputs, ... }: {

  den.aspects.nixosrouter = {

    includes = [ den.aspects.core._ ];
  };

}
