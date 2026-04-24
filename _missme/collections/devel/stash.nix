{
  config,
  pkgs,
  lib,
  ...
}:
{


  services.stash = {
    enable = true;
    username = "stash";
    passwordFile = "/Storage/0Torrents/stashConf/password";
    jwtSecretKeyFile = "/Storage/0Torrents/stashConf/jwt";
    sessionStoreKeyFile = "/Storage/0Torrents/stashConf/session";
    mutableSettings = true;
    mutablePlugins = true;
    mutableScrapers = true;
    settings = 
    {
      stash = [{path = "/Storage/0Torrents/exitbox";}];
      plugins_path = "/Storage/0Torrents/stashConf/plugins";
      scrapers_path  = "/Storage/0Torrents/stashConf/scrapers";
    };
  };


  users = {
    groups.${"media"} = {};
    users.likivik.extraGroups = ["media"];
    users.stash.extraGroups = ["users"];
  };
}
