"""Configuration module for Instagram Slang NLP CLI.

Manages application settings, path resolutions using pathlib,
strict validation of runtime parameters, and guarantees that secrets
and tokens are never exposed or saved inadvertently.
"""

from __future__ import annotations

import getpass
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

# Base Paths using pathlib
BASE_DIR: Path = Path(__file__).resolve().parent.parent
SRC_DIR: Path = BASE_DIR / "src"
DATA_DIR: Path = BASE_DIR / "data"
RAW_DATA_DIR: Path = DATA_DIR / "raw"
PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
ANNOTATED_DATA_DIR: Path = DATA_DIR / "annotated"
PREDICTIONS_DATA_DIR: Path = DATA_DIR / "predictions"
MODELS_DIR: Path = BASE_DIR / "models"
REPORTS_DIR: Path = BASE_DIR / "reports"
DOCS_DIR: Path = BASE_DIR / "docs"

# Taxonomy Constants
SLANG_FORMS: tuple[str, ...] = (
    "akronim",
    "singkatan",
    "bahasa_asing",
    "plesetan",
    "pemendekan",
    "tidak_ada",
    "lainnya",
)

LANGUAGE_FUNCTIONS: tuple[str, ...] = (
    "emotif",
    "referensial",
    "konatif",
    "tidak_jelas",
)


class ConfigValidationError(ValueError):
    """Exception raised when configuration parameters fail validation."""

    def __init__(self, message: str, safe_action: str | None = None) -> None:
        full_msg = message
        if safe_action:
            full_msg = f"{message} Tindakan aman: {safe_action}"
        super().__init__(full_msg)
        self.message = message
        self.safe_action = safe_action


def ensure_directories() -> None:
    """Ensure all required application directories exist."""
    directories: list[Path] = [
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        ANNOTATED_DATA_DIR,
        PREDICTIONS_DATA_DIR,
        MODELS_DIR,
        REPORTS_DIR,
        DOCS_DIR,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)


