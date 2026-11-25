# Fixtures for lib/token-ownership.nix. Returns a list of failures; empty means
# the function behaves. Imported by checks.telegram-token-ownership before the
# real config is checked, so a broken invariant fails even if the fleet happens
# to be wired correctly.
{ lib, tokenOwnership }:
let
  v = tokenOwnership.violations;
  host = host: rendersToken: tokenSecrets: { inherit host rendersToken tokenSecrets; };
  secret = file: key: { inherit file key; };
  serenityToken = secret "secrets/serenity/hermes-secrets.yaml" "hermes/telegram-bot-token";
  erebusToken = secret "secrets/erebus/secrets.yaml" "hermes/telegram-bot-token";

  expect =
    name: actual: ok:
    lib.optional (!ok) "${name}: got ${builtins.toJSON actual}";

  # 1. The happy path: one whitelisted host, one secret, no sharing.
  happy = v {
    telegramHosts = [ "serenity" ];
    hosts = [ (host "serenity" true [ serenityToken ]) (host "erebus" false [ ]) ];
  };

  # 2. Two hosts wired to the SAME sops file+key — the copy-paste bug this
  #    branch exists for. Must be caught even though only one is whitelisted.
  sameFile = v {
    telegramHosts = [ "serenity" ];
    hosts = [
      (host "serenity" true [ serenityToken ])
      (host "erebus" true [ (secret "secrets/serenity/hermes-secrets.yaml" "hermes/telegram-bot-token") ])
    ];
  };

  # 3. A non-whitelisted host renders the token — the erebus incident itself.
  rogueHost = v {
    telegramHosts = [ "serenity" ];
    hosts = [ (host "serenity" true [ serenityToken ]) (host "erebus" true [ erebusToken ]) ];
  };

  # 4. Whitelisted host renders nothing — now a loud config error upstream, and
  #    still a violation here.
  silentHost = v {
    telegramHosts = [ "serenity" ];
    hosts = [ (host "serenity" false [ serenityToken ]) ];
  };

  # 5. Documented blind spot: two different files, same token value. The
  #    function cannot see inside them, so this MUST stay a pass — if it ever
  #    starts failing, someone started decrypting secrets at eval time.
  differentFiles = v {
    telegramHosts = [ "serenity" "erebus" ];
    hosts = [ (host "serenity" true [ serenityToken ]) (host "erebus" true [ erebusToken ]) ];
  };
in
expect "happy path must be clean" happy (happy == [ ])
++ expect "same sops file on two hosts must be caught" sameFile
  (lib.any (m: lib.hasInfix "wired on serenity and erebus" m) sameFile)
++ expect "non-whitelisted host must be caught" rogueHost
  (lib.any (m: lib.hasInfix "not in telegramHosts" m) rogueHost)
++ expect "silent whitelisted host must be caught" silentHost
  (lib.any (m: lib.hasInfix "no TELEGRAM_BOT_TOKEN is rendered" m) silentHost)
++ expect "two different files are a known blind spot" differentFiles (differentFiles == [ ])
