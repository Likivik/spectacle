{ pkgs, lib }:

# himalaya-mcp (Data-Wise) — TypeScript MCP wrapper around the Rust himalaya CLI.
# Exposes himalaya as MCP tools (read/draft/send w/ confirm=true gate) over stdio.
# Bundled with esbuild so the runtime artifact is a single self-contained
# dist/index.js — no node_modules at runtime, only `node dist/index.js`.
pkgs.buildNpmPackage rec {
  pname = "himalaya-mcp";
  version = "1.7.0";

  src = pkgs.fetchFromGitHub {
    owner = "Data-Wise";
    repo = "himalaya-mcp";
    rev = "v${version}";
    hash = "sha256-AlzRc4jIJOjAXdaT9tXVb00r+1b0ev9RozidLdJJ7d0=";
  };

  npmDepsHash = "sha256-28I0J1iNkiBKDAYsIB1bJ/NvM8Tq2sDwuwQF3kkNGVM=";

  buildPhase = ''
    runHook preBuild
    npm run build:bundle
    runHook postBuild
  '';

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/dist"
    cp dist/index.js "$out/dist/index.js"
    runHook postInstall
  '';

  meta = with lib; {
    description = "MCP server wrapping the himalaya CLI for privacy-first email (confirm-gated send, drafts, attachments)";
    homepage = "https://github.com/Data-Wise/himalaya-mcp";
    license = licenses.mit;
    mainProgram = "himalaya-mcp";
  };
}
