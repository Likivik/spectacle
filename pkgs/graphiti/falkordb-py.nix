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
    sha256 = "sha256-sXVx6/TWXb01iOjEcLFvDd/qgg4KFe1zrw3RpHKLSA0=";
  };

  doCheck = false;

  pythonImportsCheck = [ "falkordb" ];

  meta = {
    description = "Python client for FalkorDB";
    license = lib.licenses.mit;
    homepage = "https://github.com/FalkorDB/falkordb-py";
  };
}