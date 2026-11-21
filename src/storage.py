"""Storage module for managing datasets, run metadata, and ensuring privacy & immutability.

Strict privacy rules:
- Author usernames and account identities are NEVER stored in exported datasets.
- Mentions in comments are sanitized to [@USER].
- Supports both CSV and Excel (.xlsx) formats.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from src.collectors.base import CommentRecord
from src.config import (
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    REPORTS_DIR,
    ensure_directories,
)
from src.privacy import sanitize_comment_text

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


def get_raw_filepath(run_id: str, extension: str = "csv") -> Path:
    """Get the target Path for a RAW comments dataset file."""
    ext = extension.lstrip(".")
    return RAW_DATA_DIR / f"comments_{run_id}.{ext}"


def get_processed_filepath(run_id: str, extension: str = "csv") -> Path:
    """Get the target Path for a processed clean comments dataset file."""
    ext = extension.lstrip(".")
    return PROCESSED_DATA_DIR / f"comments_clean_{run_id}.{ext}"


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


def prepare_rows_for_export(
    comments: Sequence[CommentRecord | dict[str, Any]]
) -> list[dict[str, Any]]:
    """Convert comment records to privacy-compliant dictionaries."""
    rows: list[dict[str, Any]] = []
    for comment in comments:
        if isinstance(comment, CommentRecord):
            raw_txt = comment.comment_text
            row = {
                "comment_id": comment.comment_id,
                "media_id": comment.media_id,
                "comment_text": sanitize_comment_text(raw_txt),
                "timestamp": comment.timestamp or "",
                "like_count": comment.like_count if comment.like_count is not None else 0,
                "collected_at": comment.collected_at or "",
                "source_type": comment.source_type,
            }
        elif isinstance(comment, dict):
            raw_txt = str(comment.get("comment_text", ""))
            row = {
                "comment_id": str(comment.get("comment_id", "")),
                "media_id": str(comment.get("media_id", "")),
                "comment_text": sanitize_comment_text(raw_txt),
                "timestamp": comment.get("timestamp") or "",
                "like_count": comment.get("like_count", 0),
                "collected_at": comment.get("collected_at") or datetime.datetime.now().isoformat(),
                "source_type": comment.get("source_type", "social_scraper"),
            }
        else:
            continue

        # Double check: username must never be present
        row.pop("username", None)
        row.pop("author", None)
        rows.append(row)
    return rows


def save_raw_comments(
    run_id: str,
    comments: Sequence[CommentRecord | dict[str, Any]],
    output_format: str = "both",
) -> Path:
    """Save collected comments to RAW dataset file(s) (CSV, Excel, or Both).

    Guarantees privacy:
    - Never persists usernames or account handles.
    - Sanitizes @mentions into [@USER].

    Args:
        run_id: Unique run identifier.
        comments: Sequence of CommentRecord objects or dictionaries.
        output_format: "csv", "xlsx", or "both" (default).

    Returns:
        Path: The primary created dataset file path.
    """
    ensure_directories()
    rows = prepare_rows_for_export(comments)

    save_csv = output_format.lower() in {"csv", "both"}
    save_xlsx = output_format.lower() in {"xlsx", "excel", "both"}

    primary_path: Path | None = None

    # 1. Save CSV
    if save_csv:
        csv_path = get_raw_filepath(run_id, "csv")
        if csv_path.exists():
            raise FileExistsError(f"RAW CSV '{csv_path}' sudah ada.")

        with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(
                csvfile,
                fieldnames=RAW_FIELDNAMES,
                extrasaction="ignore",
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        primary_path = csv_path

    # 2. Save Excel (.xlsx)
    if save_xlsx:
        xlsx_path = get_raw_filepath(run_id, "xlsx")
        if xlsx_path.exists():
            raise FileExistsError(f"RAW Excel '{xlsx_path}' sudah ada.")

        df = pd.DataFrame(rows, columns=RAW_FIELDNAMES)
        df.to_excel(xlsx_path, index=False, engine="openpyxl")
        if not primary_path:
            primary_path = xlsx_path

    return primary_path or get_raw_filepath(run_id, "csv")


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
