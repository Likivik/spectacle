"""pytest conftest for pkgs/monkeyocr-server/tests.

Adds the package directory to sys.path so the bare `monkey_server` module can
be imported without installing anything, and forces LAZY model loading so pure
helper tests pass without torch/transformers/GPU.
"""
import os
import sys
from pathlib import Path

# Must be set BEFORE monkey_server is imported (tests import it at top).
os.environ.setdefault("MONKEY_LAZY_LOAD", "1")

_PKG = Path(__file__).resolve().parent.parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))