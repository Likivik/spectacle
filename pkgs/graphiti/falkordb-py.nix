{
  buildPythonPackage,
  fetchPypi,
  lib,
}:

buildPythonPackage rec {
  pname = "falkordb";
  version = "1.6.2";

  pyproject = true;

  src = fetchPypi {
    inherit pname version;
    sha256 = "sha256-c9u9nfYcVvRc8v6LkCiIitSJJxJ5DOTkDXzqvhGGCa4=";
  };

  hatchling, python-dateutil, redis;

  build-system = [ hatchling ];

  propagatedBuildInputs = [ python-dateutil redis ];

  doCheck = false;

  pythonImportsCheck = [ "falkordb" ];

  meta = {
    description = "Python client for FalkorDB";
    license = lib.licenses.mit;
    homepage = "https://github.com/FalkorDB/falkordb-py";
  };
}