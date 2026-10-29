"""Unit tests for InstagramBrowserNLPCollector."""

from __future__ import annotations

import unittest
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


if __name__ == "__main__":
    unittest.main()
