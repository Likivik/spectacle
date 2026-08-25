{ den, inputs, lib, pkgs, ... }:

{
  den.aspects.server.beszel = {
    nixos = { config, lib, pkgs, ... }:
    {
      services.beszel = {
        hub = {
          enable = true;
          host = "0.0.0.0";
          port = 8090;
        };

        agent = {
          enable = true;
          environment = {
            HUB_URL = "http://127.0.0.1:8090";
            LISTEN = "127.0.0.1:45876";
            KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGPrtvI27vyurBaC3Tus7FyHzkCtCZVWwXkaD9DInW+R";
            TOKEN = "64e23de8-b39a-4e0c-abc4-6e071b00cbec";
          };
        };
      };
    };
  };
}
