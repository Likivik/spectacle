{
  buildPythonPackage,
  fetchPypi,
  lib,
}:

buildPythonPackage rec {
  pname = "falkordb";
  version = "1.6.2";

  format = "setuptools";

  src = fetchPypi {
    inherit pname version;
    sha256 = "sha256-b17571ebf4d65dbd3588e8c470b16f0ddfea820e0a15ed73af0dd1a4728b480d";
  };

  doCheck = false;

  pythonImportsCheck = [ "falkordb" ];

  meta = {
    description = "Python client for FalkorDB";
    license = lib.licenses.mit;
    homepage = "https://github.com/FalkorDB/falkordb-py";
  };
}