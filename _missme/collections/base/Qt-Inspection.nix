{ config, pkgs, ... }: {



environment.systemPackages = with pkgs; [
  gammaray # Software introspection tool for Qt applications developed by KDAB
  gdb #GNU Project debugger
  lldb #Next-generation high-performance debugger
];

}