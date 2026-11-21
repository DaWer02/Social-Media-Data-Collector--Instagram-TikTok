"""Unit tests for storage exports (CSV & Excel) with privacy validation."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.collectors.base import CommentRecord
from src.storage import get_raw_filepath, prepare_rows_for_export, save_raw_comments


class TestStorageExport(unittest.TestCase):
    """Test suite for CSV and Excel dataset exports."""

    def setUp(self) -> None:
        self.sample_comments = [
            CommentRecord(
                comment_id="c_1",
                media_id="media_101",
                username="private_user",
                comment_text="Halo @kawan_lama, apa kabar?",
                timestamp="2026-11-20T10:00:00Z",
                like_count=5,
                collected_at="2026-11-21T00:00:00Z",
                source_type="browser_social",
            ),
            CommentRecord(
                comment_id="c_2",
                media_id="media_101",
                username="another_user",
                comment_text="Setuju banget nih!",
                timestamp="2026-11-20T10:05:00Z",
                like_count=12,
                collected_at="2026-11-21T00:00:00Z",
                source_type="browser_social",
            ),
        ]

    def test_prepare_rows_for_export_omits_username(self) -> None:
        rows = prepare_rows_for_export(self.sample_comments)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertNotIn("username", row)
            self.assertNotIn("author", row)
            self.assertIn("comment_text", row)
            self.assertIn("comment_id", row)
        self.assertEqual(rows[0]["comment_text"], "Halo [@USER], apa kabar?")

    def test_save_raw_comments_both_csv_and_xlsx(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            with patch("src.storage.RAW_DATA_DIR", tmp_path):
                run_id = "test_run_both"
                csv_path = save_raw_comments(run_id, self.sample_comments, output_format="both")
                xlsx_path = get_raw_filepath(run_id, "xlsx")

                self.assertTrue(csv_path.exists())
                self.assertTrue(xlsx_path.exists())

                # Check CSV columns
                df_csv = pd.read_csv(csv_path)
                self.assertNotIn("username", df_csv.columns)
                self.assertIn("comment_text", df_csv.columns)
                self.assertEqual(len(df_csv), 2)
                self.assertIn("[@USER]", df_csv.iloc[0]["comment_text"])

                # Check Excel columns
                df_xlsx = pd.read_excel(xlsx_path)
                self.assertNotIn("username", df_xlsx.columns)
                self.assertIn("comment_text", df_xlsx.columns)
                self.assertEqual(len(df_xlsx), 2)


if __name__ == "__main__":
    unittest.main()
