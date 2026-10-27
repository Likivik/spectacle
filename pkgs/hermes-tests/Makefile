.PHONY: test test-live smoke bootstrap

# Interpreter for the local suite. This used to borrow ../nc-ocr-flow/.venv,
# which the OCR cutover deleted (the worker moved to github:Likivik/ocrflow).
# CI does not use this Makefile — checks.nix builds the suite with nix — so this
# is the developer path only: point PYTHON at any interpreter that has pytest
# and pytest_httpserver, or run `make bootstrap` once.
PYTHON ?= python3

bootstrap:
	$(PYTHON) -m venv .venv
	./.venv/bin/python -m pip install --upgrade pip
	./.venv/bin/python -m pip install pytest pytest_httpserver
	@echo "now run: make test PYTHON=./.venv/bin/python"

test:
	$(PYTHON) -m pytest -v

test-live:
	$(PYTHON) -m pytest -m live -v

smoke: test-live
