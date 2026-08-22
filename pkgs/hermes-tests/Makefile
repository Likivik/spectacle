.PHONY: test test-live smoke

# Reuses the nc-ocr-flow venv (python3.14 + pytest + pytest_httpserver).
# A dedicated devShell/venv can replace this later via flake wiring.
VENV := ../nc-ocr-flow/.venv

test:
	$(VENV)/bin/python -m pytest -v

test-live:
	$(VENV)/bin/python -m pytest -m live -v

smoke: test-live
