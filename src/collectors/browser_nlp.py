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
        comment_tolerance: int = 10,
        match_reported_total: bool = True,
        max_recovery_sweeps: int = 3,
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
        self.comment_tolerance = max(0, int(comment_tolerance))
        self.match_reported_total = match_reported_total
        self.max_recovery_sweeps = max(0, int(max_recovery_sweeps))

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

    @staticmethod
    def parse_human_count(raw_text: str) -> tuple[int | None, bool]:
        """Parse localized Instagram counters into (count, is_exact).

        Supports Indonesian/English thousands separators ('1.135', '1,135' -> (1135, True))
        and compact unit abbreviations ('1,2 rb', '1.2K' -> (1200, False), '1,5 jt' -> (1500000, False)).
        """
        if not raw_text or not isinstance(raw_text, str):
            return None, False

        text = raw_text.strip()
        if not text:
            return None, False

        # 1. Abbreviated counts like '1,2 rb', '42,3 rb', '1.2K', '1,5 jt', '1.5M'
        unit_match = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(rb|ribu|k|jt|juta|m)\b",
            text,
            re.IGNORECASE,
        )
        if unit_match:
            num_str = unit_match.group(1)
            unit = unit_match.group(2).lower()
            mult = 1_000_000 if unit in {"jt", "juta", "m"} else 1_000
            if "." in num_str and "," in num_str:
                normalized = num_str.replace(".", "").replace(",", ".")
            elif re.match(r"^\d+[.,]\d{3}$", num_str):
                normalized = num_str.replace(".", "").replace(",", "")
            else:
                normalized = num_str.replace(",", ".")
            try:
                return int(round(float(normalized) * mult)), False
            except ValueError:
                return None, False

        # 2. Exact grouped integer like '1.135', '1,135', '12.345'
        grouped_match = re.search(r"\b(\d{1,3}(?:[.,]\d{3})+)\b", text)
        if grouped_match:
            digits = grouped_match.group(1).replace(".", "").replace(",", "")
            try:
                return int(digits), True
            except ValueError:
                return None, False

        # 3. Plain integer like '850'
        plain_match = re.search(r"\b(\d+)\b", text)
        if plain_match:
            try:
                return int(plain_match.group(1)), True
            except ValueError:
                return None, False

        return None, False

    _IGNORED_GRAPHQL_KEYS = frozenset({
        "xdt_api__v1__feed__timeline__connection",
        "explore_story",
    })

    @staticmethod
    def _is_foreign_media_dict(data: dict[str, Any], target_shortcode: str) -> bool:
        """Return True when a payload dict explicitly carries another post's shortcode."""
        obj_code = data.get("code") or data.get("shortcode")
        return isinstance(obj_code, str) and bool(obj_code.strip()) and obj_code.strip() != target_shortcode

    def _extract_comment_count_from_payload(self, payload: Any, shortcode: str) -> int | None:
        """Extract exact media comment_count from intercepted GraphQL/JSON payload."""
        found_counts: list[int] = []

        def recurse(data: Any) -> None:
            if isinstance(data, dict):
                if self._is_foreign_media_dict(data, shortcode):
                    return

                is_comment_node = "text" in data and ("user" in data or "owner" in data)
                matches_shortcode = str(data.get("code") or data.get("shortcode") or "") == shortcode
                is_media_root = (
                    not is_comment_node
                    and ("media_type" in data or "caption" in data or "edge_media_to_comment" in data or "edge_media_to_parent_comment" in data)
                )

                if matches_shortcode or is_media_root:
                    direct_cnt = data.get("comment_count")
                    if isinstance(direct_cnt, int) and not isinstance(direct_cnt, bool) and direct_cnt >= 0:
                        found_counts.append(direct_cnt)

                    for edge_key in (
                        "edge_media_to_parent_comment",
                        "edge_media_to_comment",
                        "edge_media_preview_comment",
                    ):
                        edge_obj = data.get(edge_key)
                        if isinstance(edge_obj, dict):
                            edge_cnt = edge_obj.get("count")
                            if isinstance(edge_cnt, int) and not isinstance(edge_cnt, bool) and edge_cnt >= 0:
                                found_counts.append(edge_cnt)

                for key, val in data.items():
                    if key in self._IGNORED_GRAPHQL_KEYS:
                        continue
                    recurse(val)
            elif isinstance(data, list):
                for item in data:
                    recurse(item)

        recurse(payload)
        return max(found_counts) if found_counts else None

    def _detect_reported_comment_count(self, page: Any) -> tuple[int | None, bool]:
        """Inspect rendered DOM counters and meta tags to detect total post comment count."""
        try:
            eval_res = page.evaluate(
                r"""
                () => {
                    const candidates = [];
                    const icons = document.querySelectorAll(
                        'svg[aria-label="Komentar"], svg[aria-label="Comment"], svg[aria-label="Comments"]'
                    );
                    for (const svg of icons) {
                        const btn = svg.closest('div[role="button"], button, a') || svg.parentElement;
                        if (!btn) continue;

                        const rawSources = [
                            btn.innerText || '',
                            btn.nextElementSibling ? (btn.nextElementSibling.innerText || '') : '',
                        ];
                        if (btn.parentElement && btn.parentElement.querySelectorAll('svg').length === 1) {
                            rawSources.push(btn.parentElement.innerText || '');
                        }
                        for (const raw of rawSources) {
                            const txt = raw.replace(/\s+/g, ' ').trim();
                            if (txt && txt.length <= 30 && /\d/.test(txt)) {
                                candidates.push(txt);
                            }
                        }
                    }

                    const labelNodes = document.querySelectorAll('a, span, button, div[role="button"]');
                    for (const el of labelNodes) {
                        const t = (el.innerText || '').replace(/\s+/g, ' ').trim();
                        if (
                            t.length > 5 &&
                            t.length <= 60 &&
                            /^(?:lihat\s+semua|view\s+all)\s+[\d.,]+\s*(?:rb|ribu|k|jt|juta|m)?\s+(?:komentar|comments?)$/i.test(t)
                        ) {
                            candidates.push(t);
                        }
                    }

                    const metas = document.querySelectorAll(
                        'meta[property="og:description"], meta[name="description"]'
                    );
                    const metaTexts = Array.from(metas)
                        .map(m => m.getAttribute('content') || '')
                        .filter(Boolean);

                    return { candidates, metaTexts };
                }
                """
            )
        except Exception:
            return None, False

        if not isinstance(eval_res, dict):
            return None, False

        best_exact: int | None = None
        best_approx: int | None = None

        for cand in eval_res.get("candidates") or []:
            if isinstance(cand, str):
                cnt, is_exact = self.parse_human_count(cand)
                if cnt is not None and cnt > 0:
                    if is_exact:
                        best_exact = max(best_exact, cnt) if best_exact is not None else cnt
                    else:
                        best_approx = max(best_approx, cnt) if best_approx is not None else cnt

        if best_exact is not None:
            return best_exact, True

        for meta_txt in eval_res.get("metaTexts") or []:
            if isinstance(meta_txt, str):
                m = re.search(
                    r"([\d.,]+(?:\s*(?:rb|ribu|k|jt|juta|m))?)\s+(?:komentar|comments?)\b",
                    meta_txt,
                    re.IGNORECASE,
                )
                if m:
                    cnt, is_exact = self.parse_human_count(m.group(1))
                    if cnt is not None and cnt > 0:
                        if is_exact:
                            best_exact = max(best_exact, cnt) if best_exact is not None else cnt
                        else:
                            best_approx = max(best_approx, cnt) if best_approx is not None else cnt

        if best_exact is not None:
            return best_exact, True
        if best_approx is not None:
            return best_approx, False
        return None, False

    def _compute_tolerance_target(
        self,
        reported_total: int,
        is_exact: bool,
        limit: int,
    ) -> tuple[int, int]:
        """Compute (effective_goal, minimum_acceptable_tolerance_target)."""
        effective_goal = min(limit, max(1, reported_total))
        if self.comment_tolerance <= 0 and is_exact:
            return effective_goal, effective_goal

        if is_exact:
            eff_tol = min(self.comment_tolerance, max(1, int(effective_goal * 0.05)))
        else:
            eff_tol = max(self.comment_tolerance, int(effective_goal * 0.05))

        return effective_goal, max(1, effective_goal - eff_tol)

    def _parse_graphql_comment_node(
        self,
        node: dict[str, Any],
        media_id: str,
        collected_at: str,
        on_rejected: Callable[[str, str | None], None] | None = None,
    ) -> CommentRecord | None:
        """Parse an intercepted GraphQL comment node dictionary into a CommentRecord."""
        raw_text = node.get("text", "")
        if not isinstance(raw_text, str) or not raw_text:
            return None

        user_dict = node.get("user") if isinstance(node.get("user"), dict) else {}
        owner_dict = node.get("owner") if isinstance(node.get("owner"), dict) else {}
        author = str(user_dict.get("username") or owner_dict.get("username") or "")

        eval_res = self.extractor.evaluate_comment(
            raw_text=raw_text,
            comment_text=raw_text,
            author=author,
            timestamp_raw=str(node.get("created_at", "") or ""),
            like_count=node.get("comment_like_count", 0) or node.get("like_count", 0) or 0,
        )

        cid = str(node.get("id") or node.get("pk") or "")
        if not eval_res.is_valid:
            if on_rejected and (author.strip() or eval_res.comment_text.strip()):
                if author.strip() and eval_res.comment_text.strip():
                    rej_key = f"{author.strip().lower()}|{eval_res.comment_text.strip().lower()}"
                else:
                    rej_key = cid or f"{author.strip().lower()}|{eval_res.timestamp_raw.strip().lower()}"
                on_rejected(rej_key, eval_res.rejection_reason)
            return None

        if self.only_slang_candidates and not eval_res.has_slang_candidate:
            if on_rejected and (author.strip() or eval_res.clean_text.strip()):
                rej_key = (
                    f"{author.strip().lower()}|{eval_res.clean_text.strip().lower()}"
                    if author.strip() and eval_res.clean_text.strip()
                    else (cid or eval_res.clean_text.strip().lower())
                )
                on_rejected(rej_key, "not_slang_candidate")
            return None

        if not cid:
            id_seed = (
                f"{eval_res.author.strip().lower()}|{eval_res.clean_text}"
                if eval_res.author.strip()
                else eval_res.clean_text
            )
            cid = f"ig_{hashlib.md5(id_seed.encode('utf-8')).hexdigest()[:12]}"

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
        on_rejected: Callable[[str, str | None], None] | None = None,
    ) -> list[CommentRecord]:
        """Recursively scan JSON network response for comment items."""
        found: list[CommentRecord] = []

        def recurse(data: Any) -> None:
            if isinstance(data, dict):
                if self._is_foreign_media_dict(data, media_id):
                    return
                # Check for standard Instagram comment object signatures
                if ("text" in data and ("user" in data or "owner" in data or "comment_like_count" in data)):
                    rec = self._parse_graphql_comment_node(
                        data,
                        media_id,
                        collected_at,
                        on_rejected=on_rejected,
                    )
                    if rec:
                        found.append(rec)
                for key, val in data.items():
                    if key in self._IGNORED_GRAPHQL_KEYS:
                        continue
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
        seen_author_texts: set[tuple[str, str]] = set()
        seen_rejected_keys: set[str] = set()
        rejection_breakdown: dict[str, int] = {}
        reported_state: dict[str, Any] = {"total": None, "is_exact": False}

        def update_reported_total(candidate_total: int | None, is_exact: bool) -> None:
            if candidate_total is None or candidate_total <= 0:
                return
            prev_total = reported_state["total"]
            prev_exact = bool(reported_state["is_exact"])
            if prev_total is None:
                reported_state["total"] = candidate_total
                reported_state["is_exact"] = is_exact
            elif is_exact and (not prev_exact or candidate_total > prev_total):
                reported_state["total"] = candidate_total
                reported_state["is_exact"] = True
            elif not prev_exact and candidate_total > prev_total:
                reported_state["total"] = candidate_total

        def record_rejected(rejected_key: str, reason: str | None) -> None:
            if not rejected_key or rejected_key in seen_rejected_keys:
                return
            seen_rejected_keys.add(rejected_key)
            r_key = reason or "filtered_invalid"
            rejection_breakdown[r_key] = rejection_breakdown.get(r_key, 0) + 1

        def add_comment(rec: CommentRecord) -> bool:
            if rec.comment_id in comments_dict:
                return False
            text_key = rec.comment_text.strip().lower()
            author_key = rec.username.strip().lower()
            dedup_key = (author_key, text_key)
            if dedup_key in seen_author_texts:
                return False
            seen_author_texts.add(dedup_key)
            comments_dict[rec.comment_id] = rec

            curr_count = len(comments_dict)
            preview = rec.comment_text.replace("\n", " ").strip()
            if len(preview) > 50:
                preview = preview[:47] + "..."
            print(f"[INFO] + [{curr_count}/{limit}] {preview}")

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
                    content_type = str(response.headers.get("content-type", "") or "").lower()
                    if "json" in content_type or "javascript" in content_type:
                        try:
                            body = None
                            try:
                                body = response.json()
                            except Exception:
                                if hasattr(response, "text"):
                                    raw_txt = response.text()
                                    if isinstance(raw_txt, str):
                                        cleaned_txt = raw_txt.lstrip()
                                        if cleaned_txt.startswith("for (;;);"):
                                            cleaned_txt = cleaned_txt[len("for (;;);"):].lstrip()
                                        body = json.loads(cleaned_txt)
                            if not isinstance(body, (dict, list)):
                                return
                            gql_count = self._extract_comment_count_from_payload(body, shortcode)
                            if gql_count is not None:
                                update_reported_total(gql_count, True)

                            extracted = self._extract_comments_from_network_payload(
                                body,
                                shortcode,
                                collected_at,
                                on_rejected=record_rejected,
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

                def get_tolerance_target() -> int | None:
                    rt = reported_state["total"]
                    if not self.match_reported_total or not isinstance(rt, int) or rt <= 0:
                        return None
                    _, tol_target = self._compute_tolerance_target(
                        reported_total=rt,
                        is_exact=bool(reported_state["is_exact"]),
                        limit=limit,
                    )
                    return tol_target

                def get_effective_max_scrolls() -> int:
                    rt = reported_state["total"]
                    if (
                        self.match_reported_total
                        and self.max_scroll_attempts > 5
                        and isinstance(rt, int)
                        and rt > 0
                    ):
                        return max(self.max_scroll_attempts, min(1500, rt + 150))
                    return self.max_scroll_attempts

                if self.match_reported_total:
                    ui_cnt, ui_exact = self._detect_reported_comment_count(page)
                    update_reported_total(ui_cnt, ui_exact)
                    if reported_state["total"] is not None:
                        tol_t = get_tolerance_target()
                        logger.info(
                            "Total komentar postingan terdeteksi: %d%s (target toleransi min: %s)",
                            reported_state["total"],
                            "" if reported_state["is_exact"] else " [perkiraan]",
                            tol_t if tol_t is not None else "-",
                        )

                consecutive_idle_scrolls = 0
                consecutive_zero_yield_clicks = 0
                scroll_progress_only = 0
                recovery_sweeps = 0
                max_idle = 10
                scroll_count = 0

                while len(comments_dict) < limit and scroll_count < get_effective_max_scrolls():
                    scroll_count += 1
                    initial_valid = len(comments_dict)
                    initial_coverage = len(comments_dict) + len(seen_rejected_keys)
                    scroll_expanded = 0

                    # 1. Extract currently visible DOM comments first
                    self._extract_from_page_dom(
                        page,
                        shortcode,
                        collected_at,
                        add_comment,
                        limit,
                        on_rejected=record_rejected,
                    )

                    if len(comments_dict) >= limit:
                        break

                    # 2. Multi-pass reply expansion ('View replies' -> 'View more replies', etc.)
                    zero_yield_expand_rounds = 0
                    for _reply_pass in range(6):
                        before_expand_count = len(comments_dict) + len(seen_rejected_keys)
                        expanded = self._expand_reply_threads(page)
                        if not expanded:
                            break
                        scroll_expanded += expanded
                        self._extract_from_page_dom(
                            page,
                            shortcode,
                            collected_at,
                            add_comment,
                            limit,
                            on_rejected=record_rejected,
                        )
                        if len(comments_dict) >= limit:
                            break
                        after_expand_count = len(comments_dict) + len(seen_rejected_keys)
                        if after_expand_count == before_expand_count:
                            zero_yield_expand_rounds += 1
                            if zero_yield_expand_rounds >= 2:
                                break
                        else:
                            zero_yield_expand_rounds = 0

                    if len(comments_dict) >= limit:
                        break

                    # 3. Click "Load more comments" / "View more comments" / "Hidden comments" button
                    load_more_clicked = self._click_load_more_buttons(page)

                    # 4. Gradual dynamic scroll inside comment panel (avoid jumping straight past replies)
                    scrolled_inner = False
                    near_bottom = False
                    try:
                        step_mult = 1.6 if scroll_progress_only >= 3 else 1.0
                        scroll_res = self._scroll_comment_container(
                            page,
                            mode="step",
                            step_multiplier=step_mult,
                        )
                        if isinstance(scroll_res, dict):
                            scrolled_inner = bool(scroll_res.get("scrolledInner"))
                            near_bottom = bool(scroll_res.get("nearBottom"))
                            target_x = scroll_res.get("targetX")
                            target_y = scroll_res.get("targetY")
                        else:
                            target_x = None
                            target_y = None

                        if not scrolled_inner:
                            if (
                                isinstance(target_x, (int, float))
                                and isinstance(target_y, (int, float))
                                and not isinstance(target_x, bool)
                                and not isinstance(target_y, bool)
                                and hasattr(page, "mouse")
                            ):
                                page.mouse.move(float(target_x), float(target_y))
                                page.mouse.wheel(0, 600)
                            else:
                                comment_col = page.locator(
                                    "div[role='dialog'] ul, article ul, main ul, article div[style*='overflow'], main div[style*='overflow']"
                                ).first
                                col_count = comment_col.count() if hasattr(comment_col, "count") else 0
                                if isinstance(col_count, (int, float)) and not isinstance(col_count, bool) and col_count > 0:
                                    comment_col.hover(timeout=1000)
                                    page.mouse.wheel(0, 500)
                    except Exception:
                        pass

                    time.sleep(self.scroll_delay_sec)

                    # Re-check DOM count lazily if still unknown during first scrolls
                    if self.match_reported_total and reported_state["total"] is None and scroll_count <= 2:
                        ui_cnt, ui_exact = self._detect_reported_comment_count(page)
                        update_reported_total(ui_cnt, ui_exact)

                    current_valid = len(comments_dict)
                    current_coverage = len(comments_dict) + len(seen_rejected_keys)
                    tolerance_target = get_tolerance_target()
                    idle_limit = (
                        2
                        if (tolerance_target is not None and current_coverage >= tolerance_target)
                        else max_idle
                    )

                    if current_valid > initial_valid or current_coverage > initial_coverage:
                        consecutive_idle_scrolls = 0
                        consecutive_zero_yield_clicks = 0
                        scroll_progress_only = 0
                    elif (scroll_expanded > 0 or load_more_clicked > 0) and consecutive_zero_yield_clicks < 5:
                        consecutive_zero_yield_clicks += 1
                        consecutive_idle_scrolls = 0
                        scroll_progress_only = 0
                    elif scrolled_inner and not near_bottom and scroll_progress_only < 30:
                        scroll_progress_only += 1
                        consecutive_idle_scrolls = 0
                    else:
                        consecutive_idle_scrolls += 1
                        if consecutive_idle_scrolls >= idle_limit:
                            recovered = False
                            while (
                                self.match_reported_total
                                and tolerance_target is not None
                                and current_coverage < tolerance_target
                                and len(comments_dict) < limit
                                and recovery_sweeps < self.max_recovery_sweeps
                            ):
                                recovery_sweeps += 1
                                logger.info(
                                    "Cakupan %d/%d (ambang toleransi %d) belum tercapai; menjalankan recovery sweep %d/%d...",
                                    current_coverage,
                                    reported_state["total"] or limit,
                                    tolerance_target,
                                    recovery_sweeps,
                                    self.max_recovery_sweeps,
                                )
                                before_recov_cov = current_coverage
                                self._perform_recovery_sweep(page, recovery_sweeps)
                                self._expand_reply_threads(page)
                                self._click_load_more_buttons(page)
                                self._extract_from_page_dom(
                                    page,
                                    shortcode,
                                    collected_at,
                                    add_comment,
                                    limit,
                                    on_rejected=record_rejected,
                                )
                                current_coverage = len(comments_dict) + len(seen_rejected_keys)
                                tolerance_target = get_tolerance_target()
                                if current_coverage > before_recov_cov:
                                    recovered = True
                                    consecutive_idle_scrolls = 0
                                    break

                            if not recovered:
                                logger.info(
                                    "Tidak ada komentar baru setelah %d kali scroll. Pengambilan selesai.",
                                    idle_limit,
                                )
                                break

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
        final_rejected = len(seen_rejected_keys)
        final_raw_encountered = len(all_comments) + final_rejected
        final_reported = reported_state["total"]
        final_tolerance = (
            self._compute_tolerance_target(
                reported_total=final_reported,
                is_exact=bool(reported_state["is_exact"]),
                limit=limit,
            )[1]
            if self.match_reported_total and isinstance(final_reported, int) and final_reported > 0
            else None
        )
        coverage_ok = (
            final_tolerance is not None and final_raw_encountered >= final_tolerance
        ) or (len(all_comments) >= limit)

        return CollectionResult(
            media_id=shortcode,
            comments=all_comments,
            total_collected=len(all_comments),
            unique_collected=len(all_comments),
            status="completed" if all_comments else "empty",
            paging_completed=(len(all_comments) < limit),
            reported_total=final_reported,
            tolerance_target=final_tolerance,
            raw_encountered=final_raw_encountered,
            filtered_out_count=final_rejected,
            rejection_breakdown=dict(rejection_breakdown),
            coverage_reached=coverage_ok,
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
        """Find and click collapsed reply dropdown buttons inside comment containers.

        Matches English and Indonesian reply expand/pagination buttons such as:
        - 'View replies', 'View replies (3)', 'View all 12 replies', 'View more replies',
          'View 5 more replies', 'View previous replies', 'View hidden replies'
        - 'Lihat balasan', 'Lihat balasan (3)', 'Lihat 5 balasan', 'Lihat semua balasan',
          'Lihat balasan lainnya', 'Lihat 3 lagi'

        Explicitly excludes collapse buttons ('Hide ...', 'Sembunyikan ...', 'Tutup ...').
        Uses DOM tagging + Playwright locator click so shifting layout after earlier
        expansions never causes misclicks on stale coordinates, while remaining compatible
        with mocked `page.evaluate` returning an `int`.
        """
        try:
            tagged_count = page.evaluate(
                r"""
                () => {
                    const scope = (
                        document.querySelector('div[role="dialog"] article') ||
                        document.querySelector('div[role="dialog"]') ||
                        document.querySelector('article') ||
                        document.querySelector('main') ||
                        document.body
                    );
                    if (!scope) return 0;

                    document.querySelectorAll('[data-nlp-expand-id]').forEach(el => {
                        el.removeAttribute('data-nlp-expand-id');
                    });

                    const normalizeText = (raw) => {
                        const collapsed = (raw || '').replace(/\s+/g, ' ').trim();
                        return collapsed.replace(/^[\-\u2013\u2014\u2015\u2500\u2022\u00b7\s]+/, '').trim();
                    };

                    const hideRegex = /^(?:hide|sembunyikan|tutup)\b/i;
                    const enReplyRegex = /^view\s+(?:(?:all|more|previous|hidden)\s+|\d+\s+)*(?:more\s+|previous\s+|hidden\s+)?repl(?:y|ies)(?:\s*\(\d+\))?$/i;
                    const idReplyRegex = /^lihat\s+(?:semua\s+|\d+\s+)*(?:balasan|tanggapan)(?:\s+(?:lainnya|lagi|sebelumnya|tersembunyi))?(?:\s*\(\d+\))?$/i;
                    const idMoreRegex = /^lihat\s+\d+\s+lagi$/i;

                    const matchesExpand = (txt) => {
                        if (!txt || txt.length > 70) return false;
                        if (hideRegex.test(txt)) return false;
                        return enReplyRegex.test(txt) || idReplyRegex.test(txt) || idMoreRegex.test(txt);
                    };

                    const primary = Array.from(scope.querySelectorAll('button, [role="button"], [tabindex="0"]'));
                    const fallback = Array.from(scope.querySelectorAll('span, div'));
                    const candidates = primary.concat(fallback);

                    const selected = [];
                    for (const el of candidates) {
                        const txt = normalizeText(el.innerText || el.textContent || '');
                        if (!matchesExpand(txt)) continue;
                        if (el.querySelector('time')) continue;

                        let target = el.closest('button, [role="button"], [tabindex="0"]');
                        if (target) {
                            const targetTxt = normalizeText(target.innerText || target.textContent || '');
                            if (!matchesExpand(targetTxt) || target.querySelector('time')) {
                                target = el;
                            }
                        } else {
                            // For plain span/div without interactive roles, prefer the innermost node
                            const hasMatchingChild = Array.from(el.querySelectorAll('span, div')).some(
                                child => matchesExpand(normalizeText(child.innerText || child.textContent || ''))
                            );
                            if (hasMatchingChild) continue;
                            target = el;
                        }

                        const rect = target.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) continue;
                        const style = window.getComputedStyle(target);
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;

                        const attempts = Number(target.getAttribute('data-nlp-reply-attempts') || '0');
                        if (attempts >= 15) continue;

                        if (selected.some(s => s === target || s.contains(target) || target.contains(s))) {
                            continue;
                        }
                        selected.push(target);
                    }

                    selected.forEach((btn, idx) => {
                        const prev = Number(btn.getAttribute('data-nlp-reply-attempts') || '0');
                        btn.setAttribute('data-nlp-reply-attempts', String(prev + 1));
                        btn.setAttribute('data-nlp-expand-id', `nlp_reply_${idx}`);
                    });

                    return selected.length;
                }
                """
            )
            if not isinstance(tagged_count, int) or isinstance(tagged_count, bool) or tagged_count <= 0:
                return 0

            locator_supported = False
            actually_clicked = 0
            for idx in range(tagged_count):
                if not hasattr(page, "locator"):
                    break
                btn_loc = page.locator(f'[data-nlp-expand-id="nlp_reply_{idx}"]').first
                loc_count = btn_loc.count() if hasattr(btn_loc, "count") else None
                if not isinstance(loc_count, int) or isinstance(loc_count, bool):
                    break
                locator_supported = True
                if loc_count <= 0:
                    continue
                try:
                    if hasattr(btn_loc, "scroll_into_view_if_needed"):
                        btn_loc.scroll_into_view_if_needed(timeout=1500)
                    btn_loc.click(timeout=1500)
                    actually_clicked += 1
                    time.sleep(0.25)
                except Exception:
                    try:
                        btn_loc.evaluate("el => el.click()")
                        actually_clicked += 1
                        time.sleep(0.25)
                    except Exception:
                        pass

            expanded_count = actually_clicked if locator_supported else tagged_count
            if expanded_count > 0:
                logger.debug("Memperluas %d dropdown balasan komentar.", expanded_count)
                time.sleep(1.0)
            return expanded_count
        except Exception:
            return 0

    def _scroll_comment_container(
        self,
        page: Any,
        mode: str = "step",
        delta: int = 0,
        step_multiplier: float = 1.0,
    ) -> dict[str, Any]:
        """Locate the tallest active scrollable comment panel, scroll it, and return telemetry."""
        mode_js = json.dumps(mode)
        delta_val = int(delta)
        step_mult = float(step_multiplier)
        res = page.evaluate(
            f"""
            () => {{
                const mode = {mode_js};
                const deltaVal = {delta_val};
                const stepMult = {step_mult};
                const scope = (
                    document.querySelector('div[role="dialog"] article') ||
                    document.querySelector('div[role="dialog"]') ||
                    document.querySelector('article') ||
                    document.querySelector('main') ||
                    document.body
                );
                let bestEl = null;
                let bestScore = -1;
                const allElements = scope ? scope.querySelectorAll('*') : [];
                for (const el of allElements) {{
                    const oy = window.getComputedStyle(el).overflowY;
                    if (
                        (oy === 'auto' || oy === 'scroll') &&
                        el.scrollHeight > el.clientHeight + 10 &&
                        el.clientHeight >= 50
                    ) {{
                        if (el.scrollHeight > bestScore) {{
                            bestScore = el.scrollHeight;
                            bestEl = el;
                        }}
                    }}
                }}

                let scrolledInner = false;
                let nearBottom = false;
                let targetX = null;
                let targetY = null;

                if (bestEl) {{
                    const rect = bestEl.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {{
                        targetX = Math.round(rect.left + rect.width / 2);
                        targetY = Math.round(rect.top + rect.height / 2);
                    }}
                    const beforeTop = bestEl.scrollTop;
                    if (mode === 'bottom') {{
                        bestEl.scrollTop = bestEl.scrollHeight;
                        bestEl.dispatchEvent(new Event('scroll', {{ bubbles: true }}));
                    }} else if (mode === 'delta') {{
                        if (deltaVal !== 0) {{
                            bestEl.scrollBy(0, deltaVal);
                        }}
                    }} else {{
                        const step = Math.max(450, Math.floor(bestEl.clientHeight * 0.8 * stepMult));
                        bestEl.scrollBy(0, step);
                    }}
                    if (bestEl.scrollTop > beforeTop + 2) {{
                        scrolledInner = true;
                    }}
                    nearBottom = (bestEl.scrollTop + bestEl.clientHeight >= bestEl.scrollHeight - 25);
                }}

                if (mode === 'step') {{
                    if (scrolledInner) {{
                        window.scrollTo(0, 0);
                    }} else {{
                        const items = (scope || document).querySelectorAll('ul li, ul > div');
                        if (items.length > 0) {{
                            items[items.length - 1].scrollIntoView({{ behavior: 'smooth', block: 'end' }});
                        }}
                    }}
                }} else if (!bestEl && deltaVal !== 0) {{
                    window.scrollBy(0, mode === 'bottom' ? 750 : deltaVal);
                }}

                return {{ scrolledInner, nearBottom, targetX, targetY }};
            }}
            """
        )
        return res if isinstance(res, dict) else {}

    def _perform_recovery_sweep(self, page: Any, sweep_idx: int) -> None:
        """Perform bounded scroll/keyboard nudges to wake stalled Instagram lazy loading."""
        try:
            if sweep_idx == 1:
                self._scroll_comment_container(page, mode="delta", delta=-700)
                time.sleep(0.4)
                self._scroll_comment_container(page, mode="bottom")
                time.sleep(0.8)
            elif sweep_idx == 2:
                probe = self._scroll_comment_container(page, mode="delta", delta=0)
                target_x = probe.get("targetX")
                target_y = probe.get("targetY")
                if (
                    isinstance(target_x, (int, float))
                    and isinstance(target_y, (int, float))
                    and not isinstance(target_x, bool)
                    and not isinstance(target_y, bool)
                    and hasattr(page, "mouse")
                ):
                    page.mouse.move(float(target_x), float(target_y))
                    page.mouse.wheel(0, 1200)
                else:
                    comment_col = page.locator(
                        "div[role='dialog'] ul, article ul, main ul, article div[style*='overflow'], main div[style*='overflow']"
                    ).first
                    col_count = comment_col.count() if hasattr(comment_col, "count") else 0
                    if isinstance(col_count, (int, float)) and not isinstance(col_count, bool) and col_count > 0:
                        comment_col.hover(timeout=1000)
                        page.mouse.wheel(0, 800)
                if hasattr(page, "keyboard"):
                    for _ in range(3):
                        page.keyboard.press("PageDown")
                        time.sleep(0.2)
                time.sleep(min(2.5, max(0.5, self.scroll_delay_sec * 1.5)))
            else:
                probe = self._scroll_comment_container(page, mode="bottom")
                target_x = probe.get("targetX")
                target_y = probe.get("targetY")
                if hasattr(page, "mouse"):
                    if (
                        isinstance(target_x, (int, float))
                        and isinstance(target_y, (int, float))
                        and not isinstance(target_x, bool)
                        and not isinstance(target_y, bool)
                    ):
                        page.mouse.move(float(target_x), float(target_y))
                    page.mouse.wheel(0, 1500)
                time.sleep(min(3.5, max(0.5, self.scroll_delay_sec * 2.0)))
        except Exception:
            pass

    def _click_load_more_buttons(self, page: Any) -> int:
        """Find and click 'Load more comments' / 'View hidden comments' / '+' buttons."""
        try:
            tagged_count = page.evaluate(
                """
                () => {
                    document.querySelectorAll('[data-nlp-loadmore-id]').forEach(el => {
                        el.removeAttribute('data-nlp-loadmore-id');
                    });

                    const scope = (
                        document.querySelector('div[role="dialog"]') ||
                        document.querySelector('article') ||
                        document.querySelector('main') ||
                        document.body
                    );
                    if (!scope) return 0;

                    const phrases = [
                        'lihat komentar lainnya',
                        'muat komentar lainnya',
                        'lihat komentar sebelumnya',
                        'lihat lebih banyak komentar',
                        'lihat komentar tersembunyi',
                        'load more comments',
                        'view more comments',
                        'view previous comments',
                        'view hidden comments',
                    ];
                    const excludePhrases = ['sembunyikan', 'hide', 'tutup', 'close', 'collapse'];

                    const isVisible = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        if (rect.width <= 0 || rect.height <= 0) return false;
                        const style = window.getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
                    };

                    const seen = new Set();
                    const selected = [];
                    const addTarget = (el) => {
                        const target = el.closest('button, [role="button"]') || el;
                        if (!seen.has(target) && isVisible(target)) {
                            seen.add(target);
                            selected.push(target);
                        }
                    };

                    scope.querySelectorAll(
                        'svg[aria-label="Muat komentar lainnya"], svg[aria-label="Load more comments"]'
                    ).forEach(addTarget);

                    const candidates = scope.querySelectorAll('button, div[role="button"], span[role="button"], a[role="button"]');
                    for (const el of candidates) {
                        if (el.querySelector('time')) continue;
                        const raw = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                        if (!raw || raw.length > 75) continue;
                        const norm = raw.toLowerCase().replace(/\\s+/g, ' ');
                        if (excludePhrases.some(ex => norm.includes(ex))) continue;
                        if (phrases.some(p => norm.includes(p))) {
                            addTarget(el);
                        }
                    }

                    selected.forEach((btn, idx) => {
                        btn.setAttribute('data-nlp-loadmore-id', `nlp_loadmore_${idx}`);
                    });
                    return selected.length;
                }
                """
            )
            if not isinstance(tagged_count, int) or isinstance(tagged_count, bool) or tagged_count <= 0:
                return 0

            locator_supported = False
            actually_clicked = 0
            for idx in range(tagged_count):
                if not hasattr(page, "locator"):
                    break
                btn_loc = page.locator(f'[data-nlp-loadmore-id="nlp_loadmore_{idx}"]').first
                loc_count = btn_loc.count() if hasattr(btn_loc, "count") else None
                if not isinstance(loc_count, int) or isinstance(loc_count, bool):
                    break
                locator_supported = True
                if loc_count <= 0:
                    continue
                try:
                    if hasattr(btn_loc, "scroll_into_view_if_needed"):
                        btn_loc.scroll_into_view_if_needed(timeout=1500)
                    btn_loc.click(timeout=1000)
                    actually_clicked += 1
                    time.sleep(0.5)
                except Exception:
                    try:
                        btn_loc.evaluate("el => el.click()")
                        actually_clicked += 1
                        time.sleep(0.5)
                    except Exception:
                        pass

            return actually_clicked if locator_supported else tagged_count
        except Exception:
            return 0

    def _extract_from_page_dom(
        self,
        page: Any,
        media_id: str,
        collected_at: str,
        add_fn: Callable[[CommentRecord], bool],
        limit: int,
        on_rejected: Callable[[str, str | None], None] | None = None,
    ) -> None:
        """Extract comment text blocks from rendered DOM inside post article using multi-tier semantic anchors."""
        try:
            raw_blocks: list[str] = page.evaluate(
                """
                () => {
                    const blocks = [];
                    const seen = new Set();
                    const article = (
                        document.querySelector('div[role="dialog"] article') ||
                        document.querySelector('div[role="dialog"]') ||
                        document.querySelector('article') ||
                        document.querySelector('main') ||
                        document.body
                    );

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
                    if (
                        on_rejected
                        and extracted.rejection_reason
                        and extracted.rejection_reason != "empty_input"
                        and extracted.author.strip()
                        and extracted.comment_text.strip()
                    ):
                        rej_key = (
                            f"{extracted.author.strip().lower()}|"
                            f"{extracted.comment_text.strip().lower()}"
                        )
                        on_rejected(rej_key, extracted.rejection_reason)
                    continue

                if self.only_slang_candidates and not extracted.has_slang_candidate:
                    if on_rejected and extracted.author.strip() and extracted.clean_text.strip():
                        rej_key = (
                            f"{extracted.author.strip().lower()}|"
                            f"{extracted.clean_text.strip().lower()}"
                        )
                        on_rejected(rej_key, "not_slang_candidate")
                    continue

                id_seed = (
                    f"{extracted.author.strip().lower()}|{extracted.clean_text}"
                    if extracted.author.strip()
                    else extracted.clean_text
                )
                cid = f"dom_{hashlib.md5(id_seed.encode('utf-8')).hexdigest()[:12]}"
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
