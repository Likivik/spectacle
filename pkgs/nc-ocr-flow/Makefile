.PHONY: test test-slow lint

# On NixOS, PyMuPDF needs libstdc++ which isn't in the default linker path
LIBSTDCPP := $(shell nix eval nixpkgs#gcc.cc.lib --raw 2>/dev/null)/lib
export LD_LIBRARY_PATH := $(LIBSTDCPP):$(LD_LIBRARY_PATH)

test:
	.venv/bin/python -m pytest tests/ -v

test-slow:
	.venv/bin/python -m pytest tests/ -v --runslow

lint:
	.venv/bin/python -m pyflakes src/nc_ocr_flow/ tests/ 2>/dev/null || true
