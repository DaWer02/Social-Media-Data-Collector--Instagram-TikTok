"""Unit tests ensuring secrets and tokens are redacted from all logging records."""

import io
import logging
import unittest

from src.logging_config import SecretRedactingFilter, setup_logger


class TestLoggingRedaction(unittest.TestCase):
    """Test suite ensuring secret redaction in logging."""

    def test_filter_redacts_known_secret(self) -> None:
        """Known secrets must be redacted from log record messages."""
        secret = "EAABwz91928347abcdef987654"
        logger = setup_logger("test_redact_logger", level="DEBUG", token_to_redact=secret)

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.addFilter(SecretRedactingFilter(secrets=[secret]))
        logger.addHandler(handler)

        logger.info(f"Connecting to Graph API with token {secret} now.")

        output = stream.getvalue()
        self.assertNotIn(secret, output)
        self.assertIn("EAAB...7654", output)

    def test_filter_redacts_url_query_token(self) -> None:
        """URL tokens in log messages must be automatically scrubbed."""
        stream = io.StringIO()
        logger = logging.getLogger("test_url_logger")
        logger.setLevel(logging.INFO)
        for h in list(logger.handlers):
            logger.removeHandler(h)

        handler = logging.StreamHandler(stream)
        handler.addFilter(SecretRedactingFilter())
        logger.addHandler(handler)

        raw_url = "Requesting https://graph.facebook.com/v21.0/123/comments?access_token=TOP_SECRET_12345&limit=50"
        logger.info(raw_url)

        output = stream.getvalue()
        self.assertNotIn("TOP_SECRET_12345", output)
        self.assertIn("access_token=***REDACTED***", output)

    def test_filter_redacts_bearer_token(self) -> None:
        """Bearer tokens in log messages must be scrubbed."""
        stream = io.StringIO()
        logger = logging.getLogger("test_bearer_logger")
        logger.setLevel(logging.INFO)
        for h in list(logger.handlers):
            logger.removeHandler(h)

        handler = logging.StreamHandler(stream)
        handler.addFilter(SecretRedactingFilter())
        logger.addHandler(handler)

        logger.info("Headers: {'Authorization': 'Bearer MY_SECRET_BEARER_TOKEN'}")

        output = stream.getvalue()
        self.assertNotIn("MY_SECRET_BEARER_TOKEN", output)
        self.assertIn("Bearer ***REDACTED***", output)


if __name__ == "__main__":
    unittest.main()
