# `expression` (ExpressionPy) — pure-Python functional-programming lib that
# litellm 1.97.0 imports in its _experimental MCP outbound-credentials module
# (`from expression import case, tag, tagged_union`). nixpkgs does not package
# it, so the 1.89->1.97 bump shipped without this dep and litellm.service
# crashed at import time (`ModuleNotFoundError: No module named 'expression'`).
{
  lib,
  fetchurl,
  buildPythonPackage,
  typing-extensions,
}:

buildPythonPackage rec {
  pname = "expression";
  version = "5.7.0";

  # Pure-python wheel (no sdist `..` member risk); sha256 from PyPI JSON.
  format = "wheel";
  src = fetchurl {
    url = "https://files.pythonhosted.org/packages/07/9d/790e25dcba0b299f9a756ae2dcc52a705be07bd1c3fd54267ade0521bea6/expression-5.7.0-py3-none-any.whl";
    sha256 = "d8d903cb9ddcb252dbd64612e329bd86f09d770c7812eaf8f9cc0b9f8e6480bd";
  };

  propagatedBuildInputs = [ typing-extensions ];

  pythonImportsCheck = [ "expression" ];

  meta = with lib; {
    description = "Algebraic data types & discriminated unions for Python (Expr/F#-style)";
    homepage = "https://github.com/ExpressionPy/Expression";
    license = licenses.mit;
  };
}
