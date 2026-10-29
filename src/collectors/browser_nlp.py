"""Browser Automation and NLP-driven comment collector for Instagram posts.

Uses Playwright to navigate to arbitrary public Instagram posts in a visible
or headless browser, intercepts internal GraphQL JSON data, extracts and parses
rendered DOM text blocks using NLP, filters spam/noise in real time, and produces
standardized CommentRecord objects.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from src.collectors.base import (
    BaseCollector,
    CollectorError,
    CollectorValidationError,
    CommentRecord,
    CollectionResult,
    NetworkCollectorError,
)
from src.config import BROWSER_PROFILE_DIR
from src.extractors.nlp_comment_extractor import ExtractedComment, NLPCommentExtractor
from src.logging_config import setup_logger

logger = setup_logger("browser_nlp_collector")

# Specific patterns for Instagram URL structure and shortcode extraction
RE_IG_URL = re.compile(
    r"(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
RE_SHORT_PREFIX = re.compile(
    r"^(?:p|reel|tv)/([a-zA-Z0-9_-]+)/?$",
    re.IGNORECASE,
)
RE_RAW_SHORTCODE = re.compile(r"^[a-zA-Z0-9_-]{5,40}$")
RESERVED_SLUGS = frozenset({"explore", "accounts", "direct", "stories", "login", "reels", "about"})


class InstagramBrowserNLPCollector(BaseCollector):
    """Collects comments from any public Instagram URL via browser automation and NLP extraction."""

    def __init__(
        self,
        headless: bool = False,
        timeout_ms: int = 40000,
        scroll_delay_sec: float = 1.5,
        max_scroll_attempts: int = 250,
        extractor: NLPCommentExtractor | None = None,
        only_slang_candidates: bool = False,
        browser_profile_dir: Path | None = None,
        sync_playwright_factory: Any | None = None,
        input_fn: Callable[[str], str] = input,
    ) -> None:
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.scroll_delay_sec = scroll_delay_sec
        self.max_scroll_attempts = max_scroll_attempts
        self.extractor = extractor or NLPCommentExtractor()
        self.only_slang_candidates = only_slang_candidates
        self.browser_profile_dir = browser_profile_dir or BROWSER_PROFILE_DIR
        self._sync_playwright_factory = sync_playwright_factory
        self.input_fn = input_fn

    def is_login_required(self, page: Any) -> bool:
        """Check if Instagram is currently displaying a login barrier or login page."""
        try:
            current_url = page.url.lower() if hasattr(page, "url") and page.url else ""
            if "accounts/login" in current_url or "/login/" in current_url:
                return True

            has_barrier = page.evaluate(
                """
                () => {
                    const userField = document.querySelector('input[name="username"]');
                    const passField = document.querySelector('input[name="password"]');
                    if (userField && passField) return true;

                    const text = document.body ? document.body.innerText : '';
                    if (text.includes("Masuk untuk melihat") || 
                        text.includes("Log in to see") ||
                        text.includes("Masuk ke Instagram") ||
                        text.includes("Log in to Instagram")) {
                        return true;
                    }
                    return false;
                }
                """
            )
            return has_barrier is True
        except Exception:
            return False

    def wait_for_user_login(
        self,
        page: Any,
        post_url: str,
        input_fn: Callable[[str], str] | None = None,
    ) -> bool:
        """Prompt user in terminal to complete login in the opened browser window."""
        prompt_fn = input_fn or self.input_fn
        print("\n" + "=" * 64)
        print("          [LOGIN INSTAGRAM DIPERLUKAN]")
        print("=" * 64)
        print("Instagram membatasi akses komentar untuk akun yang belum masuk.")
        print("Jendela browser saat ini sedang terbuka di layar Anda.")
        print("")
        print("Instruksi:")
        print("1. Silakan login ke akun Instagram Anda di jendela browser yang terbuka.")
        print("2. Sesi login akan otomatis tersimpan di folder lokal (.browser_profile/)")
        print("   sehingga Anda TIDAK perlu login lagi di masa mendatang.")
        print("3. Setelah berhasil login dan halaman postingan terbuka kembali,")
        print("   tekan tombol ENTER pada terminal ini untuk melanjutkan.")
        print("=" * 64)

        try:
            prompt_fn("\nTekan [ENTER] setelah Anda selesai login di jendela browser... ")
        except (KeyboardInterrupt, EOFError):
            logger.info("Pengguna membatalkan proses login.")
            return False

        # Attempt to reload target post if still on login page
        try:
            current_url = page.url.lower() if hasattr(page, "url") and page.url else ""
            if "login" in current_url:
                logger.info("Memuat ulang halaman target postingan: %s", post_url)
                page.goto(post_url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                time.sleep(2.0)
        except Exception as e:
            logger.warning("Peringatan navigasi ulang target: %s", e)

        return True

    def open_interactive_login(
        self,
        input_fn: Callable[[str], str] | None = None,
    ) -> bool:
        """Open persistent browser directly to Instagram login page for session setup."""
        prompt_fn = input_fn or self.input_fn
        profile_path = self.browser_profile_dir or BROWSER_PROFILE_DIR
        profile_path.mkdir(parents=True, exist_ok=True)

        try:
            if self._sync_playwright_factory:
                pw_manager = self._sync_playwright_factory()
            else:
                from playwright.sync_api import sync_playwright
                pw_manager = sync_playwright()
        except ImportError as err:
            raise CollectorError(
                "Library 'playwright' belum terpasang. Jalankan 'pip install playwright' dan 'playwright install chromium'.",
                safe_action="pip install playwright && playwright install chromium",
            ) from err

        print("\n" + "=" * 64)
        print("       SETUP SESI LOGIN INSTAGRAM DI BROWSER")
        print("=" * 64)
        print("Membuka browser Chromium untuk login akun Instagram...")
        print(f"Folder sesi lokal : {profile_path}")
        print("Silakan login menggunakan akun Instagram Anda.")
        print("Setelah berhasil masuk ke beranda/feed Instagram,")
        print("kembali ke terminal ini dan tekan ENTER untuk menyimpan sesi.")
        print("=" * 64)

        try:
            with pw_manager as p:
                context_kwargs: dict[str, Any] = {
                    "headless": False,
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
                if hasattr(p.chromium, "launch_persistent_context"):
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_path),
                        **context_kwargs,
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    browser_or_context = context
                else:
                    browser = p.chromium.launch(headless=False)
                    context = browser.new_context()
                    page = context.new_page()
                    browser_or_context = browser

                page.goto("https://www.instagram.com/accounts/login/", timeout=self.timeout_ms)
                time.sleep(2.0)

                prompt_fn("\nTekan [ENTER] jika Anda sudah selesai login di browser... ")

                browser_or_context.close()
                print("\n[SUKSES] Sesi login tersimpan! Anda sekarang siap mengambil komentar.")
                return True
        except (KeyboardInterrupt, EOFError):
            print("\n[INFO] Setup login dibatalkan oleh pengguna.")
            return False
        except Exception as e:
            logger.error("Gagal melakukan setup login: %s", e)
            print(f"\n[ERROR] Terjadi kesalahan: {e}")
            return False

    def resolve_media_id(self, target: str) -> str:
        """Resolve a public Instagram URL or shortcode to a clean media identifier.

        Examples:
            'https://www.instagram.com/p/DFxyz123/' -> 'DFxyz123'
            'https://www.instagram.com/reel/C_abc456/' -> 'C_abc456'
            'DFxyz123' -> 'DFxyz123'
        """
        if not target or not target.strip():
            raise CollectorValidationError("Input URL atau ID postingan tidak boleh kosong.")

        clean_target = target.strip()

        # 1. Full Instagram URL match
        url_match = RE_IG_URL.search(clean_target)
        if url_match:
            shortcode = url_match.group(1)
            if shortcode.lower() in RESERVED_SLUGS:
                raise CollectorValidationError(
                    f"URL '{clean_target}' bukan tautan postingan Instagram yang valid."
                )
            return shortcode

        # 2. Prefixed shortcode (p/XYZ or reel/XYZ)
        prefixed_match = RE_SHORT_PREFIX.match(clean_target)
        if prefixed_match:
            return prefixed_match.group(1)

        # 3. Direct alphanumeric shortcode or numeric Media ID
        if RE_RAW_SHORTCODE.match(clean_target):
            if clean_target.lower() in RESERVED_SLUGS:
                raise CollectorValidationError(
                    f"'{clean_target}' adalah slug sistem, bukan postingan Instagram yang valid."
                )
            return clean_target

        raise CollectorValidationError(
            f"Format URL atau shortcode Instagram '{clean_target}' tidak valid."
        )

    def validate_access(self, media_id: str) -> tuple[bool, str | None]:
        """Validate whether the target post is accessible for browser automation.

        For browser-based public web extraction, access is valid if media_id is non-empty
        and conforms to standard shortcode format.
        """
        if not media_id or not media_id.strip():
            return False, "Media ID atau shortcode Instagram kosong."
        return True, None

    def _parse_graphql_comment_node(
        self,
        node: dict[str, Any],
        media_id: str,
        collected_at: str,
    ) -> CommentRecord | None:
        """Parse an intercepted GraphQL comment node dictionary into a CommentRecord."""
        raw_text = node.get("text", "")
        if not raw_text:
            return None

        eval_res = self.extractor.evaluate_comment(
            raw_text=raw_text,
            comment_text=raw_text,
            author=node.get("user", {}).get("username", "") or node.get("owner", {}).get("username", ""),
            timestamp_raw=str(node.get("created_at", "")),
            like_count=node.get("comment_like_count", 0) or node.get("like_count", 0),
        )

        if not eval_res.is_valid:
            return None

        if self.only_slang_candidates and not eval_res.has_slang_candidate:
            return None

        cid = str(node.get("id") or node.get("pk") or "")
        if not cid:
            cid = f"ig_{hashlib.md5(eval_res.clean_text.encode('utf-8')).hexdigest()[:12]}"

        return CommentRecord(
            comment_id=cid,
            media_id=media_id,
            username=eval_res.author,
            comment_text=eval_res.clean_text,
            timestamp=eval_res.timestamp_raw,
            like_count=eval_res.like_count,
            collected_at=collected_at,
            source_type="browser_nlp",
        )

    def _extract_comments_from_network_payload(
        self,
        payload: dict[str, Any],
        media_id: str,
        collected_at: str,
    ) -> list[CommentRecord]:
        """Recursively scan JSON network response for comment items."""
        found: list[CommentRecord] = []

        def recurse(data: Any) -> None:
            if isinstance(data, dict):
                # Check for standard Instagram comment object signatures
                if ("text" in data and ("user" in data or "owner" in data or "comment_like_count" in data)):
                    rec = self._parse_graphql_comment_node(data, media_id, collected_at)
                    if rec:
                        found.append(rec)
                for val in data.values():
                    recurse(val)
            elif isinstance(data, list):
                for item in data:
                    recurse(item)

        recurse(payload)
        return found

    def collect_comments(
        self,
        target: str,
        limit: int = 3000,
        run_id: str | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> CollectionResult:
        """Open browser, navigate to post, scroll & extract comments using NLP."""
        shortcode = self.resolve_media_id(target)
        url = f"https://www.instagram.com/p/{shortcode}/"
        collected_at = datetime.datetime.now().isoformat()

        logger.info("Memulai Browser NLP Collector untuk media %s (URL: %s)", shortcode, url)

        # Import playwright lazily or use factory
        try:
            if self._sync_playwright_factory:
                pw_manager = self._sync_playwright_factory()
            else:
                from playwright.sync_api import sync_playwright
                pw_manager = sync_playwright()
        except ImportError as err:
            raise CollectorError(
                "Library 'playwright' belum terpasang. Jalankan 'pip install playwright' dan 'playwright install chromium'.",
                safe_action="pip install playwright && playwright install chromium",
            ) from err

        comments_dict: dict[str, CommentRecord] = {}
        seen_texts: set[str] = set()

        def add_comment(rec: CommentRecord) -> bool:
            text_key = rec.comment_text.strip().lower()
            if text_key in seen_texts:
                return False
            if rec.comment_id in comments_dict:
                return False
            seen_texts.add(text_key)
            comments_dict[rec.comment_id] = rec

            curr_count = len(comments_dict)
            user_tag = f"@{rec.username}: " if rec.username else ""
            preview = rec.comment_text.replace("\n", " ").strip()
            if len(preview) > 50:
                preview = preview[:47] + "..."
            print(f"[INFO] + [{curr_count}/{limit}] {user_tag}{preview}")

            if progress_callback:
                progress_callback(curr_count, limit)
            return True

        # Network response handler to intercept GraphQL JSON
        def handle_response(response: Any) -> None:
            try:
                url_resp = response.url.lower()
                if (
                    "comments" in url_resp
                    or "graphql/query" in url_resp
                    or "xdt_api__v1__media" in url_resp
                ):
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            body = response.json()
                            extracted = self._extract_comments_from_network_payload(
                                body, shortcode, collected_at
                            )
                            for rec in extracted:
                                add_comment(rec)
                                if len(comments_dict) >= limit:
                                    break
                        except Exception:
                            pass
            except Exception:
                pass

        try:
            with pw_manager as p:
                profile_path = self.browser_profile_dir or BROWSER_PROFILE_DIR
                profile_path.mkdir(parents=True, exist_ok=True)

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

                # Support persistent browser context if available
                if hasattr(p.chromium, "launch_persistent_context"):
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=str(profile_path),
                        **context_kwargs,
                    )
                    page = context.pages[0] if context.pages else context.new_page()
                    browser_or_context = context
                else:
                    browser = p.chromium.launch(headless=self.headless)
                    context = browser.new_context(
                        viewport=context_kwargs["viewport"],
                        user_agent=context_kwargs["user_agent"],
                        locale=context_kwargs["locale"],
                    )
                    page = context.new_page()
                    browser_or_context = browser

                page.on("response", handle_response)

                logger.info("Membuka browser dan menuju ke URL: %s", url)
                try:
                    page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                except Exception as nav_err:
                    raise NetworkCollectorError(
                        f"Gagal memuat halaman Instagram: {nav_err}",
                        safe_action="Periksa koneksi internet atau verifikasi URL postingan.",
                    ) from nav_err

                time.sleep(2.0)

                # Check if login barrier / wall is present
                if self.is_login_required(page):
                    logger.info("Terdeteksi login wall / halaman login Instagram.")
                    self.wait_for_user_login(page=page, post_url=url, input_fn=self.input_fn)

                # Attempt to close login modal / cookie banner if present
                self._dismiss_modals(page)

                consecutive_idle_scrolls = 0
                max_idle = 10
                scroll_count = 0

                while len(comments_dict) < limit and scroll_count < self.max_scroll_attempts:
                    scroll_count += 1
                    initial_count = len(comments_dict)

                    # 1. Fallback / Complementary: Extract from rendered DOM text blocks
                    self._extract_from_page_dom(page, shortcode, collected_at, add_comment, limit)

                    if len(comments_dict) >= limit:
                        break

                    # 2. Expand collapsed reply threads ('Lihat balasan (X)')
                    self._expand_reply_threads(page)

                    # 3. Click "Load more comments" or "+" button if visible inside article
                    self._click_load_more_buttons(page)

                    # 3. Dynamic scroll down targeted specifically at comments container inside article
                    try:
                        page.evaluate(
                            """
                            () => {
                                // 1. Keep main window locked to top of post (prevent drift to bottom grid)
                                window.scrollTo(0, 0);

                                const article = document.querySelector('article') || document.body;

                                // 2. Find and scroll any inner scrollable element inside article
                                const allElements = article.querySelectorAll('*');
                                for (const el of allElements) {
                                    const style = window.getComputedStyle(el);
                                    const oy = style.overflowY;
                                    if ((oy === 'auto' || oy === 'scroll') && el.scrollHeight > el.clientHeight) {
                                        el.scrollTop = el.scrollHeight;
                                        el.scrollBy(0, 600);
                                        break;
                                    }
                                }

                                // 3. Smooth scroll last comment into view
                                const items = article.querySelectorAll('ul li, ul > div');
                                if (items.length > 0) {
                                    items[items.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
                                }
                            }
                            """
                        )
                        # Also dispatch mouse wheel over comment column
                        comment_col = page.locator("article ul, article div[style*='overflow']").first
                        if hasattr(comment_col, "count") and comment_col.count() > 0:
                            comment_col.hover(timeout=1000)
                            page.mouse.wheel(0, 600)
                    except Exception:
                        pass

                    time.sleep(self.scroll_delay_sec)

                    if len(comments_dict) == initial_count:
                        consecutive_idle_scrolls += 1
                        if consecutive_idle_scrolls >= max_idle:
                            logger.info(
                                "Tidak ada komentar baru setelah %d kali scroll. Pengambilan selesai.",
                                max_idle,
                            )
                            break
                    else:
                        consecutive_idle_scrolls = 0

                browser_or_context.close()

        except KeyboardInterrupt:
            logger.info("Pengambilan dihentikan manual oleh pengguna. Menyimpan data yang sudah ditarik...")
        except Exception as e:
            if isinstance(e, (CollectorError, CollectorValidationError, NetworkCollectorError)):
                raise
            logger.error("Terjadi kesalahan tak terduga selama browser automation: %s", e)
            raise CollectorError(
                f"Browser automation terhenti: {e}",
                safe_action="Pastikan Chromium terpasang dan jendela browser tidak ditutup paksa.",
            ) from e

        all_comments = list(comments_dict.values())
        return CollectionResult(
            media_id=shortcode,
            comments=all_comments,
            total_collected=len(all_comments),
            unique_collected=len(all_comments),
            status="completed" if all_comments else "empty",
            paging_completed=(len(all_comments) < limit),
        )

    def _dismiss_modals(self, page: Any) -> None:
        """Dismiss common cookie popups and login dialog banners if present."""
        try:
            # Common close button selectors for Instagram popups
            close_selectors = [
                'svg[aria-label="Tutup"]',
                'svg[aria-label="Close"]',
                'button:has-text("Batal")',
                'button:has-text("Lain Kali")',
                'button:has-text("Not Now")',
                'button:has-text("Decline optional cookies")',
                'button:has-text("Hanya izinkan cookie penting")',
            ]
            for sel in close_selectors:
                elements = page.query_selector_all(sel)
                for el in elements:
                    try:
                        if el.is_visible():
                            el.click(timeout=1000)
                            time.sleep(0.5)
                    except Exception:
                        pass
        except Exception:
            pass

    def _expand_reply_threads(self, page: Any) -> int:
        """Find and click collapsed reply dropdown buttons inside post article.

        Matches buttons like 'Lihat balasan (3)', 'Lihat 5 balasan', 'View replies (2)',
        'View 3 more replies', 'Lihat balasan', etc.
        """
        try:
            expanded_count: int = page.evaluate(
                r"""
                () => {
                    let clicked = 0;
                    const article = document.querySelector('article') || document.body;
                    const candidates = article.querySelectorAll('button, div[role="button"], span[role="button"]');
                    
                    const replyRegex = /(?:lihat|view)\s+(?:\d+\s+)?(?:balasan|replies)|(?:lihat|view)\s+\d+\s+lagi/i;

                    candidates.forEach(btn => {
                        const txt = (btn.innerText || '').trim();
                        if (replyRegex.test(txt)) {
                            try {
                                btn.click();
                                clicked++;
                            } catch (e) {}
                        }
                    });
                    return clicked;
                }
                """
            )
            if expanded_count and expanded_count > 0:
                logger.debug("Memperluas %d dropdown balasan komentar.", expanded_count)
                time.sleep(1.0)
            return expanded_count or 0
        except Exception:
            return 0

    def _click_load_more_buttons(self, page: Any) -> None:
        """Find and click 'Load more comments' or '+' icon buttons inside post article."""
        try:
            # Query inside article to prevent clicking recommendations or footer elements
            more_selectors = [
                'article svg[aria-label="Muat komentar lainnya"]',
                'article svg[aria-label="Load more comments"]',
                'article button:has-text("Lihat komentar lainnya")',
                'article button:has-text("Load more comments")',
                'article button:has-text("Muat komentar lainnya")',
                'article span:has-text("Lihat komentar lainnya")',
                'article span:has-text("Muat komentar lainnya")',
                'article div[role="button"]:has-text("Lihat komentar lainnya")',
                'article div[role="button"]:has-text("Muat komentar lainnya")',
            ]
            for sel in more_selectors:
                elements = page.query_selector_all(sel)
                for b in elements:
                    try:
                        if b.is_visible():
                            b.click(timeout=1000)
                            time.sleep(0.8)
                    except Exception:
                        pass
        except Exception:
            pass

    def _extract_from_page_dom(
        self,
        page: Any,
        media_id: str,
        collected_at: str,
        add_fn: Callable[[CommentRecord], bool],
        limit: int,
    ) -> None:
        """Extract comment text blocks from rendered DOM inside post article using multi-tier semantic anchors."""
        try:
            raw_blocks: list[str] = page.evaluate(
                """
                () => {
                    const blocks = [];
                    const seen = new Set();
                    const article = document.querySelector('article') || document.body;

                    function addBlock(txt) {
                        if (!txt) return;
                        const clean = txt.trim();
                        // Ignore full page blocks or tiny button labels
                        if (clean.length > 5 && clean.length < 2500 && !seen.has(clean)) {
                            seen.add(clean);
                            blocks.push(clean);
                        }
                    }

                    // TIER 1: Semantic Time Anchors (Every comment on Instagram has a <time> element)
                    const timeElements = article.querySelectorAll('time');
                    timeElements.forEach(t => {
                        let curr = t.parentElement;
                        for (let depth = 0; depth < 6 && curr && curr !== article; depth++) {
                            const hasAuthor = curr.querySelector('h2 a, h3 a, a[role="link"], a[href^="/"]');
                            const timeCount = curr.querySelectorAll('time').length;
                            if (hasAuthor && timeCount === 1) {
                                const txt = curr.innerText;
                                if (txt && txt.length > 5 && txt.length < 2000) {
                                    addBlock(txt);
                                    break;
                                }
                            }
                            curr = curr.parentElement;
                        }
                    });

                    // TIER 2: Semantic Action Anchors (Buttons with 'Balas' or 'Reply')
                    const allButtons = article.querySelectorAll('button, div[role="button"], span[role="button"]');
                    allButtons.forEach(btn => {
                        const bText = (btn.innerText || '').trim().toLowerCase();
                        if (bText === 'balas' || bText === 'reply') {
                            let curr = btn.parentElement;
                            for (let depth = 0; depth < 6 && curr && curr !== article; depth++) {
                                const hasAuthor = curr.querySelector('a[href^="/"]');
                                const replyBtns = Array.from(curr.querySelectorAll('button, div[role="button"]'))
                                    .filter(b => ['balas', 'reply'].includes((b.innerText || '').trim().toLowerCase()));
                                if (hasAuthor && replyBtns.length === 1) {
                                    addBlock(curr.innerText);
                                    break;
                                }
                                curr = curr.parentElement;
                            }
                        }
                    });

                    // TIER 3: Universal structural list/div items inside article (fallback)
                    const structuralItems = article.querySelectorAll(
                        'ul li, ul > div, div[role="listitem"], div[tabindex="0"]'
                    );
                    structuralItems.forEach(item => {
                        if (item.querySelector('a[href^="/"]')) {
                            addBlock(item.innerText);
                        }
                    });

                    return blocks;
                }
                """
            )

            if not raw_blocks:
                return

            for block in raw_blocks:
                extracted: ExtractedComment = self.extractor.extract_from_dom_text_block(block)
                if not extracted.is_valid:
                    continue

                if self.only_slang_candidates and not extracted.has_slang_candidate:
                    continue

                cid = f"dom_{hashlib.md5(extracted.clean_text.encode('utf-8')).hexdigest()[:12]}"
                rec = CommentRecord(
                    comment_id=cid,
                    media_id=media_id,
                    username=extracted.author,
                    comment_text=extracted.clean_text,
                    timestamp=extracted.timestamp_raw or "",
                    like_count=extracted.like_count,
                    collected_at=collected_at,
                    source_type="browser_nlp",
                )
                add_fn(rec)
        except Exception as err:
            logger.debug("Peringatan ekstraksi DOM: %s", err)
