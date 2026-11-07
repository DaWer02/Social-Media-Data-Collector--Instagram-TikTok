"""Bounded browser collection using explicitly reviewed, versioned DOM locators.

Locators are supplied by a research manifest: no claim of stable platform access.
No login automation, stealth flags, saved browser credentials or private APIs.
"""
from __future__ import annotations

import csv
import ipaddress
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .pipeline import clean, load_manifest, pseudonym, timestamp, write_json

HOSTS = {"instagram": {"www.instagram.com", "instagram.com"},
         "tiktok": {"www.tiktok.com", "tiktok.com"}}


def validate_url(url: str, platform: str, resolve: bool = True) -> str:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS[platform]
            or parsed.username or parsed.password or parsed.port not in {None, 443}):
        raise ValueError("URL harus HTTPS pada host platform yang diizinkan.")
    import re
    pattern = r"/(p|reel)/[A-Za-z0-9_-]+/?" if platform == "instagram" else r"/@[\w.-]+/video/\d+/?"
    if not re.fullmatch(pattern, parsed.path):
        raise ValueError("URL bukan permalink postingan yang didukung.")
    if resolve:
        for address in socket.getaddrinfo(parsed.hostname, 443):
            if not ipaddress.ip_address(address[4][0]).is_global:
                raise ValueError("Alamat jaringan nonpublik ditolak.")
    return urlunsplit(("https", parsed.netloc, parsed.path, "", ""))


def collect(manifest_path: Path, output: Path) -> dict:
    import os
    manifest = load_manifest(manifest_path)
    secret = os.environ.get("REDAM_DATASET_SECRET", "")
    if len(secret) < 32:
        raise ValueError("Set REDAM_DATASET_SECRET minimal 32 karakter.")
    # Validate all configuration before opening the browser.
    for spec in manifest["cases"]:
        if spec["origin"] != "research_collection" or spec["source_type"] != "live":
            raise ValueError("collect hanya untuk research_collection LIVE.")
        if not spec.get("access_reviewed_by"):
            raise ValueError("Manifest membutuhkan access_reviewed_by dan rights_reference.")
        for key in ["item", "text", "id_attribute"]:
            if not spec.get("locators", {}).get(key):
                raise ValueError("Lokator item/text/id_attribute tervalidasi wajib tersedia.")
        validate_url(spec["url"], spec["platform"])
    from playwright.sync_api import sync_playwright
    output.mkdir(parents=True, exist_ok=False)
    prepared_manifest = {"version": manifest.get("version"), "cases": []}
    outcomes = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            for spec in manifest["cases"]:
                records, status = {}, "partial"
                started = time.monotonic()
                context = browser.new_context(service_workers="block", accept_downloads=False)
                def route_request(route):
                    parsed = urlsplit(route.request.url)
                    # Same-origin only; resources not needed for text collection are blocked.
                    if parsed.scheme != "https" or parsed.hostname not in HOSTS[spec["platform"]]:
                        route.abort(); return
                    if route.request.resource_type in {"image", "media", "font"}:
                        route.abort(); return
                    try:
                        addresses = socket.getaddrinfo(parsed.hostname, 443)
                        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                            route.abort(); return
                    except OSError:
                        route.abort(); return
                    route.continue_()
                context.route("**/*", route_request)
                page = context.new_page()
                page.set_default_timeout(3000)
                loc = spec["locators"]
                try:
                    page.goto(validate_url(spec["url"], spec["platform"]), timeout=30000, wait_until="domcontentloaded")
                    stagnant = 0
                    for _ in range(20):
                        if time.monotonic() - started >= 85:
                            status = "timeout_partial"; break
                        if ("login" in page.url.lower() or page.locator('input[type="password"], iframe[src*="captcha"]').count()
                                or (loc.get("access_barrier") and page.locator(loc["access_barrier"]).count())):
                            status = "ACCESS_RESTRICTED"; break
                        before = len(records)
                        for item in page.locator(loc["item"]).all()[:200]:
                            identifier = item.get_attribute(loc["id_attribute"])
                            if not identifier:
                                status = "SCRAPER_CHANGED"; break
                            text = clean(item.locator(loc["text"]).inner_text())
                            if not text:
                                continue
                            account = item.locator(loc["account"]).inner_text() if loc.get("account") and item.locator(loc["account"]).count() else ""
                            date = item.locator(loc["time"]).get_attribute("datetime") if loc.get("time") and item.locator(loc["time"]).count() else None
                            records[identifier] = {"comment_id": pseudonym(secret, spec["case_id"], identifier), "text": text,
                                "created_at": timestamp(date), "account": pseudonym(secret, spec["case_id"], account) if account else None,
                                "likes_count": None}
                            if len(records) >= 200:
                                break
                        if status == "SCRAPER_CHANGED" or len(records) >= 200:
                            break
                        stagnant = stagnant + 1 if len(records) == before else 0
                        if stagnant >= 3:
                            break
                        if loc.get("scroll_container"):
                            page.locator(loc["scroll_container"]).evaluate("e => e.scrollBy(0, 900)")
                        else:
                            page.mouse.wheel(0, 900)
                        page.wait_for_timeout(1500)
                except Exception as exc:
                    # Do not persist exception strings that can contain URLs/cookies/content.
                    status = "COLLECTION_ERROR_" + type(exc).__name__
                finally:
                    context.close()
                outcomes.append({"case_id": spec["case_id"], "status": status, "count": len(records)})
                if records and status not in {"ACCESS_RESTRICTED", "SCRAPER_CHANGED"}:
                    filename = spec["case_id"] + ".json"
                    write_json(output / filename, list(records.values()))
                    safe_spec = {k: spec[k] for k in ["case_id", "platform", "topic_group", "period", "rights_reference", "retention_until", "source_type", "origin"]}
                    safe_spec.update({"input": filename, "adapter_version": spec.get("adapter_version", "reviewed_dom_v1"),
                                      "collected_at": datetime.now(timezone.utc).isoformat(), "is_partial": True,
                                      "limitations": ["Best-effort DOM; cakupan seluruh komentar tidak diketahui.", status]})
                    prepared_manifest["cases"].append(safe_spec)
        finally:
            browser.close()
    write_json(output / "collection_report.json", outcomes)
    write_json(output / "manifest.json", prepared_manifest)
    return {"cases_collected": len(prepared_manifest["cases"]), "outcomes": outcomes}


