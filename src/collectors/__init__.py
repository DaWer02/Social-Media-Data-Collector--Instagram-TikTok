"""Collectors package for retrieving comments from Instagram and TikTok."""

from src.collectors.base import (
    AuthenticationError,
    BaseCollector,
    CollectionResult,
    CollectorError,
    CollectorValidationError,
    CommentRecord,
    MediaUnavailableError,
    NetworkCollectorError,
    PermissionDeniedError,
    RateLimitError,
)
from src.collectors.browser_nlp import InstagramBrowserNLPCollector
from src.collectors.instagram_api import InstagramGraphAPICollector
from src.collectors.tiktok import TikTokBrowserCollector
from src.collectors.unified import (
    collect_social_comments,
    detect_platform,
    extract_clean_url,
    open_login_session,
)

__all__ = [
    "AuthenticationError",
    "BaseCollector",
    "CollectionResult",
    "CollectorError",
    "CollectorValidationError",
    "CommentRecord",
    "InstagramBrowserNLPCollector",
    "InstagramGraphAPICollector",
    "MediaUnavailableError",
    "NetworkCollectorError",
    "PermissionDeniedError",
    "RateLimitError",
    "TikTokBrowserCollector",
    "collect_social_comments",
    "detect_platform",
    "extract_clean_url",
    "open_login_session",
]
