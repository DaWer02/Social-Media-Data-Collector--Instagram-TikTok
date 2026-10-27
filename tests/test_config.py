"""Unit tests for configuration management and security validations."""

import os
import unittest
from pathlib import Path

from src.config import (
    AppConfig,
    ConfigValidationError,
    mask_token,
    sanitize_headers,
    sanitize_url,
    validate_graph_api_version,
    validate_target_comments,
)


class TestConfigValidation(unittest.TestCase):
    """Test suite for config validation and secret sanitization."""

    def test_validate_target_comments_positive(self) -> None:
        """Valid positive integer targets should succeed."""
        self.assertEqual(validate_target_comments(3000), 3000)
        self.assertEqual(validate_target_comments("500"), 500)
        self.assertEqual(validate_target_comments(1), 1)
        self.assertEqual(validate_target_comments(None), 3000)

    def test_validate_target_comments_invalid(self) -> None:
        """Zero, negative numbers, or non-numeric strings should raise ConfigValidationError."""
        invalid_values = [0, -1, -500, "0", "-10", "abc", "", "3.14"]
        for val in invalid_values:
            with self.subTest(val=val):
                with self.assertRaises(ConfigValidationError) as ctx:
                    validate_target_comments(val)
                # Verify error message recommends a safe action without suggesting bypass
                self.assertIn("Tindakan aman", str(ctx.exception))
                self.assertNotIn("bypass", str(ctx.exception).lower())

    def test_validate_graph_api_version(self) -> None:
        """Valid version formats should be preserved or defaulted."""
        self.assertEqual(validate_graph_api_version("v21.0"), "v21.0")
        self.assertEqual(validate_graph_api_version("V20.0"), "v20.0")
        self.assertEqual(validate_graph_api_version(None), "v21.0")
        self.assertEqual(validate_graph_api_version(""), "v21.0")

        # Invalid versions
        with self.assertRaises(ConfigValidationError):
            validate_graph_api_version("21.0")
        with self.assertRaises(ConfigValidationError):
            validate_graph_api_version("version21")

    def test_mask_token(self) -> None:
        """Verify token masking preserves confidentiality."""
        self.assertEqual(mask_token(None), "<TIDAK_DISET>")
        self.assertEqual(mask_token(""), "<TIDAK_DISET>")
        self.assertEqual(mask_token("short"), "***")
        long_token = "EAABwz91928347abcdef987654"
        masked = mask_token(long_token)
        self.assertEqual(masked, "EAAB...7654")
        self.assertNotIn("1928347abcdef", masked)

    def test_sanitize_url(self) -> None:
        """Verify URL token sanitization removes tokens from query params."""
        raw_url = "https://graph.facebook.com/v21.0/123/comments?access_token=EAAB123456789xyz&limit=100"
        sanitized = sanitize_url(raw_url)
        self.assertNotIn("EAAB123456789xyz", sanitized)
        self.assertIn("access_token=***REDACTED***", sanitized)

    def test_sanitize_headers(self) -> None:
        """Verify Authorization headers are sanitized."""
        headers = {
            "Authorization": "Bearer EAAB998877665544",
            "Content-Type": "application/json",
            "User-Agent": "InstagramSlangNLP/1.0",
        }
        sanitized = sanitize_headers(headers)
        self.assertEqual(sanitized["Authorization"], "Bearer ***REDACTED***")
        self.assertEqual(sanitized["Content-Type"], "application/json")
        self.assertNotIn("EAAB998877665544", str(sanitized))

    def test_appconfig_repr_str_never_exposes_token(self) -> None:
        """Ensure AppConfig.__repr__ and __str__ never display plaintext token."""
        secret = "SUPER_SECRET_TOKEN_DO_NOT_PRINT"
        config = AppConfig(access_token=secret)
        self.assertNotIn(secret, repr(config))
        self.assertNotIn(secret, str(config))
        self.assertIn("access_token=SUPE...RINT", repr(config))

    def test_get_or_prompt_access_token_with_existing_token(self) -> None:
        """When token is already set, it should be returned directly."""
        config = AppConfig(access_token="ALREADY_CONFIGURED_TOKEN")
        token = config.get_or_prompt_access_token()
        self.assertEqual(token, "ALREADY_CONFIGURED_TOKEN")

    def test_get_or_prompt_access_token_prompting(self) -> None:
        """When token is empty, prompt_fn should be called and set token in-memory only."""
        config = AppConfig(access_token=None)

        def mock_prompt(prompt_text: str) -> str:
            return "SESSION_PROMPTED_SECRET_TOKEN_123"

        token = config.get_or_prompt_access_token(prompt_fn=mock_prompt)
        self.assertEqual(token, "SESSION_PROMPTED_SECRET_TOKEN_123")
        self.assertEqual(config.access_token, "SESSION_PROMPTED_SECRET_TOKEN_123")

    def test_get_or_prompt_access_token_empty_error(self) -> None:
        """Prompting empty token should raise ConfigValidationError with safe action."""
        config = AppConfig(access_token=None)

        def mock_empty_prompt(prompt_text: str) -> str:
            return ""

        with self.assertRaises(ConfigValidationError) as ctx:
            config.get_or_prompt_access_token(prompt_fn=mock_empty_prompt)
        self.assertIn("Tindakan aman", str(ctx.exception))
        self.assertNotIn("bypass", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
