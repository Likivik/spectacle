"""CLI entry: nc-ocr-flow watch|ocr|serve"""
from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: nc-ocr-flow {watch|ocr FILE|serve}")
        return 1
    cmd = sys.argv[1]
    if cmd == "watch":
        from .watcher import main as watcher_main
        return watcher_main(sys.argv[2:])
    if cmd == "ocr":
        from .ocr import process_pdf
        from pathlib import Path
        if len(sys.argv) < 3:
            print("usage: nc-ocr-flow ocr FILE [OUTPUT]")
            return 1
        result = process_pdf(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
        print(f"output: {result.output_pdf}")
        print(f"vlm_pages: {result.vlm_pages}")
        return 0
    if cmd == "serve":
        from .surya_server import main as server_main
        return server_main()
    print(f"unknown command: {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
