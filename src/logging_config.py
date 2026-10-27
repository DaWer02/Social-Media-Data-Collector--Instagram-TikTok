"""Logging configuration with secret redaction for Instagram Slang NLP CLI."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from src.config import mask_token


class SecretRedactingFilter(logging.Filter):
    """Logging filter that scrubs known secrets and tokens from log messages."""

    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets: list[str] = [s for s in (secrets or []) if s and len(s) > 4]

    def add_secret(self, secret: str) -> None:
        """Add a secret token to be redacted."""
        if secret and len(secret) > 4 and secret not in self.secrets:
            self.secrets.append(secret)

    def _redact_text(self, text: str) -> str:
        # Redact specific secrets
        for secret in self.secrets:
            if secret in text:
                text = text.replace(secret, mask_token(secret))

        # Redact access_token in URLs: ?access_token=... or &access_token=...
        text = re.sub(r"([?&]access_token=)[^&\s]+", r"\1***REDACTED***", text)

        # Redact Authorization Bearer headers
        text = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", r"\1***REDACTED***", text, flags=re.IGNORECASE)

        # Redact Meta Graph API token patterns (e.g. EAAB...)
        text = re.sub(r"(EAA[A-Za-z0-9]{15,})", r"***REDACTED_META_TOKEN***", text)

        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = self._redact_text(record.msg)

        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: (self._redact_text(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self._redact_text(arg) if isinstance(arg, str) else arg
                    for arg in record.args
                )
        return True


def setup_logger(
    name: str = "nlp_cli",
    level: str = "INFO",
    token_to_redact: str | None = None,
) -> logging.Logger:
    """Configure and return a sanitized application logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates during reconfiguration
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # Attach secret filter
    secrets: list[str] = []
    if token_to_redact:
        secrets.append(token_to_redact)
    env_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if env_token:
        secrets.append(env_token)

    redacting_filter = SecretRedactingFilter(secrets=secrets)
    logger.addFilter(redacting_filter)

    return logger
