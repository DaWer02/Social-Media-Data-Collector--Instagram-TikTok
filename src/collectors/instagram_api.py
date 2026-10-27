"""Official Meta Graph API collector for Instagram comments.

Adheres strictly to official Meta specifications for Instagram Professional accounts
(Business & Creator). Does not perform unofficial scraping, respects privacy by
omitting personal usernames, handles pagination & rate limits gracefully, and redacts tokens.
"""

from __future__ import annotations

import datetime
import logging
import re
import time
from typing import Any

import requests

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
from src.config import mask_token, sanitize_headers, sanitize_url
from src.logging_config import setup_logger

logger = setup_logger("instagram_collector")

# Regex to match valid Instagram post/reel/tv URLs and capture shortcode
INSTAGRAM_URL_PATTERN = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)/?",
    re.IGNORECASE,
)


class InstagramGraphAPICollector(BaseCollector):
    """Collector adapter for Instagram Professional accounts via Meta Graph API."""

    DEFAULT_CONNECT_TIMEOUT: float = 5.0
    DEFAULT_READ_TIMEOUT: float = 30.0
    MAX_RETRIES: int = 2
    PAGE_LIMIT: int = 100

    def __init__(
        self,
        access_token: str | None = None,
        api_version: str = "v21.0",
        api_variant: str = "facebook_login",
        session: requests.Session | None = None,
        timeout: tuple[float, float] | None = None,
        max_retries: int = MAX_RETRIES,
        backoff_factor: float = 0.5,
    ) -> None:
        """Initialize the collector.

        Args:
            access_token: Meta User or Page access token.
            api_version: Meta Graph API version string (e.g. 'v21.0').
            api_variant: 'facebook_login' (default) or 'instagram_login'.
            session: Optional custom requests.Session (invaluable for testing).
            timeout: Optional (connect_timeout, read_timeout) tuple.
            max_retries: Maximum retries for transient HTTP 5xx or connection errors.
            backoff_factor: Multiplier for exponential backoff delay.
        """
        self.access_token = access_token.strip() if access_token else None
        self.api_version = api_version.strip().lower()
        self.api_variant = api_variant.strip().lower()
        self.session = session or requests.Session()
        self.timeout = timeout or (self.DEFAULT_CONNECT_TIMEOUT, self.DEFAULT_READ_TIMEOUT)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    @property
    def base_url(self) -> str:
        """Return the official base URL according to the chosen login variant."""
        if self.api_variant == "instagram_login":
            return f"https://graph.instagram.com/{self.api_version}"
        return f"https://graph.facebook.com/{self.api_version}"

    @staticmethod
    def get_api_limitations() -> str:
        """Return explicit limitations enforced by Meta's official Graph API."""
        return (
            "KETERBATASAN RESMI META GRAPH API:\n"
            "1. Endpoint /{media-id}/comments HANYA dapat membaca komentar dari media milik "
            "akun Profesional (Business/Creator) yang terotorisasi oleh token Anda.\n"
            "2. Pengambilan komentar dari akun pihak ketiga / sembarang URL publik TIDAK DIDUKUNG "
            "oleh API resmi Meta (mencegah scraping tanpa izin).\n"
            "3. Izin wajib: 'instagram_manage_comments' (Facebook Login) atau "
            "'instagram_business_manage_comments' (Instagram Login).\n"
            "4. Instagram Basic Display API telah dimatikan total oleh Meta per 4 Desember 2024.\n"
            "5. Aplikasi ini patuh pada ToS Meta dan tidak menggunakan browser automation/scraping."
        )

    def _parse_meta_error_and_raise(self, response: requests.Response) -> None:
        """Inspect response body from Meta Graph API and raise specific domain error."""
        status_code = response.status_code
        error_data: dict[str, Any] = {}
        try:
            body = response.json()
            if isinstance(body, dict):
                error_data = body.get("error", {})
        except Exception:
            pass

        code = error_data.get("code")
        subcode = error_data.get("error_subcode")
        message = error_data.get("message", response.text or f"HTTP {status_code}")
        error_type = error_data.get("type", "Unknown")

        # 1. Authentication failure (HTTP 401 or Code 190)
        if status_code == 401 or code == 190:
            raise AuthenticationError(
                f"Autentikasi Meta gagal ({error_type}: {message}).",
                safe_action=(
                    "Periksa INSTAGRAM_ACCESS_TOKEN di .env atau masukkan token sesi yang sah. "
                    "Pastikan token belum kedaluwarsa di Meta for Developers."
                ),
                status_code=status_code,
            )

        # 2. Permission denied (HTTP 403 or Code 10 / 200-299)
        if status_code == 403 or code == 10 or (isinstance(code, int) and 200 <= code <= 299):
            raise PermissionDeniedError(
                f"Izin akses tidak mencukupi ({error_type}: {message}).",
                safe_action=(
                    "Pastikan akun Anda merupakan akun Profesional (Business/Creator) "
                    "dan token memiliki izin 'instagram_manage_comments' atau "
                    "'instagram_business_manage_comments'."
                ),
                status_code=status_code,
            )

        # 3. Rate limit reached (HTTP 429 or Code 4, 17, 32, 613)
        if status_code == 429 or code in {4, 17, 32, 613}:
            raise RateLimitError(
                f"Batas panggilan API Meta tercapai ({error_type}: {message}).",
                safe_action=(
                    "Hentikan pengumpulan data dan tunggu beberapa menit/jam sebelum mencoba kembali "
                    "sesuai batas kuota resmi Meta."
                ),
                status_code=status_code,
            )

        # 4. Media unavailable / not found (HTTP 400 with code 100/803 or HTTP 404)
        if status_code in {400, 404} and code in {100, 803}:
            raise MediaUnavailableError(
                f"Media tidak ditemukan atau bukan milik akun terotorisasi ({message}).",
                safe_action=(
                    "Periksa kembali Media ID atau pastikan postingan berasal dari akun profesional "
                    "yang dikelola oleh token Anda."
                ),
                status_code=status_code,
            )

        # 5. Generic collector error
        raise CollectorError(
            f"Kesalahan respons API Meta (HTTP {status_code}): {message}",
            safe_action="Periksa parameter input atau status server Meta.",
            status_code=status_code,
        )

    def _make_request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute HTTP GET with exponential backoff for transient errors only.

        Fatal errors (401, 403, 404, 429) are NEVER retried and fail immediately.
        """
        request_params = dict(params or {})
        headers = {
            "User-Agent": "InstagramSlangNLP/1.0",
            "Accept": "application/json",
        }

        # Safely log URL without exposing tokens
        sanitized_url = sanitize_url(url)
        logger.debug("Requesting Meta API: %s", sanitized_url)

        last_exception: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=request_params,
                    headers=headers,
                    timeout=self.timeout,
                )

                # Retry transient server errors (HTTP 500, 502, 503, 504)
                if response.status_code in {500, 502, 503, 504}:
                    if attempt < self.max_retries:
                        sleep_time = self.backoff_factor * (2 ** attempt)
                        logger.warning(
                            "Transient server error HTTP %d. Retrying in %.1fs (attempt %d/%d)...",
                            response.status_code,
                            sleep_time,
                            attempt + 1,
                            self.max_retries,
                        )
                        time.sleep(sleep_time)
                        continue
                    else:
                        raise NetworkCollectorError(
                            f"Server Meta mengalami kendala sementara (HTTP {response.status_code}).",
                            safe_action="Coba jalankan kembali program beberapa saat lagi.",
                            status_code=response.status_code,
                        )

                # Non-transient client/auth errors: raise immediately without retrying
                if response.status_code >= 400:
                    self._parse_meta_error_and_raise(response)

                return response.json()

            except CollectorError:
                raise
            except (requests.exceptions.RequestException, Exception) as net_err:
                last_exception = net_err
                if attempt < self.max_retries:
                    sleep_time = self.backoff_factor * (2 ** attempt)
                    logger.warning(
                        "Network error (%s). Retrying in %.1fs (attempt %d/%d)...",
                        net_err.__class__.__name__,
                        sleep_time,
                        attempt + 1,
                        self.max_retries,
                    )
                    time.sleep(sleep_time)
                    continue
                else:
                    raise NetworkCollectorError(
                        f"Gagal terhubung ke API Meta: {net_err}",
                        safe_action="Periksa koneksi internet Anda atau ketersediaan host Meta.",
                    )

        if last_exception:
            raise NetworkCollectorError(
                f"Gagal melakukan permintaan setelah {self.max_retries} percobaan: {last_exception}",
                safe_action="Periksa stabilitas koneksi internet Anda.",
            )
        raise CollectorError("Permintaan API tidak menghasilkan respons.")

    _sanitize_url = staticmethod(sanitize_url)

    def _extract_target(self, target: str) -> tuple[str, str]:
        """Extract target type and identifier from user input.

        Returns:
            tuple[str, str]: ("media_id", id_str) or ("shortcode", code_str).

        Raises:
            CollectorValidationError: If target format is empty or not recognized.
        """
        cleaned = target.strip()
        if not cleaned:
            raise CollectorValidationError(
                "Input URL atau Media ID tidak boleh kosong.",
                safe_action="Masukkan URL postingan atau Media ID numerik.",
            )

        if cleaned.isdigit():
            return "media_id", cleaned

        match = INSTAGRAM_URL_PATTERN.match(cleaned)
        if not match:
            raise CollectorValidationError(
                f"Format input '{cleaned}' tidak dikenali sebagai Media ID atau URL Instagram yang sah.",
                safe_action=(
                    "Masukkan URL format resmi (contoh: https://www.instagram.com/p/C_abc123/) "
                    "atau Media ID numerik (contoh: 17970528943031455)."
                ),
            )

        return "shortcode", match.group(1)

    def _query_authorized_media(self) -> list[dict[str, Any]]:
        """Query recent media of the authenticated account to resolve URLs to Media IDs."""
        if not self.access_token:
            raise AuthenticationError(
                "Access token belum diset.",
                safe_action="Konfigurasikan INSTAGRAM_ACCESS_TOKEN di .env atau berikan token sesi.",
            )

        url = f"{self.base_url}/me/media"
        params = {
            "fields": "id,permalink,caption,timestamp",
            "limit": 100,
            "access_token": self.access_token,
        }

        try:
            data = self._make_request(url, params=params)
            return data.get("data", [])
        except (AuthenticationError, PermissionDeniedError):
            raise
        except CollectorError:
            # If /me/media fails (e.g. page token needs specific user ID), return empty list
            return []

    def resolve_media_id(self, target: str) -> str:
        """Resolve a post URL or raw Media ID to an authorized numeric Media ID.

        Scraping public HTML pages is strictly forbidden. URL mapping is performed
        exclusively through Meta's official media collection for the authorized account.

        Args:
            target: Post URL or numeric Media ID.

        Returns:
            str: Resolved numeric Media ID.

        Raises:
            CollectorValidationError: If target is not a valid URL or digits.
            MediaUnavailableError: If URL cannot be matched with an authorized post.
        """
        target_type, identifier = self._extract_target(target)
        if target_type == "media_id":
            return identifier

        shortcode = identifier

        # Official URL-to-ID matching against user's authorized media
        logger.info("Mencoba memetakan URL shortcode '%s' ke Media ID resmi...", shortcode)
        authorized_media = self._query_authorized_media()

        for item in authorized_media:
            permalink = item.get("permalink", "")
            media_id = item.get("id")
            if permalink and shortcode in permalink and media_id:
                logger.info("URL berhasil dipetakan ke Media ID resmi: %s", media_id)
                return str(media_id)

        # 4. If URL is not found among authorized posts, fail safely
        raise MediaUnavailableError(
            f"URL postingan (shortcode: '{shortcode}') tidak ditemukan pada akun profesional yang terotorisasi.",
            safe_action=(
                "Meta Graph API hanya mengizinkan pembacaan komentar pada postingan milik akun "
                "profesional Anda sendiri. Masukkan Media ID numerik langsung dari akun Anda, "
                "atau gunakan dataset berizin yang telah diekspor secara sah."
            ),
        )

    def validate_access(self, media_id: str) -> tuple[bool, str | None]:
        """Validate whether the media object is accessible with current credentials."""
        if not self.access_token:
            raise AuthenticationError(
                "Access token belum diset.",
                safe_action="Konfigurasikan INSTAGRAM_ACCESS_TOKEN di .env atau masukkan token sesi.",
            )

        url = f"{self.base_url}/{media_id}"
        params = {
            "fields": "id,media_type,comments_count",
            "access_token": self.access_token,
        }

        data = self._make_request(url, params=params)
        if "id" in data:
            return True, None
        return False, "Media tidak mengembalikan field 'id'."

    def collect_comments(
        self,
        target: str,
        limit: int = 3000,
    ) -> CollectionResult:
        """Collect comments from an authorized Instagram post up to the limit.

        Implements cursor pagination, deduplication by comment_id, and minimal field extraction.

        Args:
            target: Post URL or numeric Media ID.
            limit: Maximum comments to collect (default: 3000).

        Returns:
            CollectionResult: Container holding unique comments and metadata.
        """
        if not self.access_token:
            raise AuthenticationError(
                "Access token belum diset.",
                safe_action="Konfigurasikan INSTAGRAM_ACCESS_TOKEN di .env atau masukkan token sesi.",
            )

        limit = max(1, limit)
        media_id = self.resolve_media_id(target)
        self.validate_access(media_id)

        collected_comments: list[CommentRecord] = []
        seen_comment_ids: set[str] = set()
        collected_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        current_url = f"{self.base_url}/{media_id}/comments"
        current_params: dict[str, Any] | None = {
            "fields": "id,text,timestamp,like_count",
            "limit": min(limit, self.PAGE_LIMIT),
            "access_token": self.access_token,
        }

        paging_completed = False

        while len(collected_comments) < limit:
            logger.info(
                "Mengambil halaman komentar (saat ini terkumpul: %d/%d)...",
                len(collected_comments),
                limit,
            )
            response_data = self._make_request(current_url, params=current_params)
            data_items = response_data.get("data", [])

            if not data_items:
                paging_completed = True
                break

            for item in data_items:
                cid = str(item.get("id", "")).strip()
                if not cid:
                    continue

                # Deduplicate by comment_id
                if cid in seen_comment_ids:
                    continue

                seen_comment_ids.add(cid)
                record = CommentRecord(
                    comment_id=cid,
                    media_id=media_id,
                    comment_text=str(item.get("text", "")),
                    timestamp=item.get("timestamp"),
                    like_count=item.get("like_count"),
                    collected_at=collected_at,
                    source_type="authorized_api",
                )
                collected_comments.append(record)

                if len(collected_comments) >= limit:
                    break

            # Handle official pagination
            paging = response_data.get("paging", {})
            cursors = paging.get("cursors", {})
            after_cursor = cursors.get("after")
            next_url = paging.get("next")

            if len(collected_comments) >= limit:
                break

            if after_cursor:
                current_url = f"{self.base_url}/{media_id}/comments"
                current_params = {
                    "fields": "id,text,timestamp,like_count",
                    "limit": min(limit - len(collected_comments), self.PAGE_LIMIT),
                    "after": after_cursor,
                    "access_token": self.access_token,
                }
            elif next_url:
                current_url = next_url
                current_params = None  # next_url already includes after cursor & credentials
            else:
                paging_completed = True
                break

        logger.info(
            "Pengumpulan selesai. Media ID: %s | Total unik: %d",
            media_id,
            len(collected_comments),
        )

        return CollectionResult(
            media_id=media_id,
            comments=collected_comments[:limit],
            total_collected=len(collected_comments[:limit]),
            unique_collected=len(seen_comment_ids),
            status="completed",
            paging_completed=paging_completed,
        )
