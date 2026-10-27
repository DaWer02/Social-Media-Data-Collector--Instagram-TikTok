"""Unit tests for external CSV/Excel import tool."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.storage import calculate_file_sha256
from src.tools.import_external_csv import (
    convert_external_file_to_raw,
    detect_column_mapping,
    extract_shortcode_from_url_or_text,
    main,
)


class TestImportExternalCSV(unittest.TestCase):
    """Test suite for converting external comment exports into RAW format."""

    def test_extract_shortcode(self) -> None:
        self.assertEqual(
            extract_shortcode_from_url_or_text("https://www.instagram.com/p/DeRfCHemNKL/?foo=bar"),
            "DeRfCHemNKL",
        )
        self.assertEqual(
            extract_shortcode_from_url_or_text("https://instagram.com/reel/C_abc123/"),
            "C_abc123",
        )
        self.assertEqual(
            extract_shortcode_from_url_or_text("DeRfCHemNKL"),
            "DeRfCHemNKL",
        )
        self.assertIsNone(extract_shortcode_from_url_or_text(""))

    def test_detect_column_mapping(self) -> None:
        cols = ["Username", "Comment", "Date", "Likes"]
        mapping = detect_column_mapping(cols)
        self.assertEqual(mapping.get("comment_text"), "Comment")
        self.assertEqual(mapping.get("timestamp"), "Date")
        self.assertEqual(mapping.get("like_count"), "Likes")
        self.assertNotIn("comment_id", mapping)

    def test_convert_external_csv_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            ext_csv = Path(tmpdir) / "export_comments.csv"
            # Simulate typical Chrome extension output
            df = pd.DataFrame([
                {"Username": "user_a", "Comment": "gokil bgt lur mantul", "Date": "2026-10-27T10:00:00"},
                {"Username": "user_b", "Comment": "wkwk keren abis cuy", "Date": "2026-10-27T10:05:00"},
                {"Username": "user_c", "Comment": "", "Date": "2026-10-27T10:06:00"},  # empty should be skipped
            ])
            df.to_csv(ext_csv, index=False)

            raw_path, count = convert_external_file_to_raw(
                filepath=ext_csv,
                media_id="DeRfCHemNKL",
                run_id="test_import_001",
            )

            self.assertTrue(raw_path.exists())
            self.assertEqual(count, 2)

            # Validate saved RAW columns
            result_df = pd.read_csv(raw_path)
            self.assertIn("comment_id", result_df.columns)
            self.assertIn("media_id", result_df.columns)
            self.assertIn("comment_text", result_df.columns)
            self.assertEqual(len(result_df), 2)
            self.assertEqual(result_df.iloc[0]["comment_text"], "gokil bgt lur mantul")
            self.assertEqual(result_df.iloc[0]["media_id"], "DeRfCHemNKL")

            # Clean up created file
            if raw_path.exists():
                raw_path.unlink()

    def test_convert_file_missing_comment_column_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_csv = Path(tmpdir) / "bad.csv"
            df = pd.DataFrame([{"foo": "bar", "baz": 123}])
            df.to_csv(bad_csv, index=False)

            with self.assertRaises(ValueError) as ctx:
                convert_external_file_to_raw(bad_csv)
            self.assertIn("Kolom teks komentar tidak ditemukan", str(ctx.exception))

    def test_cli_main_entry_point(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "ig_comments.csv"
            pd.DataFrame([{"comment": "mantap", "id": "111"}]).to_csv(csv_path, index=False)

            code = main([str(csv_path), "--media-id", "post123", "--run-id", "test_cli_imp"])
            self.assertEqual(code, 0)

            # Cleanup
            from src.storage import get_raw_filepath
            created = get_raw_filepath("test_cli_imp")
            if created.exists():
                created.unlink()


if __name__ == "__main__":
    unittest.main()
