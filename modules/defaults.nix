# This file: nixos default stuffs
{ inputs, den, lib, pkgs, ... }:
{


  
  /* ---------------------------------------------------------------------------
    This is the part that allowed Watcher to inherit from Spectacle's `includes`
    specifically -> den._.host-aspects
    ---------------------------------------------------------------------------- */
  den.ctx.user.includes = [ den._.mutual-provider den._.host-aspects];
  den.ctx.host.includes = [ den._.mutual-provider ];
  # den.stages.home.includes = [ den._.mutual-provider ];
  # den.stages.host.includes = [ den._.mutual-provider ];

  den.ctx.hm-host = {
    home-manager.useGlobalPkgs = true; 
    home-manager.useUserPackages = true;
  };

  den.default.nixos.system.stateVersion = "25.11";
  den.default.homeManager.home.stateVersion = "25.11";

  den.schema.user.classes = lib.mkDefault [ "homeManager" ];

  den.default.nixos.nixpkgs.config.allowUnfree = true;

  # Enable a basic set of fonts providing several styles and families and reasonable coverage of Unicode.
  den.default.nixos.fonts.enableDefaultPackages = true;


  den.default.includes = [     
    
    /* ------------------------------ Den Batteries ----------------------------- */
    den.provides.define-user # Automatically create users + their homes, by just adding them to hosts
    
    # TODO: ??? Learn why this is useful ${user}.provides.${host} and ${host}.provides.${user}
    den.provides.mutual-provider
    # TODO: ??? this Automatically sets hostname, but isn't it already automatically set as per host schema?
    den.provides.hostname 

    /* --------------------------------- Aspects -------------------------------- */
    den.aspects.determinateNix # determinate systems `nix`
    den.aspects.defaultLocale # probably the locale settings I'll need everywhere?
  ];

}