"""Abstract base collector interface, data models, and error hierarchy for comment extraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class CollectorError(Exception):
    """Base exception for all comment collection errors."""

    def __init__(
        self,
        message: str,
        safe_action: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message
        self.safe_action = safe_action
        self.status_code = status_code
        full_msg = message
        if safe_action:
            full_msg = f"{message} Tindakan aman: {safe_action}"
        super().__init__(full_msg)


class AuthenticationError(CollectorError):
    """HTTP 401 or Code 190: Invalid, expired, or missing access token."""


class PermissionDeniedError(CollectorError):
    """HTTP 403 or Code 10/200: Missing required permission/scope."""


class MediaUnavailableError(CollectorError):
    """HTTP 404/400 or Code 100: Media ID not found or not owned/accessible."""


class RateLimitError(CollectorError):
    """HTTP 429 or Code 4/17/32/613: API call limit exceeded."""


class NetworkCollectorError(CollectorError):
    """Network connection failure, DNS failure, or request timeout."""


class CollectorValidationError(CollectorError):
    """Invalid URL or media ID format."""


@dataclass(frozen=True)
class CommentRecord:
    """Standardized representation of a single collected comment."""

    comment_id: str
    media_id: str
    comment_text: str
    timestamp: str | None = None
    like_count: int | None = 0
    collected_at: str = ""
    source_type: str = "authorized_api"
    username: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert record to dictionary for CSV or JSON storage."""
        return {
            "comment_id": self.comment_id,
            "media_id": self.media_id,
            "username": self.username,
            "comment_text": self.comment_text,
            "timestamp": self.timestamp or "",
            "like_count": self.like_count if self.like_count is not None else 0,
            "collected_at": self.collected_at or "",
            "source_type": self.source_type,
        }


@dataclass
class CollectionResult:
    """Summary result of a comment collection run."""

    media_id: str
    comments: list[CommentRecord]
    total_collected: int
    unique_collected: int
    status: str
    error_message: str | None = None
    paging_completed: bool = False
    reported_total: int | None = None
    tolerance_target: int | None = None
    raw_encountered: int = 0
    filtered_out_count: int = 0
    rejection_breakdown: dict[str, int] = field(default_factory=dict)
    coverage_reached: bool = False


class BaseCollector(ABC):
    """Abstract base class for all comment collection adapters."""

    @abstractmethod
    def resolve_media_id(self, target: str) -> str:
        """Resolve a user input (URL or raw Media ID) to an authorized numeric Media ID.

        Args:
            target: Post URL or raw numeric media ID.

        Returns:
            str: Resolved numeric Media ID.

        Raises:
            CollectorValidationError: If format is invalid.
            MediaUnavailableError: If URL cannot be matched to an authorized post.
        """
        pass

    @abstractmethod
    def validate_access(self, media_id: str) -> tuple[bool, str | None]:
        """Validate whether the media object can be accessed with current credentials.

        Args:
            media_id: Numeric Instagram media ID.

        Returns:
            tuple[bool, str | None]: (True, None) if authorized, or (False, reason).
        """
        pass

    @abstractmethod
    def collect_comments(
        self,
        target: str,
        limit: int = 3000,
    ) -> CollectionResult:
        """Collect comments up to the specified limit without duplicates.

        Args:
            target: Post URL or numeric media ID.
            limit: Maximum comments to collect.

        Returns:
            CollectionResult: Result container with collected comments and metadata.
        """
        pass