def load_env_file(env_path: Path | None = None) -> None:
    """Load environment variables from .env file if it exists."""
    target_path = env_path or (BASE_DIR / ".env")
    if not target_path.exists():
        return

    try:
        from dotenv import load_dotenv
        load_dotenv(target_path)
    except ImportError:
        # Fallback simple parser if python-dotenv is not installed
        with open(target_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key not in os.environ:
                        os.environ[key] = val


def validate_target_comments(val: Any) -> int:
    """Validate that target comment count is a positive integer.

    Args:
        val: Value to validate (int, float, or str).

    Returns:
        int: Validated positive integer.

    Raises:
        ConfigValidationError: If value is not a positive integer.
    """
    safe_action = (
        "Tentukan angka bulat positif lebih besar dari 0 (contoh: TARGET_COMMENTS=3000 pada .env)."
    )
    if val is None:
        return 3000

    try:
        num = int(str(val).strip())
    except (ValueError, TypeError):
        raise ConfigValidationError(
            f"Target komentar '{val}' bukan angka integer yang valid.",
            safe_action=safe_action,
        )

    if num <= 0:
        raise ConfigValidationError(
            f"Target komentar harus lebih besar dari 0 (diterima: {num}).",
            safe_action=safe_action,
        )

    return num


def validate_graph_api_version(version: str | None) -> str:
    """Validate Graph API version format (e.g. v21.0)."""
    if not version or not str(version).strip():
        return "v21.0"

    cleaned = str(version).strip().lower()
    if not re.match(r"^v\d+\.\d+$", cleaned):
        raise ConfigValidationError(
            f"Format versi Graph API '{version}' tidak valid.",
            safe_action="Gunakan format versi resmi Meta Graph API seperti 'v21.0' pada GRAPH_API_VERSION di .env.",
        )
    return cleaned


def validate_api_variant(variant: str | None) -> str:
    """Validate Instagram API variant (facebook_login or instagram_login)."""
    if not variant or not str(variant).strip():
        return "facebook_login"
    cleaned = str(variant).strip().lower()
    if cleaned not in {"facebook_login", "instagram_login"}:
        raise ConfigValidationError(
            f"Varian API '{variant}' tidak didukung.",
            safe_action="Gunakan 'facebook_login' (default) atau 'instagram_login' pada INSTAGRAM_API_VARIANT di .env.",
        )
    return cleaned


def mask_token(token: str | None) -> str:
    """Return a safely redacted representation of a secret token.

    Never exposes full tokens in output, logs, or reports.
    """
    if not token or not token.strip():
        return "<TIDAK_DISET>"
    token = token.strip()
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"


def sanitize_url(url: str) -> str:
    """Remove access tokens from query strings in URLs."""
    if not url:
        return ""
    # Redact access_token parameter
    sanitized = re.sub(r"([?&]access_token=)[^&\s]+", r"\1***REDACTED***", url)
    return sanitized


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of headers with authorization credentials sanitized."""
    sanitized = {}
    for k, v in headers.items():
        if k.lower() in {"authorization", "x-access-token", "token"}:
            sanitized[k] = "Bearer ***REDACTED***" if "bearer" in v.lower() else "***REDACTED***"
        else:
            sanitized[k] = v
    return sanitized


@dataclass
class AppConfig:
    """Application runtime configuration with secure defaults."""

    access_token: str | None = None
    target_comments: int = 3000
    graph_api_version: str = "v21.0"
    api_variant: str = "facebook_login"
    app_env: str = "development"
    log_level: str = "INFO"
    raw_dir: Path = RAW_DATA_DIR
    processed_dir: Path = PROCESSED_DATA_DIR
    annotated_dir: Path = ANNOTATED_DATA_DIR
    predictions_dir: Path = PREDICTIONS_DATA_DIR
    models_dir: Path = MODELS_DIR
    reports_dir: Path = REPORTS_DIR
    docs_dir: Path = DOCS_DIR

    def __post_init__(self) -> None:
        """Validate fields upon initialization."""
        self.target_comments = validate_target_comments(self.target_comments)
        self.graph_api_version = validate_graph_api_version(self.graph_api_version)
        self.api_variant = validate_api_variant(self.api_variant)

    def __repr__(self) -> str:
        """Secure representation that masks sensitive tokens."""
        return (
            f"AppConfig("
            f"access_token={mask_token(self.access_token)}, "
            f"target_comments={self.target_comments}, "
            f"graph_api_version='{self.graph_api_version}', "
            f"api_variant='{self.api_variant}', "
            f"app_env='{self.app_env}', "
            f"log_level='{self.log_level}')"
        )

    def __str__(self) -> str:
        return self.__repr__()

    def get_or_prompt_access_token(
        self,
        prompt_fn: Callable[[str], str] | None = None,
    ) -> str:
        """Return the current token, or prompt securely using hidden input for this session.

        Does NOT write or persist the token to file.

        Args:
            prompt_fn: Optional callable for hidden input (defaults to getpass.getpass).

        Returns:
            str: Valid session access token.

        Raises:
            ConfigValidationError: If no token is provided.
        """
        if self.access_token and self.access_token.strip():
            return self.access_token.strip()

        prompter = prompt_fn or getpass.getpass
        print("\n[PERINGATAN] Access Token tidak ditemukan di .env atau variabel lingkungan.")
        print("Silakan masukkan token akses Meta for Developers secara aman untuk sesi ini.")
        print("(Karakter tidak akan ditampilkan ke layar dan TIDAK akan disimpan ke file).")

        try:
            token_input = prompter("Masukkan Instagram Access Token: ").strip()
        except (KeyboardInterrupt, EOFError):
            raise ConfigValidationError(
                "Input token dibatalkan oleh pengguna.",
                safe_action="Jalankan kembali program dan masukkan token yang sah saat diminta.",
            )

        if not token_input:
            raise ConfigValidationError(
                "Token akses Instagram tidak boleh kosong.",
                safe_action=(
                    "Dapatkan User/Page Access Token dengan scope 'instagram_manage_comments' "
                    "dari Meta for Developers, lalu masukkan token untuk sesi ini atau simpan di file .env lokal."
                ),
            )

        # Store in-memory only for this session
        self.access_token = token_input
        return self.access_token

    @classmethod
    def from_env(cls, env_path: Path | None = None) -> AppConfig:
        """Create configuration instance from environment variables with validation."""
        load_env_file(env_path)

        token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip() or None
        api_version = os.getenv("GRAPH_API_VERSION", "v21.0").strip()
        api_variant = os.getenv("INSTAGRAM_API_VARIANT", "facebook_login").strip()

        raw_target = os.getenv("TARGET_COMMENTS", "3000")
        target_comments = validate_target_comments(raw_target)

        app_env = os.getenv("APP_ENV", "development").strip()
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

        return cls(
            access_token=token,
            target_comments=target_comments,
            graph_api_version=api_version,
            api_variant=api_variant,
            app_env=app_env,
            log_level=log_level,
            raw_dir=RAW_DATA_DIR,
            processed_dir=PROCESSED_DATA_DIR,
            annotated_dir=ANNOTATED_DATA_DIR,
            predictions_dir=PREDICTIONS_DATA_DIR,
            models_dir=MODELS_DIR,
            reports_dir=REPORTS_DIR,
            docs_dir=DOCS_DIR,
        )
