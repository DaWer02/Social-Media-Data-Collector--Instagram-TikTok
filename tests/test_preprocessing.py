"""Unit and integration tests for text preprocessing module.

Tests cover:
- Indonesian slang preservation
- Emoji preservation
- URL handling to [URL]
- Punctuation & repeated character retention
- Empty & whitespace-only text handling
- Duplicate ID detection
- Missing mandatory columns validation
- RAW file immutability verification
"""

from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from src.preprocessing import (
    PreprocessingValidationError,
    clean_comment_text,
    normalize_text_for_analysis,
    preprocess_dataset_with_report,
    preprocess_raw_dataset,
    validate_raw_dataset_schema,
)
from src.storage import calculate_file_sha256


class TestPreprocessingModule(unittest.TestCase):
    """Test suite for preprocessing logic, schema validation, and immutability."""

    def setUp(self) -> None:
        self.test_dir = Path(tempfile.mkdtemp(prefix="nlp_prep_test_"))
        self.raw_csv_path = self.test_dir / "comments_sample.csv"
        self.processed_csv_path = self.test_dir / "comments_clean_sample.csv"

    def tearDown(self) -> None:
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_raw_sample(self, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> Path:
        """Helper to create sample RAW CSV files."""
        fields = fieldnames or [
            "comment_id",
            "media_id",
            "comment_text",
            "timestamp",
            "like_count",
            "collected_at",
            "source_type",
        ]
        with open(self.raw_csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return self.raw_csv_path

    def test_indonesian_slang_preservation(self) -> None:
        """Verify Indonesian slang words are preserved without stemming or modification."""
        sample_texts = [
            ("gws ya kak semoga cepet sembuh", "gws"),
            ("otw nih gaes tungguin ya", "otw"),
            ("mager bgt hari ini asli", "mager"),
            ("kuy nongkrong bareng bestie", "kuy"),
        ]
        for text, slang_word in sample_texts:
            with self.subTest(text=text):
                cleaned = clean_comment_text(text)
                self.assertEqual(cleaned, text)
                self.assertIn(slang_word, cleaned)

    def test_emoji_preservation(self) -> None:
        """Verify emoji characters are preserved completely in clean_text."""
        sample = "Keren bangeeet kak! 🔥😍🙌 Sukses terus yaa ✨"
        cleaned = clean_comment_text(sample)
        self.assertIn("🔥", cleaned)
        self.assertIn("😍", cleaned)
        self.assertIn("🙌", cleaned)
        self.assertIn("✨", cleaned)

    def test_url_normalization(self) -> None:
        """Verify web URLs are replaced with [URL] token."""
        samples = [
            ("Cek info promo di https://promo.link.id/merdeka ya", "Cek info promo di [URL] ya"),
            ("kunjungi www.example.com untuk detail", "kunjungi [URL] untuk detail"),
            ("klik http://bit.ly/xyz123 sekarang!!", "klik [URL] sekarang!!"),
        ]
        for raw, expected in samples:
            with self.subTest(raw=raw):
                cleaned = clean_comment_text(raw)
                self.assertEqual(cleaned, expected)

    def test_punctuation_and_repeated_characters(self) -> None:
        """Verify punctuation marks and repeated expressive letters are retained."""
        sample = "bangeeeettt... loool!!! baper parah???"
        cleaned = clean_comment_text(sample)
        self.assertEqual(cleaned, "bangeeeettt... loool!!! baper parah???")

    def test_empty_and_whitespace_text(self) -> None:
        """Verify empty or whitespace-only text is correctly cleaned and flagged."""
        self.assertEqual(clean_comment_text(""), "")
        self.assertEqual(clean_comment_text("   \n\t  "), "")
        self.assertEqual(clean_comment_text(None), "")

        norm = normalize_text_for_analysis("   \n\t  ")
        self.assertEqual(norm, "")

    def test_duplicate_id_handling_and_report_stats(self) -> None:
        """Verify duplicate comment IDs are flagged and statistics are computed accurately."""
        rows = [
            {"comment_id": "c1", "media_id": "m1", "comment_text": "Komentar pertama unik"},
            {"comment_id": "c2", "media_id": "m1", "comment_text": "Komentar kedua unik"},
            {"comment_id": "c1", "media_id": "m1", "comment_text": "Komentar pertama duplikat"},
            {"comment_id": "c3", "media_id": "m1", "comment_text": "   \n\t  "},  # empty
        ]
        self._create_raw_sample(rows)

        report = preprocess_dataset_with_report(
            raw_csv_path=self.raw_csv_path,
            output_csv_path=self.processed_csv_path,
        )

        self.assertEqual(report.total_initial, 4)
        self.assertEqual(report.total_empty, 1)
        self.assertEqual(report.total_duplicate, 1)
        self.assertEqual(report.total_final, 2)  # c1 (first), c2

        # Check processed CSV records
        with open(self.processed_csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        self.assertEqual(len(reader), 4)
        self.assertEqual(reader[0]["duplicate_status"], "unique")
        self.assertEqual(reader[1]["duplicate_status"], "unique")
        self.assertEqual(reader[2]["duplicate_status"], "duplicate")
        self.assertEqual(reader[3]["is_empty_after_cleaning"], "true")

    def test_missing_mandatory_columns_validation(self) -> None:
        """Verify missing mandatory columns in RAW raises PreprocessingValidationError."""
        # Create CSV missing 'comment_text'
        bad_rows = [{"comment_id": "c1", "media_id": "m1"}]
        self._create_raw_sample(bad_rows, fieldnames=["comment_id", "media_id"])

        missing = validate_raw_dataset_schema(self.raw_csv_path)
        self.assertIn("comment_text", missing)

        with self.assertRaises(PreprocessingValidationError) as ctx:
            preprocess_dataset_with_report(
                raw_csv_path=self.raw_csv_path,
                output_csv_path=self.processed_csv_path,
            )
        self.assertIn("comment_text", str(ctx.exception))
        self.assertEqual(ctx.exception.missing_columns, ["comment_text"])

    def test_raw_file_immutability(self) -> None:
        """Verify that RAW file is never altered during preprocessing."""
        rows = [
            {"comment_id": "c100", "media_id": "m1", "comment_text": "Asli gak berubah 🔥"},
            {"comment_id": "c101", "media_id": "m1", "comment_text": "Cek https://link.id"},
        ]
        self._create_raw_sample(rows)

        sha256_before = calculate_file_sha256(self.raw_csv_path)
        raw_bytes_before = self.raw_csv_path.read_bytes()

        # Run preprocessing
        processed_path = preprocess_raw_dataset(
            raw_csv_path=self.raw_csv_path,
            output_csv_path=self.processed_csv_path,
        )
        self.assertTrue(processed_path.exists())

        sha256_after = calculate_file_sha256(self.raw_csv_path)
        raw_bytes_after = self.raw_csv_path.read_bytes()

        self.assertEqual(sha256_before, sha256_after)
        self.assertEqual(raw_bytes_before, raw_bytes_after)

    def test_processed_output_schema_and_text_preservation(self) -> None:
        """Verify processed output has exact required columns and preserves raw comment_text."""
        raw_text_original = "  Ini Teks ASLI Dengan Huruf BESAR dan Spasi   "
        rows = [{"comment_id": "c200", "media_id": "m2", "comment_text": raw_text_original}]
        self._create_raw_sample(rows)

        preprocess_raw_dataset(
            raw_csv_path=self.raw_csv_path,
            output_csv_path=self.processed_csv_path,
        )

        with open(self.processed_csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)

        # Fieldnames verification
        expected_fields = [
            "comment_id",
            "media_id",
            "username",
            "comment_text",
            "clean_text",
            "normalized_text",
            "is_empty_after_cleaning",
            "duplicate_status",
            "bentuk_bahasa_gaul",
            "fungsi_bahasa",
            "kata_gaul",
        ]
        self.assertEqual(list(row.keys()), expected_fields)

        # comment_text must be 100% untouched
        self.assertEqual(row["comment_text"], raw_text_original)
        # clean_text has normalized whitespace but original casing
        self.assertEqual(row["clean_text"], "Ini Teks ASLI Dengan Huruf BESAR dan Spasi")
        # normalized_text is lowercased
        self.assertEqual(row["normalized_text"], "ini teks asli dengan huruf besar dan spasi")

    def test_username_field_preservation(self) -> None:
        """Verify username field from RAW CSV is correctly propagated into processed CSV."""
        rows = [
            {"comment_id": "c301", "media_id": "m1", "username": "anwar_ibrahim", "comment_text": "Hebat sekali!"},
            {"comment_id": "c302", "media_id": "m1", "username": "rakyat_jelata", "comment_text": "Setuju bgt mantap"},
        ]
        self._create_raw_sample(rows, fieldnames=["comment_id", "media_id", "username", "comment_text"])

        preprocess_raw_dataset(
            raw_csv_path=self.raw_csv_path,
            output_csv_path=self.processed_csv_path,
        )

        with open(self.processed_csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        self.assertEqual(len(reader), 2)
        self.assertEqual(reader[0]["username"], "anwar_ibrahim")
        self.assertEqual(reader[1]["username"], "rakyat_jelata")

    def test_linguistic_categorization_in_preprocessing(self) -> None:
        """Verify NLP categorization is performed directly during preprocessing with category statistics."""
        rows = [
            {"comment_id": "c401", "media_id": "m1", "comment_text": "Santuy bgt ngab, gokil abiss wkwk 🔥"},
            {"comment_id": "c402", "media_id": "m1", "comment_text": "Tolong evaluasi kebijakan ini segera @prabowo"},
            {"comment_id": "c403", "media_id": "m1", "comment_text": "Gaji minimum dinaikkan jadi RM2,000"},
        ]
        self._create_raw_sample(rows)

        report = preprocess_dataset_with_report(
            raw_csv_path=self.raw_csv_path,
            output_csv_path=self.processed_csv_path,
        )

        with open(self.processed_csv_path, "r", encoding="utf-8") as f:
            reader = list(csv.DictReader(f))

        # Check Row 1: santuy, bgt, ngab, gokil, wkwk
        self.assertIn("plesetan", reader[0]["bentuk_bahasa_gaul"])
        self.assertIn("singkatan", reader[0]["bentuk_bahasa_gaul"])
        self.assertIn("emotif", reader[0]["fungsi_bahasa"])
        self.assertIn("santuy", reader[0]["kata_gaul"])

        # Check Row 2: tolong, @prabowo
        self.assertIn("konatif", reader[1]["fungsi_bahasa"])

        # Check Row 3: gaji minimum, RM2,000
        self.assertIn("referensial", reader[2]["fungsi_bahasa"])

        # Check summary text mentions category distributions
        summary = report.summary_text()
        self.assertIn("DISTRIBUSI BENTUK BAHASA GAUL:", summary)
        self.assertIn("DISTRIBUSI FUNGSI BAHASA:", summary)


if __name__ == "__main__":
    unittest.main()
