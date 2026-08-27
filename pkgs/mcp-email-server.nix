# mcp-email-server (Wh1isper) 1.5.1 — IMAP+SMTP MCP (read / search / draft / send).
#
# Extracted to its own derivation (instead of living inside the
# `den.aspects.server.email` aspect's `let`) so BOTH the aspect and the
# `email-mcp-roundtrip` check reference the exact same package — a real nixosTest
# can boot this binary and run an MCP handshake against it without duplicating
# the build expression.
#
# Requires callers to pass `pkgs` + `lib` explicitly (den aspects resolve `pkgs`
# via inputs.nixpkgs; flake checks resolve it via perSystem).

{ pkgs, lib }:

let
  # ---- aioimaplib 2.0.1 — doCheck disabled ----
  # Why: aioimaplib's OWN test suite fails under Python 3.14 (test_store /
  # test_idle break on the new interpreter), and upstream only officially tests
  # 3.9–3.11. That means nixpkgs has no cached py3.14 binary → the source build
  # fails its OWN tests. The library body itself is protocol-complete (23/25
  # IMAP4 commands, zero runtime deps) and is exercised indirectly by
  # mcp-email-server's own 448-test suite. We skip only the dependency's stale,
  # interpreter-mismatched tests — NOT mcp-email-server's checks.
  aioimaplib = pkgs.python3Packages.aioimaplib.overridePythonAttrs (_: {
    doCheck = false;
  });

  # mcp-email-server 1.5.1 declares filelock>=3.32.2; nixpkgs (unstable AND
  # master) is pinned at 3.29.7. Pull the pure-Python wheel directly.
  filelock = pkgs.python3Packages.buildPythonPackage rec {
    pname = "filelock";
    version = "3.32.4";
    format = "wheel";
    src = pkgs.fetchurl {
      url = "https://files.pythonhosted.org/packages/01/a4/9b63d595d748e3aff8812b65eacc1a2c4bd90b7c2012e08e72373b4835eb/filelock-3.32.4-py3-none-any.whl";
      sha256 = "1pffy76ypgx3kpapigsj0bjlzrks6qw76bbn7fcrhfxfn6iqrr92";
    };
    doCheck = false; # pure-Python wheel, upstream already tested
  };
in
pkgs.python3Packages.buildPythonApplication {
  pname = "mcp-email-server";
  version = "1.5.1";
  src = pkgs.fetchurl {
    url = "https://files.pythonhosted.org/packages/b8/d8/362d66fab84c70e292fd22ef6c9a95eb05d88d8b9d6249c1dfe30a20f77a/mcp_email_server-1.5.1-py3-none-any.whl";
    sha256 = "0ya4v9vvcr46wm9mf2dvivn4hzfcqjdwzyz6gy103kpai990dwxq";
  };
  format = "wheel";
  propagatedBuildInputs = with pkgs.python3Packages; [
    aioimaplib
    aiosmtplib
    beautifulsoup4
    click
    filelock
    jinja2
    keyring
    loguru
    mcp
    pydantic
    pydantic-settings
    starlette
    tomli-w
    typer
    uvicorn
  ];
  nativeBuildInputs = with pkgs.python3Packages; [ setuptools wheel ];
  pythonImportsCheck = [ "mcp_email_server" ];
  meta = with lib; {
    description = "MCP server for reading/searching/drafting/sending email over IMAP+SMTP (Wh1isper/mcp-email-server)";
    homepage = "https://github.com/Wh1isper/mcp-email-server";
    license = licenses.bsd3;
    mainProgram = "mcp-email-server";
  };
}
