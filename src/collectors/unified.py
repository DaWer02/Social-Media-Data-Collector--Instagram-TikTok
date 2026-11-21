"""Unified Social Media Comment Collector for Instagram & TikTok.

Provides platform auto-detection, standardized routing, and strict privacy enforcement
(username omission, @mention masking, and zero-PII storage).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

from src.collectors.base import (
    BaseCollector,
    CollectorError,
    CollectorValidationError,
    CommentRecord,
    CollectionResult,
)
from src.collectors.browser_nlp import InstagramBrowserNLPCollector
from src.collectors.tiktok import TikTokBrowserCollector
from src.config import BROWSER_PROFILE_DIR
from src.logging_config import setup_logger
from src.privacy import sanitize_comment_text

logger = setup_logger("unified_collector")


def extract_clean_url(text: str) -> str:
    """Extract clean HTTP/HTTPS URL from pasted text string (e.g. share captions)."""
    if not text:
        return ""
    match = re.search(r"https?://[^\s'\"<>]+", text.strip())
    if match:
        url = match.group(0)
        return url.rstrip(".,;:!?)")
    return text.strip()


def detect_platform(url_or_target: str) -> str:
    """Detect whether a URL belongs to Instagram or TikTok.

    Args:
        url_or_target: Input URL or post link.

    Returns:
        str: "instagram" or "tiktok"

    Raises:
        CollectorValidationError: If URL does not match supported platforms.
    """
    clean_target = extract_clean_url(url_or_target).lower()

    if "instagram.com" in clean_target or re.search(r"^(?:p|reel|tv)/", clean_target):
        return "instagram"

    if "tiktok.com" in clean_target:
        return "tiktok"

    raise CollectorValidationError(
        f"URL tidak dikenali atau bukan dari Instagram / TikTok: '{url_or_target}'.",
        safe_action=(
            "Pastikan URL diawali https://www.instagram.com/... atau https://www.tiktok.com/..."
        ),
    )


def collect_social_comments(
    target_url: str,
    limit: int = 300,
    headless: bool = False,
    browser_profile_dir: Path | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    input_fn: Callable[[str], str] = input,
    sync_playwright_factory: Any | None = None,
    sanitize_mentions: bool = True,
) -> tuple[CollectionResult, str]:
    """Collect comments from Instagram or TikTok with unified auto-detection & privacy masking.

    Args:
        target_url: Target post or video URL.
        limit: Target number of comments to collect.
        headless: Run browser in headless mode (default: False for interactive verification).
        browser_profile_dir: Directory where persistent browser profile is stored.
        progress_callback: Callback receiving (current_count, target_count).
        input_fn: Input function for terminal prompts.
        sync_playwright_factory: Optional Playwright factory (for testing/mocking).
        sanitize_mentions: Whether to replace @mentions with [@USER] (default True).

    Returns:
        tuple[CollectionResult, str]: Collection result and detected platform string.
    """
    clean_url = extract_clean_url(target_url)
    platform = detect_platform(clean_url)
    profile_dir = browser_profile_dir or BROWSER_PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Memulai pengumpulan komentar [{platform.upper()}] dari: {clean_url}")

    if platform == "instagram":
        collector = InstagramBrowserNLPCollector(
            headless=headless,
            browser_profile_dir=profile_dir,
            sync_playwright_factory=sync_playwright_factory,
            input_fn=input_fn,
        )
        res = collector.collect_comments(
            target=clean_url,
            limit=limit,
            progress_callback=progress_callback,
        )
    else:
        collector = TikTokBrowserCollector(
            headless=headless,
            browser_profile_dir=profile_dir,
            sync_playwright_factory=sync_playwright_factory,
            input_fn=input_fn,
            sanitize_mentions=sanitize_mentions,
        )
        res = collector.collect_comments(
            target=clean_url,
            limit=limit,
            progress_callback=progress_callback,
        )

    # Privacy Enforcement Guarantee: Strip usernames and sanitize text
    anonymized_comments: list[CommentRecord] = []
    for c in res.comments:
        sanitized_text = sanitize_comment_text(c.comment_text) if sanitize_mentions else c.comment_text
        anonymized_record = CommentRecord(
            comment_id=c.comment_id,
            media_id=c.media_id,
            username="",  # Strictly omit username for privacy
            comment_text=sanitized_text,
            timestamp=c.timestamp,
            like_count=c.like_count,
            collected_at=c.collected_at,
            source_type=platform,  # "instagram" or "tiktok"
        )
        anonymized_comments.append(anonymized_record)

    sanitized_result = CollectionResult(
        media_id=res.media_id,
        comments=anonymized_comments,
        total_collected=len(anonymized_comments),
        unique_collected=len(anonymized_comments),
        status=res.status,
        error_message=res.error_message,
        paging_completed=res.paging_completed,
        raw_encountered=res.raw_encountered,
        filtered_out_count=res.filtered_out_count,
        coverage_reached=res.coverage_reached,
    )

    return sanitized_result, platform


def open_login_session(
    platform: str,
    browser_profile_dir: Path | None = None,
    sync_playwright_factory: Any | None = None,
    input_fn: Callable[[str], str] = input,
) -> None:
    """Open a visible browser window so user can log in to Instagram or TikTok once."""
    profile_dir = browser_profile_dir or BROWSER_PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)

    if platform not in {"instagram", "tiktok"}:
        raise ValueError("Platform harus 'instagram' atau 'tiktok'.")

    target_url = (
        "https://www.instagram.com/accounts/login/"
        if platform == "instagram"
        else "https://www.tiktok.com/login"
    )

    print("\n" + "=" * 64)
    print(f"      MEMBUKA BROWSER UNTUK LOGIN {platform.upper()}")
    print("=" * 64)
    print(f"URL: {target_url}")
    print(f"Profil tersimpan di: {profile_dir}")
    print("\nLangkah:")
    print("1. Jendela browser akan terbuka di layar Anda.")
    print("2. Masuk ke akun Anda di browser.")
    print("3. Setelah berhasil masuk, kembali ke terminal ini dan tekan [ENTER].")
    print("=" * 64)

    try:
        if sync_playwright_factory:
            pw_manager = sync_playwright_factory()
        else:
            from playwright.sync_api import sync_playwright
            pw_manager = sync_playwright()
    except ImportError as err:
        raise RuntimeError("Playwright belum terpasang. Jalankan 'pip install playwright'.") from err

    with pw_manager as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 800},
            args=["--start-maximized"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(target_url, timeout=60000, wait_until="domcontentloaded")
            input_fn("\nTekan [ENTER] jika Anda sudah selesai login di browser... ")
        finally:
            try:
                context.close()
            except Exception:
                pass

    print(f"\n[SUKSES] Sesi login {platform.upper()} berhasil diperbarui dan tersimpan.")
