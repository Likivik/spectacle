{ inputs, den, lib, ... }:
{
  den.aspects.test-aspect = {
    includes = [
      ({ user ? null, ... }: {
        nixos = lib.mkIf (user != null) {
          users.users.${user.userName}.extraGroups = [ "test" ];
        };
      })
    ];
  };
}
