"""Privacy and data protection module for social media comment harvesting.

Enforces ethical data collection principles (GDPR, Indonesian UU PDP, and platform ethics):
1. Complete removal of author usernames and account identifiers from exported datasets.
2. Sanitization of @mentions inside comment texts to generic [@USER] tokens.
3. Masking of sensitive Personally Identifiable Information (PII) such as emails, phone numbers, and URLs.
4. Pseudonymization of internal identifiers to ensure data traceability without privacy leaks.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

# Negative lookbehind (?<![\w.+-]) ensures @ in an email address like test@mail.com is not treated as a username mention
_MENTION_PATTERN = re.compile(r"(?<![\w.+-])@[A-Za-z0-9_.]+", re.UNICODE)

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
)
_PHONE_PATTERN = re.compile(
    r"(?:\+?62|08|60)[0-9\s\-]{8,14}\b"
)
_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)"
)


def mask_mentions(text: str) -> str:
    """Replace all @username mentions in text with [@USER].

    Examples:
        >>> mask_mentions("Halo @jokowi dan @prabowo")
        'Halo [@USER] dan [@USER]'
    """
    if not text:
        return ""
    return _MENTION_PATTERN.sub("[@USER]", text)


def mask_emails(text: str) -> str:
    """Replace email addresses with [EMAIL]."""
    if not text:
        return ""
    return _EMAIL_PATTERN.sub("[EMAIL]", text)


def mask_phone_numbers(text: str) -> str:
    """Replace Indonesian / Malaysian format phone numbers with [TELEPON]."""
    if not text:
        return ""
    return _PHONE_PATTERN.sub("[TELEPON]", text)


def mask_urls(text: str) -> str:
    """Replace HTTP/HTTPS URLs with [LINK]."""
    if not text:
        return ""
    return _URL_PATTERN.sub("[LINK]", text)


def sanitize_comment_text(
    text: str,
    mask_user_mentions: bool = True,
    mask_emails_flag: bool = True,
    mask_phones_flag: bool = True,
    mask_urls_flag: bool = False,
) -> str:
    """Clean and sanitize comment text according to privacy guidelines.

    Args:
        text: Raw comment text string.
        mask_user_mentions: Whether to replace @mentions with [@USER].
        mask_emails_flag: Whether to replace email addresses with [EMAIL].
        mask_phones_flag: Whether to replace phone numbers with [TELEPON].
        mask_urls_flag: Whether to replace URLs with [LINK].

    Returns:
        Cleaned, privacy-compliant text string.
    """
    if not text:
        return ""

    sanitized = text

    # Mask URLs first to prevent query params or paths from triggering other patterns
    if mask_urls_flag:
        sanitized = mask_urls(sanitized)

    # Mask emails before mentions so that test@mail.com is not matched as a mention
    if mask_emails_flag:
        sanitized = mask_emails(sanitized)

    if mask_user_mentions:
        sanitized = mask_mentions(sanitized)

    if mask_phones_flag:
        sanitized = mask_phone_numbers(sanitized)

    # Normalize whitespace
    sanitized = re.sub(r"[ \t]+", " ", sanitized).strip()
    return sanitized


def sanitize_comment_dict(
    record: Mapping[str, Any],
    anonymize_comment_id: bool = False,
    anonymous_index: int | None = None,
) -> dict[str, Any]:
    """Sanitize a single comment record dictionary for open-source dataset export.

    - Removes or blanks username fields.
    - Sanitizes comment_text to mask @mentions and PII.
    - Optionally replaces platform-specific comment_id with an anonymous sequential ID.
    """
    data = dict(record)

    # Strictly strip account name
    if "username" in data:
        data.pop("username", None)
    if "author" in data:
        data.pop("author", None)
    if "user_id" in data:
        data.pop("user_id", None)

    # Sanitize comment text
    raw_text = str(data.get("comment_text", ""))
    data["comment_text"] = sanitize_comment_text(raw_text)

    # Anonymize comment ID if requested
    if anonymize_comment_id and anonymous_index is not None:
        data["comment_id"] = f"KOM_{anonymous_index:05d}"

    return data
