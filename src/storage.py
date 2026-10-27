"""Storage module for managing datasets, run metadata, and ensuring RAW immutability."""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Sequence

from src.collectors.base import CommentRecord
from src.config import (
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    REPORTS_DIR,
    ensure_directories,
)

RAW_FIELDNAMES: list[str] = [
    "comment_id",
    "media_id",
    "comment_text",
    "timestamp",
    "like_count",
    "collected_at",
    "source_type",
]


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp and short UUID."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    short_uid = uuid.uuid4().hex[:6]
    return f"{timestamp}_{short_uid}"


def get_raw_filepath(run_id: str) -> Path:
    """Get the target Path for a RAW comments CSV file."""
    return RAW_DATA_DIR / f"comments_{run_id}.csv"


def get_processed_filepath(run_id: str) -> Path:
    """Get the target Path for a processed clean comments CSV file."""
    return PROCESSED_DATA_DIR / f"comments_clean_{run_id}.csv"


def get_run_metadata_filepath(run_id: str) -> Path:
    """Get the target Path for a run report JSON file."""
    return REPORTS_DIR / f"run_{run_id}.json"


def calculate_file_sha256(filepath: Path) -> str:
    """Calculate the SHA-256 hash of a file for immutability verification."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _sanitize_metadata_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize any dictionary to guarantee no secret tokens are stored."""
    sanitized: dict[str, Any] = {}
    for k, v in data.items():
        k_lower = str(k).lower()
        if "token" in k_lower or "secret" in k_lower or "password" in k_lower:
            continue
        if isinstance(v, dict):
            sanitized[k] = _sanitize_metadata_dict(v)
        else:
            sanitized[k] = v
    return sanitized


def save_raw_comments(
    run_id: str,
    comments: Sequence[CommentRecord | dict[str, Any]],
) -> Path:
    """Save collected comments to a new RAW CSV file.

    Guarantees immutability: will fail if the file already exists,
    ensures strictly minimal fields, and never persists sensitive tokens or usernames.

    Args:
        run_id: Unique run identifier.
        comments: Sequence of CommentRecord objects or dictionaries.

    Returns:
        Path: The absolute path of the created RAW CSV file.

    Raises:
        FileExistsError: If a file with this run_id already exists.
    """
    ensure_directories()
    raw_path = get_raw_filepath(run_id)

    if raw_path.exists():
        raise FileExistsError(
            f"RAW dataset '{raw_path}' sudah ada. File RAW bersifat immutable dan tidak boleh ditimpa."
        )

    with open(raw_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=RAW_FIELDNAMES,
            extrasaction="ignore",
        )
        writer.writeheader()

        for comment in comments:
            if isinstance(comment, CommentRecord):
                row = comment.to_dict()
            elif isinstance(comment, dict):
                row = {
                    "comment_id": str(comment.get("comment_id", "")),
                    "media_id": str(comment.get("media_id", "")),
                    "comment_text": str(comment.get("comment_text", "")),
                    "timestamp": comment.get("timestamp") or "",
                    "like_count": comment.get("like_count", 0),
                    "collected_at": comment.get("collected_at") or datetime.datetime.now().isoformat(),
                    "source_type": comment.get("source_type", "authorized_api"),
                }
            else:
                continue

            writer.writerow(row)

    return raw_path


def save_run_metadata(
    run_id: str,
    status: str,
    extra_data: dict[str, Any] | None = None,
) -> Path:
    """Save run metadata to reports/run_<run_id>.json without sensitive tokens."""
    ensure_directories()
    metadata_path = get_run_metadata_filepath(run_id)

    metadata: dict[str, Any] = {
        "run_id": run_id,
        "recorded_at": datetime.datetime.now().isoformat(),
        "status": status,
    }

    if extra_data:
        sanitized_extra = _sanitize_metadata_dict(extra_data)
        metadata.update(sanitized_extra)

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return metadata_path


def update_run_metadata(
    run_id: str,
    updates: dict[str, Any],
) -> Path:
    """Update existing run metadata in reports/run_<run_id>.json safely."""
    ensure_directories()
    metadata_path = get_run_metadata_filepath(run_id)

    existing_data: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = {"run_id": run_id}
    else:
        existing_data = {"run_id": run_id, "recorded_at": datetime.datetime.now().isoformat()}

    sanitized_updates = _sanitize_metadata_dict(updates)
    existing_data.update(sanitized_updates)
    existing_data["updated_at"] = datetime.datetime.now().isoformat()

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2)

    return metadata_path
