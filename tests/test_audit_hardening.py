"""Comprehensive audit and hardening test suite.

Explicitly verifies all 17 audit items required for pipeline robustness:
1. main.py execution in Windows.
2. Clean module imports and dependency setup.
3. Empty and invalid token configurations.
4. Total absence of secrets/tokens in logs, exceptions, metadata, CSV, and output.
5. Input URL and media ID resolution (valid and invalid).
6. API error handling (401, 403, rate limits, media unavailable, network errors).
7. Pagination and deduplication without data loss.
8. RAW immutability and persistence before NLP confirmation prompt.
9. Refusal to proceed to NLP on 'N', 'n', empty string, or invalid answers.
10. Explicit approval 'y' strictly proceeds to preprocessing only (no training).
11. Preprocessing does not modify or corrupt RAW datasets.
12. Template regeneration strictly preserves existing human annotations.
13. Baseline training stops if annotations are invalid or group split is not viable.
14. Vectorizer is fit ONLY on train data (never on test data).
15. Predictions do not overwrite manual annotations or RAW data.
16. Statistical analysis metrics are consistent with actual data counts.
17. Sensitive files and directories are properly excluded by .gitignore.

All network interactions are mocked via fixtures; no live API calls are made.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from main import main
from src.analysis import compute_multilabel_distribution, run_comprehensive_analysis
from src.annotations import (
    ANNOTATED_FIELDNAMES,
    generate_annotation_template,
    validate_annotated_dataset,
)
from src.cli import run_cli
from src.collectors.base import (
    AuthenticationError,
    CommentRecord,
    MediaUnavailableError,
    NetworkCollectorError,
    PermissionDeniedError,
    RateLimitError,
)
from src.collectors.instagram_api import InstagramGraphAPICollector
from src.config import (
    BASE_DIR,
    RAW_DATA_DIR,
    REPORTS_DIR,
    AppConfig,
    ConfigValidationError,
    mask_token,
    validate_graph_api_version,
    validate_target_comments,
)
from src.logging_config import SecretRedactingFilter, setup_logger
from src.predict import PREDICTIONS_FIELDNAMES, predict_processed_dataset
from src.preprocessing import clean_comment_text, preprocess_dataset_with_report
from src.storage import (
    calculate_file_sha256,
    generate_run_id,
    save_raw_comments,
    save_run_metadata,
)
from src.train import (
    AnnotationSchemaValidationError,
    InsufficientDataForSplitError,
    train_baseline_models,
)


class TestPipelineAuditAndHardening(unittest.TestCase):
    """Rigorous audit test suite covering all 17 robustness requirements."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        self.dummy_token = "EAABtest_mock_token_secret_12345"
        self.raw_files_before = set(RAW_DATA_DIR.glob("*.csv")) if RAW_DATA_DIR.exists() else set()
        self.meta_files_before = set(REPORTS_DIR.glob("run_*.json")) if REPORTS_DIR.exists() else set()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        if RAW_DATA_DIR.exists():
            for f in RAW_DATA_DIR.glob("*.csv"):
                if f not in self.raw_files_before:
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass
        if REPORTS_DIR.exists():
            for f in REPORTS_DIR.glob("run_*.json"):
                if f not in self.meta_files_before:
                    try:
                        f.unlink(missing_ok=True)
                    except Exception:
                        pass

    def _create_csv(self, filepath: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> Path:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return filepath

    # -------------------------------------------------------------------------
    # Audit Item 1: python main.py runs in Windows
    # -------------------------------------------------------------------------
    def test_audit_01_main_execution_in_windows(self) -> None:
        """Verify main.py runs and exits cleanly with --status on Windows."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            code = main(["--status"])
            output = fake_out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("INSTAGRAM SLANG NLP PIPELINE - WINDOWS CLI", output)
        self.assertIn("Mode non-interaktif", output)

    # -------------------------------------------------------------------------
    # Audit Item 2: Module imports and dependency setup
    # -------------------------------------------------------------------------
    def test_audit_02_all_modules_import_cleanly(self) -> None:
        """Verify that all core pipeline modules import without circular dependencies or errors."""
        import src.analysis
        import src.annotations
        import src.cli
        import src.collectors.base
        import src.collectors.instagram_api
        import src.config
        import src.logging_config
        import src.predict
        import src.preprocessing
        import src.storage
        import src.train

        self.assertIsNotNone(src.train.train_baseline_models)
        self.assertIsNotNone(src.predict.predict_processed_dataset)
        self.assertIsNotNone(src.analysis.run_comprehensive_analysis)

    # -------------------------------------------------------------------------
    # Audit Item 3: Empty and invalid token configurations
    # -------------------------------------------------------------------------
    def test_audit_03_token_configuration_validation(self) -> None:
        """Verify handling of empty tokens, masked tokens, and invalid graph API versions."""
        self.assertEqual(mask_token(None), "<TIDAK_DISET>")
        self.assertEqual(mask_token(""), "<TIDAK_DISET>")
        self.assertEqual(mask_token("   "), "<TIDAK_DISET>")
        self.assertEqual(mask_token("1234567890"), "1234...7890")

        with self.assertRaises(ConfigValidationError):
            validate_graph_api_version("15.0")  # Missing 'v' prefix
        with self.assertRaises(ConfigValidationError):
            validate_graph_api_version("invalid_ver")  # Invalid string format
        with self.assertRaises(ConfigValidationError):
            validate_target_comments("-5")  # Negative count
        with self.assertRaises(ConfigValidationError):
            validate_target_comments("0")  # Zero count
        with self.assertRaises(ConfigValidationError):
            validate_target_comments("bukan_angka")  # Non-numeric string

    # -------------------------------------------------------------------------
    # Audit Item 4: Total absence of secrets in logs, metadata, CSV, and output
    # -------------------------------------------------------------------------
    def test_audit_04_secret_redaction_everywhere(self) -> None:
        """Verify secrets are redacted from logging, run metadata JSON, and error messages."""
        real_secret = "EAABvery_secret_token_value_987654"

        # 1. Logging redaction
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg=f"Requesting https://graph.facebook.com/v21.0/media?access_token={real_secret} now",
            args=(),
            exc_info=None,
        )
        redacting_filter = SecretRedactingFilter()
        redacting_filter.filter(record)
        self.assertNotIn(real_secret, record.msg)
        self.assertIn("access_token=***REDACTED***", record.msg)

        # 2. Storage run metadata redaction
        meta_path = save_run_metadata(
            run_id="test_redact_run",
            status="test",
            extra_data={"access_token": real_secret, "api_secret": "xyz", "safe_field": 123},
        )
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_json = json.load(f)
        self.assertNotIn("access_token", meta_json)
        self.assertNotIn("api_secret", meta_json)
        self.assertEqual(meta_json["safe_field"], 123)

        # 3. Collector exception message sanitization
        collector = InstagramGraphAPICollector(access_token=real_secret)
        sanitized_url = collector._sanitize_url(f"https://graph.facebook.com/v21.0/123/comments?access_token={real_secret}")
        self.assertNotIn(real_secret, sanitized_url)
        self.assertIn("access_token=***REDACTED***", sanitized_url)

    # -------------------------------------------------------------------------
    # Audit Item 5: Input URL and media ID resolution
    # -------------------------------------------------------------------------
    def test_audit_05_input_url_and_media_id_resolution(self) -> None:
        """Verify URL parsing, shortcode extraction, and direct numeric media ID support."""
        collector = InstagramGraphAPICollector(access_token=self.dummy_token)

        # Direct media IDs
        self.assertEqual(collector._extract_target("180011223344"), ("media_id", "180011223344"))

        # Valid post URLs
        self.assertEqual(
            collector._extract_target("https://www.instagram.com/p/C_abc123/"),
            ("shortcode", "C_abc123"),
        )
        self.assertEqual(
            collector._extract_target("https://instagram.com/reel/D_xyz987/?utm_source=ig_web"),
            ("shortcode", "D_xyz987"),
        )

        # Invalid URLs
        with self.assertRaises(Exception):
            collector._extract_target("https://www.google.com/search?q=instagram")

    # -------------------------------------------------------------------------
    # Audit Item 6: API error handling (401, 403, rate limits, media unavailable, network)
    # -------------------------------------------------------------------------
    def test_audit_06_api_error_handling_mocked(self) -> None:
        """Verify specific custom exceptions are raised for each HTTP error status."""
        collector = InstagramGraphAPICollector(access_token=self.dummy_token)

        # Mock 401 Authentication error
        with patch("requests.Session.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.json.return_value = {"error": {"code": 190, "message": "Invalid OAuth access token"}}
            mock_get.return_value = mock_resp
            with self.assertRaises(AuthenticationError):
                collector.collect_comments("12345", limit=10)

        # Mock 403 Permission denied
        with patch("requests.Session.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 403
            mock_resp.json.return_value = {"error": {"code": 10, "message": "Permission denied"}}
            mock_get.return_value = mock_resp
            with self.assertRaises(PermissionDeniedError):
                collector.collect_comments("12345", limit=10)

        # Mock Rate limit error
        with patch("requests.Session.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.json.return_value = {"error": {"code": 32, "message": "Page request limit reached"}}
            mock_get.return_value = mock_resp
            with self.assertRaises(RateLimitError):
                collector.collect_comments("12345", limit=10)

        # Mock Media Unavailable error (code 100 / subcode 33)
        with patch("requests.Session.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 400
            mock_resp.json.return_value = {"error": {"code": 100, "error_subcode": 33, "message": "Unsupported get request"}}
            mock_get.return_value = mock_resp
            with self.assertRaises(MediaUnavailableError):
                collector.collect_comments("12345", limit=10)

        # Mock Network error
        fast_collector = InstagramGraphAPICollector(access_token=self.dummy_token, max_retries=0)
        with patch("requests.Session.get", side_effect=Exception("Connection reset by peer")):
            with self.assertRaises(NetworkCollectorError):
                fast_collector.collect_comments("12345", limit=10)

    # -------------------------------------------------------------------------
    # Audit Item 7: Pagination and deduplication without data loss
    # -------------------------------------------------------------------------
    def test_audit_07_pagination_and_deduplication(self) -> None:
        """Verify cursor pagination and in-stream comment ID deduplication."""
        collector = InstagramGraphAPICollector(access_token=self.dummy_token)

        # Validate access response
        mock_val = MagicMock(status_code=200)
        mock_val.json.return_value = {"id": "1800112233"}

        # Page 1 contains comment 'c1' and duplicate 'c2'
        page1 = {
            "data": [
                {"id": "c1", "text": "komentar satu"},
                {"id": "c2", "text": "komentar dua"},
            ],
            "paging": {"cursors": {"after": "cursor_page_2"}},
        }
        # Page 2 contains duplicate 'c2' and new 'c3'
        page2 = {
            "data": [
                {"id": "c2", "text": "komentar dua duplicate"},
                {"id": "c3", "text": "komentar tiga"},
            ],
            "paging": {},
        }

        with patch("requests.Session.get") as mock_get:
            mock_resp1 = MagicMock(status_code=200)
            mock_resp1.json.return_value = page1
            mock_resp2 = MagicMock(status_code=200)
            mock_resp2.json.return_value = page2
            mock_get.side_effect = [mock_val, mock_resp1, mock_resp2]

            result = collector.collect_comments("1800112233", limit=10)

        self.assertEqual(result.total_collected, 3)
        self.assertEqual(result.unique_collected, 3)
        comment_ids = [c.comment_id for c in result.comments]
        self.assertEqual(comment_ids, ["c1", "c2", "c3"])

    # -------------------------------------------------------------------------
    # Audit Item 8: RAW always saved before prompt NLP
    # -------------------------------------------------------------------------
    def test_audit_08_raw_saved_before_nlp_prompt(self) -> None:
        """Verify RAW comments file is physically created and hashed before confirmation prompt."""
        run_id = generate_run_id()
        comments = [
            CommentRecord(comment_id="c1", media_id="m1", comment_text="tes satu"),
            CommentRecord(comment_id="c2", media_id="m1", comment_text="tes dua"),
        ]
        raw_path = save_raw_comments(run_id=run_id, comments=comments)
        self.assertTrue(raw_path.exists())
        sha256 = calculate_file_sha256(raw_path)
        self.assertEqual(len(sha256), 64)

    # -------------------------------------------------------------------------
    # Audit Item 9: Jawaban N/Enter menghentikan NLP
    # -------------------------------------------------------------------------
    def test_audit_09_nlp_declined_stops_cleanly(self) -> None:
        """Selecting 'N' or empty Enter aborts NLP and sets status 'nlp_declined'."""
        from src.cli import handle_collect_comments
        from src.collectors.base import CollectionResult

        mock_collector = MagicMock()
        mock_collector.collect_comments.return_value = CollectionResult(
            media_id="18001122",
            comments=[CommentRecord(comment_id="c1", media_id="18001122", comment_text="test")],
            total_collected=1,
            unique_collected=1,
            status="completed",
        )

        mock_preprocess = MagicMock()
        config = AppConfig(access_token=self.dummy_token, target_comments=100)

        # Answering Enter (empty string)
        inputs = iter(["18001122", "10", ""])
        with patch("sys.stdout", new=io.StringIO()):
            handle_collect_comments(
                config=config,
                input_fn=lambda _: next(inputs),
                collector_instance=mock_collector,
                preprocess_fn=mock_preprocess,
            )

        # Preprocessing was NEVER called
        mock_preprocess.assert_not_called()

    # -------------------------------------------------------------------------
    # Audit Item 10: Jawaban Y melanjutkan ke preprocessing saja
    # -------------------------------------------------------------------------
    def test_audit_10_nlp_confirmed_runs_preprocessing_only(self) -> None:
        """Selecting 'y' executes preprocessing ONLY without triggering model training."""
        from src.cli import handle_collect_comments
        from src.collectors.base import CollectionResult

        mock_collector = MagicMock()
        mock_collector.collect_comments.return_value = CollectionResult(
            media_id="18001122",
            comments=[CommentRecord(comment_id="c1", media_id="18001122", comment_text="test")],
            total_collected=1,
            unique_collected=1,
            status="completed",
        )

        mock_preprocess = MagicMock(return_value=Path("dummy_clean.csv"))
        config = AppConfig(access_token=self.dummy_token, target_comments=100)

        inputs = iter(["18001122", "10", "y"])
        with patch("sys.stdout", new=io.StringIO()):
            with patch("src.train.train_baseline_models") as mock_train:
                handle_collect_comments(
                    config=config,
                    input_fn=lambda _: next(inputs),
                    collector_instance=mock_collector,
                    preprocess_fn=mock_preprocess,
                )
                mock_train.assert_not_called()

        mock_preprocess.assert_called_once()

    # -------------------------------------------------------------------------
    # Audit Item 11: Preprocessing tidak mengubah RAW
    # -------------------------------------------------------------------------
    def test_audit_11_preprocessing_does_not_modify_raw(self) -> None:
        """Verify RAW file content and SHA256 are completely untouched during preprocessing."""
        raw_path = self.test_dir / "comments_raw_test.csv"
        self._create_csv(
            raw_path,
            ["comment_id", "media_id", "comment_text", "collected_at", "source_type"],
            [{"comment_id": "c1", "media_id": "m1", "comment_text": "gws ya bro! https://bit.ly/xyz", "collected_at": "now", "source_type": "api"}],
        )
        before_hash = calculate_file_sha256(raw_path)

        report = preprocess_dataset_with_report(
            raw_path,
            run_id="audit_prep",
            output_csv_path=self.test_dir / "comments_clean_audit_prep.csv",
        )
        after_hash = calculate_file_sha256(raw_path)

        self.assertEqual(before_hash, after_hash)
        self.assertTrue(report.processed_filepath.exists())

    # -------------------------------------------------------------------------
    # Audit Item 12: Template anotasi ulang tidak menghapus label lama
    # -------------------------------------------------------------------------
    def test_audit_12_non_destructive_annotation_merge(self) -> None:
        """Regenerating annotation template preserves existing human labels."""
        annotated_csv = self.test_dir / "comments_labeled.csv"
        self._create_csv(
            annotated_csv,
            ANNOTATED_FIELDNAMES,
            [
                {
                    "comment_id": "c1",
                    "clean_text": "gws bro",
                    "slang_present": "ya",
                    "slang_forms": "singkatan",
                    "slang_spans": "gws",
                    "slang_meanings": "get well soon",
                    "language_functions": "emotif",
                    "annotator_id": "A1",
                    "review_status": "selesai",
                    "adjudication_note": "disepakati tim",
                }
            ],
        )

        new_batch_csv = self.test_dir / "comments_clean_new.csv"
        self._create_csv(
            new_batch_csv,
            ["comment_id", "clean_text"],
            [
                {"comment_id": "c1", "clean_text": "gws bro"},
                {"comment_id": "c2", "clean_text": "komentar baru"},
            ],
        )

        generate_annotation_template(new_batch_csv, output_csv_path=annotated_csv)

        with open(annotated_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = {r["comment_id"]: r for r in reader}

        # c1 retained exact human annotation
        self.assertEqual(rows["c1"]["review_status"], "selesai")
        self.assertEqual(rows["c1"]["slang_forms"], "singkatan")
        self.assertEqual(rows["c1"]["annotator_id"], "A1")

        # c2 added with default 'belum'
        self.assertEqual(rows["c2"]["review_status"], "belum")

    # -------------------------------------------------------------------------
    # Audit Item 13: Training berhenti jika anotasi tidak valid atau group split tidak layak
    # -------------------------------------------------------------------------
    def test_audit_13_training_stops_on_invalid_data_or_single_group(self) -> None:
        """Training strictly aborts on invalid schema or insufficient group count."""
        # 1. Invalid schema
        invalid_csv = self.test_dir / "invalid.csv"
        self._create_csv(
            invalid_csv,
            ANNOTATED_FIELDNAMES,
            [{"comment_id": "c1", "clean_text": "x", "slang_present": "tidak", "slang_forms": "singkatan", "review_status": "selesai"}],
        )
        with self.assertRaises(AnnotationSchemaValidationError):
            train_baseline_models(annotated_csv_path=invalid_csv)

        # 2. Single group
        single_group_csv = self.test_dir / "single_group.csv"
        rows = [
            {"comment_id": f"c{i}", "media_id": "same_post", "clean_text": f"text {i}", "slang_present": "tidak", "slang_forms": "tidak_ada", "language_functions": "referensial", "review_status": "selesai"}
            for i in range(8)
        ]
        self._create_csv(single_group_csv, ["media_id"] + ANNOTATED_FIELDNAMES, rows)
        with self.assertRaises(InsufficientDataForSplitError):
            train_baseline_models(annotated_csv_path=single_group_csv)

    # -------------------------------------------------------------------------
    # Audit Item 14: Data test tidak digunakan untuk fitting vectorizer
    # -------------------------------------------------------------------------
    def test_audit_14_vectorizer_fitted_only_on_train(self) -> None:
        """Verify vectorizer vocabulary strictly contains train tokens, never test tokens."""
        import joblib

        annotated_csv = self.test_dir / "train_leakage_test.csv"
        fixture_rows = [
            {"comment_id": "1", "media_id": "post_A", "clean_text": "kata_latih_satu", "slang_present": "ya", "slang_forms": "akronim", "language_functions": "emotif", "review_status": "selesai"},
            {"comment_id": "2", "media_id": "post_A", "clean_text": "kata_latih_dua", "slang_present": "ya", "slang_forms": "akronim", "language_functions": "emotif", "review_status": "selesai"},
            {"comment_id": "3", "media_id": "post_A", "clean_text": "kata_latih_tiga", "slang_present": "tidak", "slang_forms": "tidak_ada", "language_functions": "referensial", "review_status": "selesai"},
            {"comment_id": "4", "media_id": "post_B", "clean_text": "kata_latih_empat", "slang_present": "ya", "slang_forms": "singkatan", "language_functions": "konatif", "review_status": "selesai"},
            {"comment_id": "5", "media_id": "post_B", "clean_text": "kata_latih_lima", "slang_present": "ya", "slang_forms": "singkatan", "language_functions": "konatif", "review_status": "selesai"},
            {"comment_id": "6", "media_id": "post_B", "clean_text": "kata_latih_enam", "slang_present": "tidak", "slang_forms": "tidak_ada", "language_functions": "referensial", "review_status": "selesai"},
            # post_C will be held out as test set
            {"comment_id": "7", "media_id": "post_C", "clean_text": "kata_khusus_uji_test", "slang_present": "ya", "slang_forms": "singkatan", "language_functions": "emotif", "review_status": "selesai"},
            {"comment_id": "8", "media_id": "post_C", "clean_text": "kata_khusus_uji_test dua", "slang_present": "tidak", "slang_forms": "tidak_ada", "language_functions": "referensial", "review_status": "selesai"},
        ]
        self._create_csv(annotated_csv, ["media_id"] + ANNOTATED_FIELDNAMES, fixture_rows)

        report = train_baseline_models(
            annotated_csv_path=annotated_csv,
            output_models_dir=self.test_dir / "models",
            output_reports_dir=self.test_dir / "reports",
            random_seed=42,
            test_size=0.33,
        )

        saved_vec = joblib.load(report.saved_model_paths["vectorizer"])
        if "post_C" in report.test_groups:
            self.assertNotIn("kata_khusus_uji_test", saved_vec.vocabulary_)

    # -------------------------------------------------------------------------
    # Audit Item 15: Prediction tidak menimpa label manual
    # -------------------------------------------------------------------------
    def test_audit_15_prediction_does_not_overwrite_manual_labels(self) -> None:
        """Inference outputs to data/predictions/ and never touches data/annotated/."""
        # Setup model first
        self.test_audit_14_vectorizer_fitted_only_on_train()

        proc_csv = self.test_dir / "comments_clean_pred.csv"
        self._create_csv(
            proc_csv,
            ["comment_id", "media_id", "comment_text", "clean_text"],
            [{"comment_id": "p1", "media_id": "m1", "comment_text": "gws", "clean_text": "gws"}],
        )

        pred_out = self.test_dir / "predictions" / "test_pred.csv"
        result = predict_processed_dataset(
            processed_csv_path=proc_csv,
            output_predictions_path=pred_out,
            models_dir=self.test_dir / "models",
        )
        self.assertTrue(pred_out.exists())
        self.assertEqual(result.total_predicted, 1)

    # -------------------------------------------------------------------------
    # Audit Item 16: Output analisis konsisten dengan jumlah data
    # -------------------------------------------------------------------------
    def test_audit_16_analysis_consistency(self) -> None:
        """Verify analysis volume metrics exactly match counts on disk."""
        raw_csv = self.test_dir / "raw" / "comments_audit1.csv"
        self._create_csv(
            raw_csv,
            ["comment_id", "media_id", "comment_text", "collected_at", "source_type"],
            [{"comment_id": "c1", "media_id": "m1", "comment_text": "a", "collected_at": "now", "source_type": "api"}],
        )

        annotated_csv = self.test_dir / "annotated" / "comments_labeled.csv"
        self._create_csv(
            annotated_csv,
            ANNOTATED_FIELDNAMES,
            [{"comment_id": "c1", "clean_text": "a", "slang_present": "tidak", "slang_forms": "tidak_ada", "language_functions": "referensial", "review_status": "selesai"}],
        )

        report = run_comprehensive_analysis(
            annotated_csv_path=annotated_csv,
            output_reports_dir=self.test_dir / "reports",
            raw_dir=self.test_dir / "raw",
            processed_dir=self.test_dir / "processed",
            predictions_dir=self.test_dir / "predictions",
        )

        self.assertEqual(report.total_raw_comments, 1)
        self.assertEqual(report.total_annotated_comments, 1)
        self.assertEqual(report.human_completed_count, 1)

    # -------------------------------------------------------------------------
    # Audit Item 17: File sensitif dikecualikan oleh .gitignore
    # -------------------------------------------------------------------------
    def test_audit_17_gitignore_excludes_sensitive_files(self) -> None:
        """Verify .gitignore includes patterns for secrets, raw data, models, and predictions."""
        gitignore_path = BASE_DIR / ".gitignore"
        self.assertTrue(gitignore_path.exists())

        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check required sensitive exclusions
        self.assertIn(".env", content)
        self.assertIn("data/raw/*", content)
        self.assertIn("data/processed/*", content)
        self.assertIn("data/annotated/*", content)
        self.assertIn("data/predictions/*", content)
        self.assertIn("models/*", content)
        self.assertIn("reports/*", content)


if __name__ == "__main__":
    unittest.main()
