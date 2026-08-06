{ lib
, buildPythonPackage
, fetchFromGitHub
, graphiti-core   # our pinned package, satisfies ">=0.29.2" from upstream
, hatchling
, python
, mcp
, openai
, pydantic-settings
, pyyaml
, typing-extensions
}:

# graphiti-mcp-server — the FastMCP server sitting in front of graphiti-core.
# Same monorepo as graphiti-core (getzep/graphiti) but separate package.
# Pinned to commit 526dcad7 (HEAD on 2026-08-06) — keeps `>=0.29.2` core
# constraint; our graphiti-core package pins exactly 0.29.3 so it satisfies.
buildPythonPackage rec {
  pname = "graphiti-mcp-server";
  version = "1.0.2+526dcad";

  src = fetchFromGitHub {
    owner = "getzep";
    repo = "graphiti";
    rev = "526dcad7a300f3c5c506ff96a68bcdc7ca9f97ed";
    sha256 = lib.fakeHash;   # fill via first build + read-back
    fetchSubmodules = false;
  };

  # mcp_server/ has its own pyproject.toml — point hatchling at the subdir.
  sourceRoot = "source/mcp_server";

  pyproject = true;

  build-system = [ hatchling ];

  doCheck = false;   # requires neo4j/falkordb running

  propagatedBuildInputs = [
    graphiti-core
    mcp
    openai
    pydantic-settings
    pyyaml
    typing-extensions
  ];

  # Hook graphiti_mcp_server CLI entry point into the output bin dir.
  postInstall = ''
    # hatchling auto-discovers [project.scripts]; no manual link needed.
    # But verify it's there.
    test -f $out/bin/graphiti_mcp_server || \
      test -f $out/lib/python*/site-packages/graphiti_mcp_server-*.dist-info/entry_points.txt || \
      echo "graphiti_mcp_server entry point not found - check pyproject [project.scripts]"
  '';

  meta = with lib; {
    description = "Graphiti MCP Server (FastMCP wrapper around graphiti-core)";
    homepage = "https://help.getzep.com/graphiti/getting-started/mcp-server";
    license = licenses.asl20;
    platforms = platforms.linux;
  };
}