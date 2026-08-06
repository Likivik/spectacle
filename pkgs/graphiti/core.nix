{ lib
, buildPythonPackage
, fetchPypi
, hatchling
, pydantic
, neo4j
, openai
, tenacity
, numpy
, python-dotenv
, posthog
, falkordb-py
}:

buildPythonPackage rec {
  pname = "graphiti-core";
  version = "0.29.3";

  src = fetchPypi {
    inherit pname version;
    sha256 = "c3650626c0eb61c1ba2765ce6f08900abe68ec7f984f2e098b4922ebf5e81298";
  };

  # Edge-search perf fix — upstream PR #1500. Replaces per-row
  # MATCH (n:Entity)-[e:RELATES_TO {uuid: rel.uuid}]->(m:Entity)
  # in graphiti-core's fulltext search path. Without this patch,
  # add_memory / search queries time out on FalkorDB at our scale
  # (issue graphiti#1506).
  patches = [ ./patches/edge-search.patch ];

  pyproject = true;

  build-system = [ hatchling ];

  # Pinned exactly — graphiti-core's fulltext search is brittle
  # across versions and PR #1500 hasn't landed upstream yet.
  doCheck = false;

  propagatedBuildInputs = [
    pydantic
    neo4j
    openai
    tenacity
    numpy
    python-dotenv
    posthog
    falkordb   # [falkordb] extra: required for our driver
  ];

  meta = with lib; {
    description = "A temporal graph building library";
    homepage = "https://help.getzep.com/graphiti/graphiti/overview";
    license = licenses.asl20;
    platforms = platforms.linux;
  };
}