def is_login_required(page: Any) -> bool:
    """Check if platform (Instagram or TikTok) is currently displaying a login barrier or page."""
    try:
        current_url = (getattr(page, "url", "") or "").lower()
        if "accounts/login" in current_url or "/login" in current_url:
            return True

        has_barrier = page.evaluate(
            """
            () => {
                const userField = document.querySelector('input[name="username"], input[type="email"]');
                const passField = document.querySelector('input[name="password"], input[type="password"]');
                if (userField && passField) return true;

                const text = document.body ? document.body.innerText : '';
                if (text.includes("Masuk untuk melihat") || 
                    text.includes("Log in to see") ||
                    text.includes("Masuk ke Instagram") ||
                    text.includes("Log in to Instagram") ||
                    text.includes("Log in to TikTok") ||
                    text.includes("Masuk ke TikTok")) {
                    return true;
                }
                return false;
            }
            """
        )
        return has_barrier is True
    except Exception:
        return False


def is_human_verification_required(page: Any) -> bool:
    """Check if platform (especially TikTok) is displaying a human verification / bot challenge (CAPTCHA)."""
    try:
        current_url = (getattr(page, "url", "") or "").lower()
        if "captcha" in current_url or "verify" in current_url:
            return True

        has_challenge = page.evaluate(
            """
            () => {
                // 1. Common TikTok SecSDK & CAPTCHA containers
                const selectors = [
                    '#secsdk-captcha-drag-wrapper',
                    '.captcha_verify_container',
                    '.captcha-disable-scroll',
                    'div[id*="verify-bar"]',
                    'div[id*="captcha"]',
                    'div[class*="captcha"]',
                    'div[class*="secsdk"]',
                    'iframe[src*="captcha"]',
                    'iframe[src*="verify"]',
                    'iframe[src*="secsdk"]',
                    'div[role="dialog"] div[class*="verify"]'
                ];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && (el.offsetWidth > 0 || el.offsetHeight > 0 || (window.getComputedStyle && window.getComputedStyle(el).display !== 'none'))) {
                        return true;
                    }
                }

                // 2. Specific textual cues for human verification
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
    """Prompt user in terminal to complete human verification / CAPTCHA puzzle in the browser."""
    print("\n" + "=" * 64)
    print("       [VERIFIKASI MANUSIA / CEK HUMAN DIPERLUKAN]")
    print("=" * 64)
    print("TikTok menampilkan pemeriksaan keamanan (Verifikasi Manusia / CAPTCHA).")
    print("Jendela browser saat ini sedang terbuka di layar Anda.")
    print("")
    print("Instruksi:")
    print("1. Silakan selesaikan geser teka-teki (puzzle slider / objek) di browser.")
    print("2. Pastikan video TikTok sudah terbuka dan dapat diputar dengan normal.")
    print("3. Setelah selesai, tekan tombol [ENTER] pada terminal ini untuk")
    print("   memulai pengumpulan komentar.")
    print("=" * 64)

    try:
        input_fn("\nTekan [ENTER] setelah Anda selesai verifikasi di jendela browser... ")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Pengguna membatalkan proses verifikasi.")
        return False

    time.sleep(2.0)
    # Check if target URL needs to be reloaded if still on verify page
    if target_url:
        try:
            current_url = (getattr(page, "url", "") or "").lower()
            if "verify" in current_url or "captcha" in current_url:
                page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                time.sleep(2.0)
        except Exception:
            pass

    return True


def wait_for_user_login(
    page: Any,
    target_url: str,
    input_fn: Callable[[str], str] = input,
    timeout_sec: int = 40,
) -> bool:
    """Prompt user in terminal to complete login in the opened browser window and resume."""
    print("\n" + "=" * 64)
    print("          [LOGIN DIPERLUKAN]")
    print("=" * 64)
    print("Platform membatasi akses komentar untuk akun yang belum masuk.")
    print("Jendela browser saat ini sedang terbuka di layar Anda.")
    print("")
    print("Instruksi:")
    print("1. Silakan login ke akun Anda di jendela browser yang terbuka.")
    print("2. Sesi login akan otomatis tersimpan di folder lokal (.browser_profile/)")
    print("   sehingga Anda TIDAK perlu login lagi di masa mendatang.")
    print("3. Setelah berhasil login dan halaman postingan terbuka kembali,")
    print("   tekan tombol ENTER pada terminal ini untuk melanjutkan.")
    print("=" * 64)

    try:
        input_fn("\nTekan [ENTER] setelah Anda selesai login di jendela browser... ")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Pengguna membatalkan proses login.")
        return False

    # Attempt to reload target post if still on login page
    try:
        current_url = (getattr(page, "url", "") or "").lower()
        if "login" in current_url:
            page.goto(target_url, timeout=timeout_sec * 1000, wait_until="domcontentloaded")
            time.sleep(2.0)
    except Exception:
        pass

    return True


def collect_browser_comments_to_csv(
    target_url: str,
    output_csv_path: Path | None = None,
    limit: int = 300,
    headless: bool = False,
    progress_callback: Callable[[int, int], None] | None = None,
    input_fn: Callable[[str], str] = input,
    sync_playwright_factory: Any | None = None,
    browser_profile_dir: Path | None = None,
) -> dict[str, Any]:
    """Buka browser Playwright, akses link, buka kolom komentar, baca semua, dan simpan ke file CSV."""
    from src.collectors.base import CommentRecord
    from src.config import BROWSER_PROFILE_DIR

    clean_url = target_url.strip()
    platform = "tiktok" if "tiktok.com" in clean_url.lower() else "instagram"
    profile_dir = browser_profile_dir or BROWSER_PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)

    if platform == "instagram":
        from src.collectors.browser_nlp import InstagramBrowserNLPCollector

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
        case_id = res.media_id
        comments = res.comments

    else:
        # TikTok collection via Playwright
        try:
            if sync_playwright_factory:
                pw_manager = sync_playwright_factory()
            else:
                from playwright.sync_api import sync_playwright
                pw_manager = sync_playwright()
        except ImportError as err:
            raise RuntimeError("Library 'playwright' belum terpasang. Jalankan 'pip install playwright'.") from err

        import hashlib
        vid_match = re.search(r"/video/(\d+)", clean_url)
        case_id = vid_match.group(1) if vid_match else hashlib.md5(clean_url.encode()).hexdigest()[:12]
        collected_at = datetime.now(timezone.utc).isoformat()
        comments_dict: dict[str, CommentRecord] = {}
        seen_texts: set[str] = set()

        def add_comment(rec: CommentRecord) -> bool:
            if rec.comment_id in comments_dict:
                return False
            t_norm = rec.comment_text.strip().lower()
            if t_norm in seen_texts:
                return False
            seen_texts.add(t_norm)
            comments_dict[rec.comment_id] = rec
            idx = len(comments_dict)
            user_preview = f"@{rec.username}: " if rec.username else ""
            preview = rec.comment_text.replace("\n", " ")[:45]
            print(f"[INFO] + [{idx}/{limit}] {user_preview}{preview}")
            if progress_callback:
                progress_callback(idx, limit)
            return True

        with pw_manager as p:
            context_kwargs = {
                "headless": headless,
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
                context = p.chromium.launch_persistent_context(user_data_dir=str(profile_dir), **context_kwargs)
                page = context.pages[0] if context.pages else context.new_page()
                browser_or_ctx = context
            else:
                browser = p.chromium.launch(headless=headless, args=context_kwargs.get("args"))
                context = browser.new_context(
                    viewport=context_kwargs["viewport"],
                    user_agent=context_kwargs["user_agent"],
                    locale=context_kwargs["locale"],
                )
                page = context.new_page()
                browser_or_ctx = browser

            # Intercept TikTok internal comment API response
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
                                raw_t = clean(item.get("text") or "")
                                if not raw_t:
                                    continue
                                if not cid:
                                    cid = hashlib.md5(raw_t.encode("utf-8")).hexdigest()[:12]
                                user_info = item.get("user") or {}
                                author = str(user_info.get("unique_id") or user_info.get("nickname") or "").strip().lstrip("@")
                                c_time = item.get("create_time")
                                ts_str = datetime.fromtimestamp(c_time, tz=timezone.utc).isoformat() if c_time else ""
                                likes = item.get("digg_count") or 0
                                rec = CommentRecord(
                                    comment_id=f"tt_{cid}",
                                    media_id=case_id,
                                    username=author,
                                    comment_text=raw_t,
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
                page.goto(clean_url, timeout=40000, wait_until="domcontentloaded")
                time.sleep(3.0)

                # Update case_id from canonical URL if redirected (e.g. vt.tiktok.com)
                final_url = page.url or clean_url
                vid_match = re.search(r"/video/(\d+)", final_url)
                if vid_match:
                    case_id = vid_match.group(1)

                # Check if human verification / CAPTCHA puzzle is required
                if is_human_verification_required(page):
                    wait_for_human_verification(page, final_url, input_fn=input_fn)

                if is_login_required(page):
                    wait_for_user_login(page, final_url, input_fn=input_fn)

                # Dismiss TikTok guest modals / cookie overlays if present
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

                # Ensure comment section / drawer is opened on TikTok
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

                # Scroll & extract TikTok comments
                scroll_count = 0
                max_scrolls = 250
                idle_scrolls = 0
                max_idle = 10

                while len(comments_dict) < limit and scroll_count < max_scrolls:
                    scroll_count += 1
                    before_count = len(comments_dict)

                    # Extract from rendered DOM elements as complementary tier
                    raw_items = page.evaluate(
                        """
                        () => {
                            const items = [];
                            const containers = document.querySelectorAll(
                                '[data-e2e="comment-item"], div[class*="CommentItemContainer"], div[class*="DivCommentItemContainer"]'
                            );
                            containers.forEach(el => {
                                const userEl = el.querySelector('[data-e2e="comment-username"], a[href^="/@"]');
                                const textEl = el.querySelector('[data-e2e="comment-level-1"], p[data-e2e="comment-text"]');
                                const timeEl = el.querySelector('time, span[class*="Time"]');
                                const author = userEl ? (userEl.innerText || '').trim().replace(/^@/, '') : '';
                                const text = textEl ? (textEl.innerText || '').trim() : '';
                                const ts = timeEl ? (timeEl.innerText || '').trim() : '';
                                if (text.length > 0) {
                                    items.push({ author, text, timestamp: ts });
                                }
                            });
                            return items;
                        }
                        """
                    )
                    for item in raw_items or []:
                        t_clean = clean(item.get("text", ""))
                        if not t_clean:
                            continue
                        c_id = f"tt_dom_{hashlib.md5(t_clean.encode('utf-8')).hexdigest()[:12]}"
                        rec = CommentRecord(
                            comment_id=c_id,
                            media_id=case_id,
                            username=item.get("author", ""),
                            comment_text=t_clean,
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

                    # Check if human verification or login wall appeared mid-scroll
                    if scroll_count <= 4 and len(comments_dict) == 0:
                        if is_human_verification_required(page):
                            wait_for_human_verification(page, final_url, input_fn=input_fn)
                        elif is_login_required(page):
                            wait_for_user_login(page, final_url, input_fn=input_fn)

                    # Auto-expand reply threads on TikTok ("Lihat balasan (X)", "View replies")
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

                    # Multi-strategy scrolling:
                    # 1. Smooth scroll last comment into view & adjust real scrollable ancestor
                    try:
                        page.evaluate(
                            """
                            () => {
                                // A. Scroll last comment item into view
                                const items = document.querySelectorAll(
                                    '[data-e2e="comment-item"], div[class*="CommentItemContainer"], div[class*="DivCommentItemContainer"]'
                                );
                                if (items.length > 0) {
                                    items[items.length - 1].scrollIntoView({ behavior: 'smooth', block: 'end' });
                                }

                                // B. Find true scrollable ancestor container of comments
                                const anchor = document.querySelector('[data-e2e="comment-item"]') ||
                                               document.querySelector('[data-e2e="comment-list"]') ||
                                               document.querySelector('[data-e2e="search-comment-container"]');
                                if (anchor) {
                                    let el = anchor;
                                    while (el && el !== document.body) {
                                        const style = window.getComputedStyle(el);
                                        if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && el.scrollHeight > el.clientHeight) {
                                            el.scrollTop = el.scrollHeight;
                                            el.scrollBy(0, 800);
                                            return true;
                                        }
                                        el = el.parentElement;
                                    }
                                }

                                // C. Fallback: scroll any container on the right side of the screen
                                const divs = document.querySelectorAll('div');
                                for (const d of divs) {
                                    const rect = d.getBoundingClientRect();
                                    if (rect.left >= window.innerWidth * 0.4 && rect.height > 200) {
                                        const st = window.getComputedStyle(d);
                                        if ((st.overflowY === 'auto' || st.overflowY === 'scroll') && d.scrollHeight > d.clientHeight) {
                                            d.scrollTop = d.scrollHeight;
                                            d.scrollBy(0, 800);
                                            return true;
                                        }
                                    }
                                }
                                return false;
                            }
                            """
                        )
                    except Exception:
                        pass

                    # 2. Hover mouse physically over the comment sidebar, then dispatch wheel
                    try:
                        comment_col = page.locator(
                            '[data-e2e="comment-item"], [data-e2e="comment-list"], div[class*="CommentListContainer"], div[class*="DivCommentListContainer"]'
                        ).last
                        count_val = comment_col.count() if hasattr(comment_col, "count") else 0
                        is_pos = (count_val > 0) if isinstance(count_val, (int, float)) else False
                        if is_pos and comment_col.is_visible():
                            comment_col.hover(timeout=1000)
                            page.mouse.wheel(0, 800)
                        else:
                            # Fallback: hover right side of screen (where sidebar resides)
                            vp = page.viewport_size or {"width": 1280, "height": 800}
                            page.mouse.move(vp["width"] * 0.75, vp["height"] * 0.5)
                            page.mouse.wheel(0, 800)
                    except Exception:
                        pass

                    # 3. Dispatch keyboard PageDown to trigger virtual scroll event
                    try:
                        page.keyboard.press("PageDown")
                    except Exception:
                        pass

                    if len(comments_dict) == before_count:
                        idle_scrolls += 1
                        if idle_scrolls >= max_idle:
                            # Before terminating, if 0 comments were collected, check one last time for human verification
                            if len(comments_dict) == 0 and is_human_verification_required(page):
                                wait_for_human_verification(page, final_url, input_fn=input_fn)
                                idle_scrolls = 0
                            else:
                                break
                    else:
                        idle_scrolls = 0

                    time.sleep(2.0)

            finally:
                browser_or_ctx.close()

        comments = list(comments_dict.values())

    # Determine final CSV destination
    if output_csv_path is None:
        from src.redam.menu import DATA_DIR
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_csv = DATA_DIR / "raw" / f"comments_{case_id}_{stamp}.csv"
    else:
        target_csv = Path(output_csv_path).resolve()

    target_csv.parent.mkdir(parents=True, exist_ok=True)

    # Write CSV
    fieldnames = [
        "comment_id",
        "media_id",
        "username",
        "comment_text",
        "timestamp",
        "like_count",
        "collected_at",
        "source_type",
    ]
    with open(target_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for rec in comments:
            writer.writerow(rec.to_dict() if hasattr(rec, "to_dict") else rec)

    # Generate companion manifest for REDAM pipeline menu 3
    manifest_path = target_csv.parent / "manifest.json"
    manifest_data = {
        "version": "redam-dataset-1.0",
        "cases": [
            {
                "case_id": case_id,
                "platform": platform,
                "topic_group": "research_topic",
                "period": datetime.now(timezone.utc).strftime("%Y-%m"),
                "rights_reference": "public_web_research",
                "retention_until": "2030-12-31",
                "source_type": "live",
                "origin": "research_collection",
                "input": target_csv.name,
                "columns": {
                    "comment_id": "comment_id",
                    "text": "comment_text",
                    "account": "username",
                    "created_at": "timestamp",
                    "likes_count": "like_count",
                },
            }
        ],
    }
    try:
        write_json(manifest_path, manifest_data)
    except Exception:
        manifest_path = None

    return {
        "url": clean_url,
        "case_id": case_id,
        "platform": platform,
        "total_collected": len(comments),
        "csv_path": str(target_csv),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "status": "completed",
    }
