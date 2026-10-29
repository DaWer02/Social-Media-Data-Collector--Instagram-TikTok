"""Unit tests for terminal CLI navigation and menu handling."""

import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.cli import display_menu, run_cli
from src.config import AppConfig


class TestCLIInterface(unittest.TestCase):
    """Test suite for CLI interaction and error handling."""

    def test_display_menu_contains_all_required_items(self) -> None:
        """Verify display_menu contains all required menu items 1 through 7 and 0."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            display_menu()
            output = fake_out.getvalue()

        expected_menu_items = [
            "1. Kumpulkan komentar Instagram",
            "2. Jalankan NLP pada RAW yang sudah ada",
            "3. Buat template anotasi",
            "4. Validasi anotasi",
            "5. Latih model baseline",
            "6. Prediksi dataset",
            "7. Analisis hasil",
            "0. Keluar",
        ]
        for item in expected_menu_items:
            with self.subTest(item=item):
                self.assertIn(item, output)

    def test_run_cli_exit_immediately(self) -> None:
        """Choosing '0' must exit cleanly with code 0."""
        inputs = iter(["0"])
        exit_code = run_cli(input_fn=lambda _: next(inputs))
        self.assertEqual(exit_code, 0)

    def test_run_cli_invalid_then_exit(self) -> None:
        """Invalid inputs (letters, out-of-range numbers) must warn without crashing."""
        inputs = iter(["abc", "9", "-1", "0"])
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=lambda _: next(inputs))
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Pilihan 'abc' tidak valid", output)
        self.assertIn("Pilihan '9' tidak valid", output)
        self.assertIn("Pilihan '-1' tidak valid", output)

    def test_run_cli_ctrl_c_handled_gracefully(self) -> None:
        """KeyboardInterrupt (Ctrl+C) must exit cleanly with code 0."""
        def mock_interrupt(_: str) -> str:
            raise KeyboardInterrupt()

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=mock_interrupt)
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Keluar dengan aman", output)

    def test_run_cli_eof_handled_gracefully(self) -> None:
        """EOFError (Ctrl+Z/Ctrl+D) must exit cleanly with code 0."""
        def mock_eof(_: str) -> str:
            raise EOFError()

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=mock_eof)
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Keluar dengan aman", output)

    def test_run_cli_menu_7_analysis_flow(self) -> None:
        """Menu 7 executes comprehensive analysis across datasets and prints report."""
        inputs = iter(["7", "0"])  # Menu 7, then exit
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=lambda _: next(inputs))
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Analisis Dataset & Laporan Hasil", output)
        self.assertIn("RINGKASAN ANALISIS DATASET & LAPORAN NLP", output)

    def test_run_cli_menu_5_no_completed_annotations(self) -> None:
        """Menu 5 gracefully reports validation error when no completed annotations exist."""
        inputs = iter(["5", "y", "0"])  # Menu 5, confirm run, then exit
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=lambda _: next(inputs))
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Latih Model Baseline", output)
        self.assertIn("VALIDASI ERROR", output)

    def test_run_cli_menu_6_no_processed_files(self) -> None:
        """Menu 6 reports info message if no processed dataset files exist."""
        with tempfile.TemporaryDirectory() as empty_dir:
            with patch("src.config.PROCESSED_DATA_DIR", new=Path(empty_dir)):
                inputs = iter(["6", "0"])
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    exit_code = run_cli(input_fn=lambda _: next(inputs))
                    output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Prediksi Dataset Menggunakan Model Baseline", output)
        self.assertIn("Tidak ada file hasil preprocessing", output)

    def test_run_cli_menu_2_no_raw_files(self) -> None:
        """Menu 2 with no RAW files reports info and returns safely."""
        with tempfile.TemporaryDirectory() as empty_dir:
            with patch("src.config.RAW_DATA_DIR", new=Path(empty_dir)):
                inputs = iter(["2", "0"])
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    exit_code = run_cli(input_fn=lambda _: next(inputs))
                    output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Jalankan NLP pada RAW yang Sudah Ada", output)

    def test_run_cli_menu_3_no_processed_files(self) -> None:
        """Menu 3 reports informative message if no processed dataset files exist."""
        with tempfile.TemporaryDirectory() as empty_dir:
            with patch("src.config.PROCESSED_DATA_DIR", new=Path(empty_dir)):
                inputs = iter(["3", "0"])
                with patch("sys.stdout", new=io.StringIO()) as fake_out:
                    exit_code = run_cli(input_fn=lambda _: next(inputs))
                    output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Buat / Perbarui Template Anotasi", output)
        self.assertIn("Tidak ada file hasil preprocessing", output)

    def test_run_cli_menu_4_no_annotated_file(self) -> None:
        """Menu 4 reports informative message if comments_labeled.csv does not exist yet."""
        non_existent = Path("non_existent_dir_xyz/comments_labeled.csv")
        with patch("src.annotations.DEFAULT_ANNOTATED_PATH", new=non_existent):
            inputs = iter(["4", "0"])
            with patch("sys.stdout", new=io.StringIO()) as fake_out:
                exit_code = run_cli(input_fn=lambda _: next(inputs))
                output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Validasi Dataset Anotasi", output)
        self.assertIn("File anotasi belum dibuat", output)

    def test_run_cli_menu_4_existing_annotated_file(self) -> None:
        """Menu 4 performs validation and prints summary report for existing annotated file."""
        inputs = iter(["4", "y", "0"])  # Menu 4, confirm default file, then exit
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=lambda _: next(inputs))
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("RINGKASAN VALIDASI DATASET ANOTASI", output)

    def test_run_cli_option_1_empty_target_cancels(self) -> None:
        """Option 1 with empty target input cancels without error."""
        inputs = iter(["1", "", "0"])  # Menu 1, then empty input for target, then exit
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=lambda _: next(inputs))
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Pengumpulan dibatalkan (input kosong)", output)

    @patch("src.cli.AppConfig.from_env")
    @patch("src.collectors.instagram_api.InstagramGraphAPICollector.collect_comments")
    def test_run_cli_option_1_session_token_flow(
        self,
        mock_collect: MagicMock,
        mock_from_env: MagicMock,
    ) -> None:
        """Option 1 prompts for session token securely when not configured in graph_api mode."""
        from src.collectors.base import CollectionResult

        # Mock config with NO access token configured and graph_api mode
        mock_from_env.return_value = AppConfig(
            access_token=None,
            target_comments=3000,
            graph_api_version="v21.0",
            collector_method="graph_api",
        )

        mock_collect.return_value = CollectionResult(
            media_id="17970528943031455",
            comments=[],
            total_collected=0,
            unique_collected=0,
            status="completed",
        )

        inputs = iter([
            "1",                                       # Menu 1
            "https://www.instagram.com/p/test1234/",  # Target URL
            "1500",                                    # Target comments
            "0",                                       # Exit menu
        ])

        def mock_token_prompt(prompt_text: str) -> str:
            return "SESSION_MOCK_TOKEN_XYZ12345"

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(
                input_fn=lambda _: next(inputs),
                prompt_token_fn=mock_token_prompt,
            )
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Target terpilih: 1500 komentar", output)
        self.assertIn("Token sesi berhasil disimpan di memori", output)
        self.assertNotIn("SESSION_MOCK_TOKEN_XYZ12345", output)
        self.assertIn("SESS...2345", output)
        mock_collect.assert_called_once()

    @patch("src.cli.AppConfig.from_env")
    @patch("src.collectors.browser_nlp.InstagramBrowserNLPCollector.collect_comments")
    def test_run_cli_option_1_browser_nlp_flow(
        self,
        mock_collect: MagicMock,
        mock_from_env: MagicMock,
    ) -> None:
        """Option 1 runs Browser NLP Collector by default without requiring access tokens."""
        from src.collectors.base import CollectionResult

        mock_from_env.return_value = AppConfig(
            collector_method="browser_nlp",
            target_comments=3000,
        )

        mock_collect.return_value = CollectionResult(
            media_id="test1234",
            comments=[],
            total_collected=0,
            unique_collected=0,
            status="completed",
        )

        inputs = iter([
            "1",                                       # Menu 1
            "https://www.instagram.com/p/test1234/",  # Target URL
            "500",                                     # Target comments
            "0",                                       # Exit menu
        ])

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=lambda _: next(inputs))
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Browser Automation (Playwright) + NLP Extractor", output)
        self.assertIn("Target terpilih: 500 komentar", output)
        mock_collect.assert_called_once()


if __name__ == "__main__":
    unittest.main()
