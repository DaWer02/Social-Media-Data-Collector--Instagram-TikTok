"""Unit tests for terminal CLI navigation in Social Media Data Collector."""

import io
import unittest
from unittest.mock import patch

from src.cli import display_menu, run_cli
from src.config import AppConfig


class TestCLIInterface(unittest.TestCase):
    """Test suite for Social Media Data Collector CLI menu."""

    def test_display_menu_contains_collector_items(self) -> None:
        """Verify display_menu contains options for collection, login, and exit."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            display_menu()
            output = fake_out.getvalue()

        self.assertIn("1. Kumpulkan komentar (Instagram / TikTok)", output)
        self.assertIn("2. Buka browser untuk login Instagram", output)
        self.assertIn("3. Buka browser untuk login TikTok", output)
        self.assertIn("4. Cek status profil browser", output)
        self.assertIn("0. Keluar", output)

    def test_run_cli_exit_immediately(self) -> None:
        """Choosing '0' must exit cleanly with code 0."""
        inputs = iter(["0"])
        exit_code = run_cli(input_fn=lambda _: next(inputs))
        self.assertEqual(exit_code, 0)

    def test_run_cli_invalid_choice_warning(self) -> None:
        """Invalid inputs must warn without crashing."""
        inputs = iter(["99", "", "0"])
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=lambda _: next(inputs))
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Pilihan '99' tidak valid", output)

    def test_run_cli_ctrl_c_handled_gracefully(self) -> None:
        """KeyboardInterrupt must exit cleanly with code 0."""
        def mock_interrupt(_: str) -> str:
            raise KeyboardInterrupt()

        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(input_fn=mock_interrupt)
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("Keluar dengan aman", output)

    def test_run_cli_non_interactive_status(self) -> None:
        """Non-interactive status check returns 0."""
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            exit_code = run_cli(non_interactive=True)
            output = fake_out.getvalue()

        self.assertEqual(exit_code, 0)
        self.assertIn("SOCIAL MEDIA DATA COLLECTOR", output)


if __name__ == "__main__":
    unittest.main()
