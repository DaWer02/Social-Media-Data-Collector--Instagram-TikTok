"""Unit tests for baseline model training, group splitting, and multi-label evaluation.

Note:
These unit tests utilize small synthetic fixtures to verify algorithmic correctness,
mathematical separation, absence of data leakage, and error handling.
Performance metrics on these small fixtures are NOT scientific claims of model quality.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from src.annotations import ANNOTATED_FIELDNAMES
from src.train import (
    AnnotationSchemaValidationError,
    InsufficientDataForSplitError,
    perform_group_split,
    predict_single_comment,
    train_baseline_models,
)


class TestBaselineTraining(unittest.TestCase):
    """Test suite for baseline model training pipeline and group splitting."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.models_dir = self.test_dir / "models"
        self.reports_dir = self.test_dir / "reports"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_annotated_csv(self, filepath: Path, rows: list[dict[str, str]]) -> Path:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            # We include media_id in the row dicts for explicit test fixtures
            fieldnames = ["media_id"] + ANNOTATED_FIELDNAMES
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return filepath

    # -------------------------------------------------------------------------
    # 1. Prerequisite & Validation Error Handling Tests
    # -------------------------------------------------------------------------

    def test_training_fails_if_no_completed_annotations(self) -> None:
        """Training aborts with clear error message if zero completed annotations exist."""
        annotated_path = self.test_dir / "pending_only.csv"
        self._create_annotated_csv(
            annotated_path,
            rows=[
                {
                    "comment_id": "c1",
                    "media_id": "m1",
                    "clean_text": "belum ada label",
                    "slang_present": "",
                    "slang_forms": "",
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "",
                    "annotator_id": "",
                    "review_status": "belum",
                    "adjudication_note": "",
                }
            ],
        )

        with self.assertRaises(AnnotationSchemaValidationError) as ctx:
            train_baseline_models(
                annotated_csv_path=annotated_path,
                output_models_dir=self.models_dir,
                output_reports_dir=self.reports_dir,
            )
        self.assertIn("Tidak ditemukan anotasi manusia yang berstatus 'selesai'", str(ctx.exception))

    def test_training_fails_on_schema_inconsistency(self) -> None:
        """Training aborts if dataset contains schema or consistency errors."""
        annotated_path = self.test_dir / "invalid_schema.csv"
        self._create_annotated_csv(
            annotated_path,
            rows=[
                {
                    "comment_id": "c1",
                    "media_id": "m1",
                    "clean_text": "halo",
                    "slang_present": "tidak",
                    "slang_forms": "singkatan",  # Inconsistency: tidak but singkatan!
                    "slang_spans": "",
                    "slang_meanings": "",
                    "language_functions": "referensial",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "",
                }
            ],
        )

        with self.assertRaises(AnnotationSchemaValidationError) as ctx:
            train_baseline_models(
                annotated_csv_path=annotated_path,
                output_models_dir=self.models_dir,
                output_reports_dir=self.reports_dir,
            )
        self.assertIn("kesalahan validasi", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 2. Group Split Integrity & Leakage Prevention Tests
    # -------------------------------------------------------------------------

    def test_training_fails_if_only_one_media_group(self) -> None:
        """Group split stops if all comments come from only 1 media post (leakage risk)."""
        annotated_path = self.test_dir / "single_group.csv"
        rows = [
            {
                "comment_id": f"c_{i}",
                "media_id": "single_post_123",  # All 8 comments from same post
                "clean_text": f"komentar nomor {i}",
                "slang_present": "tidak",
                "slang_forms": "tidak_ada",
                "slang_spans": "",
                "slang_meanings": "",
                "language_functions": "referensial",
                "annotator_id": "A1",
                "review_status": "selesai",
                "adjudication_note": "",
            }
            for i in range(8)
        ]
        self._create_annotated_csv(annotated_path, rows)

        with self.assertRaises(InsufficientDataForSplitError) as ctx:
            train_baseline_models(
                annotated_csv_path=annotated_path,
                output_models_dir=self.models_dir,
                output_reports_dir=self.reports_dir,
            )
        self.assertIn("hanya memuat 1 media_id", str(ctx.exception).lower())
        self.assertIn("mencegah kebocoran komentar", str(ctx.exception))

    def test_training_fails_if_too_few_samples(self) -> None:
        """Training aborts if total completed comments is smaller than minimum threshold (6)."""
        annotated_path = self.test_dir / "too_few.csv"
        rows = [
            {
                "comment_id": "c1",
                "media_id": "post_A",
                "clean_text": "gws",
                "slang_present": "ya",
                "slang_forms": "singkatan",
                "slang_spans": "gws",
                "slang_meanings": "get well soon",
                "language_functions": "emotif",
                "annotator_id": "A1",
                "review_status": "selesai",
                "adjudication_note": "",
            },
            {
                "comment_id": "c2",
                "media_id": "post_B",
                "clean_text": "halo",
                "slang_present": "tidak",
                "slang_forms": "tidak_ada",
                "slang_spans": "",
                "slang_meanings": "",
                "language_functions": "referensial",
                "annotator_id": "A1",
                "review_status": "selesai",
                "adjudication_note": "",
            },
        ]
        self._create_annotated_csv(annotated_path, rows)

        with self.assertRaises(InsufficientDataForSplitError) as ctx:
            train_baseline_models(
                annotated_csv_path=annotated_path,
                output_models_dir=self.models_dir,
                output_reports_dir=self.reports_dir,
            )
        self.assertIn("terlalu sedikit untuk evaluasi split grup", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. End-to-End Pipeline & TF-IDF Fitting Verification
    # -------------------------------------------------------------------------

    def test_baseline_training_pipeline_success(self) -> None:
        """Full pipeline executes on synthetic fixture, fitting vectorizer only on train."""
        annotated_path = self.test_dir / "comments_fixture.csv"

        # Synthetic fixture: 12 comments across 3 media IDs with diverse slang forms & language functions
        fixture_rows = [
            # Group post_A (4 comments)
            {"comment_id": "1", "media_id": "post_A", "clean_text": "gws ya bro", "slang_present": "ya", "slang_forms": "singkatan", "slang_spans": "gws", "slang_meanings": "get well soon", "language_functions": "emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "2", "media_id": "post_A", "clean_text": "mager banget hari ini", "slang_present": "ya", "slang_forms": "akronim;pemendekan", "slang_spans": "mager;bgt", "slang_meanings": "malas gerak;banget", "language_functions": "emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "3", "media_id": "post_A", "clean_text": "pansos terus kerjaannya", "slang_present": "ya", "slang_forms": "akronim", "slang_spans": "pansos", "slang_meanings": "panjat sosial", "language_functions": "emotif;referensial", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "4", "media_id": "post_A", "clean_text": "informasi resmi dari panitia", "slang_present": "tidak", "slang_forms": "tidak_ada", "slang_spans": "", "slang_meanings": "", "language_functions": "referensial", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},

            # Group post_B (4 comments)
            {"comment_id": "5", "media_id": "post_B", "clean_text": "kuy berangkat sekarang", "slang_present": "ya", "slang_forms": "plesetan", "slang_spans": "kuy", "slang_meanings": "yuk", "language_functions": "konatif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "6", "media_id": "post_B", "clean_text": "santuy aja kawan", "slang_present": "ya", "slang_forms": "plesetan", "slang_spans": "santuy", "slang_meanings": "santai", "language_functions": "konatif;emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "7", "media_id": "post_B", "clean_text": "harga tiket lima puluh ribu", "slang_present": "tidak", "slang_forms": "tidak_ada", "slang_spans": "", "slang_meanings": "", "language_functions": "referensial", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "8", "media_id": "post_B", "clean_text": "bestie spill dong lokasinya", "slang_present": "ya", "slang_forms": "bahasa_asing", "slang_spans": "bestie;spill", "slang_meanings": "sahabat;bocorkan", "language_functions": "konatif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},

            # Group post_C (4 comments) - will be isolated by group split
            {"comment_id": "9", "media_id": "post_C", "clean_text": "keren bgt kak unik_kata_khusus_test", "slang_present": "ya", "slang_forms": "pemendekan", "slang_spans": "bgt", "slang_meanings": "banget", "language_functions": "emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "10", "media_id": "post_C", "clean_text": "jangan lupa follow ya gaes", "slang_present": "ya", "slang_forms": "bahasa_asing", "slang_spans": "gaes", "slang_meanings": "guys", "language_functions": "konatif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "11", "media_id": "post_C", "clean_text": "lokasi di jalan sudirman nomor 10", "slang_present": "tidak", "slang_forms": "tidak_ada", "slang_spans": "", "slang_meanings": "", "language_functions": "referensial", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
            {"comment_id": "12", "media_id": "post_C", "clean_text": "gws semoga lekas sembuh", "slang_present": "ya", "slang_forms": "singkatan", "slang_spans": "gws", "slang_meanings": "get well soon", "language_functions": "emotif", "annotator_id": "A1", "review_status": "selesai", "adjudication_note": ""},
        ]
        self._create_annotated_csv(annotated_path, fixture_rows)

        report = train_baseline_models(
            annotated_csv_path=annotated_path,
            output_models_dir=self.models_dir,
            output_reports_dir=self.reports_dir,
            random_seed=42,
            test_size=0.33,
        )

        # 1. Assert groups are completely separated (no leakage)
        train_groups = set(report.train_groups)
        test_groups = set(report.test_groups)
        self.assertTrue(train_groups.isdisjoint(test_groups))
        self.assertGreaterEqual(len(train_groups), 1)
        self.assertGreaterEqual(len(test_groups), 1)

        # 2. Assert all required models and reports exist
        for m_name in ["vectorizer", "slang_classifier", "lang_classifier", "slang_mlb", "lang_mlb", "metadata"]:
            self.assertIn(m_name, report.saved_model_paths)
            self.assertTrue(Path(report.saved_model_paths[m_name]).exists())

        self.assertTrue(Path(report.report_json_path).exists())
        self.assertTrue(Path(report.report_md_path).exists())

        # 3. Assert disclaimer is included
        self.assertIn("HASIL INI ADALAH BASELINE EKSPERIMEN AWAL", report.disclaimer)
        self.assertIn("HASIL INI ADALAH BASELINE EKSPERIMEN AWAL", report.summary_text())

        # 4. Check metadata JSON contents
        with open(report.saved_model_paths["metadata"], "r", encoding="utf-8") as f:
            metadata = json.load(f)
        self.assertEqual(metadata["random_seed"], 42)
        self.assertIn("slang_forms", metadata["taxonomy"])
        self.assertIn("language_functions", metadata["taxonomy"])

        # 5. Check vectorizer fitting: words that only existed in post_C (test) must NOT be in vocab if post_C was test!
        import joblib
        saved_vectorizer = joblib.load(report.saved_model_paths["vectorizer"])
        if "post_C" in test_groups:
            self.assertNotIn("unik_kata_khusus_test", saved_vectorizer.vocabulary_)

        # 6. Test single comment prediction (multi-label)
        saved_slang_clf = joblib.load(report.saved_model_paths["slang_classifier"])
        saved_lang_clf = joblib.load(report.saved_model_paths["lang_classifier"])
        saved_slang_mlb = joblib.load(report.saved_model_paths["slang_mlb"])
        saved_lang_mlb = joblib.load(report.saved_model_paths["lang_mlb"])

        prediction = predict_single_comment(
            clean_text="gws ya kawan",
            vectorizer=saved_vectorizer,
            slang_clf=saved_slang_clf,
            lang_clf=saved_lang_clf,
            slang_mlb=saved_slang_mlb,
            lang_mlb=saved_lang_mlb,
        )
        self.assertIn("slang_forms", prediction)
        self.assertIn("language_functions", prediction)
        self.assertIsInstance(prediction["slang_forms"], list)
        self.assertIsInstance(prediction["language_functions"], list)


if __name__ == "__main__":
    unittest.main()
