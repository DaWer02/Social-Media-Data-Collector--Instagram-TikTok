"""Main entry point for Social Media Data Collector (Instagram & TikTok).

Privacy-first open-source comment harvester for linguistic research, NLP dataset
creation, and sentiment analysis.
"""

from __future__ import annotations

import argparse
import sys
from src.cli import handle_browser_login, handle_collect_comments, run_cli
from src.config import AppConfig


def main(argv: list[str] | None = None) -> int:
    """Parse command line arguments and execute collection or interactive CLI."""
    parser = argparse.ArgumentParser(
        description="Social Media Data Collector — Instagram & TikTok Comment Harvester"
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="URL postingan Instagram (/p/, /reel/) atau video TikTok (/video/, vt.tiktok.com)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Target jumlah komentar yang akan diambil (default: 300)",
    )
    parser.add_argument(
        "--format",
        choices=["both", "csv", "xlsx"],
        default="both",
        help="Format penyimpanan file output: both (CSV & Excel), csv, atau xlsx (default: both)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Jalankan browser tanpa antarmuka GUI (headless)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Cek status konfigurasi dan profil browser lokal tanpa membuka menu interaktif",
    )
    parser.add_argument(
        "--login-instagram",
        action="store_true",
        help="Buka browser langsung untuk login akun Instagram",
    )
    parser.add_argument(
        "--login-tiktok",
        action="store_true",
        help="Buka browser langsung untuk login akun TikTok",
    )

    args = parser.parse_args(argv)
    config = AppConfig.from_env()

    # Direct CLI action flags
    if args.login_instagram:
        handle_browser_login(platform="instagram")
        return 0

    if args.login_tiktok:
        handle_browser_login(platform="tiktok")
        return 0

    if args.status:
        return run_cli(config=config, non_interactive=True)

    if args.url:
        return handle_collect_comments(
            config=config,
            target_url_override=args.url,
            limit_override=args.limit,
            format_override=args.format,
            headless_override=args.headless,
        )

    # Interactive menu by default
    return run_cli(config=config)


if __name__ == "__main__":
    sys.exit(main())
