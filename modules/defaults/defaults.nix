# This file: nixos default stuffs
{ inputs, den, lib, pkgs, ... }:
{



  /* ---------------------------------------------------------------------------
    This is the part that allowed Watcher to inherit from Spectacle's `includes`
    specifically -> den._.host-aspects, apparently was a bug fixed in fx-effects branch
    ---------------------------------------------------------------------------- */
  # den.schema.user.includes = [ den._.mutual-provider den._.host-aspects];
  # den.schema.host.includes = [ den._.mutual-provider ];
  # den.stages.home.includes = [ den._.mutual-provider ];
  # den.stages.host.includes = [ den._.mutual-provider ];

  /* ------------------------------------------------------------------------
                                  Home manager
    ------------------------------------------------------------------------- */
  den.schema.user.classes = lib.mkDefault [ "homeManager" ]; # enable HM for every user by default
  den.default.homeManager.home.stateVersion = "25.11"; # Set HM version with which you started, never change for proper backward compatability
  den.ctx.hm-host = {
    home-manager.useGlobalPkgs = true; # TODO: ???
    home-manager.useUserPackages = true; # TODO: ???
  };

  /* ------------------------------------------------------------------------
                                      NixOS
    ------------------------------------------------------------------------- */
  den.default.networking.firewall.enable = true; # enable firewall everywhere

  den.default.includes = [

    /* ------------------------------ Den Batteries ----------------------------- */
    den.provides.define-user # Automatically create users + their homes, by just adding them to hosts
    den.provides.mutual-provider  # TODO: ??? Learn why this is useful ${user}.provides.${host} and ${host}.provides.${user}
    den.provides.hostname # TODO: ??? this Automatically sets hostname, but isn't it already automatically set as per host schema?

    /* --------------------------------- Aspects -------------------------------- */
    den.aspects.determinateNix # determinate systems `nix`
    den.aspects.defaultLocale # the locale settings I'll probably need everywhere?
    den.aspects.nix
    den.aspects.bootloader

  ];

}