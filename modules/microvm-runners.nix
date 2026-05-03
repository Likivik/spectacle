# for each host exposes microvm declaredRunner (if exists) as package output of this flake.
# feel free to remove or adapt.
{
  den,
  lib,
  config,
  inputs,
  # flake-file,
  ...
}:
let
  microvmRunners = lib.pipe den.hosts [
    lib.attrValues
    (lib.concatMap lib.attrValues)
    (map (
      host:
      let
        osConf = lib.attrByPath host.intoAttr null config.flake;
        vmRunner = osConf.config.microvm.declaredRunner or null;
        package = lib.optionalAttrs (vmRunner != null) {
          ${host.system}.${host.name} = vmRunner;
        };
      in
      package
    ))
  ];
in
{

  flake-file.inputs.microvm.url = "github:microvm-nix/microvm.nix";

  flake.nixConfig = {
    extra-substituters = [ "https://microvm.cachix.org" ];
    extra-trusted-public-keys = [ "microvm.cachix.org-1:oXnBc6hRE3eX5rSYdRyMYXnfzcCxC7yKPTbZXALsqys=" ];
  };

  flake.packages = lib.mkMerge microvmRunners;
}
