#!/usr/bin/env python3
"""Host smoke test — run the live subset (network + real creds) against erebus.

Usage (on the host, venv with pytest available):
    ../nc-ocr-flow/.venv/bin/python smoke.py [-v]
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Use the python running this script (so a venv's pytest is picked up).
cmd = [
    sys.executable,
    "-m",
    "pytest",
    str(HERE),
    "-m",
    "live",
    "-v",
] + sys.argv[1:]

raise SystemExit(subprocess.call(cmd))
