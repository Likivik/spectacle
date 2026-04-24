{ pkgs, lib, ... }:

{

  # FIX for VSCODE not properly asking and/or remembering ssh passphrase
  programs.ssh.startAgent = lib.mkDefault true; # start agent, ssh-add to add keys
  programs.ssh.enableAskPassword = lib.mkDefault true; # SSH_ASKPASS
  # programs.ssh.askPassword = lib.mkDefault "ksshaskpass";
  environment.variables.SSH_ASKPASS_REQUIRE = lib.mkDefault "prefer";
  environment.systemPackages = [ pkgs.kdePackages.ksshaskpass ];

}
