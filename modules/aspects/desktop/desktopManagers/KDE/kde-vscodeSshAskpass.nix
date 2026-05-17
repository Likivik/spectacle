{ inputs, den, ... }:
{
  den.aspects.kde-vscodeSshAskpass = {
    nixos = { config, pkgs, lib, ... }: {
      programs.ssh.startAgent = lib.mkDefault true;
      programs.ssh.enableAskPassword = lib.mkDefault true;
      environment.variables.SSH_ASKPASS_REQUIRE = lib.mkDefault "prefer";
      environment.systemPackages = [ pkgs.kdePackages.ksshaskpass ];
    };
  };
}