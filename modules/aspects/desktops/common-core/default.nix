{ inputs, den, ... }:

{
  # Create namespace for common desktop aspects
  imports = [ (inputs.den.namespace "common-core" false) ];

  # Common desktop core aspect that includes all sub-aspects
  den.ful.common-core.common-core = {
    includes = [
      den.ful.common-core.desktop-core
      den.ful.common-core.filesystems-support
      den.ful.common-core.networking
      den.ful.common-core.package-sources
      den.ful.common-core.peripherals-base
      den.ful.common-core.printers-scanners
      den.ful.common-core.remote-desktops
      den.ful.common-core.vpn
    ];
  };
}