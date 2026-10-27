"""Main entry point for Instagram Slang NLP CLI."""

from __future__ import annotations

import argparse
import sys
from src.cli import run_cli


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and start the CLI application."""
    parser = argparse.ArgumentParser(
        description="Instagram Slang NLP Pipeline — Windows CLI"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Cek status fondasi repositori tanpa membuka menu interaktif",
    )
    args = parser.parse_args(argv)

    return run_cli(non_interactive=args.status)


if __name__ == "__main__":
    sys.exit(main())
