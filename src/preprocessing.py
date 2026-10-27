"""Text preprocessing module for Instagram slang comments.

Preserves original comment text without destructive filtering,
handles emoji and punctuation conservatively, normalizes URLs to [URL],
checks mandatory columns, flags duplicates and empty comments,
and guarantees that RAW files remain immutable.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config import ensure_directories
from src.storage import get_processed_filepath

# Mandatory columns required in RAW dataset according to Data Dictionary
REQUIRED_RAW_COLUMNS: list[str] = ["comment_id", "media_id", "comment_text"]

PROCESSED_FIELDNAMES: list[str] = [
    "comment_id",
    "media_id",
    "comment_text",
    "clean_text",
    "normalized_text",
    "is_empty_after_cleaning",
    "duplicate_status",
]

# Regex pattern for web URLs
URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


class PreprocessingValidationError(ValueError):
    """Exception raised when RAW dataset fails schema or validation checks."""

    def __init__(self, message: str, missing_columns: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.missing_columns = missing_columns or []


@dataclass(frozen=True)
class PreprocessingReport:
    """Summary of data transformations performed during preprocessing."""

    raw_filepath: Path
    processed_filepath: Path
    total_initial: int
    total_empty: int
    total_duplicate: int
    total_final: int
    missing_columns: list[str]

    def summary_text(self) -> str:
        """Format report into human-readable summary for terminal display."""
        return (
            "=" * 60 + "\n"
            "RINGKASAN PREPROCESSING DATASET\n"
            f"File Sumber RAW    : {self.raw_filepath.name}\n"
            f"File Hasil Bersih  : {self.processed_filepath.name}\n"
            f"Total Baris Awal   : {self.total_initial}\n"
            f"Komentar Kosong    : {self.total_empty}\n"
            f"Komentar Duplikat  : {self.total_duplicate}\n"
            f"Total Baris Akhir  : {self.total_final} (unik & tidak kosong)\n"
            + "=" * 60
        )


def clean_comment_text(text: str | None) -> str:
    """Conservatively clean raw comment text while preserving slang, emoji, and punctuation.

    Decisions (Rule FR-06 & Guideline):
    1. Normalizes web URLs to the canonical '[URL]' token to eliminate noise while retaining link presence.
    2. Preserves all emoji characters (essential for emotional/sentiment context).
    3. Preserves punctuation marks (!, ?, ..., etc.) and repeated letters (e.g. 'bangeeet', 'kuyyy').
    4. Normalizes excessive whitespace and line breaks into single spaces.
    5. Strips leading and trailing whitespace.
    6. Does NOT perform stemming, stopword removal, or automatic slang replacement.
    """
    if text is None:
        return ""

    raw_str = str(text)

    # 1. Replace web URLs with [URL] token
    without_urls = URL_PATTERN.sub("[URL]", raw_str)

    # 2. Normalize whitespace (tabs, newlines, multiple spaces) to a single space
    normalized_spaces = re.sub(r"\s+", " ", without_urls)

    # 3. Strip leading and trailing whitespace
    return normalized_spaces.strip()


def normalize_text_for_analysis(text: str | None) -> str:
    """Provide lowercased text for downstream tokenization without altering clean_text.

    Stored in the separate 'normalized_text' column; comment_text and clean_text
    maintain their original letter casing.
    """
    return clean_comment_text(text).lower()


def validate_raw_dataset_schema(raw_csv_path: Path) -> list[str]:
    """Validate that the RAW dataset contains all mandatory columns.

    Args:
        raw_csv_path: Path to the RAW CSV file.

    Returns:
        list[str]: List of missing mandatory column names (empty if valid).

    Raises:
        FileNotFoundError: If raw_csv_path does not exist.
    """
    if not raw_csv_path.exists():
        raise FileNotFoundError(f"File RAW tidak ditemukan: {raw_csv_path}")

    with open(raw_csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            return REQUIRED_RAW_COLUMNS.copy()

    headers_set = {h.strip() for h in headers}
    missing = [col for col in REQUIRED_RAW_COLUMNS if col not in headers_set]
    return missing


def preprocess_dataset_with_report(
    raw_csv_path: Path,
    run_id: str | None = None,
    output_csv_path: Path | None = None,
) -> PreprocessingReport:
    """Read a RAW comments CSV in read-only mode, clean data, and output a detailed report.

    Guarantees RAW dataset immutability: the source file is never modified or opened in write mode.

    Args:
        raw_csv_path: Path to the source RAW CSV file.
        run_id: Optional run_id (inferred from filename if not provided).
        output_csv_path: Optional explicit output path in data/processed/.

    Returns:
        PreprocessingReport: Detailed count statistics and paths.

    Raises:
        FileNotFoundError: If raw_csv_path does not exist.
        PreprocessingValidationError: If mandatory columns are missing from the RAW file.
    """
    raw_csv_path = Path(raw_csv_path).resolve()
    if not raw_csv_path.exists():
        raise FileNotFoundError(f"RAW dataset tidak ditemukan di: {raw_csv_path}")

    # Validate mandatory schema
    missing_cols = validate_raw_dataset_schema(raw_csv_path)
    if missing_cols:
        raise PreprocessingValidationError(
            f"File RAW '{raw_csv_path.name}' tidak memenuhi skema wajib. "
            f"Kolom yang hilang: {', '.join(missing_cols)}.",
            missing_columns=missing_cols,
        )

    ensure_directories()

    # Determine run_id and output path
    effective_run_id = run_id or raw_csv_path.stem.replace("comments_", "")
    output_path = output_csv_path or get_processed_filepath(effective_run_id)

    total_initial = 0
    total_empty = 0
    total_duplicate = 0
    seen_comment_ids: set[str] = set()
    rows_to_write: list[dict[str, Any]] = []

    # Read RAW file in strict read-only mode
    with open(raw_csv_path, "r", encoding="utf-8") as infile:
        reader = csv.DictReader(infile)

        for row in reader:
            total_initial += 1
            cid = row.get("comment_id", "").strip()
            raw_text = row.get("comment_text", "")
            media_id = row.get("media_id", "").strip()

            clean_text = clean_comment_text(raw_text)
            norm_text = normalize_text_for_analysis(raw_text)
            is_empty = len(clean_text) == 0

            if is_empty:
                total_empty += 1

            # Deduplication logic by comment_id
            is_dup = False
            if cid:
                if cid in seen_comment_ids:
                    is_dup = True
                    total_duplicate += 1
                else:
                    seen_comment_ids.add(cid)

            rows_to_write.append(
                {
                    "comment_id": cid,
                    "media_id": media_id,
                    "comment_text": raw_text,  # Untouched original text
                    "clean_text": clean_text,
                    "normalized_text": norm_text,
                    "is_empty_after_cleaning": str(is_empty).lower(),
                    "duplicate_status": "duplicate" if is_dup else "unique",
                }
            )

    # Calculate final usable rows (non-empty and unique)
    total_final = sum(
        1 for r in rows_to_write
        if r["is_empty_after_cleaning"] == "false" and r["duplicate_status"] == "unique"
    )

    # Write processed clean dataset
    with open(output_path, "w", newline="", encoding="utf-8") as outfile:
        writer = csv.DictWriter(outfile, fieldnames=PROCESSED_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows_to_write)

    return PreprocessingReport(
        raw_filepath=raw_csv_path,
        processed_filepath=output_path,
        total_initial=total_initial,
        total_empty=total_empty,
        total_duplicate=total_duplicate,
        total_final=total_final,
        missing_columns=[],
    )


def preprocess_raw_dataset(
    raw_csv_path: Path,
    run_id: str | None = None,
    output_csv_path: Path | None = None,
) -> Path:
    """Wrapper that executes preprocessing and returns the Path to the processed file.

    Maintains full backward compatibility with CLI and pipeline integration callers.
    """
    report = preprocess_dataset_with_report(
        raw_csv_path=raw_csv_path,
        run_id=run_id,
        output_csv_path=output_csv_path,
    )
    return report.processed_filepath
