"""Unit and integration tests for Indonesian Pretrained Language Model (IndoBERT) Experiment Pipeline.

Tests dependency checks, hardware detection, 3-way GroupSplit zero-leakage validation,
metric calculations, demo dataset generation, and mock-based end-to-end execution.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from src.annotations import ANNOTATED_FIELDNAMES, validate_annotated_dataset
from src.config import LANGUAGE_FUNCTIONS, SLANG_FORMS
from src.experiments.indobert_experiment import (
    DEFAULT_PRETRAINED_MODEL,
    InsufficientGroupsForThreeWaySplitError,
    MissingDeepLearningDependenciesError,
    calculate_multilabel_scores,
    check_dl_dependencies,
    create_label_indicator_matrix,
    get_hardware_footprint,
    run_indobert_experiment,
    split_train_val_test_by_group,
)
from src.experiments.synthetic_demo import create_demo_multipost_dataset


class TestIndoBERTExperimentPipeline(unittest.TestCase):
    """Test suite for IndoBERT fine-tuning and baseline comparison experiment."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # -------------------------------------------------------------------------
    # 1. Dependency and Environment Checks
    # -------------------------------------------------------------------------
    def test_check_dl_dependencies_returns_tuple_and_instructions(self) -> None:
        """Verify check_dl_dependencies returns status and actionable instructions."""
        is_ready, msg = check_dl_dependencies()
        self.assertIsInstance(is_ready, bool)
        self.assertIsInstance(msg, str)
        if not is_ready:
            self.assertIn("pip install torch", msg)
            self.assertIn("transformers", msg)
            self.assertIn("cu121", msg)

    def test_get_hardware_footprint(self) -> None:
        """Verify hardware detection returns dictionary with required footprint keys."""
        hw = get_hardware_footprint()
        self.assertIn("cuda_available", hw)
        self.assertIn("device_name", hw)
        self.assertIn("vram_total_mb", hw)
        self.assertIn("vram_allocated_mb", hw)

    # -------------------------------------------------------------------------
    # 2. Demo Dataset Generation & Validation
    # -------------------------------------------------------------------------
    def test_create_demo_multipost_dataset(self) -> None:
        """Verify demo dataset generation creates a valid, compliant multi-post dataset."""
        dest_csv = self.test_dir / "demo_test.csv"
        out_path = create_demo_multipost_dataset(output_path=dest_csv)
        self.assertTrue(out_path.exists())

        # Validate with existing validator
        report = validate_annotated_dataset(out_path)
        self.assertTrue(report.is_valid_for_training)
        self.assertEqual(len(report.errors), 0)
        self.assertGreaterEqual(report.total_completed, 25)

        # Verify multiple media_id presence
        df = pd.read_csv(out_path)
        unique_posts = df["media_id"].unique()
        self.assertGreaterEqual(len(unique_posts), 4)

    # -------------------------------------------------------------------------
    # 3. 3-Way GroupSplit Zero-Leakage Partitioning
    # -------------------------------------------------------------------------
    def test_split_train_val_test_by_group_zero_leakage(self) -> None:
        """Verify Train, Val, and Test partitions have completely disjoint media_id sets."""
        df = pd.DataFrame({
            "comment_id": [f"c{i}" for i in range(12)],
            "media_id": ["m1", "m1", "m2", "m2", "m3", "m3", "m4", "m4", "m5", "m5", "m6", "m6"],
            "clean_text": [f"teks {i}" for i in range(12)],
        })

        train_df, val_df, test_df, tr_g, val_g, ts_g = split_train_val_test_by_group(
            df=df,
            group_col="media_id",
            val_ratio=0.20,
            test_ratio=0.20,
            random_seed=42,
        )

        tr_set = set(tr_g)
        val_set = set(val_g)
        ts_set = set(ts_g)

        # Zero leakage assertions
        self.assertTrue(tr_set.isdisjoint(val_set))
        self.assertTrue(tr_set.isdisjoint(ts_set))
        self.assertTrue(val_set.isdisjoint(ts_set))
        self.assertEqual(tr_set | val_set | ts_set, set(df["media_id"].unique()))

        # Rows match groups strictly
        self.assertTrue(all(m in tr_set for m in train_df["media_id"]))
        self.assertTrue(all(m in val_set for m in val_df["media_id"]))
        self.assertTrue(all(m in ts_set for m in test_df["media_id"]))

    def test_split_train_val_test_by_group_insufficient_groups(self) -> None:
        """Verify InsufficientGroupsForThreeWaySplitError is raised when media_id < 3."""
        df = pd.DataFrame({
            "comment_id": ["c1", "c2", "c3", "c4"],
            "media_id": ["post_A", "post_A", "post_B", "post_B"],
            "clean_text": ["a", "b", "c", "d"],
        })
        with self.assertRaises(InsufficientGroupsForThreeWaySplitError):
            split_train_val_test_by_group(df, group_col="media_id")

    # -------------------------------------------------------------------------
    # 4. Multi-Label Metric Calculation
    # -------------------------------------------------------------------------
    def test_calculate_multilabel_scores(self) -> None:
        """Verify exact precision, recall, and F1 calculations for multi-label targets."""
        classes = ["singkatan", "akronim"]
        y_true = np.array([
            [1, 0],
            [1, 1],
            [0, 1],
            [0, 0],
        ])
        y_pred = np.array([
            [1, 0],
            [1, 0],
            [0, 1],
            [0, 0],
        ])

        scores = calculate_multilabel_scores(y_true, y_pred, classes)

        # singkatan: TP=2, FP=0, FN=0 -> P=1.0, R=1.0, F1=1.0
        self.assertEqual(scores["per_class"]["singkatan"]["precision"], 1.0)
        self.assertEqual(scores["per_class"]["singkatan"]["recall"], 1.0)
        self.assertEqual(scores["per_class"]["singkatan"]["f1"], 1.0)

        # akronim: TP=1, FP=0, FN=1 -> P=1.0, R=0.5, F1=0.6667
        self.assertEqual(scores["per_class"]["akronim"]["precision"], 1.0)
        self.assertEqual(scores["per_class"]["akronim"]["recall"], 0.5)
        self.assertAlmostEqual(scores["per_class"]["akronim"]["f1"], 0.6667, places=3)

        self.assertGreater(scores["macro_f1"], 0.0)
        self.assertGreater(scores["micro_f1"], 0.0)

    def test_create_label_indicator_matrix(self) -> None:
        """Verify conversion from label list to binary matrix."""
        labels = [["singkatan"], ["akronim", "singkatan"], ["tidak_ada"]]
        classes = ["singkatan", "akronim", "tidak_ada"]
        mat = create_label_indicator_matrix(labels, classes)
        expected = np.array([
            [1, 0, 0],
            [1, 1, 0],
            [0, 0, 1],
        ])
        np.testing.assert_array_equal(mat, expected)

    # -------------------------------------------------------------------------
    # 5. Missing Deep Learning Dependencies Graceful Exit
    # -------------------------------------------------------------------------
    def test_run_indobert_experiment_raises_missing_dependencies(self) -> None:
        """Verify experiment raises MissingDeepLearningDependenciesError when torch is absent."""
        with patch("src.experiments.indobert_experiment.check_dl_dependencies") as mock_check:
            mock_check.return_value = (False, "Paket torch dan transformers belum terpasang.")
            with self.assertRaises(MissingDeepLearningDependenciesError):
                run_indobert_experiment(annotated_csv_path="dummy.csv")

    # -------------------------------------------------------------------------
    # 6. End-to-End Experiment Pipeline with Mocked Transformer
    # -------------------------------------------------------------------------
    def test_run_indobert_experiment_with_mocked_transformer(self) -> None:
        """Verify end-to-end experiment execution, report generation, and non-destruction of baseline."""
        demo_csv = self.test_dir / "comments_demo.csv"
        create_demo_multipost_dataset(output_path=demo_csv)

        out_reports_dir = self.test_dir / "reports"

        # Mock deep learning dependencies check
        with patch("src.experiments.indobert_experiment.check_dl_dependencies", return_value=(True, "Ready")):
            with patch("src.experiments.indobert_experiment.TORCH_AVAILABLE", True):
                with patch("src.experiments.indobert_experiment.TRANSFORMERS_AVAILABLE", True):
                    # Mock torch & transformers
                    mock_torch = MagicMock()
                    mock_torch.cuda.is_available.return_value = False
                    mock_torch.device.return_value = "cpu"

                    mock_tokenizer = MagicMock()
                    mock_tokenizer.return_value = {
                        "input_ids": MagicMock(squeeze=lambda _: MagicMock()),
                        "attention_mask": MagicMock(squeeze=lambda _: MagicMock()),
                    }

                    mock_slang_logits = MagicMock()
                    mock_lang_logits = MagicMock()
                    mock_model = MagicMock()
                    mock_model.to.return_value = mock_model
                    mock_model.return_value = (mock_slang_logits, mock_lang_logits)
                    mock_model.state_dict.return_value = {"weight": MagicMock(cpu=lambda: MagicMock(clone=lambda: 1))}

                    # Prepare matching array shapes
                    slang_arr = np.zeros((6, len(SLANG_FORMS)), dtype=int)
                    lang_arr = np.zeros((6, len(LANGUAGE_FUNCTIONS)), dtype=int)

                    mock_slang_res = MagicMock()
                    mock_slang_res.__gt__ = lambda s, o: MagicMock(cpu=lambda: MagicMock(numpy=lambda: slang_arr))

                    mock_lang_res = MagicMock()
                    mock_lang_res.__gt__ = lambda s, o: MagicMock(cpu=lambda: MagicMock(numpy=lambda: lang_arr))

                    def fake_sigmoid(x):
                        if x is mock_slang_logits:
                            return mock_slang_res
                        return mock_lang_res

                    mock_torch.sigmoid.side_effect = fake_sigmoid

                    with patch("src.experiments.indobert_experiment.torch", mock_torch):
                        with patch("src.experiments.indobert_experiment.AutoTokenizer") as mock_tok_cls:
                            mock_tok_cls.from_pretrained.return_value = mock_tokenizer
                            with patch("src.experiments.indobert_experiment.IndoBERTMultiLabelClassifier") as mock_model_cls:
                                mock_model_cls.return_value = mock_model
                                with patch("src.experiments.indobert_experiment.DataLoader") as mock_loader_cls:
                                    mock_batch = {
                                        "input_ids": MagicMock(to=lambda _: MagicMock()),
                                        "attention_mask": MagicMock(to=lambda _: MagicMock()),
                                        "slang_labels": MagicMock(to=lambda _: MagicMock()),
                                        "lang_labels": MagicMock(to=lambda _: MagicMock()),
                                    }
                                    mock_loader = MagicMock()
                                    mock_loader.__iter__.return_value = [mock_batch]
                                    mock_loader.__len__.return_value = 1
                                    mock_loader_cls.return_value = mock_loader

                                    # Run experiment
                                    report = run_indobert_experiment(
                                        annotated_csv_path=demo_csv,
                                        pretrained_model_name="indobenchmark/indobert-base-p1",
                                        epochs=1,
                                        batch_size=8,
                                        output_dir=out_reports_dir,
                                    )

                                    self.assertIsNotNone(report)
                                    self.assertEqual(report.pretrained_model_name, "indobenchmark/indobert-base-p1")
                                    self.assertTrue(Path(report.json_path).exists())
                                    self.assertTrue(Path(report.csv_path).exists())
                                    self.assertTrue(Path(report.markdown_path).exists())

                                    # Verify markdown format
                                    with open(report.markdown_path, "r", encoding="utf-8") as f:
                                        md_content = f.read()
                                    self.assertIn("Laporan Komparasi: Baseline (TF-IDF) vs IndoBERT", md_content)
                                    self.assertIn("Bentuk Slang", md_content)
                                    self.assertIn("Fungsi Bahasa", md_content)
                                    self.assertIn("CATATAN EVALUASI & VALIDITAS ILMIAH", md_content)


if __name__ == "__main__":
    unittest.main()
