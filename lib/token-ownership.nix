# Pure fleet invariant: one bot token, one owner.
#
# Kept out of the module tree so it can be exercised with synthetic fixtures —
# the real check in modules/defaults/checks.nix is a thin wrapper that feeds it
# evaluated host config. Two hosts polling one token make Telegram answer 409
# and drop both (2026-11-24: erebus hijacked serenity's getUpdates queue, and
# Salem's bot was live on two hosts at once).
{ lib }:
{
  # hosts:         [ { host, rendersToken, tokenSecrets = [ { file, key } ]; } ]
  #                one entry per host, tokenSecrets = every sops secret whose
  #                name looks like a bot token.
  # telegramHosts: the whitelist, e.g. [ "serenity" ].
  #
  # Returns human-readable violations; empty list means the invariant holds.
  #
  # Known blind spot, on purpose: two DIFFERENT sops files holding the same
  # token are indistinguishable here — that needs the decrypted values, i.e. a
  # runtime audit.
  violations =
    { hosts, telegramHosts }:
    let
      tokenHosts = map (h: h.host) (builtins.filter (h: h.rendersToken) hosts);
      silent = builtins.filter (h: !(builtins.elem h tokenHosts)) telegramHosts;
      extra = builtins.filter (h: !(builtins.elem h telegramHosts)) tokenHosts;
      pairs = lib.concatMap
        (h: map (s: { inherit (h) host; inherit (s) file key; }) h.tokenSecrets)
        hosts;
      dupes = lib.filterAttrs (_: v: builtins.length v > 1)
        (lib.groupBy (p: "${p.file}:${p.key}") pairs);
    in
    lib.optional (silent != [ ])
      "telegramHosts lists ${lib.concatStringsSep ", " silent}, but no TELEGRAM_BOT_TOKEN is rendered there"
    ++ lib.optional (extra != [ ])
      "TELEGRAM_BOT_TOKEN is rendered by ${lib.concatStringsSep ", " extra}, which is not in telegramHosts"
    ++ lib.mapAttrsToList
      (pair: v: "bot-token secret ${pair} is wired on ${lib.concatStringsSep " and " (map (x: x.host) v)}")
      dupes;
}
