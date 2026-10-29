"""Unit tests for InstagramGraphAPICollector using mock responses and fixtures.

Ensures zero live network calls and verifies pagination, deduplication,
privacy preservation, and error handling.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import requests

from src.collectors.base import (
    AuthenticationError,
    CollectorValidationError,
    CommentRecord,
    MediaUnavailableError,
    NetworkCollectorError,
    PermissionDeniedError,
    RateLimitError,
)
from src.collectors.instagram_api import InstagramGraphAPICollector


def create_mock_response(status_code: int, json_data: dict, text: str = "") -> requests.Response:
    """Helper to generate a mock requests.Response object."""
    resp = requests.Response()
    resp.status_code = status_code
    resp._content = (
        str(json_data).replace("'", '"').encode("utf-8") if json_data else text.encode("utf-8")
    )
    resp.json = MagicMock(return_value=json_data)
    return resp


class TestInstagramCollector(unittest.TestCase):
    """Test suite for Instagram Graph API collector."""

    def setUp(self) -> None:
        self.mock_session = MagicMock(spec=requests.Session)
        self.collector = InstagramGraphAPICollector(
            access_token="TEST_MOCK_TOKEN_12345",
            api_version="v21.0",
            api_variant="facebook_login",
            session=self.mock_session,
            max_retries=1,
            backoff_factor=0.01,
        )

    def test_base_url_variants(self) -> None:
        """Verify host URL is mapped correctly according to login variant."""
        fb_collector = InstagramGraphAPICollector(
            api_version="v21.0",
            api_variant="facebook_login",
        )
        self.assertEqual(fb_collector.base_url, "https://graph.facebook.com/v21.0")

        ig_collector = InstagramGraphAPICollector(
            api_version="v21.0",
            api_variant="instagram_login",
        )
        self.assertEqual(ig_collector.base_url, "https://graph.instagram.com/v21.0")

    def test_resolve_media_id_direct_numeric(self) -> None:
        """Direct numeric string should be returned immediately without network calls."""
        media_id = self.collector.resolve_media_id("17970528943031455")
        self.assertEqual(media_id, "17970528943031455")
        self.mock_session.get.assert_not_called()

    def test_resolve_media_id_invalid_format(self) -> None:
        """Invalid string or unknown domain should raise CollectorValidationError."""
        with self.assertRaises(CollectorValidationError):
            self.collector.resolve_media_id("https://facebook.com/posts/123")

        with self.assertRaises(CollectorValidationError):
            self.collector.resolve_media_id("")

    def test_resolve_media_id_url_matching_authorized(self) -> None:
        """Instagram URL matching user's authorized media should return official numeric ID."""
        target_url = "https://www.instagram.com/p/C_abc123xyz/"
        mock_media_response = {
            "data": [
                {
                    "id": "18001122334455",
                    "permalink": "https://www.instagram.com/p/C_abc123xyz/",
                    "caption": "Test post caption",
                },
                {
                    "id": "18009988776655",
                    "permalink": "https://www.instagram.com/p/OTHER_POST/",
                    "caption": "Other post",
                },
            ]
        }
        self.mock_session.get.return_value = create_mock_response(200, mock_media_response)

        resolved_id = self.collector.resolve_media_id(target_url)
        self.assertEqual(resolved_id, "18001122334455")

    def test_resolve_media_id_url_not_authorized(self) -> None:
        """Third-party or foreign URL not owned by user should raise MediaUnavailableError."""
        target_url = "https://www.instagram.com/p/FOREIGN_POST_999/"
        mock_media_response = {
            "data": [
                {
                    "id": "18001122334455",
                    "permalink": "https://www.instagram.com/p/MY_OWN_POST/",
                }
            ]
        }
        self.mock_session.get.return_value = create_mock_response(200, mock_media_response)

        with self.assertRaises(MediaUnavailableError) as ctx:
            self.collector.resolve_media_id(target_url)
        self.assertIn("tidak ditemukan pada akun profesional yang terotorisasi", str(ctx.exception))

    def test_validate_access_success(self) -> None:
        """Valid media access should return (True, None)."""
        self.mock_session.get.return_value = create_mock_response(
            200, {"id": "18001122334455", "media_type": "IMAGE", "comments_count": 42}
        )
        is_valid, reason = self.collector.validate_access("18001122334455")
        self.assertTrue(is_valid)
        self.assertIsNone(reason)

    def test_auth_failure_401_raises_immediately_without_retry(self) -> None:
        """HTTP 401 should raise AuthenticationError and never be retried."""
        error_payload = {
            "error": {
                "message": "Error validating access token: Session has expired.",
                "type": "OAuthException",
                "code": 190,
            }
        }
        self.mock_session.get.return_value = create_mock_response(401, error_payload)

        with self.assertRaises(AuthenticationError):
            self.collector.validate_access("18001122334455")

        # Must only call once (no retry on auth error)
        self.assertEqual(self.mock_session.get.call_count, 1)

    def test_permission_denied_403_raises_immediately(self) -> None:
        """HTTP 403 should raise PermissionDeniedError without retry."""
        error_payload = {
            "error": {
                "message": "(#10) Application does not have permission for this action.",
                "type": "OAuthException",
                "code": 10,
            }
        }
        self.mock_session.get.return_value = create_mock_response(403, error_payload)

        with self.assertRaises(PermissionDeniedError):
            self.collector.validate_access("18001122334455")
        self.assertEqual(self.mock_session.get.call_count, 1)

    def test_rate_limit_429_raises_immediately(self) -> None:
        """HTTP 429 should raise RateLimitError without retry."""
        error_payload = {
            "error": {
                "message": "(#4) Application request limit reached",
                "type": "OAuthException",
                "code": 4,
            }
        }
        self.mock_session.get.return_value = create_mock_response(429, error_payload)

        with self.assertRaises(RateLimitError):
            self.collector.validate_access("18001122334455")
        self.assertEqual(self.mock_session.get.call_count, 1)

    def test_media_unavailable_404_raises_immediately(self) -> None:
        """HTTP 404 should raise MediaUnavailableError."""
        error_payload = {
            "error": {
                "message": "Unsupported get request. Object with ID does not exist.",
                "type": "GraphMethodException",
                "code": 100,
            }
        }
        self.mock_session.get.return_value = create_mock_response(404, error_payload)

        with self.assertRaises(MediaUnavailableError):
            self.collector.validate_access("NON_EXISTENT_ID")

    def test_transient_error_retry_then_success(self) -> None:
        """Transient HTTP 503 should retry and succeed when next call returns 200."""
        self.mock_session.get.side_effect = [
            create_mock_response(503, {}, text="Service Unavailable"),
            create_mock_response(200, {"id": "18001122334455"}),
        ]
        is_valid, _ = self.collector.validate_access("18001122334455")
        self.assertTrue(is_valid)
        self.assertEqual(self.mock_session.get.call_count, 2)

    def test_collect_comments_pagination_and_deduplication(self) -> None:
        """Verify cursor pagination and deduplication by comment_id."""
        # 1. Validation call response
        resp_validate = create_mock_response(200, {"id": "18001122334455"})

        # 2. Page 1 response: 2 comments, cursor 'after_page_1'
        resp_page1 = create_mock_response(
            200,
            {
                "data": [
                    {"id": "cmt_1", "text": "Komentar pertama mantul", "like_count": 5},
                    {"id": "cmt_2", "text": "Komentar kedua gws ya", "like_count": 0},
                ],
                "paging": {
                    "cursors": {"after": "cursor_token_page_1"},
                },
            },
        )

        # 3. Page 2 response: 1 duplicate (cmt_2) and 1 new (cmt_3), no more cursors
        resp_page2 = create_mock_response(
            200,
            {
                "data": [
                    {"id": "cmt_2", "text": "Komentar kedua gws ya duplicate"},
                    {"id": "cmt_3", "text": "Komentar ketiga otw gaes", "like_count": 12},
                ],
                "paging": {},
            },
        )

        self.mock_session.get.side_effect = [resp_validate, resp_page1, resp_page2]

        result = self.collector.collect_comments("18001122334455", limit=10)

        self.assertEqual(result.media_id, "18001122334455")
        self.assertEqual(result.total_collected, 3)  # Only 3 unique comments (cmt_1, cmt_2, cmt_3)
        self.assertEqual(result.unique_collected, 3)
        self.assertTrue(result.paging_completed)

        # Privacy verification: verify Graph API collector does not leak tokens or private usernames
        for record in result.comments:
            self.assertIsInstance(record, CommentRecord)
            self.assertEqual(record.username, "")
            dict_rep = record.to_dict()
            self.assertNotIn("token", str(dict_rep))

    def test_collect_comments_stops_at_limit(self) -> None:
        """Collection stops when target limit is reached even if more pages exist."""
        resp_validate = create_mock_response(200, {"id": "18001122334455"})
        resp_page1 = create_mock_response(
            200,
            {
                "data": [
                    {"id": f"cmt_{i}", "text": f"Teks komentar {i}"} for i in range(10)
                ],
                "paging": {"cursors": {"after": "more_data_cursor"}},
            },
        )
        self.mock_session.get.side_effect = [resp_validate, resp_page1]

        # Target limit = 5
        result = self.collector.collect_comments("18001122334455", limit=5)

        self.assertEqual(result.total_collected, 5)
        self.assertEqual(len(result.comments), 5)
        self.assertEqual(result.comments[0].comment_id, "cmt_0")
        self.assertEqual(result.comments[4].comment_id, "cmt_4")


if __name__ == "__main__":
    unittest.main()
