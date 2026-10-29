"""Annotation management and schema validation module for Instagram slang comments.

Generates annotation templates, performs non-destructive merges preserving existing
human annotations, and validates multi-label taxonomy consistency without auto-labeling.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config import (
    ANNOTATED_DATA_DIR,
    LANGUAGE_FUNCTIONS,
    PROCESSED_DATA_DIR,
    SLANG_FORMS,
    ensure_directories,
)

# Standard columns for the annotated dataset according to Data Dictionary
ANNOTATED_FIELDNAMES: list[str] = [
    "comment_id",
    "clean_text",
    "slang_present",
    "slang_forms",
    "slang_spans",
    "slang_meanings",
    "language_functions",
    "annotator_id",
    "review_status",
    "adjudication_note",
]

DEFAULT_ANNOTATED_PATH: Path = ANNOTATED_DATA_DIR / "comments_labeled.csv"

VALID_SLANG_PRESENT = {"ya", "tidak"}
VALID_REVIEW_STATUS = {"belum", "selesai"}
VALID_SLANG_FORMS = set(SLANG_FORMS)
VALID_LANGUAGE_FUNCTIONS = set(LANGUAGE_FUNCTIONS)


@dataclass
class AnnotationValidationReport:
    """Detailed summary of annotation schema validation."""

    dataset_path: Path
    total_comments: int = 0
    total_completed: int = 0
    total_pending: int = 0
    total_invalid: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid_for_training(self) -> bool:
        """Training requires at least 1 validated completed annotation and 0 errors."""
        return self.total_completed > 0 and len(self.errors) == 0

    def summary_text(self) -> str:
        """Format validation results for terminal display."""
        lines = [
            "=" * 64,
            "RINGKASAN VALIDASI DATASET ANOTASI",
            "=" * 64,
            f"Lokasi File         : {self.dataset_path}",
            f"Total Komentar      : {self.total_comments}",
            f"Anotasi Selesai     : {self.total_completed}",
            f"Anotasi Belum Selesai: {self.total_pending}",
            f"Baris Bermasalah    : {self.total_invalid}",
            f"Siap untuk Training : {'YA' if self.is_valid_for_training else 'BELUM'}",
            "-" * 64,
        ]

        if self.warnings:
            lines.append(f"Peringatan ({len(self.warnings)}):")
            for w in self.warnings[:10]:
                lines.append(f"  [PERINGATAN] {w}")
            if len(self.warnings) > 10:
                lines.append(f"  ... dan {len(self.warnings) - 10} peringatan lainnya.")

        if self.errors:
            lines.append(f"Daftar Masalah Validasi ({len(self.errors)}):")
            for err in self.errors[:15]:
                lines.append(f"  [ERROR] {err}")
            if len(self.errors) > 15:
                lines.append(f"  ... dan {len(self.errors) - 15} kesalahan lainnya.")
        else:
            lines.append("[SUKSES] Semua label dan skema konsisten tanpa kesalahan.")

        lines.append("=" * 64)
        return "\n".join(lines)


def parse_multilabel_field(raw_value: str | None) -> list[str]:
    """Parse a semicolon-separated multi-label string into a trimmed, lowercased list of unique labels."""
    if not raw_value:
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw_part in str(raw_value).split(";"):
        cleaned = raw_part.strip().lower()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            items.append(cleaned)
    return items


def generate_annotation_template(
    processed_csv_path: Path,
    output_csv_path: Path | None = None,
) -> Path:
    """Generate or update the annotation template CSV from a processed dataset.

    Strict Non-Destructive Merge:
    - Merges by comment_id.
    - Preserves existing human annotations, status, spans, and notes.
    - Adds new comments from the processed dataset with review_status='belum'.
    - Does NOT attempt to automatically guess or predict labels.

    Args:
        processed_csv_path: Path to clean comments CSV in data/processed/.
        output_csv_path: Optional output path (defaults to data/annotated/comments_labeled.csv).

    Returns:
        Path: Path to the generated/merged comments_labeled.csv.

    Raises:
        FileNotFoundError: If processed_csv_path does not exist.
    """
    processed_csv_path = Path(processed_csv_path).resolve()
    if not processed_csv_path.exists():
        raise FileNotFoundError(f"Processed dataset tidak ditemukan di: {processed_csv_path}")

    ensure_directories()
    target_output_path = Path(output_csv_path or DEFAULT_ANNOTATED_PATH).resolve()
    target_output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Load existing annotations if file already exists
    existing_records: dict[str, dict[str, str]] = {}
    if target_output_path.exists():
        with open(target_output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                cid = row.get("comment_id", "").strip()
                if cid:
                    existing_records[cid] = row

    # 2. Read new processed comments
    new_records: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    with open(processed_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("comment_id", "").strip()
            clean_text = row.get("clean_text", "").strip()

            # Skip missing IDs, empty comments, or internal duplicate IDs in the batch
            if not cid or not clean_text or cid in seen_ids:
                continue
            seen_ids.add(cid)

            # If comment was already annotated in existing file, preserve exact human labels!
            if cid in existing_records:
                existing_row = existing_records[cid]
                record = {
                    "comment_id": cid,
                    "clean_text": clean_text or existing_row.get("clean_text", ""),
                    "slang_present": existing_row.get("slang_present", ""),
                    "slang_forms": existing_row.get("slang_forms", ""),
                    "slang_spans": existing_row.get("slang_spans", ""),
                    "slang_meanings": existing_row.get("slang_meanings", ""),
                    "language_functions": existing_row.get("language_functions", ""),
                    "annotator_id": existing_row.get("annotator_id", ""),
                    "review_status": existing_row.get("review_status", "belum"),
                    "adjudication_note": existing_row.get("adjudication_note", ""),
                }
            else:
                # Brand new record: pre-populate with linguistic classifier suggestions if available
                pre_forms = row.get("bentuk_bahasa_gaul", "").strip()
                pre_func = row.get("fungsi_bahasa", "").strip()
                pre_spans = row.get("kata_gaul", "").strip()
                slang_present = (
                    "ya" if (pre_forms and pre_forms != "tidak_ada")
                    else ("tidak" if pre_forms == "tidak_ada" else "")
                )

                record = {
                    "comment_id": cid,
                    "clean_text": clean_text,
                    "slang_present": slang_present,
                    "slang_forms": pre_forms if pre_forms != "tidak_ada" else "",
                    "slang_spans": pre_spans,
                    "slang_meanings": "",
                    "language_functions": pre_func if pre_func != "tidak_jelas" else "",
                    "annotator_id": "",
                    "review_status": "belum",
                    "adjudication_note": "",
                }
            new_records.append(record)

    # 3. Also preserve any existing records from target file that weren't in this processed batch
    for cid, existing_row in existing_records.items():
        if cid not in seen_ids:
            new_records.append(existing_row)
            seen_ids.add(cid)

    # 4. Write back merged dataset
    with open(target_output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=ANNOTATED_FIELDNAMES)
        writer.writeheader()
        writer.writerows(new_records)

    return target_output_path


def validate_annotated_dataset(
    dataset_path: Path | None = None,
) -> AnnotationValidationReport:
    """Validate annotated dataset against schema, multi-label taxonomy, and consistency rules.

    Validation Rules:
    1. Mandatory Columns: must contain all ANNOTATED_FIELDNAMES.
    2. Unique comment_id: duplicate or blank comment IDs are reported as errors.
    3. Non-empty clean_text: blank or missing comment text is reported as an error.
    4. review_status: must be 'belum' or 'selesai'.
    5. Completed Annotations (review_status == 'selesai'):
       - slang_present must be 'ya' or 'tidak'.
       - If slang_present == 'tidak': slang_forms must be 'tidak_ada'.
       - If slang_present == 'ya': slang_forms must be filled, cannot contain 'tidak_ada', and
         all items must be members of the official taxonomy.
       - language_functions must be filled, and all items must be members of the official taxonomy.
    6. Pending Annotations (review_status == 'belum'):
       - Counted toward total_pending if free from structural errors (valid ID, non-empty text).

    Args:
        dataset_path: Path to comments_labeled.csv (defaults to data/annotated/comments_labeled.csv).

    Returns:
        AnnotationValidationReport: Validation statistics and list of errors/warnings.

    Raises:
        FileNotFoundError: If dataset_path does not exist.
    """
    target_path = Path(dataset_path or DEFAULT_ANNOTATED_PATH).resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"File dataset anotasi tidak ditemukan di: {target_path}")

    report = AnnotationValidationReport(dataset_path=target_path)
    seen_comment_ids: set[str] = set()

    with open(target_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames or []

        # Check required columns
        missing_headers = [col for col in ANNOTATED_FIELDNAMES if col not in headers]
        if missing_headers:
            report.errors.append(
                f"Kolom wajib tidak lengkap pada file anotasi: {', '.join(missing_headers)}"
            )
            return report

        for row_idx, row in enumerate(reader, start=2):  # 1-indexed, header is line 1
            report.total_comments += 1
            row_has_error = False

            cid = row.get("comment_id", "").strip()
            clean_text = row.get("clean_text", "").strip()
            slang_present = row.get("slang_present", "").strip().lower()
            slang_forms_raw = row.get("slang_forms", "").strip()
            lang_funcs_raw = row.get("language_functions", "").strip()
            review_status = row.get("review_status", "").strip().lower()

            # 1. ID Check & Duplicate Detection
            if not cid:
                report.errors.append(f"Baris {row_idx}: comment_id kosong.")
                row_has_error = True
            elif cid in seen_comment_ids:
                report.errors.append(f"Baris {row_idx}: Duplikasi comment_id '{cid}' terdeteksi.")
                row_has_error = True
            else:
                seen_comment_ids.add(cid)

            # 2. Text Check
            if not clean_text:
                report.errors.append(f"Baris {row_idx} (ID: {cid or 'N/A'}): clean_text kosong.")
                row_has_error = True

            # 3. Review Status Validation
            if not review_status:
                review_status = "belum"

            if review_status not in VALID_REVIEW_STATUS:
                report.errors.append(
                    f"Baris {row_idx} (ID: {cid or 'N/A'}): review_status '{review_status}' tidak valid. "
                    f"Harus 'belum' atau 'selesai'."
                )
                row_has_error = True

            # If structural or status error occurred, row is counted as invalid
            if row_has_error:
                report.total_invalid += 1
                continue

            # If still pending review, count toward pending without requiring full labels
            if review_status == "belum":
                report.total_pending += 1
                continue

            # 4. Strict Consistency Validation for Completed Annotations ('selesai')
            # Check slang_present
            if slang_present not in VALID_SLANG_PRESENT:
                report.errors.append(
                    f"Baris {row_idx} (ID: {cid}): slang_present '{slang_present}' tidak valid. "
                    f"Harus 'ya' atau 'tidak' untuk anotasi yang selesai."
                )
                row_has_error = True

            # Parse multi-labels
            slang_forms_list = parse_multilabel_field(slang_forms_raw)
            lang_funcs_list = parse_multilabel_field(lang_funcs_raw)

            # Consistency Rule A: slang_present == 'tidak' -> slang_forms must be 'tidak_ada'
            if slang_present == "tidak":
                if not slang_forms_list or slang_forms_list != ["tidak_ada"]:
                    report.errors.append(
                        f"Baris {row_idx} (ID: {cid}): Inkonsistensi - slang_present='tidak' "
                        f"tetapi slang_forms='{slang_forms_raw}'. Harus 'tidak_ada'."
                    )
                    row_has_error = True

            # Consistency Rule B: slang_present == 'ya' -> must have valid slang forms and NOT contain 'tidak_ada'
            elif slang_present == "ya":
                if not slang_forms_list:
                    report.errors.append(
                        f"Baris {row_idx} (ID: {cid}): slang_forms belum diisi untuk slang_present='ya'."
                    )
                    row_has_error = True
                elif slang_forms_list == ["tidak_ada"]:
                    report.errors.append(
                        f"Baris {row_idx} (ID: {cid}): Inkonsistensi - slang_present='ya' "
                        f"tetapi slang_forms hanya '{slang_forms_raw}'. Harus memuat bentuk slang selain 'tidak_ada'."
                    )
                    row_has_error = True
                elif "tidak_ada" in slang_forms_list:
                    report.errors.append(
                        f"Baris {row_idx} (ID: {cid}): Inkonsistensi - slang_present='ya' "
                        f"memuat 'tidak_ada' bersama bentuk slang lainnya: '{slang_forms_raw}'."
                    )
                    row_has_error = True
                else:
                    for s_form in slang_forms_list:
                        if s_form not in VALID_SLANG_FORMS:
                            report.errors.append(
                                f"Baris {row_idx} (ID: {cid}): Bentuk slang '{s_form}' tidak dikenal. "
                                f"Pilihan resmi: {', '.join(SLANG_FORMS)}."
                            )
                            row_has_error = True

            # Consistency Rule C: language_functions must be filled and valid for completed review
            if not lang_funcs_list:
                report.errors.append(
                    f"Baris {row_idx} (ID: {cid}): language_functions belum diisi untuk anotasi selesai."
                )
                row_has_error = True
            else:
                for func in lang_funcs_list:
                    if func not in VALID_LANGUAGE_FUNCTIONS:
                        report.errors.append(
                            f"Baris {row_idx} (ID: {cid}): Fungsi bahasa '{func}' tidak dikenal. "
                            f"Pilihan resmi: {', '.join(LANGUAGE_FUNCTIONS)}."
                        )
                        row_has_error = True

            if row_has_error:
                report.total_invalid += 1
            else:
                report.total_completed += 1

    return report
