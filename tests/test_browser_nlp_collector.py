"""Unit tests for InstagramBrowserNLPCollector."""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import MagicMock

from src.collectors.base import CollectorValidationError, CommentRecord
from src.collectors.browser_nlp import InstagramBrowserNLPCollector
from src.extractors.nlp_comment_extractor import NLPCommentExtractor


class TestInstagramBrowserNLPCollector(unittest.TestCase):
    """Test suite for Browser Automation & NLP Collector."""

    def setUp(self) -> None:
        self.extractor = NLPCommentExtractor()
        self.collector = InstagramBrowserNLPCollector(
            headless=True,
            extractor=self.extractor,
        )

    def test_resolve_media_id_valid_urls(self) -> None:
        """Verify standard post, reel, and direct shortcode formats."""
        self.assertEqual(
            self.collector.resolve_media_id("https://www.instagram.com/p/C_abc123xyz/"),
            "C_abc123xyz",
        )
        self.assertEqual(
            self.collector.resolve_media_id("https://instagram.com/reel/D_987654321/"),
            "D_987654321",
        )
        self.assertEqual(
            self.collector.resolve_media_id("C_abc123xyz"),
            "C_abc123xyz",
        )

    def test_resolve_media_id_invalid(self) -> None:
        """Invalid inputs must raise CollectorValidationError."""
        with self.assertRaises(CollectorValidationError):
            self.collector.resolve_media_id("")

        with self.assertRaises(CollectorValidationError):
            self.collector.resolve_media_id("https://www.instagram.com/explore/")

    def test_parse_graphql_comment_node(self) -> None:
        """Parse simulated GraphQL comment node correctly into CommentRecord."""
        node = {
            "id": "180099887766",
            "text": "Wkwkwk santuy bgt broo, mantap infonya!",
            "created_at": 1729000000,
            "comment_like_count": 8,
            "user": {"username": "andi_slang"},
        }

        record = self.collector._parse_graphql_comment_node(
            node=node,
            media_id="C_abc123xyz",
            collected_at="2026-10-29T12:00:00",
        )

        self.assertIsNotNone(record)
        self.assertEqual(record.comment_id, "180099887766")
        self.assertEqual(record.media_id, "C_abc123xyz")
        self.assertEqual(record.username, "andi_slang")
        self.assertEqual(record.comment_text, "Wkwkwk santuy bgt broo, mantap infonya!")
        self.assertEqual(record.like_count, 8)
        self.assertEqual(record.source_type, "browser_nlp")

    def test_filter_spam_in_graphql_node(self) -> None:
        """Spam comments in GraphQL stream must be rejected."""
        spam_node = {
            "id": "180011223344",
            "text": "Mau peninggi badan tercepat? Cek bio kak!",
            "comment_like_count": 0,
            "user": {"username": "olshop_spam"},
        }
        record = self.collector._parse_graphql_comment_node(
            node=spam_node,
            media_id="C_abc123xyz",
            collected_at="2026-10-29T12:00:00",
        )
        self.assertIsNone(record)

    def test_extract_nested_network_payload(self) -> None:
        """Test recursive discovery of comments in nested response."""
        payload = {
            "data": {
                "xdt_api__v1__media__comments": {
                    "edges": [
                        {
                            "node": {
                                "id": "1",
                                "text": "Gokil bgt nih!",
                                "user": {"username": "u1"},
                            }
                        },
                        {
                            "node": {
                                "id": "2",
                                "text": "🔥🔥🔥",  # pure emoji -> filtered out
                                "user": {"username": "u2"},
                            }
                        },
                        {
                            "node": {
                                "id": "3",
                                "text": "Kuyy gas pol besok",
                                "user": {"username": "u3"},
                            }
                        },
                    ]
                }
            }
        }
        extracted = self.collector._extract_comments_from_network_payload(
            payload=payload,
            media_id="TEST_MEDIA",
            collected_at="2026-10-29T12:00:00",
        )
        self.assertEqual(len(extracted), 2)
        self.assertEqual(extracted[0].comment_text, "Gokil bgt nih!")
        self.assertEqual(extracted[1].comment_text, "Kuyy gas pol besok")

    def test_mock_playwright_collection_flow(self) -> None:
        """Verify full collection orchestration with mocked Playwright objects."""
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/p/TEST_SHORTCODE/"
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context
        mock_playwright.chromium.launch.return_value = mock_browser

        mock_pw_factory = MagicMock()
        mock_pw_factory.return_value.__enter__.return_value = mock_playwright

        # Mock page DOM evaluation returning sample text blocks
        mock_page.evaluate.return_value = [
            "user1\nAnjir gokil bgt postingannya\n1 j\nBalas\n10 suka",
            "user2\n🔥🔥🔥\n2 j\nBalas",
        ]

        collector = InstagramBrowserNLPCollector(
            headless=True,
            sync_playwright_factory=mock_pw_factory,
            max_scroll_attempts=1,
            input_fn=lambda _: "\n",
        )

        result = collector.collect_comments(
            target="https://www.instagram.com/p/TEST_SHORTCODE/",
            limit=5,
        )

        self.assertEqual(result.media_id, "TEST_SHORTCODE")
        self.assertEqual(len(result.comments), 1)
        self.assertEqual(result.comments[0].username, "user1")
        self.assertEqual(result.comments[0].comment_text, "Anjir gokil bgt postingannya")
        self.assertEqual(result.comments[0].like_count, 10)
        self.assertEqual(result.comments[0].source_type, "browser_nlp")
        mock_page.goto.assert_called_once()
        mock_context.close.assert_called_once()

    def test_expand_reply_threads(self) -> None:
        """Verify reply threads are expanded by evaluating DOM button click script."""
        mock_page = MagicMock()
        mock_page.evaluate.return_value = 3
        count = self.collector._expand_reply_threads(mock_page)
        self.assertEqual(count, 3)
        mock_page.evaluate.assert_called_once()

    def test_is_login_required_detection(self) -> None:
        """Verify login detection logic on login URL or barrier content."""
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/accounts/login/"
        self.assertTrue(self.collector.is_login_required(mock_page))

        mock_page.url = "https://www.instagram.com/p/DFxyz123/"
        mock_page.evaluate.return_value = True
        self.assertTrue(self.collector.is_login_required(mock_page))

        mock_page.evaluate.return_value = False
        self.assertFalse(self.collector.is_login_required(mock_page))

    def test_wait_for_user_login(self) -> None:
        """Verify interactive login gate pauses and navigates back to post URL."""
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/accounts/login/"
        dummy_inputs = iter(["\n"])

        success = self.collector.wait_for_user_login(
            page=mock_page,
            post_url="https://www.instagram.com/p/DFxyz123/",
            input_fn=lambda _: next(dummy_inputs),
        )
        self.assertTrue(success)
        mock_page.goto.assert_called_once()

    def test_open_interactive_login(self) -> None:
        """Verify dedicated interactive login setup method."""
        mock_page = MagicMock()
        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context

        mock_pw_factory = MagicMock()
        mock_pw_factory.return_value.__enter__.return_value = mock_playwright

        collector = InstagramBrowserNLPCollector(
            headless=False,
            sync_playwright_factory=mock_pw_factory,
        )

        dummy_inputs = iter(["\n"])
        success = collector.open_interactive_login(input_fn=lambda _: next(dummy_inputs))

        self.assertTrue(success)
        mock_page.goto.assert_called_with(
            "https://www.instagram.com/accounts/login/",
            timeout=collector.timeout_ms,
        )
        mock_context.close.assert_called_once()


    def test_expand_reply_threads_locator_clicks_and_regex_variants(self) -> None:
        """Verify JS reply regexes cover View more/all variants and click via Playwright locators."""
        import re
        from unittest.mock import MagicMock, patch

        mock_page = MagicMock()
        mock_page.evaluate.return_value = 2
        mock_loc = MagicMock()
        mock_loc.first.count.return_value = 1
        mock_page.locator.return_value = mock_loc

        with patch("src.collectors.browser_nlp.time.sleep"):
            count = self.collector._expand_reply_threads(mock_page)

        self.assertEqual(count, 2)
        mock_page.locator.assert_any_call('[data-nlp-expand-id="nlp_reply_0"]')
        mock_page.locator.assert_any_call('[data-nlp-expand-id="nlp_reply_1"]')
        self.assertEqual(mock_loc.first.click.call_count, 2)

        js_script = mock_page.evaluate.call_args[0][0]
        hide_m = re.search(r"const hideRegex = /(.*?)/([a-z]*);", js_script)
        en_m = re.search(r"const enReplyRegex = /(.*?)/([a-z]*);", js_script)
        id_m = re.search(r"const idReplyRegex = /(.*?)/([a-z]*);", js_script)
        more_m = re.search(r"const idMoreRegex = /(.*?)/([a-z]*);", js_script)
        self.assertIsNotNone(hide_m)
        self.assertIsNotNone(en_m)
        self.assertIsNotNone(id_m)
        self.assertIsNotNone(more_m)

        hide_re = re.compile(hide_m.group(1), re.IGNORECASE)
        expand_res = [
            re.compile(en_m.group(1), re.IGNORECASE),
            re.compile(id_m.group(1), re.IGNORECASE),
            re.compile(more_m.group(1), re.IGNORECASE),
        ]

        def norm(raw: str) -> str:
            collapsed = re.sub(r"\s+", " ", raw).strip()
            return re.sub(r"^[\-\u2013\u2014\u2015\u2500\u2022\u00b7\s]+", "", collapsed).strip()

        for positive in [
            "View replies",
            "View replies (3)",
            "―― View more replies",
            "― View 5 more replies",
            "View all 12 replies",
            "View previous replies",
            "Lihat balasan",
            "Lihat semua 5 balasan",
            "Lihat balasan lainnya",
            "Lihat 3 lagi",
        ]:
            cleaned = norm(positive)
            self.assertFalse(bool(hide_re.search(cleaned)), positive)
            self.assertTrue(any(r.search(cleaned) for r in expand_res), positive)

        for negative in [
            "Hide replies",
            "Hide all replies",
            "Sembunyikan balasan",
            "Tutup balasan",
            "View more comments",
        ]:
            cleaned = norm(negative)
            matched = (not hide_re.search(cleaned)) and any(r.search(cleaned) for r in expand_res)
            self.assertFalse(matched, negative)

    def test_expand_reply_threads_locator_fallback_to_js_click(self) -> None:
        """If Playwright .click() fails, fallback to element.evaluate('el => el.click()')."""
        from unittest.mock import MagicMock, patch

        mock_page = MagicMock()
        mock_page.evaluate.return_value = 1
        mock_loc = MagicMock()
        mock_loc.first.count.return_value = 1
        mock_loc.first.click.side_effect = RuntimeError("intercepted")
        mock_page.locator.return_value = mock_loc

        with patch("src.collectors.browser_nlp.time.sleep"):
            count = self.collector._expand_reply_threads(mock_page)

        self.assertEqual(count, 1)
        mock_loc.first.evaluate.assert_called_once_with("el => el.click()")

    def test_parse_graphql_comment_node_handles_null_user(self) -> None:
        """GraphQL parser must handle node['user']=None without AttributeError."""
        node = {
            "pk": "998877",
            "text": "Balasan dari thread reply",
            "user": None,
            "owner": {"username": "penjawab_resmi"},
            "comment_like_count": None,
            "created_at": 1700000000,
        }
        parsed = self.collector._parse_graphql_comment_node(node, "ABC123", "2026-11-12T12:00:00")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.username, "penjawab_resmi")
        self.assertEqual(parsed.comment_text, "Balasan dari thread reply")
        self.assertEqual(parsed.like_count, 0)

    def test_collect_comments_multipass_expands_view_more_replies(self) -> None:
        """collect_comments must loop multi-pass reply expansion and extract opened replies before scrolling."""
        from unittest.mock import MagicMock, patch
        from src.collectors.browser_nlp import InstagramBrowserNLPCollector

        collector = InstagramBrowserNLPCollector(max_scroll_attempts=1, scroll_delay_sec=0.0)
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/p/TestPost1/"
        mock_page.locator.return_value.first.count.return_value = 0
        mock_page.query_selector_all.return_value = []

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_context.new_page.return_value = mock_page
        mock_browser = MagicMock()
        mock_browser.new_context.return_value = mock_context
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch.return_value = mock_browser
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_playwright
        mock_cm.__exit__.return_value = False

        dom_blocks_sequence = [
            ["alice\n1h\nKomentar induk bagus sekali\n1 like\nReply"],
            ["alice\n1h\nKomentar induk bagus sekali\n1 like\nReply", "bob\n50m\nBalasan pertama yang muncul\nReply"],
            [
                "alice\n1h\nKomentar induk bagus sekali\n1 like\nReply",
                "bob\n50m\nBalasan pertama yang muncul\nReply",
                "charlie\n10m\nBalasan lanjutan setelah View more replies diklik\nReply",
            ],
            [
                "alice\n1h\nKomentar induk bagus sekali\n1 like\nReply",
                "bob\n50m\nBalasan pertama yang muncul\nReply",
                "charlie\n10m\nBalasan lanjutan setelah View more replies diklik\nReply",
            ],
        ]
        dom_idx = {"i": 0}

        def fake_evaluate(script, *args):
            if "data-nlp-expand-id" in script:
                # Simulate 2 reply-expansion passes before exhausting View more replies
                return 1 if dom_idx["i"] <= 2 else 0
            if "scrolledInner" in script:
                return {"scrolledInner": True, "nearBottom": False}
            if "const blocks = []" in script:
                val = dom_blocks_sequence[min(dom_idx["i"], len(dom_blocks_sequence) - 1)]
                dom_idx["i"] += 1
                return val
            return 0

        mock_page.evaluate.side_effect = fake_evaluate

        # Allow _expand_reply_threads to observe count() == 1 on tagged elements
        expand_loc = MagicMock()
        expand_loc.first.count.return_value = 1

        def fake_locator(sel: str):
            if "data-nlp-expand-id" in sel:
                return expand_loc
            m = MagicMock()
            m.first.count.return_value = 0
            return m

        mock_page.locator.side_effect = fake_locator

        with patch("playwright.sync_api.sync_playwright", return_value=mock_cm), patch.object(
            collector, "is_login_required", return_value=False
        ), patch("src.collectors.browser_nlp.time.sleep"):
            result = collector.collect_comments("https://www.instagram.com/p/TestPost1/", limit=50)

        usernames = [c.username for c in result.comments]
        self.assertIn("alice", usernames)
        self.assertIn("bob", usernames)
        self.assertIn("charlie", usernames)
        self.assertEqual(len(result.comments), 3)


    def test_parse_human_count_formats(self) -> None:
        """Verify Indonesian/English number formatting and compact unit parsing."""
        self.assertEqual(self.collector.parse_human_count("1.135"), (1135, True))
        self.assertEqual(self.collector.parse_human_count("1,135"), (1135, True))
        self.assertEqual(self.collector.parse_human_count("1.135 komentar"), (1135, True))
        self.assertEqual(self.collector.parse_human_count("1,2 rb"), (1200, False))
        self.assertEqual(self.collector.parse_human_count("42,3 rb"), (42300, False))
        self.assertEqual(self.collector.parse_human_count("1.2K"), (1200, False))
        self.assertEqual(self.collector.parse_human_count("1,5 jt"), (1500000, False))
        self.assertEqual(self.collector.parse_human_count("850"), (850, True))
        self.assertEqual(self.collector.parse_human_count(""), (None, False))

    def test_extract_comment_count_from_payload_ignores_child_comment_count(self) -> None:
        """Verify GraphQL count parser targets media count and ignores single-comment child counts."""
        payload = {
            "data": {
                "xdt_shortcode_media": {
                    "shortcode": "DWmCs8KgB5-",
                    "comment_count": 1135,
                    "edge_media_to_parent_comment": {
                        "count": 1135,
                        "edges": [
                            {
                                "node": {
                                    "pk": "111",
                                    "text": "Komentar uji coba",
                                    "user": {"username": "tester"},
                                    "child_comment_count": 15,
                                }
                            }
                        ],
                    },
                }
            }
        }
        self.assertEqual(
            self.collector._extract_comment_count_from_payload(payload, "DWmCs8KgB5-"),
            1135,
        )

        # Single comment object without media metadata must return None
        comment_only_payload = {
            "pk": "111",
            "text": "Komentar saja",
            "user": {"username": "tester"},
            "child_comment_count": 22,
        }
        self.assertIsNone(
            self.collector._extract_comment_count_from_payload(comment_only_payload, "DWmCs8KgB5-")
        )

    def test_tolerance_calculation_1135_to_1125(self) -> None:
        """Verify reported count tolerance calculation matches 1135 -> 1125 and scales safely."""
        from src.collectors.browser_nlp import InstagramBrowserNLPCollector

        collector = InstagramBrowserNLPCollector(comment_tolerance=10)
        self.assertEqual(collector._compute_tolerance_target(1135, True, 3000), (1135, 1125))
        self.assertEqual(collector._compute_tolerance_target(100, True, 3000), (100, 95))
        self.assertEqual(collector._compute_tolerance_target(15, True, 3000), (15, 14))
        # Lower explicit user limit must still cap effective goal
        self.assertEqual(collector._compute_tolerance_target(1135, True, 500), (500, 490))
        # Approximate abbreviated count uses >= 5% margin
        self.assertEqual(collector._compute_tolerance_target(1200, False, 3000), (1200, 1140))

    def test_nlp_filter_preserves_rejection_and_tracks_coverage(self) -> None:
        """Pure emoji, punctuation, too-short, and promo spam are rejected from CSV while tracked in raw_encountered."""
        from unittest.mock import MagicMock, patch
        from src.collectors.browser_nlp import InstagramBrowserNLPCollector

        collector = InstagramBrowserNLPCollector(max_scroll_attempts=1, scroll_delay_sec=0.0)
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/p/DWmCs8KgB5-/"
        mock_page.locator.return_value.first.count.return_value = 0
        mock_page.query_selector_all.return_value = []

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_context.new_page.return_value = mock_page
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_playwright
        mock_cm.__exit__.return_value = False

        dom_blocks = [
            "user1\n1j\nKomentar valid gokil bgt min\nBalas",
            "user2\n1j\n😂😂😂 🔥🔥\nBalas",
            "user3\n1j\n...\nBalas",
            "user4\n1j\na\nBalas",
            "user5\n1j\nSlot gacor maxwin zeus pragmatic\nBalas",
        ]

        def fake_evaluate(script, *args):
            if "metaTexts" in script:
                return {"candidates": ["1.135"], "metaTexts": []}
            if "const blocks = []" in script:
                return dom_blocks
            if "scrolledInner" in script:
                return {"scrolledInner": True, "nearBottom": True}
            return 0

        mock_page.evaluate.side_effect = fake_evaluate

        with patch("playwright.sync_api.sync_playwright", return_value=mock_cm), patch.object(
            collector, "is_login_required", return_value=False
        ), patch("src.collectors.browser_nlp.time.sleep"):
            result = collector.collect_comments("https://www.instagram.com/reel/DWmCs8KgB5-/", limit=3000)

        self.assertEqual(result.reported_total, 1135)
        self.assertEqual(result.tolerance_target, 1125)
        self.assertEqual(len(result.comments), 1)
        self.assertEqual(result.comments[0].username, "user1")
        self.assertEqual(result.raw_encountered, 5)
        self.assertEqual(result.filtered_out_count, 4)
        self.assertEqual(result.rejection_breakdown.get("no_alphanumeric_content"), 2)
        self.assertEqual(result.rejection_breakdown.get("too_short"), 1)
        self.assertEqual(result.rejection_breakdown.get("commercial_or_bot_spam"), 1)
        self.assertFalse(result.coverage_reached)

    def test_author_aware_dedup_keeps_identical_text_from_different_users(self) -> None:
        """Identical text comments from distinct authors must both be preserved while same-author duplicates dedup."""
        from unittest.mock import MagicMock, patch
        from src.collectors.browser_nlp import InstagramBrowserNLPCollector

        collector = InstagramBrowserNLPCollector(max_scroll_attempts=1, scroll_delay_sec=0.0)
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/p/TestDedup1/"
        mock_page.locator.return_value.first.count.return_value = 0
        mock_page.query_selector_all.return_value = []

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_playwright
        mock_cm.__exit__.return_value = False

        dom_blocks = [
            "ali_akun\n1j\nSetuju sekali!\nBalas",
            "budi_akun\n2j\nSetuju sekali!\nBalas",
            "ali_akun\n1j\nSetuju sekali!\nBalas",
        ]

        def fake_evaluate(script, *args):
            if "const blocks = []" in script:
                return dom_blocks
            return 0

        mock_page.evaluate.side_effect = fake_evaluate

        with patch("playwright.sync_api.sync_playwright", return_value=mock_cm), patch.object(
            collector, "is_login_required", return_value=False
        ), patch("src.collectors.browser_nlp.time.sleep"):
            result = collector.collect_comments("https://www.instagram.com/p/TestDedup1/", limit=50)

        self.assertEqual(len(result.comments), 2)
        self.assertEqual([c.username for c in result.comments], ["ali_akun", "budi_akun"])

    def test_deep_recovery_sweep_triggers_when_below_tolerance(self) -> None:
        """When scroll stalls below tolerance_target, collector runs bounded recovery sweeps before exiting."""
        from unittest.mock import MagicMock, patch
        from src.collectors.browser_nlp import InstagramBrowserNLPCollector

        collector = InstagramBrowserNLPCollector(
            max_scroll_attempts=20,
            scroll_delay_sec=0.0,
            max_recovery_sweeps=2,
        )
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/p/TestRecov1/"
        mock_page.locator.return_value.first.count.return_value = 0
        mock_page.query_selector_all.return_value = []

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context

        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_playwright
        mock_cm.__exit__.return_value = False

        sweep_count = {"n": 0}

        def fake_evaluate(script, *args):
            if "metaTexts" in script:
                return {"candidates": ["1.135"], "metaTexts": []}
            if "const blocks = []" in script:
                if sweep_count["n"] >= 1:
                    return [
                        "ali_awal\n1j\nKomentar awal sebelum macet\nBalas",
                        "budi_pulih\n5m\nKomentar baru setelah recovery sweep\nBalas",
                    ]
                return ["ali_awal\n1j\nKomentar awal sebelum macet\nBalas"]
            if "scrolledInner" in script:
                return {"scrolledInner": True, "nearBottom": True}
            return 0

        mock_page.evaluate.side_effect = fake_evaluate

        def track_sweep(page, idx):
            sweep_count["n"] += 1

        with patch("playwright.sync_api.sync_playwright", return_value=mock_cm), patch.object(
            collector, "is_login_required", return_value=False
        ), patch.object(
            collector, "_perform_recovery_sweep", side_effect=track_sweep
        ) as mock_sweep, patch("src.collectors.browser_nlp.time.sleep"):
            result = collector.collect_comments("https://www.instagram.com/p/TestRecov1/", limit=3000)

        self.assertEqual(mock_sweep.call_count, 2)
        self.assertEqual(len(result.comments), 2)
        self.assertEqual(result.reported_total, 1135)
        self.assertEqual(result.tolerance_target, 1125)
        self.assertFalse(result.coverage_reached)

    def test_extract_comment_count_and_comments_ignore_feed_timeline_and_foreign_media(self) -> None:
        """Feed timeline recommendations and foreign shortcodes must not overwrite target count or inject comments."""
        collector = InstagramBrowserNLPCollector()
        payload = {
            "data": {
                "xdt_api__v1__feed__timeline__connection": {
                    "edges": [
                        {
                            "node": {
                                "explore_story": {
                                    "media": {
                                        "code": "Dfm6PAPSgCn",
                                        "media_type": 2,
                                        "comment_count": 2328,
                                        "comments": [
                                            {
                                                "pk": "9991",
                                                "text": "Komentar dari feed post orang lain",
                                                "user": {"username": "foreign_user"},
                                            }
                                        ],
                                    }
                                }
                            }
                        }
                    ]
                },
                "xdt_shortcode_media": {
                    "shortcode": "DWmCs8KgB5-",
                    "comment_count": 1135,
                },
                "comments_media": {
                    "comments_connection": {
                        "edges": [
                            {
                                "node": {
                                    "pk": "1801",
                                    "text": "Komentar asli postingan target ini",
                                    "user": {"username": "target_user"},
                                }
                            }
                        ]
                    }
                },
            }
        }

        cnt = collector._extract_comment_count_from_payload(payload, "DWmCs8KgB5-")
        recs = collector._extract_comments_from_network_payload(
            payload, "DWmCs8KgB5-", "2026-11-12T13:00:00"
        )

        self.assertEqual(cnt, 1135)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0].username, "target_user")
        self.assertEqual(recs[0].comment_id, "1801")

    def test_handle_response_accepts_text_javascript_for_graphql_comments(self) -> None:
        """GraphQL comment batches sent with Content-Type text/javascript and for(;;); prefix must parse cleanly."""
        from unittest.mock import MagicMock, patch

        collector = InstagramBrowserNLPCollector(max_scroll_attempts=1, scroll_delay_sec=0.0)
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/p/DWmCs8KgB5-/"
        mock_page.locator.return_value.first.count.return_value = 0

        registered_handlers: dict[str, Any] = {}

        def capture_on(event_name, handler):
            registered_handlers[event_name] = handler

        mock_page.on.side_effect = capture_on

        def fake_evaluate(script, *args):
            if "const blocks = []" in script:
                return []
            if "scrolledInner" in script:
                fake_resp = MagicMock()
                fake_resp.url = "https://www.instagram.com/graphql/query"
                fake_resp.headers = {"content-type": "text/javascript; charset=utf-8"}
                fake_resp.json.side_effect = ValueError("not application/json")
                fake_resp.text.return_value = (
                    'for (;;);{"data":{"comments_media":{"comments_connection":{"edges":[{"node":'
                    '{"pk":"180555","text":"Komentar valid dari payload text javascript","created_at":1700000000,'
                    '"user":{"username":"js_commenter"}}}]}}}}'
                )
                if "response" in registered_handlers:
                    registered_handlers["response"](fake_resp)
                return {"scrolledInner": False, "nearBottom": True}
            return 0

        mock_page.evaluate.side_effect = fake_evaluate

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_playwright
        mock_cm.__exit__.return_value = False

        with patch("playwright.sync_api.sync_playwright", return_value=mock_cm), patch.object(
            collector, "is_login_required", return_value=False
        ), patch("src.collectors.browser_nlp.time.sleep"):
            result = collector.collect_comments("https://www.instagram.com/p/DWmCs8KgB5-/", limit=50)

        self.assertEqual(len(result.comments), 1)
        self.assertEqual(result.comments[0].username, "js_commenter")
        self.assertEqual(result.comments[0].comment_id, "180555")

    def test_scroll_progress_not_counted_as_idle_before_near_bottom(self) -> None:
        """Advancing downward across already-extracted replies must not trigger early idle exit before nearBottom."""
        from unittest.mock import MagicMock, patch

        collector = InstagramBrowserNLPCollector(
            max_scroll_attempts=20,
            scroll_delay_sec=0.0,
            max_recovery_sweeps=1,
        )
        mock_page = MagicMock()
        mock_page.url = "https://www.instagram.com/p/TestLongReply1/"
        mock_page.locator.return_value.first.count.return_value = 0

        step_state = {"scrolls": 0}

        def fake_evaluate(script, *args):
            if "const blocks = []" in script:
                if step_state["scrolls"] >= 12:
                    return [
                        "user_awal\n2j\nKomentar pembuka yang panjang\nBalas",
                        "user_bawah\n1j\nKomentar baru setelah melewati balasan panjang\nBalas",
                    ]
                return ["user_awal\n2j\nKomentar pembuka yang panjang\nBalas"]
            if "scrolledInner" in script:
                step_state["scrolls"] += 1
                if step_state["scrolls"] <= 12:
                    return {"scrolledInner": True, "nearBottom": False, "targetX": 500, "targetY": 400}
                return {"scrolledInner": False, "nearBottom": True, "targetX": 500, "targetY": 400}
            return 0

        mock_page.evaluate.side_effect = fake_evaluate

        mock_context = MagicMock()
        mock_context.pages = [mock_page]
        mock_playwright = MagicMock()
        mock_playwright.chromium.launch_persistent_context.return_value = mock_context
        mock_cm = MagicMock()
        mock_cm.__enter__.return_value = mock_playwright
        mock_cm.__exit__.return_value = False

        with patch("playwright.sync_api.sync_playwright", return_value=mock_cm), patch.object(
            collector, "is_login_required", return_value=False
        ), patch("src.collectors.browser_nlp.time.sleep"):
            result = collector.collect_comments("https://www.instagram.com/p/TestLongReply1/", limit=50)

        self.assertEqual([c.username for c in result.comments], ["user_awal", "user_bawah"])
        self.assertGreaterEqual(step_state["scrolls"], 13)

    def test_click_load_more_buttons_uses_fast_dom_tagger(self) -> None:
        """_click_load_more_buttons must use a single evaluate scan and mock-safe locators without query_selector_all."""
        from unittest.mock import MagicMock, patch

        collector = InstagramBrowserNLPCollector()
        mock_page = MagicMock()
        mock_page.evaluate.return_value = ["not-an-int"]
        self.assertEqual(collector._click_load_more_buttons(mock_page), 0)

        mock_page.reset_mock()
        mock_page.evaluate.return_value = 2
        mock_loc = MagicMock()
        mock_loc.first.count.return_value = 1
        mock_page.locator.return_value = mock_loc

        with patch("src.collectors.browser_nlp.time.sleep"):
            clicked = collector._click_load_more_buttons(mock_page)

        self.assertEqual(clicked, 2)
        self.assertEqual(mock_loc.first.click.call_count, 2)
        mock_page.query_selector_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()
