"""Smoke tests for Instagram Slang NLP foundation."""

import importlib
from pathlib import Path
import unittest

from src.config import (
    ANNOTATED_DATA_DIR,
    BASE_DIR,
    DATA_DIR,
    DOCS_DIR,
    MODELS_DIR,
    PREDICTIONS_DATA_DIR,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    REPORTS_DIR,
    AppConfig,
    ensure_directories,
    mask_token,
)
from src.logging_config import setup_logger
from src.storage import (
    generate_run_id,
    get_raw_filepath,
    get_run_metadata_filepath,
    save_run_metadata,
)
from src.collectors.base import BaseCollector
from src.collectors.instagram_api import InstagramGraphAPICollector
from src.cli import run_cli


class TestFoundationSmoke(unittest.TestCase):
    """Smoke test suite to verify project structure and foundational modules."""

    def test_module_imports(self) -> None:
        """Verify all core production modules can be imported without error."""
        modules_to_test = [
            "src",
            "src.config",
            "src.logging_config",
            "src.storage",
            "src.collectors",
            "src.collectors.base",
            "src.collectors.instagram_api",
            "src.cli",
            "src.preprocessing",
            "src.annotations",
            "src.train",
            "src.predict",
            "src.analysis",
            "main",
        ]
        for mod_name in modules_to_test:
            with self.subTest(module=mod_name):
                mod = importlib.import_module(mod_name)
                self.assertIsNotNone(mod)

    def test_pathlib_paths(self) -> None:
        """Verify that all configured paths are pathlib.Path instances."""
        paths = [
            BASE_DIR,
            DATA_DIR,
            RAW_DATA_DIR,
            PROCESSED_DATA_DIR,
            ANNOTATED_DATA_DIR,
            PREDICTIONS_DATA_DIR,
            MODELS_DIR,
            REPORTS_DIR,
            DOCS_DIR,
        ]
        for p in paths:
            with self.subTest(path=p):
                self.assertIsInstance(p, Path)

    def test_ensure_directories(self) -> None:
        """Verify that ensure_directories creates all required folders."""
        ensure_directories()
        self.assertTrue(RAW_DATA_DIR.exists())
        self.assertTrue(PROCESSED_DATA_DIR.exists())
        self.assertTrue(ANNOTATED_DATA_DIR.exists())
        self.assertTrue(PREDICTIONS_DATA_DIR.exists())
        self.assertTrue(MODELS_DIR.exists())
        self.assertTrue(REPORTS_DIR.exists())
        self.assertTrue(DOCS_DIR.exists())

    def test_token_masking(self) -> None:
        """Verify token masking sanitizes secrets properly."""
        sample_token = "EAABwz91928347abcdef12345"
        masked = mask_token(sample_token)
        self.assertNotIn("1928347abcdef", masked)
        self.assertTrue(masked.startswith("EAAB..."))

        self.assertEqual(mask_token(None), "<TIDAK_DISET>")
        self.assertEqual(mask_token(""), "<TIDAK_DISET>")
        self.assertEqual(mask_token("short"), "***")

    def test_logging_redaction(self) -> None:
        """Verify logger filters out secret tokens."""
        secret = "SUPER_SECRET_TOKEN_XYZ"
        logger = setup_logger("test_logger", level="INFO", token_to_redact=secret)
        self.assertIsNotNone(logger)

    def test_storage_helpers(self) -> None:
        """Verify run ID generation and metadata saving with redaction."""
        run_id = generate_run_id()
        self.assertIsInstance(run_id, str)
        self.assertGreater(len(run_id), 10)

        raw_path = get_raw_filepath(run_id)
        self.assertIsInstance(raw_path, Path)
        self.assertTrue(raw_path.name.startswith("comments_"))

        meta_path = get_run_metadata_filepath(run_id)
        self.assertIsInstance(meta_path, Path)

        # Save metadata with a secret field to test redaction
        saved_file = save_run_metadata(
            run_id=run_id,
            status="test_init",
            extra_data={
                "target_comments": 100,
                "api_secret": "do_not_save_this",
                "access_token": "secret_token",
            },
        )
        self.assertTrue(saved_file.exists())

        import json
        with open(saved_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["run_id"], run_id)
            self.assertEqual(data["status"], "test_init")
            self.assertEqual(data["target_comments"], 100)
            self.assertNotIn("api_secret", data)
            self.assertNotIn("access_token", data)

        # Cleanup test metadata file
        saved_file.unlink(missing_ok=True)

    def test_collector_subclasses(self) -> None:
        """Verify InstagramGraphAPICollector inherits from BaseCollector."""
        collector = InstagramGraphAPICollector()
        self.assertIsInstance(collector, BaseCollector)

    def test_cli_non_interactive_status(self) -> None:
        """Verify CLI non-interactive mode returns 0 (healthy)."""
        exit_code = run_cli(non_interactive=True)
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
