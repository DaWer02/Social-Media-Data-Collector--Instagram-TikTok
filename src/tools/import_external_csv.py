"""Module to convert external Instagram export files (CSV, Excel) to project RAW format.

Supports CSV, TSV, and XLSX exported from third-party tools such as:
- Chrome extensions (e.g. IG Comment Exporter, Export Comments for Instagram)
- Online tools (e.g. ExportComments, CommentPicker, Apify)
- Manual scrapers or datasets

Automatically maps varied column names, generates comment IDs if absent,
preserves emojis and UTF-8 characters, and writes to data/raw/comments_<run_id>.csv
for immediate use with Menu 2 ("Jalankan NLP pada RAW yang sudah ada").
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import sys
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from src.config import RAW_DATA_DIR, ensure_directories
from src.storage import generate_run_id, save_raw_comments, save_run_metadata

# Common column synonyms for Instagram comment exports
COLUMN_SYNONYMS: dict[str, list[str]] = {
    "comment_text": [
        "comment_text",
        "comment",
        "text",
        "content",
        "komentar",
        "pesan",
        "body",
        "caption",
        "review",
        "message",
        "isi_komentar",
    ],
    "comment_id": [
        "comment_id",
        "id",
        "cid",
        "commentid",
        "no",
        "index",
        "pk",
        "id_komentar",
    ],
    "media_id": [
        "media_id",
        "post_id",
        "shortcode",
        "post_shortcode",
        "url",
        "post_url",
        "media_url",
        "link",
        "post",
        "id_post",
    ],
    "timestamp": [
        "timestamp",
        "created_at",
        "created_time",
        "date",
        "time",
        "waktu",
        "tanggal",
        "datetime",
        "created_at_utc",
    ],
    "like_count": [
        "like_count",
        "likes",
        "likes_count",
        "like",
        "suka",
        "jumlah_like",
    ],
}


def detect_column_mapping(columns: Sequence[str]) -> dict[str, str]:
    """Map detected file columns to standard project schema.

    Returns:
        dict[str, str]: Map of {standard_field: detected_column_name}
    """
    mapping: dict[str, str] = {}
    normalized_cols = {str(col).strip().lower(): col for col in columns}

    for std_field, synonyms in COLUMN_SYNONYMS.items():
        for syn in synonyms:
            if syn in normalized_cols:
                mapping[std_field] = normalized_cols[syn]
                break

    return mapping


def extract_shortcode_from_url_or_text(text: str) -> str | None:
    """Extract shortcode from Instagram URL or return sanitized token."""
    if not text:
        return None
    # Match /p/DeRfCHemNKL/ or /reel/DeRfCHemNKL/
    match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", text)
    if match:
        return match.group(1)
    # If alphanumeric short string (5 to 30 chars)
    if re.match(r"^[A-Za-z0-9_-]{5,30}$", text.strip()):
        return text.strip()
    return None


def convert_external_file_to_raw(
    filepath: Path | str,
    media_id: str | None = None,
    run_id: str | None = None,
) -> tuple[Path, int]:
    """Convert an external CSV or Excel file to project RAW comments format.

    Args:
        filepath: Path to CSV or XLSX file.
        media_id: Optional fallback media ID or shortcode.
        run_id: Optional run_id. If None, generated automatically.

    Returns:
        tuple[Path, int]: (Path to created RAW file, count of comments imported)

    Raises:
        FileNotFoundError: If filepath does not exist.
        ValueError: If file cannot be read or comment text column is not found.
    """
    path = Path(filepath).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")

    # Read dataframe with robust format/encoding detection
    suffix = path.suffix.lower()
    df: pd.DataFrame
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path)
    else:
        # Try multiple encodings for CSV/TSV
        encodings = ["utf-8-sig", "utf-8", "latin-1", "cp1252"]
        delimiters = [",", ";", "\t", "|"]
        loaded = False
        last_err: Exception | None = None

        for enc in encodings:
            for sep in delimiters:
                try:
                    candidate_df = pd.read_csv(path, encoding=enc, sep=sep, dtype=str)
                    # Check if at least 1 column has reasonable name
                    if len(candidate_df.columns) >= 1:
                        df = candidate_df
                        loaded = True
                        break
                except Exception as err:
                    last_err = err
                    continue
            if loaded:
                break

        if not loaded:
            raise ValueError(f"Gagal membaca file CSV '{path}'. Detail: {last_err}")

    if df.empty:
        raise ValueError(f"File '{path}' kosong (0 baris data).")

    # Detect mapping
    col_map = detect_column_mapping(df.columns)
    if "comment_text" not in col_map:
        available_cols = ", ".join(f"'{c}'" for c in df.columns)
        raise ValueError(
            f"Kolom teks komentar tidak ditemukan dalam file.\n"
            f"Kolom yang terdeteksi: [{available_cols}].\n"
            f"Harap sediakan salah satu nama kolom berikut: {COLUMN_SYNONYMS['comment_text']}"
        )

    text_col = col_map["comment_text"]
    id_col = col_map.get("comment_id")
    media_col = col_map.get("media_id")
    time_col = col_map.get("timestamp")
    like_col = col_map.get("like_count")

    # Determine default media ID
    resolved_default_media_id = media_id or extract_shortcode_from_url_or_text(path.stem) or "ext_post"

    clean_records: list[dict[str, Any]] = []
    now_iso = datetime.datetime.now().isoformat()

    for idx, row in df.iterrows():
        raw_text = row[text_col]
        if pd.isna(raw_text):
            continue
        comment_text = str(raw_text).strip()
        if not comment_text:
            continue

        # Resolve comment_id
        if id_col and pd.notna(row[id_col]) and str(row[id_col]).strip():
            cid = str(row[id_col]).strip()
        else:
            cid = f"ext_{resolved_default_media_id}_{idx + 1:05d}"

        # Resolve media_id
        if media_col and pd.notna(row[media_col]) and str(row[media_col]).strip():
            val = str(row[media_col]).strip()
            shortcode = extract_shortcode_from_url_or_text(val)
            row_media_id = shortcode if shortcode else val
        else:
            row_media_id = resolved_default_media_id

        # Resolve timestamp
        if time_col and pd.notna(row[time_col]) and str(row[time_col]).strip():
            ts = str(row[time_col]).strip()
        else:
            ts = now_iso

        # Resolve like_count
        likes = 0
        if like_col and pd.notna(row[like_col]):
            try:
                likes = int(float(row[like_col]))
            except (ValueError, TypeError):
                likes = 0

        clean_records.append({
            "comment_id": cid,
            "media_id": row_media_id,
            "comment_text": comment_text,
            "timestamp": ts,
            "like_count": likes,
            "collected_at": now_iso,
            "source_type": "external_import",
        })

    if not clean_records:
        raise ValueError("Tidak ada komentar valid (non-kosong) yang berhasil diekstrak.")

    actual_run_id = run_id or generate_run_id()
    raw_path = save_raw_comments(run_id=actual_run_id, comments=clean_records)
    save_run_metadata(
        run_id=actual_run_id,
        status="imported_raw",
        extra_data={
            "source_file": str(path),
            "media_id": resolved_default_media_id,
            "total_imported": len(clean_records),
            "source_type": "external_import",
        },
    )

    return raw_path, len(clean_records)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point for converting external files."""
    parser = argparse.ArgumentParser(
        description="Konversi file CSV / Excel eksternal hasil export komentar Instagram ke format RAW proyek.",
    )
    parser.add_argument("file_path", help="Path file CSV atau XLSX eksternal yang diunduh")
    parser.add_argument(
        "--media-id",
        default=None,
        help="ID atau shortcode postingan (misal: DeRfCHemNKL). Opsional jika sudah ada di kolom file.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="ID run kustom (opsional). Default di-generate otomatis.",
    )

    args = parser.parse_args(argv)

    try:
        raw_path, count = convert_external_file_to_raw(
            filepath=args.file_path,
            media_id=args.media_id,
            run_id=args.run_id,
        )
        print("=" * 60)
        print("          KONVERSI DATASET RAW BERHASIL")
        print("=" * 60)
        print(f" File Sumber   : {args.file_path}")
        print(f" Total Komentar: {count} baris valid")
        print(f" File RAW Baru : {raw_path}")
        print("=" * 60)
        print("\nLangkah berikutnya:")
        print("  1. Jalankan CLI: python main.py")
        print(f"  2. Pilih Menu 2 ('Jalankan NLP pada RAW yang sudah ada')")
        print(f"  3. Pilih file '{raw_path.name}' untuk diproses!")
        print("=" * 60)
        return 0
    except Exception as err:
        print(f"\n[ERROR] Konversi gagal: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
