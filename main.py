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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--status",
        action="store_true",
        help="Cek status fondasi repositori tanpa membuka menu interaktif",
    )
    mode.add_argument("--redam", action="store_true", help="Buka menu dataset REDAM.id langsung")
    args = parser.parse_args(argv)

    if args.redam:
        from src.redam.menu import run_menu
        return run_menu()
    return run_cli(non_interactive=args.status)


if __name__ == "__main__":
    sys.exit(main())
