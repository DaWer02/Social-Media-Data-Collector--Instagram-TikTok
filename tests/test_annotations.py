"""Unit tests for annotation template generator and validator."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.annotations import (
    ANNOTATED_FIELDNAMES,
    DEFAULT_ANNOTATED_PATH,
    AnnotationValidationReport,
    generate_annotation_template,
    parse_multilabel_field,
    validate_annotated_dataset,
)


class TestAnnotations(unittest.TestCase):
    """Test suite for annotation template generation, merging, and schema validation."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_csv(self, filepath: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> Path:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return filepath

    # -------------------------------------------------------------------------
    # 1. Multi-label Parsing Tests
    # -------------------------------------------------------------------------

    def test_parse_multilabel_field(self) -> None:
        """Verify semicolon separation, trimming, lowercasing, and duplicate removal."""
        self.assertEqual(parse_multilabel_field(""), [])
        self.assertEqual(parse_multilabel_field(None), [])
        self.assertEqual(
            parse_multilabel_field("singkatan; akronim ; singkatan"),
            ["singkatan", "akronim"],
        )
        self.assertEqual(
            parse_multilabel_field("EMOTIF; Konatif"),
            ["emotif", "konatif"],
        )
        self.assertEqual(
            parse_multilabel_field(";;  ;"),
            [],
        )

    # -------------------------------------------------------------------------
    # 2. Template Generation Tests
    # -------------------------------------------------------------------------

    def test_generate_annotation_template_structure(self) -> None:
        """Generate annotation template containing exact required columns and default status 'belum'."""
        processed_path = self.test_dir / "comments_clean.csv"
        self._create_csv(
            processed_path,
            fieldnames=["comment_id", "media_id", "comment_text", "clean_text", "duplicate_status"],
            rows=[
                {
                    "comment_id": "c1",
                    "media_id": "m1",
                    "comment_text": "gws ya kak!",
                    "clean_text": "gws ya kak",
                    "duplicate_status": "unique",
                },
                {
                    "comment_id": "c2",
                    "media_id": "m1",
                    "comment_text": "keren bgt",
                    "clean_text": "keren bgt",
                    "duplicate_status": "unique",
                },
            ],
        )

        output_path = self.test_dir / "annotated" / "comments_labeled.csv"
        res_path = generate_annotation_template(processed_path, output_csv_path=output_path)
        self.assertEqual(res_path.resolve(), output_path.resolve())
        self.assertTrue(output_path.exists())

        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, ANNOTATED_FIELDNAMES)
            rows = list(reader)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["comment_id"], "c1")
        self.assertEqual(rows[0]["clean_text"], "gws ya kak")
        self.assertEqual(rows[0]["review_status"], "belum")
        self.assertEqual(rows[0]["slang_present"], "")
        self.assertEqual(rows[0]["slang_forms"], "")

    # -------------------------------------------------------------------------
    # 3. Non-Destructive Merge (Critical Requirement #3 and #9)
    # -------------------------------------------------------------------------

    def test_non_destructive_merge_preserves_human_annotations(self) -> None:
        """Re-generating template MUST NOT overwrite or erase existing human labels."""
        output_path = self.test_dir / "annotated" / "comments_labeled.csv"

        # Step A: Initial template generated
        batch1_path = self.test_dir / "processed_batch1.csv"
        self._create_csv(
            batch1_path,
            fieldnames=["comment_id", "clean_text"],
            rows=[
                {"comment_id": "101", "clean_text": "gws bro"},
                {"comment_id": "102", "clean_text": "keren bgt"},
            ],
        )
        generate_annotation_template(batch1_path, output_csv_path=output_path)

        # Step B: Human annotator fills in labels for comment '101'
        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Annotator marks 101 as completed
        rows[0]["slang_present"] = "ya"
        rows[0]["slang_forms"] = "singkatan"
        rows[0]["slang_spans"] = "gws"
        rows[0]["slang_meanings"] = "get well soon"
        rows[0]["language_functions"] = "emotif"
        rows[0]["annotator_id"] = "A1"
        rows[0]["review_status"] = "selesai"
        rows[0]["adjudication_note"] = "kesepakatan tim"

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=ANNOTATED_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)

        # Step C: Re-generate template with a new batch containing '101', '102', and new '103'
        batch2_path = self.test_dir / "processed_batch2.csv"
        self._create_csv(
            batch2_path,
            fieldnames=["comment_id", "clean_text"],
            rows=[
                {"comment_id": "101", "clean_text": "gws bro"},  # Already annotated!
                {"comment_id": "102", "clean_text": "keren bgt"},  # Previously pending
                {"comment_id": "103", "clean_text": "halo semuanya"},  # Brand new comment
            ],
        )

        generate_annotation_template(batch2_path, output_csv_path=output_path)

        # Step D: Verify that comment 101 still has all its exact annotations!
        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            updated_rows = {row["comment_id"]: row for row in reader}

        self.assertEqual(len(updated_rows), 3)

        # Comment 101: completely preserved
        c101 = updated_rows["101"]
        self.assertEqual(c101["slang_present"], "ya")
        self.assertEqual(c101["slang_forms"], "singkatan")
        self.assertEqual(c101["slang_spans"], "gws")
        self.assertEqual(c101["slang_meanings"], "get well soon")
        self.assertEqual(c101["language_functions"], "emotif")
        self.assertEqual(c101["annotator_id"], "A1")
        self.assertEqual(c101["review_status"], "selesai")
        self.assertEqual(c101["adjudication_note"], "kesepakatan tim")

        # Comment 102: still pending
        self.assertEqual(updated_rows["102"]["review_status"], "belum")

        # Comment 103: newly added with default 'belum'
        self.assertEqual(updated_rows["103"]["review_status"], "belum")
        self.assertEqual(updated_rows["103"]["slang_present"], "")

    def test_non_destructive_merge_preserves_unmatched_existing_comments(self) -> None:
        """Records in the annotated CSV that are not in the new batch are also preserved."""
        output_path = self.test_dir / "comments_labeled.csv"
        self._create_csv(
            output_path,
            fieldnames=ANNOTATED_FIELDNAMES,
            rows=[
                {
                    "comment_id": "old_01",
                    "clean_text": "komentar lama",
                    "slang_present": "tidak",
                    "slang_forms": "tidak_ada",
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "referensial",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                }
            ],
        )

        # New batch only has new_02
        new_batch = self.test_dir / "new_batch.csv"
        self._create_csv(
            new_batch,
            fieldnames=["comment_id", "clean_text"],
            rows=[{"comment_id": "new_02", "clean_text": "komentar baru"}],
        )

        generate_annotation_template(new_batch, output_csv_path=output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            ids = [r["comment_id"] for r in reader]

        self.assertIn("old_01", ids)
        self.assertIn("new_02", ids)

    # -------------------------------------------------------------------------
    # 4. Schema & Consistency Validation Tests
    # -------------------------------------------------------------------------

    def test_validate_valid_dataset(self) -> None:
        """Valid dataset with both completed and pending annotations passes validation."""
        csv_path = self.test_dir / "valid_labeled.csv"
        self._create_csv(
            csv_path,
            fieldnames=ANNOTATED_FIELDNAMES,
            rows=[
                {
                    "comment_id": "c1",
                    "clean_text": "gws ya kak",
                    "slang_present": "ya",
                    "slang_forms": "singkatan",
                    "slang_spans": "gws",
                    "slang_meanings": "get well soon",
                    "language_functions": "emotif;konatif",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
                {
                    "comment_id": "c2",
                    "clean_text": "ini adalah informasi resmi",
                    "slang_present": "tidak",
                    "slang_forms": "tidak_ada",
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "referensial",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
                {
                    "comment_id": "c3",
                    "clean_text": "masih menunggu",
                    "slang_present": "",
                    "slang_forms": "",
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "",
                    "annotator_id": "",
                    "review_status": "belum",
                    "adjudication_note": "",
                },
            ],
        )

        report = validate_annotated_dataset(csv_path)
        self.assertEqual(report.total_comments, 3)
        self.assertEqual(report.total_completed, 2)
        self.assertEqual(report.total_pending, 1)
        self.assertEqual(report.total_invalid, 0)
        self.assertEqual(len(report.errors), 0)
        self.assertTrue(report.is_valid_for_training)

    def test_validate_slang_present_tidak_requires_tidak_ada(self) -> None:
        """slang_present='tidak' must have slang_forms='tidak_ada'."""
        csv_path = self.test_dir / "invalid_tidak.csv"
        self._create_csv(
            csv_path,
            fieldnames=ANNOTATED_FIELDNAMES,
            rows=[
                {
                    "comment_id": "c1",
                    "clean_text": "halo semuanya",
                    "slang_present": "tidak",
                    "slang_forms": "singkatan",  # Inconsistent!
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "referensial",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                }
            ],
        )

        report = validate_annotated_dataset(csv_path)
        self.assertEqual(report.total_invalid, 1)
        self.assertEqual(report.total_completed, 0)
        self.assertFalse(report.is_valid_for_training)
        self.assertTrue(any("Harus 'tidak_ada'" in err for err in report.errors))

    def test_validate_slang_present_ya_cannot_be_tidak_ada(self) -> None:
        """slang_present='ya' cannot have slang_forms='tidak_ada' or empty."""
        csv_path = self.test_dir / "invalid_ya.csv"
        self._create_csv(
            csv_path,
            fieldnames=ANNOTATED_FIELDNAMES,
            rows=[
                {
                    "comment_id": "c1",
                    "clean_text": "gws ya",
                    "slang_present": "ya",
                    "slang_forms": "tidak_ada",  # Inconsistent!
                    "slang_spans": "gws",
                    "slang_meanings": "get well soon",
                    "language_functions": "emotif",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
                {
                    "comment_id": "c2",
                    "clean_text": "keren bgt",
                    "slang_present": "ya",
                    "slang_forms": "tidak_ada;singkatan",  # Contradictory mix!
                    "slang_spans": "bgt",
                    "slang_meanings": "banget",
                    "language_functions": "emotif",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
            ],
        )

        report = validate_annotated_dataset(csv_path)
        self.assertEqual(report.total_invalid, 2)
        self.assertEqual(report.total_completed, 0)
        self.assertFalse(report.is_valid_for_training)

    def test_validate_unknown_taxonomy_labels(self) -> None:
        """Slang forms and language functions outside official taxonomy are reported as errors."""
        csv_path = self.test_dir / "invalid_taxonomy.csv"
        self._create_csv(
            csv_path,
            fieldnames=ANNOTATED_FIELDNAMES,
            rows=[
                {
                    "comment_id": "c1",
                    "clean_text": "gws",
                    "slang_present": "ya",
                    "slang_forms": "slang_palsu;akronim",  # Unknown slang form
                    "slang_spans": "gws",
                    "slang_meanings": "get well soon",
                    "language_functions": "fungsi_salah",  # Unknown language function
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                }
            ],
        )

        report = validate_annotated_dataset(csv_path)
        self.assertEqual(report.total_invalid, 1)
        self.assertTrue(any("Bentuk slang 'slang_palsu' tidak dikenal" in err for err in report.errors))
        self.assertTrue(any("Fungsi bahasa 'fungsi_salah' tidak dikenal" in err for err in report.errors))

    def test_validate_completed_requires_language_functions(self) -> None:
        """Completed review requires language_functions to be filled."""
        csv_path = self.test_dir / "empty_func.csv"
        self._create_csv(
            csv_path,
            fieldnames=ANNOTATED_FIELDNAMES,
            rows=[
                {
                    "comment_id": "c1",
                    "clean_text": "gws",
                    "slang_present": "ya",
                    "slang_forms": "singkatan",
                    "slang_spans": "gws",
                    "slang_meanings": "get well soon",
                    "language_functions": "",  # Missing!
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                }
            ],
        )

        report = validate_annotated_dataset(csv_path)
        self.assertEqual(report.total_invalid, 1)
        self.assertTrue(any("language_functions belum diisi" in err for err in report.errors))

    def test_validate_empty_comment_and_duplicate_id(self) -> None:
        """Report empty clean_text, missing comment_id, and duplicate comment_ids."""
        csv_path = self.test_dir / "dups_and_empty.csv"
        self._create_csv(
            csv_path,
            fieldnames=ANNOTATED_FIELDNAMES,
            rows=[
                {
                    "comment_id": "dup_01",
                    "clean_text": "komentar satu",
                    "slang_present": "tidak",
                    "slang_forms": "tidak_ada",
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "referensial",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
                {
                    "comment_id": "dup_01",  # Duplicate ID
                    "clean_text": "komentar dua",
                    "slang_present": "tidak",
                    "slang_forms": "tidak_ada",
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "referensial",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
                {
                    "comment_id": "c3",
                    "clean_text": "",  # Empty comment
                    "slang_present": "tidak",
                    "slang_forms": "tidak_ada",
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "referensial",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
            ],
        )

        report = validate_annotated_dataset(csv_path)
        self.assertEqual(report.total_invalid, 2)  # dup_01 second time, and c3 empty
        self.assertTrue(any("Duplikasi comment_id 'dup_01'" in err for err in report.errors))
        self.assertTrue(any("clean_text kosong" in err for err in report.errors))

    def test_validate_missing_columns(self) -> None:
        """Validator reports missing mandatory columns immediately."""
        csv_path = self.test_dir / "corrupted_headers.csv"
        self._create_csv(
            csv_path,
            fieldnames=["comment_id", "clean_text"],  # Missing all label columns
            rows=[{"comment_id": "c1", "clean_text": "test"}],
        )

        report = validate_annotated_dataset(csv_path)
        self.assertFalse(report.is_valid_for_training)
        self.assertTrue(any("Kolom wajib tidak lengkap" in err for err in report.errors))

    def test_summary_text_formatting(self) -> None:
        """Validation report formats informative summary text with error counts."""
        report = AnnotationValidationReport(
            dataset_path=Path("dummy/path.csv"),
            total_comments=10,
            total_completed=6,
            total_pending=3,
            total_invalid=1,
            errors=["Baris 5: review_status 'rusak' tidak valid."],
            warnings=["Baris 2: Catatan adjudikasi kosong."],
        )
        summary = report.summary_text()
        self.assertIn("RINGKASAN VALIDASI DATASET ANOTASI", summary)
        self.assertIn("Total Komentar      : 10", summary)
        self.assertIn("Anotasi Selesai     : 6", summary)
        self.assertIn("Anotasi Belum Selesai: 3", summary)
        self.assertIn("Baris Bermasalah    : 1", summary)
        self.assertIn("review_status 'rusak' tidak valid", summary)

    def test_prepopulated_suggestions_from_processed_categories(self) -> None:
        """Verify linguistic categories from processed CSV are pre-populated as suggestions."""
        processed_path = self.test_dir / "comments_clean_cat.csv"
        self._create_csv(
            processed_path,
            fieldnames=[
                "comment_id", "clean_text", "bentuk_bahasa_gaul", "fungsi_bahasa", "kata_gaul"
            ],
            rows=[
                {
                    "comment_id": "c901",
                    "clean_text": "gws ya bro",
                    "bentuk_bahasa_gaul": "singkatan;bahasa_asing",
                    "fungsi_bahasa": "emotif",
                    "kata_gaul": "gws;bro",
                },
                {
                    "comment_id": "c902",
                    "clean_text": "Selamat pagi semuanya",
                    "bentuk_bahasa_gaul": "tidak_ada",
                    "fungsi_bahasa": "emotif",
                    "kata_gaul": "",
                },
            ],
        )

        output_path = self.test_dir / "annotated" / "comments_labeled_suggestions.csv"
        generate_annotation_template(processed_path, output_csv_path=output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

        self.assertEqual(len(rows), 2)
        # Row 1 has slang
        self.assertEqual(rows[0]["slang_present"], "ya")
        self.assertEqual(rows[0]["slang_forms"], "singkatan;bahasa_asing")
        self.assertEqual(rows[0]["language_functions"], "emotif")
        self.assertEqual(rows[0]["slang_spans"], "gws;bro")
        self.assertEqual(rows[0]["review_status"], "belum")

        # Row 2 has no slang
        self.assertEqual(rows[1]["slang_present"], "tidak")
        self.assertEqual(rows[1]["slang_forms"], "")
        self.assertEqual(rows[1]["review_status"], "belum")


if __name__ == "__main__":
    unittest.main()
