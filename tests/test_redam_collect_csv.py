"""Unit tests for REDAM direct browser comments collection to CSV."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.collectors.base import CollectionResult, CommentRecord
from src.redam.collect import (
    collect_browser_comments_to_csv,
    is_human_verification_required,
    is_login_required,
    wait_for_human_verification,
    wait_for_user_login,
)
from src.redam.menu import run_menu


class TestRedamCollectCSV(unittest.TestCase):
    """Test suite for direct Playwright browser comments collection to CSV in REDAM menu."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_is_login_required_detection(self) -> None:
        """Verify login barrier detection for Instagram and TikTok."""
        mock_page = MagicMock()

        # 1. Login URL
        mock_page.url = "https://www.instagram.com/accounts/login/?next=/p/xyz"
        self.assertTrue(is_login_required(mock_page))

        mock_page.url = "https://www.tiktok.com/login"
        self.assertTrue(is_login_required(mock_page))

        # 2. Evaluate barrier
        mock_page.url = "https://www.instagram.com/p/DeRfCHemNKL/"
        mock_page.evaluate.return_value = True
        self.assertTrue(is_login_required(mock_page))

        # 3. No barrier
        mock_page.evaluate.return_value = False
        self.assertFalse(is_login_required(mock_page))

    def test_wait_for_user_login_pauses_and_resumes(self) -> None:
        """Verify interactive login gate prompts user and resumes on Enter."""
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/accounts/login/"
        dummy_input = iter(["\n"])

        success = wait_for_user_login(
            page=mock_page,
            target_url="https://www.instagram.com/p/DeRfCHemNKL/",
            input_fn=lambda _: next(dummy_input),
        )
        self.assertTrue(success)
        mock_page.goto.assert_called_once()

    def test_wait_for_user_login_handles_cancel(self) -> None:
        """Verify interactive login gate handles user cancellation (Ctrl+C)."""
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/accounts/login/"

        def raise_interrupt(_: str) -> str:
            raise KeyboardInterrupt()

        success = wait_for_user_login(
            page=mock_page,
            target_url="https://www.instagram.com/p/DeRfCHemNKL/",
            input_fn=raise_interrupt,
        )
        self.assertFalse(success)

    def test_is_human_verification_required_detection(self) -> None:
        """Verify detection of TikTok human verification / captcha barriers."""
        mock_page = MagicMock()

        # 1. URL based detection
        mock_page.url = "https://www.tiktok.com/verify/?secsdk=1"
        self.assertTrue(is_human_verification_required(mock_page))

        mock_page.url = "https://www.tiktok.com/captcha/slider"
        self.assertTrue(is_human_verification_required(mock_page))

        # 2. Evaluate DOM container/text based detection
        mock_page.url = "https://www.tiktok.com/@user/video/12345"
        mock_page.evaluate.return_value = True
        self.assertTrue(is_human_verification_required(mock_page))

        mock_page.evaluate.return_value = False
        self.assertFalse(is_human_verification_required(mock_page))

    def test_wait_for_human_verification_pauses_and_resumes(self) -> None:
        """Verify wait_for_human_verification pauses until user presses enter in terminal."""
        mock_page = MagicMock()
        mock_page.url = "https://www.tiktok.com/verify/"
        dummy_input = iter(["\n"])

        success = wait_for_human_verification(
            page=mock_page,
            target_url="https://www.tiktok.com/@user/video/12345",
            input_fn=lambda _: next(dummy_input),
        )
        self.assertTrue(success)
        mock_page.goto.assert_called_once()

    def test_wait_for_human_verification_handles_cancel(self) -> None:
        """Verify wait_for_human_verification handles user cancellation cleanly."""
        mock_page = MagicMock()
        mock_page.url = "https://www.tiktok.com/verify/"

        def raise_interrupt(_: str) -> str:
            raise KeyboardInterrupt()

        success = wait_for_human_verification(
            page=mock_page,
            target_url="https://www.tiktok.com/@user/video/12345",
            input_fn=raise_interrupt,
        )
        self.assertFalse(success)

    def test_collect_browser_comments_to_csv_instagram(self) -> None:
        """Verify Instagram collection writes standard CSV and companion manifest."""
        csv_dest = self.test_dir / "comments_ig_test.csv"

        # Mock InstagramBrowserNLPCollector
        mock_collector = MagicMock()
        dummy_comments = [
            CommentRecord(
                comment_id="c_001",
                media_id="DeRfCHemNKL",
                username="anwaribrahim_my",
                comment_text="Belanjawan 2027 untuk semua rakyat Malaysia.",
                timestamp="2026-10-29T10:00:00Z",
                like_count=150,
                collected_at="2026-11-06T12:00:00Z",
                source_type="browser_nlp",
            ),
            CommentRecord(
                comment_id="c_002",
                media_id="DeRfCHemNKL",
                username="rakyat_madani",
                comment_text="Mantap sekali PMX!",
                timestamp="2026-10-29T10:05:00Z",
                like_count=45,
                collected_at="2026-11-06T12:00:00Z",
                source_type="browser_nlp",
            ),
        ]
        mock_collector.collect_comments.return_value = CollectionResult(
            media_id="DeRfCHemNKL",
            comments=dummy_comments,
            total_collected=2,
            unique_collected=2,
            status="completed",
            paging_completed=True,
        )

        with patch("src.collectors.browser_nlp.InstagramBrowserNLPCollector", return_value=mock_collector):
            result = collect_browser_comments_to_csv(
                target_url="https://www.instagram.com/p/DeRfCHemNKL/",
                output_csv_path=csv_dest,
                limit=10,
                headless=True,
            )

        self.assertEqual(result["total_collected"], 2)
        self.assertEqual(result["case_id"], "DeRfCHemNKL")
        self.assertEqual(result["platform"], "instagram")
        self.assertTrue(csv_dest.exists())

        # Check CSV content & columns
        with open(csv_dest, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        self.assertEqual(len(reader), 2)
        expected_cols = [
            "comment_id",
            "media_id",
            "username",
            "comment_text",
            "timestamp",
            "like_count",
            "collected_at",
            "source_type",
        ]
        self.assertEqual(list(reader[0].keys()), expected_cols)
        self.assertEqual(reader[0]["username"], "anwaribrahim_my")
        self.assertEqual(reader[1]["comment_text"], "Mantap sekali PMX!")

        # Check companion manifest
        manifest_path = csv_dest.parent / "manifest.json"
        self.assertTrue(manifest_path.exists())
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest_data["cases"][0]["input"], csv_dest.name)
        self.assertEqual(manifest_data["cases"][0]["platform"], "instagram")

    def test_collect_browser_comments_to_csv_tiktok_mock(self) -> None:
        """Verify TikTok collection flow with mocked Playwright."""
        csv_dest = self.test_dir / "comments_tt_test.csv"

        mock_page = MagicMock()
        mock_page.url = "https://www.tiktok.com/@user/video/7123456789012345678"
        def mock_eval(script, *args):
            if "secsdk" in script or "captcha" in script:
                return False
            if 'input[name="password"]' in script or "Masuk untuk melihat" in script:
                return False
            if "CommentItemContainer" in script:
                return [
                    {"author": "toktok_user1", "text": "Keren banget videonya!", "timestamp": "2d ago"},
                    {"author": "toktok_user2", "text": "Setuju parah sih ini 🔥", "timestamp": "1d ago"},
                ]
            return None
        mock_page.evaluate.side_effect = mock_eval
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_pw = MagicMock()
        mock_pw.chromium.launch_persistent_context.return_value = mock_context
        mock_pw.chromium.launch.return_value = mock_browser

        mock_factory = MagicMock()
        mock_factory.return_value.__enter__.return_value = mock_pw

        result = collect_browser_comments_to_csv(
            target_url="https://www.tiktok.com/@user/video/7123456789012345678",
            output_csv_path=csv_dest,
            limit=2,
            headless=True,
            sync_playwright_factory=mock_factory,
        )

        self.assertEqual(result["platform"], "tiktok")
        self.assertEqual(result["case_id"], "7123456789012345678")
        self.assertEqual(result["total_collected"], 2)
        self.assertTrue(csv_dest.exists())

        with open(csv_dest, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["username"], "toktok_user1")
        self.assertEqual(rows[0]["source_type"], "browser_tiktok")

    def test_collect_browser_comments_to_csv_tiktok_network_interception(self) -> None:
        """Verify TikTok network API response interception extracts comments cleanly."""
        csv_dest = self.test_dir / "comments_tt_api.csv"

        mock_page = MagicMock()
        mock_page.url = "https://www.tiktok.com/@creator/video/9988776655443322110"
        def mock_eval_api(script, *args):
            if "secsdk" in script or "captcha" in script:
                return False
            if 'input[name="password"]' in script or "Masuk untuk melihat" in script:
                return False
            if "CommentItemContainer" in script:
                return []
            return None
        mock_page.evaluate.side_effect = mock_eval_api

        registered_handlers: dict[str, list] = {}
        def mock_on(event: str, handler):
            registered_handlers.setdefault(event, []).append(handler)
        mock_page.on.side_effect = mock_on

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_pw = MagicMock()
        mock_pw.chromium.launch_persistent_context.return_value = mock_context

        mock_factory = MagicMock()
        mock_factory.return_value.__enter__.return_value = mock_pw

        # Trigger network response event during goto
        def trigger_response(*args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.url = "https://www.tiktok.com/api/comment/list/?aid=1988&aweme_id=9988776655443322110"
            mock_resp.headers = {"content-type": "application/json; charset=utf-8"}
            mock_resp.json.return_value = {
                "comments": [
                    {
                        "cid": "7711223344",
                        "text": "Wajib tonton sampai habis guys!",
                        "user": {"unique_id": "api_user_1", "nickname": "User Satu"},
                        "create_time": 1730000000,
                        "digg_count": 88,
                    },
                    {
                        "cid": "7711223345",
                        "text": "Keren banget penjelasannya kak 👍",
                        "user": {"unique_id": "api_user_2", "nickname": "User Dua"},
                        "create_time": 1730000100,
                        "digg_count": 12,
                    },
                ]
            }
            for handler in registered_handlers.get("response", []):
                handler(mock_resp)

        mock_page.goto.side_effect = trigger_response

        result = collect_browser_comments_to_csv(
            target_url="https://vt.tiktok.com/ZSjShortLink/",
            output_csv_path=csv_dest,
            limit=2,
            headless=True,
            sync_playwright_factory=mock_factory,
        )

        self.assertEqual(result["platform"], "tiktok")
        self.assertEqual(result["case_id"], "9988776655443322110")
        self.assertEqual(result["total_collected"], 2)
        self.assertTrue(csv_dest.exists())

        with open(csv_dest, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["comment_id"], "tt_7711223344")
        self.assertEqual(rows[0]["username"], "api_user_1")
        self.assertEqual(rows[0]["comment_text"], "Wajib tonton sampai habis guys!")
        self.assertEqual(rows[0]["like_count"], "88")

    def test_tiktok_scrolling_and_reply_expansion_behavior(self) -> None:
        """Verify TikTok multi-strategy scrolling and reply expansion are executed during collection."""
        csv_dest = self.test_dir / "comments_tt_scroll.csv"

        mock_page = MagicMock()
        mock_page.url = "https://www.tiktok.com/@creator/video/112233445566"
        mock_page.viewport_size = {"width": 1280, "height": 800}

        calls = []
        def mock_eval_scroll(script, *args):
            if "secsdk" in script or "captcha" in script:
                return False
            if 'input[name="password"]' in script or "Masuk untuk melihat" in script:
                return False
            if "CommentItemContainer" in script and "scroll" not in script:
                calls.append("dom_extract")
                # return 1 comment per call up to 2
                if len(calls) == 1:
                    return [{"author": "user_a", "text": "Komentar satu", "timestamp": "1h"}]
                return [{"author": "user_b", "text": "Komentar dua", "timestamp": "2h"}]
            if "scrollIntoView" in script:
                calls.append("dom_scroll")
                return True
            return None

        mock_page.evaluate.side_effect = mock_eval_scroll

        # Mock reply button
        mock_reply_btn = MagicMock()
        mock_reply_btn.is_visible.return_value = True
        mock_reply_locator = MagicMock()
        mock_reply_locator.count.return_value = 1
        mock_reply_locator.nth.return_value = mock_reply_btn

        def mock_locator(selector):
            if "view-more-replies" in selector or "Lihat balasan" in selector:
                return mock_reply_locator
            loc = MagicMock()
            loc.count.return_value = 0
            loc.last = loc
            loc.is_visible.return_value = False
            return loc

        mock_page.locator.side_effect = mock_locator

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_pw = MagicMock()
        mock_pw.chromium.launch_persistent_context.return_value = mock_context

        mock_factory = MagicMock()
        mock_factory.return_value.__enter__.return_value = mock_pw

        result = collect_browser_comments_to_csv(
            target_url="https://www.tiktok.com/@creator/video/112233445566",
            output_csv_path=csv_dest,
            limit=2,
            headless=True,
            sync_playwright_factory=mock_factory,
        )

        self.assertEqual(result["total_collected"], 2)
        # Verify reply button was clicked
        mock_reply_btn.click.assert_called()
        # Verify mouse wheel was dispatched
        mock_page.mouse.wheel.assert_called()
        # Verify keyboard PageDown was dispatched
        mock_page.keyboard.press.assert_called_with("PageDown")

    def test_menu_8_option_2_direct_collection_flow(self) -> None:
        """Verify Menu 8 option 2 triggers direct browser collection to CSV and exits cleanly."""
        csv_path = self.test_dir / "menu8_direct.csv"
        mock_collect_result = {
            "url": "https://www.instagram.com/p/DeRfCHemNKL/",
            "case_id": "DeRfCHemNKL",
            "platform": "instagram",
            "total_collected": 15,
            "csv_path": str(csv_path),
            "manifest_path": str(self.test_dir / "manifest.json"),
            "status": "completed",
        }

        inputs = iter([
            "2",                                     # Option 2
            "https://www.instagram.com/p/DeRfCHemNKL/",  # URL
            "15",                                    # limit
            str(csv_path),                           # CSV path
            "0",                                     # exit menu
        ])

        with patch("src.redam.collect.collect_browser_comments_to_csv", return_value=mock_collect_result) as mock_fn:
            exit_code = run_menu(input_fn=lambda _: next(inputs), data_dir=self.test_dir)

        self.assertEqual(exit_code, 0)
        mock_fn.assert_called_once()
        args, kwargs = mock_fn.call_args
        self.assertEqual(kwargs["target_url"], "https://www.instagram.com/p/DeRfCHemNKL/")
        self.assertEqual(kwargs["limit"], 15)
        self.assertEqual(Path(kwargs["output_csv_path"]).resolve(), csv_path.resolve())

    def test_menu_8_option_2_cancel_on_zero_or_empty(self) -> None:
        """Verify Menu 8 option 2 cancels cleanly when 0 or empty string is entered."""
        inputs = iter(["2", "0", "2", "", "0"])
        exit_code = run_menu(input_fn=lambda _: next(inputs), data_dir=self.test_dir)
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
