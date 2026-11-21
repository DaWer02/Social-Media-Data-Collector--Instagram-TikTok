"""Browser Automation comment collector for TikTok videos.

Uses Playwright to navigate to public TikTok videos (web video URLs or short vt.tiktok.com links),
intercepts TikTok's internal JSON comment API responses, parses rendered DOM comment blocks as
a fallback, expands reply threads, handles interactive human verification challenges (CAPTCHA slider),
and yields standardized CommentRecord objects adhering to privacy guidelines.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
import socket
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from src.collectors.base import (
    BaseCollector,
    CollectorError,
    CollectorValidationError,
    CommentRecord,
    CollectionResult,
    MediaUnavailableError,
    NetworkCollectorError,
)
from src.config import BROWSER_PROFILE_DIR
from src.logging_config import setup_logger
from src.privacy import sanitize_comment_text

logger = setup_logger("tiktok_collector")

RE_TIKTOK_URL = re.compile(
    r"(?:https?://)?(?:www\.)?tiktok\.com/@([\w.-]+)/video/(\d+)",
    re.IGNORECASE,
)
RE_TIKTOK_SHORT_URL = re.compile(
    r"(?:https?://)?(?:vt|vm)\.tiktok\.com/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)


def is_human_verification_required(page: Any) -> bool:
    """Detect if TikTok displays human verification (puzzle slider / CAPTCHA challenge)."""
    try:
        current_url = (getattr(page, "url", "") or "").lower()
        if "verify" in current_url or "captcha" in current_url:
            return True

        has_challenge = page.evaluate(
            """
            () => {
                const secSelectors = [
                    '#captcha_container',
                    '#captcha-verify-image',
                    '.captcha_verify_container',
                    '.secsdk-captcha-drag-icon',
                    '[id*="captcha"]',
                    '[class*="captcha"]',
                    'div[class*="VerifyContainer"]',
                    'div[class*="captcha-verify"]'
                ];
                for (const sel of secSelectors) {
                    const el = document.querySelector(sel);
                    if (el && (el.offsetWidth > 0 || el.offsetHeight > 0)) {
                        return true;
                    }
                }

                const text = document.body ? document.body.innerText : '';
                const cues = [
                    "Verifikasi untuk melanjutkan",
                    "Verify to continue",
                    "Seret penggeser",
                    "Drag the slider",
                    "Pilih 2 objek",
                    "Select 2 objects",
                    "Konfirmasi bahwa Anda bukan robot",
                    "Verify you are human",
                    "Teka-teki verifikasi",
                    "Geser untuk menyelesaikan"
                ];
                for (const cue of cues) {
                    if (text.includes(cue)) {
                        return true;
                    }
                }
                return false;
            }
            """
        )
        return has_challenge is True
    except Exception:
        return False


def wait_for_human_verification(
    page: Any,
    target_url: str = "",
    input_fn: Callable[[str], str] = input,
) -> bool:
    """Prompt user in terminal to solve human verification / CAPTCHA puzzle in the visible browser."""
    print("\n" + "=" * 64)
    print("       [VERIFIKASI MANUSIA / CEK HUMAN DIPERLUKAN]")
    print("=" * 64)
    print("TikTok menampilkan pemeriksaan keamanan (Verifikasi Manusia / CAPTCHA).")
    print("Jendela browser saat ini sedang terbuka di layar Anda.")
    print("")
    print("Instruksi:")
    print("1. Silakan selesaikan teka-teki penggeser (puzzle slider) di browser.")
    print("2. Pastikan halaman video TikTok sudah terbuka dan dapat diputar.")
    print("3. Setelah selesai, tekan tombol [ENTER] pada terminal ini untuk melanjutkan.")
    print("=" * 64)

    try:
        input_fn("\nTekan [ENTER] setelah Anda selesai verifikasi di jendela browser... ")
    except (KeyboardInterrupt, EOFError):
        logger.info("Pengguna membatalkan proses verifikasi.")
        return False

    time.sleep(2.0)
    if target_url:
        try:
            current_url = (getattr(page, "url", "") or "").lower()
            if "verify" in current_url or "captcha" in current_url:
                page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(2.0)
        except Exception:
            pass

    return True


def is_tiktok_login_required(page: Any) -> bool:
    """Detect if TikTok requires login to view video comments."""
    try:
        current_url = (getattr(page, "url", "") or "").lower()
        if "login" in current_url:
            return True

        has_barrier = page.evaluate(
            """
            () => {
                const text = document.body ? document.body.innerText : '';
                return text.includes("Masuk ke TikTok") ||
                       text.includes("Log in to TikTok") ||
                       text.includes("Log in to view comments") ||
                       text.includes("Masuk untuk melihat komentar");
            }
            """
        )
        return has_barrier is True
    except Exception:
        return False


def wait_for_tiktok_login(
    page: Any,
    target_url: str,
    input_fn: Callable[[str], str] = input,
    timeout_sec: int = 40,
) -> bool:
    """Prompt user in terminal to complete login in the opened browser window and resume."""
    print("\n" + "=" * 64)
    print("          [LOGIN TIKTOK DIPERLUKAN]")
    print("=" * 64)
    print("TikTok membatasi akses komentar untuk sesi tamu.")
    print("Jendela browser saat ini sedang terbuka di layar Anda.")
    print("")
    print("Instruksi:")
    print("1. Silakan login ke akun TikTok Anda di jendela browser yang terbuka.")
    print("2. Sesi login akan otomatis tersimpan di folder lokal (.browser_profile/)")
    print("   sehingga Anda TIDAK perlu login lagi di penarikan berikutnya.")
    print("3. Setelah berhasil login, tekan tombol [ENTER] di terminal.")
    print("=" * 64)

    try:
        input_fn("\nTekan [ENTER] setelah Anda selesai login di jendela browser... ")
    except (KeyboardInterrupt, EOFError):
        logger.info("Pengguna membatalkan proses login TikTok.")
        return False

    try:
        current_url = (getattr(page, "url", "") or "").lower()
        if "login" in current_url:
            page.goto(target_url, timeout=timeout_sec * 1000, wait_until="domcontentloaded")
            time.sleep(2.0)
    except Exception:
        pass

    return True


class TikTokBrowserCollector(BaseCollector):
    """Collects comments from TikTok videos via Playwright automation."""

    def __init__(
        self,
        headless: bool = False,
        timeout_ms: int = 40000,
        scroll_delay_sec: float = 1.8,
        max_scroll_attempts: int = 250,
        browser_profile_dir: Path | None = None,
        sync_playwright_factory: Any | None = None,
        input_fn: Callable[[str], str] = input,
        sanitize_mentions: bool = True,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.scroll_delay_sec = scroll_delay_sec
        self.max_scroll_attempts = max_scroll_attempts
        self.browser_profile_dir = browser_profile_dir or BROWSER_PROFILE_DIR
        self._sync_playwright_factory = sync_playwright_factory
        self.input_fn = input_fn
        self.sanitize_mentions = sanitize_mentions

    def resolve_media_id(self, target: str) -> str:
        """Extract or resolve the TikTok numeric video ID from URL or raw ID."""
        cleaned = target.strip()
        if cleaned.isdigit() and len(cleaned) >= 10:
            return cleaned

        match = RE_TIKTOK_URL.search(cleaned)
        if match:
            return match.group(2)

        short_match = RE_TIKTOK_SHORT_URL.search(cleaned)
        if short_match:
            # Short URL shortcode as fallback ID before redirect
            return short_match.group(1)

        if "tiktok.com" in cleaned.lower():
            # Fallback hash for complex URLs
            return hashlib.md5(cleaned.encode()).hexdigest()[:12]

        raise CollectorValidationError(
            f"URL atau ID TikTok tidak valid: '{target}'.",
            safe_action="Gunakan format https://www.tiktok.com/@user/video/123456789 atau https://vt.tiktok.com/xxxx/"
        )

    def validate_access(self, media_id: str) -> tuple[bool, str | None]:
        """Validate if the video identifier is well-formed."""
        if not media_id or len(media_id) < 5:
            return False, "Video ID TikTok terlalu pendek atau kosong."
        return True, None

    def collect_comments(
        self,
        target: str,
        limit: int = 300,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> CollectionResult:
        """Collect comments from a public TikTok video URL."""
        clean_url = target.strip().rstrip(".,;:!?)")
        media_id = self.resolve_media_id(clean_url)

        try:
            if self._sync_playwright_factory:
                pw_manager = self._sync_playwright_factory()
            else:
                from playwright.sync_api import sync_playwright
                pw_manager = sync_playwright()
        except ImportError as err:
            raise CollectorError(
                "Library Playwright belum terpasang. Jalankan 'pip install playwright && playwright install chromium'.",
                safe_action="Install dependensi Playwright."
            ) from err

        self.browser_profile_dir.mkdir(parents=True, exist_ok=True)
        collected_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        comments_dict: dict[str, CommentRecord] = {}
        seen_texts: set[str] = set()

        def add_comment(rec: CommentRecord) -> bool:
            if rec.comment_id in comments_dict:
                return False
            norm_t = rec.comment_text.strip().lower()
            if norm_t in seen_texts:
                return False
            seen_texts.add(norm_t)
            comments_dict[rec.comment_id] = rec
            idx = len(comments_dict)
            preview = rec.comment_text.replace("\n", " ")[:50]
            print(f"[INFO] + [{idx}/{limit}] {preview}")
            if progress_callback:
                progress_callback(idx, limit)
            return True

        with pw_manager as pw:
            context_kwargs: dict[str, Any] = {
                "headless": self.headless,
                "viewport": {"width": 1280, "height": 800},
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "locale": "id-ID",
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
            }

            if hasattr(pw.chromium, "launch_persistent_context"):
                context = pw.chromium.launch_persistent_context(
                    user_data_dir=str(self.browser_profile_dir),
                    **context_kwargs
                )
                page = context.pages[0] if context.pages else context.new_page()
                browser_or_ctx = context
            else:
                browser = pw.chromium.launch(
                    headless=self.headless,
                    args=context_kwargs.get("args")
                )
                context = browser.new_context(
                    viewport=context_kwargs["viewport"],
                    user_agent=context_kwargs["user_agent"],
                    locale=context_kwargs["locale"],
                )
                page = context.new_page()
                browser_or_ctx = browser

            # Network Interception for TikTok internal comment API
            def handle_response(response: Any) -> None:
                try:
                    url_resp = response.url.lower()
                    if "api/comment/list" in url_resp:
                        content_type = response.headers.get("content-type", "")
                        if "application/json" in content_type:
                            data = response.json()
                            items = data.get("comments") or []
                            for item in items:
                                cid = str(item.get("cid") or item.get("id") or "")
                                raw_t = str(item.get("text") or "").strip()
                                if not raw_t:
                                    continue
                                if not cid:
                                    cid = hashlib.md5(raw_t.encode("utf-8")).hexdigest()[:12]
                                
                                # Sanitize comment text to mask @mentions and PII
                                clean_t = sanitize_comment_text(raw_t) if self.sanitize_mentions else raw_t
                                
                                c_time = item.get("create_time")
                                ts_str = (
                                    datetime.datetime.fromtimestamp(c_time, tz=datetime.timezone.utc).isoformat()
                                    if c_time else ""
                                )
                                likes = item.get("digg_count") or 0
                                rec = CommentRecord(
                                    comment_id=f"tt_{cid}",
                                    media_id=media_id,
                                    username="",  # Strictly empty for privacy
                                    comment_text=clean_t,
                                    timestamp=ts_str,
                                    like_count=int(likes) if str(likes).isdigit() else 0,
                                    collected_at=collected_at,
                                    source_type="browser_tiktok",
                                )
                                add_comment(rec)
                                if len(comments_dict) >= limit:
                                    break
                except Exception:
                    pass

            page.on("response", handle_response)

            try:
                page.goto(clean_url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                time.sleep(3.0)

                # Update media_id from canonical redirected URL if available
                final_url = page.url or clean_url
                vid_match = re.search(r"/video/(\d+)", final_url)
                if vid_match:
                    media_id = vid_match.group(1)

                # Security check: CAPTCHA / Human verification
                if is_human_verification_required(page):
                    wait_for_human_verification(page, final_url, input_fn=self.input_fn)

                if is_tiktok_login_required(page):
                    wait_for_tiktok_login(page, final_url, input_fn=self.input_fn)

                # Dismiss TikTok guest modals / cookie overlays
                guest_close_selectors = [
                    'button[data-e2e="modal-close-inner-button"]',
                    'div[role="dialog"] button',
                    'button:has-text("Batal")',
                    'button:has-text("Lain Kali")',
                    'button:has-text("Not Now")',
                    '[aria-label="Close"]',
                ]
                for close_sel in guest_close_selectors:
                    try:
                        for el in page.query_selector_all(close_sel):
                            if el and el.is_visible():
                                el.click(timeout=1000)
                                time.sleep(0.5)
                    except Exception:
                        pass

                # Open comment section / drawer if not active
                try:
                    cmt_selectors = [
                        '[data-e2e="comment-icon"]',
                        '[data-e2e="feed-comment-icon"]',
                        'button[aria-label*="comment"]',
                        'button[aria-label*="komentar"]',
                        'span[data-e2e="comment-icon"]',
                    ]
                    for sel in cmt_selectors:
                        icon = page.locator(sel).first
                        if hasattr(icon, "count") and icon.count() > 0 and icon.is_visible():
                            icon.click(timeout=1500)
                            time.sleep(1.0)
                            break
                except Exception:
                    pass

                # Scroll & extract loop
                scroll_count = 0
                idle_scrolls = 0

                while len(comments_dict) < limit and scroll_count < self.max_scroll_attempts:
                    scroll_count += 1
                    before_count = len(comments_dict)

                    # Complementary DOM extraction
                    raw_items = page.evaluate(
                        """
                        () => {
                            const items = [];
                            const containers = document.querySelectorAll(
                                '[data-e2e="comment-item"], div[class*="CommentItemContainer"], div[class*="DivCommentItemContainer"]'
                            );
                            containers.forEach(el => {
                                const textEl = el.querySelector('[data-e2e="comment-level-1"], p[data-e2e="comment-text"]');
                                const timeEl = el.querySelector('time, span[class*="Time"]');
                                const text = textEl ? (textEl.innerText || '').trim() : '';
                                const ts = timeEl ? (timeEl.innerText || '').trim() : '';
                                if (text.length > 0) {
                                    items.push({ text, timestamp: ts });
                                }
                            });
                            return items;
                        }
                        """
                    )
                    for item in raw_items or []:
                        raw_t = item.get("text", "").strip()
                        if not raw_t:
                            continue
                        clean_t = sanitize_comment_text(raw_t) if self.sanitize_mentions else raw_t
                        c_id = f"tt_dom_{hashlib.md5(clean_t.encode('utf-8')).hexdigest()[:12]}"
                        rec = CommentRecord(
                            comment_id=c_id,
                            media_id=media_id,
                            username="",  # Strictly empty for privacy
                            comment_text=clean_t,
                            timestamp=item.get("timestamp", ""),
                            like_count=0,
                            collected_at=collected_at,
                            source_type="browser_tiktok",
                        )
                        add_comment(rec)
                        if len(comments_dict) >= limit:
                            break

                    if len(comments_dict) >= limit:
                        break

                    # Check security challenge mid-scroll
                    if scroll_count <= 4 and len(comments_dict) == 0:
                        if is_human_verification_required(page):
                            wait_for_human_verification(page, final_url, input_fn=self.input_fn)
                        elif is_tiktok_login_required(page):
                            wait_for_tiktok_login(page, final_url, input_fn=self.input_fn)

                    # Expand replies
                    try:
                        reply_btns = page.locator(
                            '[data-e2e="view-more-replies"], [data-e2e="comment-reply-1"], '
                            'div[class*="DivReplyActionContainer"] button, '
                            'button:has-text("Lihat balasan"), button:has-text("View replies")'
                        )
                        r_count = reply_btns.count() if hasattr(reply_btns, "count") else 0
                        for r_idx in range(min(r_count, 6)):
                            btn = reply_btns.nth(r_idx)
                            if btn.is_visible():
                                btn.click(timeout=1000)
                                time.sleep(0.3)
                    except Exception:
                        pass

                    # Multi-strategy scroll
                    try:
                        page.evaluate(
                            """
                            () => {
                                const items = document.querySelectorAll(
                                    '[data-e2e="comment-item"], div[class*="CommentItemContainer"], div[class*="DivCommentItemContainer"]'
                                );
                                if (items.length > 0) {
                                    items[items.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
                                }
                                const anchor = document.querySelector('[data-e2e="comment-item"]') ||
                                               document.querySelector('[data-e2e="comment-list"]');
                                if (anchor) {
                                    let p = anchor.parentElement;
                                    while (p && p !== document.body) {
                                        const ov = window.getComputedStyle(p).overflowY;
                                        if ((ov === 'auto' || ov === 'scroll') && p.scrollHeight > p.clientHeight) {
                                            p.scrollTop += 900;
                                            break;
                                        }
                                        p = p.parentElement;
                                    }
                                }
                                window.scrollBy(0, 700);
                            }
                            """
                        )
                    except Exception:
                        pass

                    # Jitter sleep for polite rate limiting
                    time.sleep(self.scroll_delay_sec)

                    if len(comments_dict) == before_count:
                        idle_scrolls += 1
                        if idle_scrolls >= 10:
                            logger.info("Tidak ada komentar baru setelah 10 kali scroll berturut-turut. Mengakhiri penarikan.")
                            break
                    else:
                        idle_scrolls = 0

            except Exception as exc:
                logger.error(f"Kesalahan saat penarikan TikTok: {exc}")
            finally:
                try:
                    browser_or_ctx.close()
                except Exception:
                    pass

        comment_list = list(comments_dict.values())
        return CollectionResult(
            media_id=media_id,
            comments=comment_list,
            total_collected=len(comment_list),
            unique_collected=len(comment_list),
            status="completed" if len(comment_list) >= limit else "partial",
            raw_encountered=len(comment_list),
            filtered_out_count=0,
            coverage_reached=len(comment_list) >= limit,
        )
