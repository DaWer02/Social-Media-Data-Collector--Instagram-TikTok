"""Unit tests for dataset analysis, multi-label frequency calculation, and report exports."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.analysis import (
    compute_multilabel_distribution,
    run_comprehensive_analysis,
    sanitize_comment_text,
)
from src.annotations import ANNOTATED_FIELDNAMES
from src.config import LANGUAGE_FUNCTIONS, SLANG_FORMS


class TestAnalysis(unittest.TestCase):
    """Test suite for statistical dataset analysis and multi-label distinction."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.raw_dir = self.test_dir / "raw"
        self.proc_dir = self.test_dir / "processed"
        self.annotated_dir = self.test_dir / "annotated"
        self.pred_dir = self.test_dir / "predictions"
        self.reports_dir = self.test_dir / "reports"

        for d in [self.raw_dir, self.proc_dir, self.annotated_dir, self.pred_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)

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
    # 1. Multi-Label Mathematical Distinction Tests (Critical Requirement)
    # -------------------------------------------------------------------------

    def test_compute_multilabel_distribution_never_mixes_metrics(self) -> None:
        """Verify distinct calculation of document frequency vs label occurrence count."""
        # 2 comments with multi-labels:
        # Comment 1: singkatan, akronim
        # Comment 2: singkatan, plesetan
        labels_sample = [
            ["singkatan", "akronim"],
            ["singkatan", "plesetan"],
        ]
        total_comments = 2

        categories = ["akronim", "singkatan", "plesetan", "bahasa_asing"]
        dist = compute_multilabel_distribution(labels_sample, categories, total_comments)
        dist_map = {row["kategori"]: row for row in dist}

        # singkatan:
        # - present in 2 out of 2 comments -> unique comment count = 2 (100.0%)
        # - appeared 2 times out of 4 total label occurrences -> 50.0%
        singkatan = dist_map["singkatan"]
        self.assertEqual(singkatan["komentar_unik_count"], 2)
        self.assertEqual(singkatan["komentar_persentase"], 100.0)
        self.assertEqual(singkatan["total_kemunculan_label"], 2)
        self.assertEqual(singkatan["proporsi_dari_seluruh_label"], 50.0)

        # akronim:
        # - present in 1 out of 2 comments -> unique comment count = 1 (50.0%)
        # - appeared 1 time out of 4 total label occurrences -> 25.0%
        akronim = dist_map["akronim"]
        self.assertEqual(akronim["komentar_unik_count"], 1)
        self.assertEqual(akronim["komentar_persentase"], 50.0)
        self.assertEqual(akronim["total_kemunculan_label"], 1)
        self.assertEqual(akronim["proporsi_dari_seluruh_label"], 25.0)

        # bahasa_asing (unseen):
        # - 0 comments, 0 occurrences
        bahasa_asing = dist_map["bahasa_asing"]
        self.assertEqual(bahasa_asing["komentar_unik_count"], 0)
        self.assertEqual(bahasa_asing["komentar_persentase"], 0.0)
        self.assertEqual(bahasa_asing["total_kemunculan_label"], 0)
        self.assertEqual(bahasa_asing["proporsi_dari_seluruh_label"], 0.0)

    def test_compute_multilabel_distribution_empty_input(self) -> None:
        """Empty input list with 0 comments handles gracefully without ZeroDivisionError."""
        dist = compute_multilabel_distribution([], SLANG_FORMS, total_comments=0)
        for row in dist:
            self.assertEqual(row["komentar_unik_count"], 0)
            self.assertEqual(row["komentar_persentase"], 0.0)
            self.assertEqual(row["total_kemunculan_label"], 0)
            self.assertEqual(row["proporsi_dari_seluruh_label"], 0.0)

    # -------------------------------------------------------------------------
    # 2. PII Sanitization Tests
    # -------------------------------------------------------------------------

    def test_sanitize_comment_text(self) -> None:
        """Sanitize @mentions, emails, and phone numbers from raw text."""
        raw_text = "Halo @andi_123 hubungi aku di user.test@gmail.com atau wa 081234567890 ya!"
        cleaned = sanitize_comment_text(raw_text)
        self.assertNotIn("@andi_123", cleaned)
        self.assertNotIn("user.test@gmail.com", cleaned)
        self.assertNotIn("081234567890", cleaned)
        self.assertIn("[@USER]", cleaned)
        self.assertIn("[EMAIL]", cleaned)
        self.assertIn("[PHONE]", cleaned)

    # -------------------------------------------------------------------------
    # 3. Comprehensive Analysis Execution Tests
    # -------------------------------------------------------------------------

    def test_run_analysis_empty_environment(self) -> None:
        """Analysis runs without error in an empty workspace with no comments."""
        empty_annotated = self.annotated_dir / "comments_labeled.csv"
        self._create_csv(empty_annotated, ANNOTATED_FIELDNAMES, [])

        report = run_comprehensive_analysis(
            annotated_csv_path=empty_annotated,
            output_reports_dir=self.reports_dir,
            raw_dir=self.raw_dir,
            processed_dir=self.proc_dir,
            predictions_dir=self.pred_dir,
        )

        self.assertEqual(report.total_raw_comments, 0)
        self.assertEqual(report.total_processed_comments, 0)
        self.assertEqual(report.human_completed_count, 0)
        self.assertTrue(Path(report.report_md_path).exists())
        self.assertIn("RINGKASAN ANALISIS DATASET", report.summary_text())

    def test_run_analysis_with_populated_pipeline(self) -> None:
        """Analysis aggregates data across RAW, processed, annotated, and predictions."""
        # 1. RAW dataset
        self._create_csv(
            self.raw_dir / "comments_raw1.csv",
            ["comment_id", "media_id", "comment_text", "collected_at", "source_type"],
            [
                {"comment_id": "r1", "media_id": "m1", "comment_text": "halo bro", "collected_at": "now", "source_type": "api"},
                {"comment_id": "r2", "media_id": "m1", "comment_text": "gws kak", "collected_at": "now", "source_type": "api"},
            ],
        )

        # 2. Processed dataset
        self._create_csv(
            self.proc_dir / "comments_clean_1.csv",
            ["comment_id", "media_id", "comment_text", "clean_text", "duplicate_status"],
            [
                {"comment_id": "r1", "media_id": "m1", "comment_text": "halo bro", "clean_text": "halo bro", "duplicate_status": "unique"},
                {"comment_id": "r2", "media_id": "m1", "comment_text": "gws kak", "clean_text": "gws kak", "duplicate_status": "unique"},
            ],
        )

        # 3. Annotated dataset (1 completed, 1 pending)
        annotated_csv = self.annotated_dir / "comments_labeled.csv"
        self._create_csv(
            annotated_csv,
            ANNOTATED_FIELDNAMES,
            [
                {
                    "comment_id": "r1",
                    "clean_text": "halo bro @andi",
                    "slang_present": "ya",
                    "slang_forms": "bahasa_asing",
                    "slang_spans": "bro",
                    "slang_meanings": "saudara",
                    "language_functions": "konatif",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                },
                {
                    "comment_id": "r2",
                    "clean_text": "gws kak",
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

        # 4. Predictions dataset
        self._create_csv(
            self.pred_dir / "comments_predictions_test.csv",
            [
                "comment_id",
                "media_id",
                "comment_text",
                "clean_text",
                "predicted_slang_forms",
                "predicted_language_functions",
                "slang_forms_confidence",
                "language_functions_confidence",
                "needs_review",
                "model_version",
            ],
            [
                {
                    "comment_id": "r1",
                    "media_id": "m1",
                    "comment_text": "halo bro",
                    "clean_text": "halo bro @andi",
                    "predicted_slang_forms": "singkatan",  # Intentionally mismatched for error analysis
                    "predicted_language_functions": "emotif",
                    "slang_forms_confidence": "0.75",
                    "language_functions_confidence": "0.80",
                    "needs_review": "False",
                    "model_version": "v1_test",
                }
            ],
        )

        report = run_comprehensive_analysis(
            annotated_csv_path=annotated_csv,
            output_reports_dir=self.reports_dir,
            raw_dir=self.raw_dir,
            processed_dir=self.proc_dir,
            predictions_dir=self.pred_dir,
        )

        # Check volume counts
        self.assertEqual(report.total_raw_comments, 2)
        self.assertEqual(report.total_processed_comments, 2)
        self.assertEqual(report.total_annotated_comments, 2)
        self.assertEqual(report.human_completed_count, 1)
        self.assertEqual(report.human_pending_count, 1)

        # Check slang presence
        self.assertEqual(report.human_slang_present_count, 1)
        self.assertEqual(report.human_slang_present_pct, 100.0)

        # Check qualitative error analysis with sanitized text
        self.assertTrue(report.has_model_predictions)
        self.assertEqual(len(report.qualitative_error_samples), 1)
        err_sample = report.qualitative_error_samples[0]
        self.assertEqual(err_sample["comment_id"], "r1")
        self.assertNotIn("@andi", err_sample["clean_text"])
        self.assertIn("[@USER]", err_sample["clean_text"])

        # Check created CSV files in reports/
        for key in ["pipeline_overview", "human_slang_forms", "human_language_functions", "media_distribution"]:
            self.assertIn(key, report.saved_csv_paths)
            self.assertTrue(Path(report.saved_csv_paths[key]).exists())

        # Check created plots (PNG)
        self.assertIn("slang_forms", report.saved_plot_paths)
        self.assertTrue(Path(report.saved_plot_paths["slang_forms"]).exists())


if __name__ == "__main__":
    unittest.main()
