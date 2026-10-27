"""Unit tests for dataset prediction, inference artifact loading, and review flagging.

Note:
These tests use synthetic fixture datasets and small mock models to verify
inference mechanics, column preservation, multi-label decoding, and error handling.
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from src.annotations import ANNOTATED_FIELDNAMES
from src.predict import (
    PREDICTIONS_FIELDNAMES,
    EmptyInputDatasetError,
    ModelCompatibilityError,
    ModelNotFoundError,
    load_inference_artifacts,
    predict_processed_dataset,
)
from src.train import train_baseline_models


class TestPrediction(unittest.TestCase):
    """Test suite for batch prediction on processed comments."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.models_dir = self.test_dir / "models"
        self.reports_dir = self.test_dir / "reports"
        self.predictions_dir = self.test_dir / "predictions"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.predictions_dir.mkdir(parents=True, exist_ok=True)

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
    # 1. Error Handling Tests (Missing Models, Empty Input, Invalid Input)
    # -------------------------------------------------------------------------

    def test_predict_fails_when_models_missing(self) -> None:
        """Prediction aborts cleanly without generating output if model files are missing."""
        proc_csv = self.test_dir / "proc.csv"
        self._create_csv(
            proc_csv,
            fieldnames=["comment_id", "media_id", "comment_text", "clean_text"],
            rows=[{"comment_id": "c1", "media_id": "m1", "comment_text": "halo", "clean_text": "halo"}],
        )

        empty_models_dir = self.test_dir / "empty_models"
        empty_models_dir.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(ModelNotFoundError) as ctx:
            predict_processed_dataset(
                processed_csv_path=proc_csv,
                models_dir=empty_models_dir,
            )
        self.assertIn("Artefak model baseline tidak lengkap", str(ctx.exception))
        # Ensure no fake output was generated
        self.assertEqual(len(list(self.predictions_dir.glob("*.csv"))), 0)

    def test_predict_fails_when_input_csv_empty(self) -> None:
        """Prediction aborts if input processed CSV has zero rows."""
        # Train valid models first so models exist
        self._train_sample_models()

        empty_csv = self.test_dir / "empty_processed.csv"
        self._create_csv(
            empty_csv,
            fieldnames=["comment_id", "media_id", "comment_text", "clean_text"],
            rows=[],  # Zero rows
        )

        with self.assertRaises(EmptyInputDatasetError) as ctx:
            predict_processed_dataset(
                processed_csv_path=empty_csv,
                models_dir=self.models_dir,
            )
        self.assertIn("kosong atau tidak memiliki baris", str(ctx.exception))

    def test_predict_fails_when_input_file_not_found(self) -> None:
        """Prediction raises FileNotFoundError if input path does not exist."""
        with self.assertRaises(FileNotFoundError):
            predict_processed_dataset(
                processed_csv_path=Path("non_existent_path.csv"),
                models_dir=self.models_dir,
            )

    # -------------------------------------------------------------------------
    # 2. Normal Prediction Flow & Multi-Label Verification
    # -------------------------------------------------------------------------

    def _train_sample_models(self) -> None:
        """Helper to train models on a small fixture dataset."""
        annotated_path = self.test_dir / "annotated.csv"
        fixture_rows = [
            {"comment_id": "1", "media_id": "post_A", "clean_text": "gws bro", "slang_present": "ya", "slang_forms": "singkatan", "slang_spans": "gws", "slang_meanings": "get well soon", "language_functions": "emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "2", "media_id": "post_A", "clean_text": "mager parah", "slang_present": "ya", "slang_forms": "akronim", "slang_spans": "mager", "slang_meanings": "malas gerak", "language_functions": "emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "3", "media_id": "post_A", "clean_text": "info resmi acara", "slang_present": "tidak", "slang_forms": "tidak_ada", "slang_spans": "", "slang_meanings": "", "language_functions": "referensial", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "4", "media_id": "post_B", "clean_text": "kuy gaskeun", "slang_present": "ya", "slang_forms": "plesetan", "slang_spans": "kuy", "slang_meanings": "yuk", "language_functions": "konatif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "5", "media_id": "post_B", "clean_text": "santuy banget", "slang_present": "ya", "slang_forms": "plesetan;pemendekan", "slang_spans": "santuy;bgt", "slang_meanings": "santai;banget", "language_functions": "konatif;emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "6", "media_id": "post_B", "clean_text": "jadwal buka jam sembilan", "slang_present": "tidak", "slang_forms": "tidak_ada", "slang_spans": "", "slang_meanings": "", "language_functions": "referensial", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
        ]
        self._create_csv(annotated_path, ["media_id"] + ANNOTATED_FIELDNAMES, fixture_rows)
        train_baseline_models(
            annotated_csv_path=annotated_path,
            output_models_dir=self.models_dir,
            output_reports_dir=self.reports_dir,
            random_seed=42,
        )

    def test_predict_normal_flow_multi_label_and_confidence(self) -> None:
        """Verify normal inference produces multi-label predictions, confidence scores, and review flags."""
        self._train_sample_models()

        proc_csv = self.test_dir / "comments_clean_batch.csv"
        self._create_csv(
            proc_csv,
            fieldnames=["comment_id", "media_id", "comment_text", "clean_text", "duplicate_status"],
            rows=[
                {
                    "comment_id": "p101",
                    "media_id": "media_post_999",
                    "comment_text": "GWS ya kak!",
                    "clean_text": "gws ya kak",
                    "duplicate_status": "unique",
                },
                {
                    "comment_id": "p102",
                    "media_id": "media_post_999",
                    "comment_text": "Info lengkap jadwal...",
                    "clean_text": "info lengkap jadwal",
                    "duplicate_status": "unique",
                },
                {
                    "comment_id": "p103",
                    "media_id": "media_post_888",
                    "comment_text": "Kuy buruan beli",
                    "clean_text": "kuy buruan beli",
                    "duplicate_status": "unique",
                },
            ],
        )

        out_path = self.predictions_dir / "test_predictions.csv"
        result = predict_processed_dataset(
            processed_csv_path=proc_csv,
            output_predictions_path=out_path,
            models_dir=self.models_dir,
            review_threshold=0.60,
        )

        self.assertEqual(result.total_predicted, 3)
        self.assertTrue(out_path.exists())

        # Read output and check schema
        with open(out_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            self.assertEqual(reader.fieldnames, PREDICTIONS_FIELDNAMES)
            rows = list(reader)

        self.assertEqual(len(rows), 3)

        # 1. Preserved source fields
        self.assertEqual(rows[0]["comment_id"], "p101")
        self.assertEqual(rows[0]["media_id"], "media_post_999")
        self.assertEqual(rows[0]["comment_text"], "GWS ya kak!")
        self.assertEqual(rows[0]["clean_text"], "gws ya kak")

        # 2. Predicted multi-labels
        self.assertIn("predicted_slang_forms", rows[0])
        self.assertIn("predicted_language_functions", rows[0])

        # 3. Confidence scores
        slang_conf = float(rows[0]["slang_forms_confidence"])
        lang_conf = float(rows[0]["language_functions_confidence"])
        self.assertGreaterEqual(slang_conf, 0.0)
        self.assertLessEqual(slang_conf, 1.0)
        self.assertGreaterEqual(lang_conf, 0.0)
        self.assertLessEqual(lang_conf, 1.0)

        # 4. Needs review is a boolean representation
        self.assertIn(rows[0]["needs_review"], {"True", "False"})

        # 5. Model version is recorded
        self.assertTrue(len(rows[0]["model_version"]) > 0)

        # 6. Verify NO span extraction column is fabricated (Requirement 12)
        self.assertNotIn("slang_spans", reader.fieldnames)
        self.assertNotIn("predicted_spans", reader.fieldnames)

    def test_needs_review_threshold_behavior(self) -> None:
        """Setting review_threshold to high value (0.99) flags ambiguous/low confidence rows."""
        self._train_sample_models()

        proc_csv = self.test_dir / "proc_threshold.csv"
        self._create_csv(
            proc_csv,
            fieldnames=["comment_id", "media_id", "comment_text", "clean_text"],
            rows=[{"comment_id": "c1", "media_id": "m1", "comment_text": "kata langka aneh", "clean_text": "kata langka aneh"}],
        )

        out_path = self.predictions_dir / "threshold_test.csv"
        result = predict_processed_dataset(
            processed_csv_path=proc_csv,
            output_predictions_path=out_path,
            models_dir=self.models_dir,
            review_threshold=0.99,  # Very strict threshold
        )

        self.assertEqual(result.total_predicted, 1)
        self.assertEqual(result.total_needs_review, 1)

        summary = result.summary_text()
        self.assertIn("RINGKASAN PREDIKSI DATASET KOMENTAR", summary)
        self.assertIn("DOKUMENTASI CONFIDENCE SCORE", summary)
        self.assertIn("Perlu Review Manusia  : 1 komentar (100.0%)", summary)


if __name__ == "__main__":
    unittest.main()
