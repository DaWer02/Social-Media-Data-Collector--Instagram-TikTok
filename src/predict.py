"""Inference module for predicting slang forms and language functions on processed comments.

Loads trained baseline artifacts (TF-IDF vectorizer + OneVsRest Logistic Regression),
generates multi-label predictions for slang_forms and language_functions, calculates
transparent uncalibrated heuristic confidence scores, flags ambiguous/low-confidence
cases for human review (needs_review), and writes structured outputs to data/predictions/.

Strict Commitments:
- Never overwrite RAW or annotated human datasets.
- No false or fabricated span extraction (span extraction requires token-level NER).
- Clear reporting of uncalibrated confidence interpretation.
- Graceful refusal if model artifacts are missing or incompatible.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from src.config import (
    LANGUAGE_FUNCTIONS,
    MODELS_DIR,
    PREDICTIONS_DATA_DIR,
    PROCESSED_DATA_DIR,
    SLANG_FORMS,
    ensure_directories,
)
from src.storage import generate_run_id

logger = logging.getLogger("predict")

DEFAULT_REVIEW_THRESHOLD: float = 0.60

PREDICTIONS_FIELDNAMES: list[str] = [
    "comment_id",
    "media_id",
    "comment_text",
    "clean_text",
    "predicted_slang_forms",
    "predicted_language_functions",
    "slang_forms_confidence",
    "language_functions_confidence",
    "needs_review",
    "model_version",
]


class PredictionError(ValueError):
    """Base exception for errors during dataset prediction."""


class ModelNotFoundError(PredictionError):
    """Raised when required model artifacts cannot be found in models/."""


class ModelCompatibilityError(PredictionError):
    """Raised when saved model metadata or taxonomy does not match current pipeline."""


class EmptyInputDatasetError(PredictionError):
    """Raised when input processed CSV contains zero comments."""


@dataclass
class PredictionResult:
    """Summary of batch prediction execution."""

    run_id: str
    input_csv_path: Path
    output_csv_path: Path
    total_predicted: int
    total_needs_review: int
    review_threshold: float
    model_version: str
    sample_predictions: list[dict[str, Any]]

    def summary_text(self) -> str:
        """Format prediction results for terminal display."""
        review_pct = (
            (self.total_needs_review / self.total_predicted * 100)
            if self.total_predicted > 0
            else 0.0
        )
        lines = [
            "=" * 72,
            "               RINGKASAN PREDIKSI DATASET KOMENTAR",
            "=" * 72,
            f"Run ID                : {self.run_id}",
            f"Model Version         : {self.model_version}",
            f"File Input Processed  : {self.input_csv_path.name}",
            f"Total Diprediksi      : {self.total_predicted} komentar",
            f"Perlu Review Manusia  : {self.total_needs_review} komentar ({review_pct:.1f}%)",
            f"Review Threshold      : {self.review_threshold:.2f}",
            f"Lokasi File Output    : {self.output_csv_path}",
            "-" * 72,
            "[DOKUMENTASI CONFIDENCE SCORE]:",
            "  Skor keyakinan (confidence) dihitung dari fungsi sigmoid uncalibrated linear",
            "  decision score [0.0 - 1.0]. Skor ini adalah ukuran jarak batas keputusan,",
            "  BUKAN probabilitas terkalibrasi. Prediksi dengan confidence < threshold atau",
            "  hasil multi-label kosong/ambigu otomatis ditandai 'needs_review=True'.",
            "-" * 72,
            "Contoh Hasil Prediksi (3-5 baris pertama):",
        ]

        for idx, item in enumerate(self.sample_predictions[:5], start=1):
            text_preview = item["clean_text"]
            if len(text_preview) > 40:
                text_preview = text_preview[:37] + "..."
            review_flag = "YA [!]" if item["needs_review"] else "TIDAK"
            lines.extend([
                f"  [{idx}] Teks      : \"{text_preview}\"",
                f"      Slang     : {item['predicted_slang_forms'] or '(kosong)'} (conf: {item['slang_forms_confidence']:.2f})",
                f"      Fungsi    : {item['predicted_language_functions'] or '(kosong)'} (conf: {item['language_functions_confidence']:.2f})",
                f"      Review?   : {review_flag}",
            ])

        lines.append("=" * 72)
        return "\n".join(lines)


def load_inference_artifacts(models_dir: Path | None = None) -> dict[str, Any]:
    """Load and validate trained baseline model artifacts from models/ directory.

    Args:
        models_dir: Optional path to models/ directory (defaults to config.MODELS_DIR).

    Returns:
        dict[str, Any]: Dictionary containing loaded vectorizer, classifiers, MLBs, and metadata.

    Raises:
        ModelNotFoundError: If any of the required joblib or json files are missing.
        ModelCompatibilityError: If metadata taxonomy mismatches current pipeline.
    """
    target_dir = Path(models_dir or MODELS_DIR).resolve()

    required_files = {
        "vectorizer": target_dir / "baseline_vectorizer.joblib",
        "slang_classifier": target_dir / "baseline_slang_classifier.joblib",
        "lang_classifier": target_dir / "baseline_lang_classifier.joblib",
        "slang_mlb": target_dir / "baseline_slang_mlb.joblib",
        "lang_mlb": target_dir / "baseline_lang_mlb.joblib",
        "metadata": target_dir / "baseline_metadata.json",
    }

    missing = [name for name, path in required_files.items() if not path.exists()]
    if missing:
        missing_str = ", ".join(f"{name} ({required_files[name].name})" for name in missing)
        raise ModelNotFoundError(
            f"Artefak model baseline tidak lengkap di folder: {target_dir}.\n"
            f"File yang hilang: {missing_str}.\n"
            "Tindakan: Silakan latih model baseline terlebih dahulu melalui menu 5 "
            "setelah dataset anotasi manusia selesai divalidasi."
        )

    # Validate metadata
    try:
        with open(required_files["metadata"], "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as err:
        raise ModelCompatibilityError(f"File metadata model rusak atau tidak terbaca: {err}")

    meta_taxonomy = metadata.get("taxonomy", {})
    meta_slang = tuple(meta_taxonomy.get("slang_forms", []))
    meta_lang = tuple(meta_taxonomy.get("language_functions", []))

    if meta_slang != SLANG_FORMS or meta_lang != LANGUAGE_FUNCTIONS:
        raise ModelCompatibilityError(
            "Taksonomi pada model tersimpan berbeda dengan taksonomi konfigurasi aktif saat ini.\n"
            f"Model slang: {meta_slang} vs Konfigurasi: {SLANG_FORMS}.\n"
            "Tindakan: Latih ulang model baseline via menu 5."
        )

    # Load joblib artifacts safely
    try:
        vectorizer: TfidfVectorizer = joblib.load(required_files["vectorizer"])
        slang_clf: OneVsRestClassifier = joblib.load(required_files["slang_classifier"])
        lang_clf: OneVsRestClassifier = joblib.load(required_files["lang_classifier"])
        slang_mlb: MultiLabelBinarizer = joblib.load(required_files["slang_mlb"])
        lang_mlb: MultiLabelBinarizer = joblib.load(required_files["lang_mlb"])
    except Exception as err:
        raise ModelCompatibilityError(f"Gagal memuat artefak model joblib: {err}")

    model_version = metadata.get("run_id", "baseline_v1")

    return {
        "vectorizer": vectorizer,
        "slang_clf": slang_clf,
        "lang_clf": lang_clf,
        "slang_mlb": slang_mlb,
        "lang_mlb": lang_mlb,
        "metadata": metadata,
        "model_version": model_version,
    }


def compute_multilabel_confidence(
    decision_scores: np.ndarray,
    binary_predictions: np.ndarray,
) -> tuple[float, bool]:
    """Compute uncalibrated confidence score and identify ambiguity for multi-label prediction.

    Interpretation & Calibration Disclaimer:
    Scores are computed via the standard logistic sigmoid function sigma(z) = 1 / (1 + exp(-z)).
    These represent uncalibrated distance metrics to the decision boundary in [0.0, 1.0],
    NOT true Bayesian posterior probabilities.

    Args:
        decision_scores: 1D array of decision function outputs (logits) or probabilities per class.
        binary_predictions: 1D array of 0s and 1s indicating predicted positive classes.

    Returns:
        tuple[float, bool]: (aggregated_confidence_score, is_ambiguous)
    """
    # If decision_scores are raw margins (logits), convert to [0.0, 1.0] via sigmoid
    if np.any(decision_scores < 0.0) or np.any(decision_scores > 1.0):
        sigmoid_scores = 1.0 / (1.0 + np.exp(-np.clip(decision_scores, -15.0, 15.0)))
    else:
        sigmoid_scores = decision_scores

    active_indices = np.where(binary_predictions == 1)[0]

    if len(active_indices) > 0:
        # Multi-label predicted: confidence is the average score of the active predicted classes
        conf = float(np.mean(sigmoid_scores[active_indices]))
        is_ambiguous = False
    else:
        # Zero classes predicted (all classes fell below boundary 0.5): ambiguous!
        # Confidence is the highest score across all inactive classes
        conf = float(np.max(sigmoid_scores)) if len(sigmoid_scores) > 0 else 0.0
        is_ambiguous = True

    return round(conf, 4), is_ambiguous


def predict_processed_dataset(
    processed_csv_path: Path,
    output_predictions_path: Path | None = None,
    models_dir: Path | None = None,
    review_threshold: float = DEFAULT_REVIEW_THRESHOLD,
) -> PredictionResult:
    """Run model inference on preprocessed comments dataset.

    Args:
        processed_csv_path: Path to clean comments CSV in data/processed/.
        output_predictions_path: Optional custom destination path in data/predictions/.
        models_dir: Optional custom models directory.
        review_threshold: Score threshold below which predictions are flagged needs_review=True.

    Returns:
        PredictionResult: Execution summary and sample records.

    Raises:
        FileNotFoundError: If processed_csv_path does not exist.
        EmptyInputDatasetError: If processed CSV has no comments.
        ModelNotFoundError: If model artifacts are missing.
        ModelCompatibilityError: If model metadata/version is invalid.
    """
    processed_csv_path = Path(processed_csv_path).resolve()
    if not processed_csv_path.exists():
        raise FileNotFoundError(f"File processed tidak ditemukan di: {processed_csv_path}")

    ensure_directories()
    run_id = generate_run_id()

    # Load artifacts first
    artifacts = load_inference_artifacts(models_dir)
    vectorizer: TfidfVectorizer = artifacts["vectorizer"]
    slang_clf: OneVsRestClassifier = artifacts["slang_clf"]
    lang_clf: OneVsRestClassifier = artifacts["lang_clf"]
    slang_mlb: MultiLabelBinarizer = artifacts["slang_mlb"]
    lang_mlb: MultiLabelBinarizer = artifacts["lang_mlb"]
    model_version: str = artifacts["model_version"]

    # Read processed comments
    rows_in: list[dict[str, str]] = []
    with open(processed_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row.get("comment_id", "").strip()
            clean_text = row.get("clean_text", "").strip()
            if cid:  # Retain all comments that have an ID
                rows_in.append(row)

    if not rows_in:
        raise EmptyInputDatasetError(
            f"File input '{processed_csv_path.name}' kosong atau tidak memiliki baris komentar yang valid."
        )

    # Extract clean text for inference
    texts = [row.get("clean_text", "").strip() for row in rows_in]
    X_vec = vectorizer.transform(texts)

    # 1. Slang Forms Predictions
    y_pred_slang = slang_clf.predict(X_vec)
    try:
        # Decision function margins or probabilities
        slang_margins = slang_clf.decision_function(X_vec)
    except AttributeError:
        slang_margins = slang_clf.predict_proba(X_vec)

    # 2. Language Functions Predictions
    y_pred_lang = lang_clf.predict(X_vec)
    try:
        lang_margins = lang_clf.decision_function(X_vec)
    except AttributeError:
        lang_margins = lang_clf.predict_proba(X_vec)

    # Decode multi-labels
    slang_labels_list = [list(lbls) for lbls in slang_mlb.inverse_transform(y_pred_slang)]
    lang_labels_list = [list(lbls) for lbls in lang_mlb.inverse_transform(y_pred_lang)]

    out_records: list[dict[str, Any]] = []
    total_needs_review = 0

    for idx, row in enumerate(rows_in):
        cid = row.get("comment_id", "").strip()
        mid = row.get("media_id", "").strip()
        comment_text = row.get("comment_text", "")
        clean_text = row.get("clean_text", "")

        slang_lbls = slang_labels_list[idx]
        lang_lbls = lang_labels_list[idx]

        slang_conf, slang_ambiguous = compute_multilabel_confidence(
            decision_scores=slang_margins[idx],
            binary_predictions=y_pred_slang[idx],
        )

        lang_conf, lang_ambiguous = compute_multilabel_confidence(
            decision_scores=lang_margins[idx],
            binary_predictions=y_pred_lang[idx],
        )

        # Flag for human review if confidence is low, prediction is empty, or contradictory
        is_low_conf = (slang_conf < review_threshold) or (lang_conf < review_threshold)
        is_empty = (len(slang_lbls) == 0) or (len(lang_lbls) == 0)
        is_contradictory = ("tidak_ada" in slang_lbls and len(slang_lbls) > 1)

        needs_review = is_low_conf or is_empty or is_contradictory or slang_ambiguous or lang_ambiguous
        if needs_review:
            total_needs_review += 1

        record = {
            "comment_id": cid,
            "media_id": mid,
            "comment_text": comment_text,
            "clean_text": clean_text,
            "predicted_slang_forms": ";".join(slang_lbls),
            "predicted_language_functions": ";".join(lang_lbls),
            "slang_forms_confidence": slang_conf,
            "language_functions_confidence": lang_conf,
            "needs_review": needs_review,
            "model_version": model_version,
        }
        out_records.append(record)

    # Determine destination filepath
    if output_predictions_path:
        out_filepath = Path(output_predictions_path).resolve()
    else:
        out_filepath = PREDICTIONS_DATA_DIR / f"comments_predictions_{run_id}.csv"

    out_filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(out_filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PREDICTIONS_FIELDNAMES)
        writer.writeheader()
        writer.writerows(out_records)

    return PredictionResult(
        run_id=run_id,
        input_csv_path=processed_csv_path,
        output_csv_path=out_filepath,
        total_predicted=len(out_records),
        total_needs_review=total_needs_review,
        review_threshold=review_threshold,
        model_version=model_version,
        sample_predictions=out_records[:5],
    )
