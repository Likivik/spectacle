{
  hardware.facter.reportPath = ./facter.json;

  # Deterministic hostId — keeps kkmserver license binding stable across reboots.
  # Randomly generated with `head -c4 /dev/urandom | od -A none -t x4`
  networking.hostId = "1a2b3c4d";
}