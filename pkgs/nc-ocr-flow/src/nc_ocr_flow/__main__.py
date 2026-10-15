"""CLI entry: nc-ocr-flow ocr FILE [OUTPUT]."""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: nc-ocr-flow ocr FILE [OUTPUT]")
        return 1
    cmd = sys.argv[1]
    if cmd == "ocr":
        from .ocr import process_pdf
        if len(sys.argv) < 3:
            print("usage: nc-ocr-flow ocr FILE [OUTPUT]")
            return 1
        result = process_pdf(
            sys.argv[2],
            sys.argv[3] if len(sys.argv) > 3 else None,
        )
        print(f"output: {result.output_pdf}")
        print(f"engine: {result.engine_used}")
        print(f"vlm_pages: {result.vlm_pages}")
        return 0
    if cmd in ("watch", "serve"):
        # Both old subcommands were inotify/watch loops that have been
        # superseded by the webhook server (`python -m nc_ocr_flow.webhook_server`).
        # watcher.py was removed because it had no unit coverage and
        # nothing on this host ran it; ``serve`` was an even older
        # name that never landed in the shipped CLI.
        print(f"unknown command: {cmd} (the watcher was removed; run "
              "the webhook server with python -m nc_ocr_flow.webhook_server)")
        return 2
    print(f"unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())