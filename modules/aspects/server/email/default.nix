{ den, inputs, lib, ... }:

let
  # den's aspect wrapper does not forward `pkgs` to module/nixos args,
  # so resolve it from the nixpkgs input directly (always present).
  pkgs = inputs.nixpkgs.legacyPackages.x86_64-linux;

  # TypeScript MCP wrapper around the Rust himalaya CLI (confirm-gated send,
  # drafts, attachments). Bundled with esbuild → single self-contained
  # dist/index.js, run as `node dist/index.js` over stdio.
  himalaya-mcp = import ../../../../pkgs/himalaya-mcp.nix { inherit pkgs lib; };

  # himalaya 2.1.0 — nixpkgs (unstable + master) still pins 2.0.0, which dies
  # mid-exchange with `Resource temporarily unavailable` (EAGAIN) on slow ops
  # (large-APPEND/slow-AUTH), himalaya #731/#732. 2.1.0 ships the
  # pimalaya-stream transport retry. Copy of the nixpkgs package pinned to 2.1.0.
  himalaya = pkgs.callPackage ../../../../pkgs/himalaya.nix { };

  # Static himalaya config — the Gmail app password is NOT embedded; it is
  # resolved at runtime by `password.command` (cat the sops-decrypted secret).
  # `mailbox.alias.*` maps Gmail's special-use folders (drafts is the exact
  # "[Gmail]/Drafts" the Wh1isper detour surfaced the hard way).
  himalayaConfig = pkgs.writeText "himalaya-config.toml" ''
    [accounts.default]
    default = true
    email = "kirilllipskii@gmail.com"
    display-name = "Кирилл Липский"

    imap.server = "imaps://imap.gmail.com:993"
    imap.sasl.plain.username = "kirilllipskii@gmail.com"
    imap.sasl.plain.password.command = ["cat", "/run/secrets/email/gmail/account1/app-password"]

    smtp.server = "smtps://smtp.gmail.com:465"
    smtp.sasl.plain.username = "kirilllipskii@gmail.com"
    smtp.sasl.plain.password.command = ["cat", "/run/secrets/email/gmail/account1/app-password"]

    mailbox.alias.inbox = "INBOX"
    mailbox.alias.sent = "[Gmail]/Sent Mail"
    mailbox.alias.drafts = "[Gmail]/Drafts"
    mailbox.alias.trash = "[Gmail]/Trash"
    mailbox.alias.archive = "[Gmail]/All Mail"
  '';

  mcpDir = "/var/lib/hermes/.hermes/mcp-servers/himalaya-mcp";
  cfgPath = "/var/lib/hermes/.config/himalaya/config.toml";
in
{
  # himalaya (Rust CLI, nixpkgs) + himalaya-mcp (TS wrapper) — NO systemd
  # service, NO port: Hermes spawns `node …/index.js` over stdio (same as the
  # existing trilium / npx MCP servers). himalaya runs as the `hermes` user and
  # reads its password from /run/secrets via `password.command`.
  den.aspects.server.email = {
    nixos = { config, lib, ... }: {
      environment.systemPackages = [ himalaya ];

      system.activationScripts.himalaya-email = lib.stringAfter [ "var" ] ''
        install -d -m 0755 -o hermes -g hermes ${mcpDir}
        install -m 0644 -o hermes -g hermes ${himalaya-mcp}/dist/index.js ${mcpDir}/index.js
        install -d -m 0755 -o hermes -g hermes /var/lib/hermes/.config/himalaya
        install -m 0600 -o hermes -g hermes ${himalayaConfig} ${cfgPath}
      '';
    };
  };
}
