"""CLI entry point."""
from .watcher import main

main_entry = main  # expose for [project.scripts]


if __name__ == "__main__":
    raise SystemExit(main())
