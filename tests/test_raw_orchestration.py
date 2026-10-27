"""Integration tests for collection orchestration, RAW storage, and confirmation gate.

Verifies:
A. Answering 'N' does NOT run preprocessing.
B. Empty Enter does NOT run preprocessing.
C. Answering 'Y' calls preprocessing exactly once.
D. RAW file is saved on disk BEFORE the confirmation prompt is presented.
E. RAW file remains identical (immutable) before and after preprocessing.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.cli import handle_collect_comments
from src.collectors.base import BaseCollector, CollectionResult, CommentRecord
from src.config import AppConfig
from src.preprocessing import preprocess_raw_dataset
from src.storage import calculate_file_sha256


class MockTestCollector(BaseCollector):
    """Deterministic in-memory collector for integration tests."""

    def __init__(self, media_id: str = "18001122334455", count: int = 3) -> None:
        self.media_id = media_id
        self.count = count

    def resolve_media_id(self, target: str) -> str:
        return self.media_id

    def validate_access(self, media_id: str) -> tuple[bool, str | None]:
        return True, None

    def collect_comments(self, target: str, limit: int = 3000) -> CollectionResult:
        comments = [
            CommentRecord(
                comment_id=f"test_cmt_{i}",
                media_id=self.media_id,
                comment_text=f"Komentar uji slang mantul {i} 🔥",
                timestamp="2026-10-27T10:00:00Z",
                like_count=i * 2,
                collected_at="2026-10-27T12:00:00Z",
                source_type="authorized_api",
            )
            for i in range(self.count)
        ]
        return CollectionResult(
            media_id=self.media_id,
            comments=comments,
            total_collected=len(comments),
            unique_collected=len(comments),
            status="completed",
            paging_completed=True,
        )


class TestRAWOrchestrationIntegration(unittest.TestCase):
    """Integration test suite verifying core business rules for RAW orchestration."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp(prefix="nlp_orch_test_"))
        self.raw_dir = self.test_dir / "data" / "raw"
        self.processed_dir = self.test_dir / "data" / "processed"
        self.reports_dir = self.test_dir / "reports"

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        self.config = AppConfig(
            access_token="MOCK_TEST_ACCESS_TOKEN",
            target_comments=100,
            raw_dir=self.raw_dir,
            processed_dir=self.processed_dir,
            reports_dir=self.reports_dir,
        )
        self.mock_collector = MockTestCollector()

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("src.storage.RAW_DATA_DIR")
    @patch("src.storage.PROCESSED_DATA_DIR")
    @patch("src.storage.REPORTS_DIR")
    def test_A_answer_n_does_not_run_preprocessing(
        self,
        mock_reports_dir: Path,
        mock_processed_dir: Path,
        mock_raw_dir: Path,
    ) -> None:
        """Requirement A: Answering 'N' must NOT execute preprocessing; RAW is preserved."""
        mock_raw_dir.__truediv__.side_effect = lambda name: self.raw_dir / name
        mock_processed_dir.__truediv__.side_effect = lambda name: self.processed_dir / name
        mock_reports_dir.__truediv__.side_effect = lambda name: self.reports_dir / name

        mock_preprocess = MagicMock()
        user_inputs = iter([
            "18001122334455",  # Target input
            "100",             # Target count
            "N",               # Confirmation prompt: 'Lanjutkan ke tahap NLP sekarang? [y/N]:' -> N
        ])

        with patch("sys.stdout", new=io.StringIO()):
            handle_collect_comments(
                config=self.config,
                input_fn=lambda _: next(user_inputs),
                collector_instance=self.mock_collector,
                preprocess_fn=mock_preprocess,
            )

        # 1. Preprocessing was NEVER called
        mock_preprocess.assert_not_called()

        # 2. RAW file was saved
        raw_files = list(self.raw_dir.glob("comments_*.csv"))
        self.assertEqual(len(raw_files), 1)

        # 3. Report recorded 'nlp_declined'
        report_files = list(self.reports_dir.glob("run_*.json"))
        self.assertEqual(len(report_files), 1)
        with open(report_files[0], "r", encoding="utf-8") as f:
            metadata = json.load(f)
            self.assertEqual(metadata["status"], "nlp_declined")
            self.assertFalse(metadata.get("nlp_confirmed", True))

    @patch("src.storage.RAW_DATA_DIR")
    @patch("src.storage.PROCESSED_DATA_DIR")
    @patch("src.storage.REPORTS_DIR")
    def test_B_empty_enter_does_not_run_preprocessing(
        self,
        mock_reports_dir: Path,
        mock_processed_dir: Path,
        mock_raw_dir: Path,
    ) -> None:
        """Requirement B: Pressing Enter (empty string) defaults to NO and terminates safely."""
        mock_raw_dir.__truediv__.side_effect = lambda name: self.raw_dir / name
        mock_processed_dir.__truediv__.side_effect = lambda name: self.processed_dir / name
        mock_reports_dir.__truediv__.side_effect = lambda name: self.reports_dir / name

        mock_preprocess = MagicMock()
        user_inputs = iter([
            "https://www.instagram.com/p/test_shortcode/",  # Target input
            "",                                             # Target count (use default)
            "",                                             # Empty enter on confirmation
        ])

        with patch("sys.stdout", new=io.StringIO()):
            handle_collect_comments(
                config=self.config,
                input_fn=lambda _: next(user_inputs),
                collector_instance=self.mock_collector,
                preprocess_fn=mock_preprocess,
            )

        mock_preprocess.assert_not_called()
        report_files = list(self.reports_dir.glob("run_*.json"))
        with open(report_files[0], "r", encoding="utf-8") as f:
            metadata = json.load(f)
            self.assertEqual(metadata["status"], "nlp_declined")

    @patch("src.storage.RAW_DATA_DIR")
    @patch("src.storage.PROCESSED_DATA_DIR")
    @patch("src.storage.REPORTS_DIR")
    def test_C_answer_y_calls_preprocessing_exactly_once(
        self,
        mock_reports_dir: Path,
        mock_processed_dir: Path,
        mock_raw_dir: Path,
    ) -> None:
        """Requirement C: Answering 'y' or 'yes' invokes preprocessing exactly once."""
        mock_raw_dir.__truediv__.side_effect = lambda name: self.raw_dir / name
        mock_processed_dir.__truediv__.side_effect = lambda name: self.processed_dir / name
        mock_reports_dir.__truediv__.side_effect = lambda name: self.reports_dir / name

        mock_preprocess = MagicMock()
        dummy_processed_path = self.processed_dir / "comments_clean_test.csv"
        mock_preprocess.return_value = dummy_processed_path

        user_inputs = iter([
            "18001122334455",
            "50",
            "y",  # Confirmed with 'y'
        ])

        with patch("sys.stdout", new=io.StringIO()):
            handle_collect_comments(
                config=self.config,
                input_fn=lambda _: next(user_inputs),
                collector_instance=self.mock_collector,
                preprocess_fn=mock_preprocess,
            )

        # Preprocessing called EXACTLY ONCE
        self.assertEqual(mock_preprocess.call_count, 1)

        # Check metadata updated to preprocessed
        report_files = list(self.reports_dir.glob("run_*.json"))
        with open(report_files[0], "r", encoding="utf-8") as f:
            metadata = json.load(f)
            self.assertEqual(metadata["status"], "preprocessed")
            self.assertTrue(metadata.get("nlp_confirmed"))

    @patch("src.storage.RAW_DATA_DIR")
    @patch("src.storage.PROCESSED_DATA_DIR")
    @patch("src.storage.REPORTS_DIR")
    def test_D_raw_saved_before_confirmation_prompt(
        self,
        mock_reports_dir: Path,
        mock_processed_dir: Path,
        mock_raw_dir: Path,
    ) -> None:
        """Requirement D: The RAW file MUST exist on disk before the confirmation question is asked."""
        mock_raw_dir.__truediv__.side_effect = lambda name: self.raw_dir / name
        mock_processed_dir.__truediv__.side_effect = lambda name: self.processed_dir / name
        mock_reports_dir.__truediv__.side_effect = lambda name: self.reports_dir / name

        raw_verified_during_prompt = False

        def input_inspector(prompt_text: str) -> str:
            nonlocal raw_verified_during_prompt
            if "Lanjutkan ke tahap NLP sekarang?" in prompt_text:
                # Inspect disk state right at the moment confirmation is asked
                raw_files = list(self.raw_dir.glob("comments_*.csv"))
                if len(raw_files) == 1 and raw_files[0].stat().st_size > 0:
                    raw_verified_during_prompt = True
                return "n"
            elif "target" in prompt_text.lower():
                return "10"
            return "18001122334455"

        with patch("sys.stdout", new=io.StringIO()):
            handle_collect_comments(
                config=self.config,
                input_fn=input_inspector,
                collector_instance=self.mock_collector,
            )

        self.assertTrue(
            raw_verified_during_prompt,
            "File RAW harus sudah tersimpan dan ada di disk sebelum pertanyaan konfirmasi ditampilkan!",
        )

    @patch("src.storage.RAW_DATA_DIR")
    @patch("src.storage.PROCESSED_DATA_DIR")
    @patch("src.storage.REPORTS_DIR")
    def test_E_raw_file_immutable_after_preprocessing(
        self,
        mock_reports_dir: Path,
        mock_processed_dir: Path,
        mock_raw_dir: Path,
    ) -> None:
        """Requirement E: SHA-256 hash and contents of the RAW file must be 100% identical before and after preprocessing."""
        mock_raw_dir.__truediv__.side_effect = lambda name: self.raw_dir / name
        mock_processed_dir.__truediv__.side_effect = lambda name: self.processed_dir / name
        mock_reports_dir.__truediv__.side_effect = lambda name: self.reports_dir / name

        user_inputs = iter([
            "18001122334455",
            "100",
            "yes",  # User says yes -> run real preprocessing
        ])

        with patch("sys.stdout", new=io.StringIO()):
            handle_collect_comments(
                config=self.config,
                input_fn=lambda _: next(user_inputs),
                collector_instance=self.mock_collector,
                preprocess_fn=preprocess_raw_dataset,  # Run real preprocessing module
            )

        raw_files = list(self.raw_dir.glob("comments_*.csv"))
        processed_files = list(self.processed_dir.glob("comments_clean_*.csv"))

        self.assertEqual(len(raw_files), 1)
        self.assertEqual(len(processed_files), 1)

        raw_path = raw_files[0]
        sha256_after = calculate_file_sha256(raw_path)

        # Retrieve SHA-256 recorded when RAW was first saved
        report_files = list(self.reports_dir.glob("run_*.json"))
        with open(report_files[0], "r", encoding="utf-8") as f:
            metadata = json.load(f)
            sha256_before = metadata.get("raw_sha256")

        # Verify that RAW dataset is strictly immutable
        self.assertIsNotNone(sha256_before)
        self.assertEqual(
            sha256_before,
            sha256_after,
            "Checksum SHA-256 file RAW tidak boleh berubah setelah tahap preprocessing!",
        )


if __name__ == "__main__":
    unittest.main()
