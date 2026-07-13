{ config, pkgs, lib }: {
  services.searx = {
    enable = true;
    settings = {
      server = {
        bind_address = "127.0.0.1";
        port = 8888;
        secret_key = "searxng-hermes-$(head -c 32 /dev/urandom | base64)";
      };
      search = {
        safe_search = 0;
        autocomplete = "google";
        default_lang = "en";
      };
      engines = [
        { name = "google"; engine = "google"; shortcut = "g"; }
        { name = "bing"; engine = "bing"; shortcut = "b"; }
        { name = "duckduckgo"; engine = "duckduckgo"; shortcut = "ddg"; }
        { name = "wikipedia"; engine = "wikipedia"; shortcut = "wp"; }
      ];
    };
  };
}
