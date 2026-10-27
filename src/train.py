"""Baseline model training and evaluation module for Instagram Slang NLP pipeline.

Implements TF-IDF feature extraction and One-vs-Rest Logistic Regression for
comment-level multi-label classification of:
A. slang_forms
B. language_functions

Prerequisites:
- Validated human-annotated dataset (review_status == 'selesai').
- Group split by media_id to strictly prevent data leakage between train and test.
- TF-IDF vectorizer fit ONLY on train data (never fit on test data).
- Clear, honest reporting of rare classes and absent labels in test set.
- All artifacts saved in models/ and reports/ (RAW is immutable).
- Prominent baseline disclaimer: experimental benchmark, not final research claim.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    hamming_loss,
    precision_score,
    recall_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.multiclass import OneVsRestClassifier
from sklearn.preprocessing import MultiLabelBinarizer

from src.annotations import (
    DEFAULT_ANNOTATED_PATH,
    parse_multilabel_field,
    validate_annotated_dataset,
)
from src.config import (
    LANGUAGE_FUNCTIONS,
    MODELS_DIR,
    PROCESSED_DATA_DIR,
    REPORTS_DIR,
    SLANG_FORMS,
    ensure_directories,
)
from src.storage import generate_run_id

logger = logging.getLogger("train")

BASELINE_DISCLAIMER: str = (
    "HASIL INI ADALAH BASELINE EKSPERIMEN AWAL (TF-IDF + One-vs-Rest Logistic Regression), "
    "BUKAN BUKTI PERFORMA TINGGI ATAU MODEL FINAL UNTUK KLAIM ILMIAH."
)


class BaselineTrainingError(ValueError):
    """Base exception for errors during baseline model training."""


class InsufficientDataForSplitError(BaselineTrainingError):
    """Raised when group count, sample size, or label distribution prevents a valid split."""


class AnnotationSchemaValidationError(BaselineTrainingError):
    """Raised when the annotated dataset fails schema validation or has zero completed rows."""


@dataclass
class TaskEvaluationMetrics:
    """Evaluation metrics for a multi-label classification task."""

    task_name: str
    per_class_metrics: dict[str, dict[str, Any]]
    macro_precision: float
    macro_recall: float
    macro_f1: float
    micro_precision: float
    micro_recall: float
    micro_f1: float
    hamming_loss: float
    exact_match_ratio: float
    absent_classes_test: list[str]
    absent_classes_train: list[str]


@dataclass
class BaselineTrainingReport:
    """Comprehensive report containing training metadata, split details, and metrics."""

    run_id: str
    timestamp: str
    random_seed: int
    total_samples: int
    train_samples: int
    test_samples: int
    train_groups: list[str]
    test_groups: list[str]
    slang_metrics: TaskEvaluationMetrics
    lang_metrics: TaskEvaluationMetrics
    saved_model_paths: dict[str, str]
    report_json_path: str
    report_md_path: str
    disclaimer: str = BASELINE_DISCLAIMER

    def summary_text(self) -> str:
        """Format an honest, transparent evaluation summary for terminal display."""
        lines = [
            "=" * 72,
            "               LAPORAN EVALUASI BASELINE MODEL NLP",
            "=" * 72,
            f"[PERINGATAN METODOLOGIS]:",
            f"  {self.disclaimer}",
            "-" * 72,
            f"Run ID           : {self.run_id}",
            f"Timestamp        : {self.timestamp}",
            f"Random Seed      : {self.random_seed}",
            f"Total Data Anotasi: {self.total_samples} komentar (selesai tervalidasi)",
            f"Split Train / Test: {self.train_samples} train / {self.test_samples} test",
            f"Group Train Post : {len(self.train_groups)} media_id ({', '.join(self.train_groups[:3])}{'...' if len(self.train_groups) > 3 else ''})",
            f"Group Test Post  : {len(self.test_groups)} media_id ({', '.join(self.test_groups[:3])}{'...' if len(self.test_groups) > 3 else ''})",
            "-" * 72,
            "",
            f"A. TASK BENTUK SLANG (slang_forms) - Multi-Label:",
            f"   Macro-F1: {self.slang_metrics.macro_f1:.4f} | Micro-F1: {self.slang_metrics.micro_f1:.4f} | Exact Match: {self.slang_metrics.exact_match_ratio:.4f} | Hamming Loss: {self.slang_metrics.hamming_loss:.4f}",
            f"   Rincian Per Kelas:",
            f"   {'Kelas':<15} | {'Train':<6} | {'Support':<8} | {'Precision':<9} | {'Recall':<8} | {'F1-Score':<8} | Status / Catatan",
            f"   {'-'*15}-+-{'-'*6}-+-{'-'*8}-+-{'-'*9}-+-{'-'*8}-+-{'-'*8}-+-{'-'*25}",
        ]

        for cls_name, m in self.slang_metrics.per_class_metrics.items():
            lines.append(
                f"   {cls_name:<15} | {m['train_count']:<6} | {m['test_support']:<8} | "
                f"{m['precision']:<9.4f} | {m['recall']:<8.4f} | {m['f1']:<8.4f} | {m['status']}"
            )

        if self.slang_metrics.absent_classes_test:
            lines.append(
                f"   [INFO] Label slang tidak hadir di data uji (support=0): {', '.join(self.slang_metrics.absent_classes_test)}"
            )

        lines.extend([
            "",
            f"B. TASK FUNGSI BAHASA (language_functions) - Multi-Label:",
            f"   Macro-F1: {self.lang_metrics.macro_f1:.4f} | Micro-F1: {self.lang_metrics.micro_f1:.4f} | Exact Match: {self.lang_metrics.exact_match_ratio:.4f} | Hamming Loss: {self.lang_metrics.hamming_loss:.4f}",
            f"   Rincian Per Kelas:",
            f"   {'Kelas':<15} | {'Train':<6} | {'Support':<8} | {'Precision':<9} | {'Recall':<8} | {'F1-Score':<8} | Status / Catatan",
            f"   {'-'*15}-+-{'-'*6}-+-{'-'*8}-+-{'-'*9}-+-{'-'*8}-+-{'-'*8}-+-{'-'*25}",
        ])

        for cls_name, m in self.lang_metrics.per_class_metrics.items():
            lines.append(
                f"   {cls_name:<15} | {m['train_count']:<6} | {m['test_support']:<8} | "
                f"{m['precision']:<9.4f} | {m['recall']:<8.4f} | {m['f1']:<8.4f} | {m['status']}"
            )

        if self.lang_metrics.absent_classes_test:
            lines.append(
                f"   [INFO] Label fungsi tidak hadir di data uji (support=0): {', '.join(self.lang_metrics.absent_classes_test)}"
            )

        lines.extend([
            "",
            "-" * 72,
            "Lokasi Artefak Model & Laporan:",
            f"  Model Joblib : {self.saved_model_paths.get('vectorizer', 'N/A')}",
            f"  Laporan JSON : {self.report_json_path}",
            f"  Laporan MD   : {self.report_md_path}",
            "=" * 72,
        ])
        return "\n".join(lines)

    def markdown_text(self) -> str:
        """Format detailed markdown report for persistent storage in reports/."""
        return f"""# Laporan Evaluasi Baseline Model NLP — Instagram Slang

> [!WARNING]
> **Peringatan Metodologis:**  
> {self.disclaimer}

---

## 1. Metadata Eksperimen

- **Run ID:** `{self.run_id}`
- **Waktu Pelatihan:** `{self.timestamp}`
- **Arsitektur:** `TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)` + `OneVsRestClassifier(LogisticRegression(solver='liblinear', class_weight='balanced'))`
- **Random Seed:** `{self.random_seed}`
- **Total Sampel Selesai Ditinjau:** {self.total_samples} komentar
- **Ukuran Split:** {self.train_samples} train / {self.test_samples} test
- **Strategi Pemisahan Data:** **Group Split berdasarkan `media_id`** (mencegah kebocoran komentar dari postingan yang sama)
- **Grup Postingan Train:** `{', '.join(self.train_groups)}`
- **Grup Postingan Test:** `{', '.join(self.test_groups)}`

---

## 2. Hasil Evaluasi Task A: Bentuk Slang (`slang_forms`)

- **Macro-F1:** `{self.slang_metrics.macro_f1:.4f}`
- **Micro-F1:** `{self.slang_metrics.micro_f1:.4f}`
- **Exact Match Ratio:** `{self.slang_metrics.exact_match_ratio:.4f}`
- **Hamming Loss:** `{self.slang_metrics.hamming_loss:.4f}`

| Bentuk Slang | Train Count | Test Support | Precision | Recall | F1-Score | Status / Catatan Kejujuran Metrik |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
""" + "\n".join(
            f"| `{k}` | {v['train_count']} | {v['test_support']} | {v['precision']:.4f} | {v['recall']:.4f} | {v['f1']:.4f} | {v['status']} |"
            for k, v in self.slang_metrics.per_class_metrics.items()
        ) + f"""

---

## 3. Hasil Evaluasi Task B: Fungsi Bahasa (`language_functions`)

- **Macro-F1:** `{self.lang_metrics.macro_f1:.4f}`
- **Micro-F1:** `{self.lang_metrics.micro_f1:.4f}`
- **Exact Match Ratio:** `{self.lang_metrics.exact_match_ratio:.4f}`
- **Hamming Loss:** `{self.lang_metrics.hamming_loss:.4f}`

| Fungsi Bahasa | Train Count | Test Support | Precision | Recall | F1-Score | Status / Catatan Kejujuran Metrik |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
""" + "\n".join(
            f"| `{k}` | {v['train_count']} | {v['test_support']} | {v['precision']:.4f} | {v['recall']:.4f} | {v['f1']:.4f} | {v['status']} |"
            for k, v in self.lang_metrics.per_class_metrics.items()
        ) + f"""

---

## 4. Lokasi File Artefak

- Vectorizer: `{self.saved_model_paths.get('vectorizer')}`
- Slang Classifier: `{self.saved_model_paths.get('slang_classifier')}`
- Language Classifier: `{self.saved_model_paths.get('lang_classifier')}`
- Metadata Model: `{self.saved_model_paths.get('metadata')}`
"""


def load_media_id_mapping(processed_dir: Path | None = None) -> dict[str, str]:
    """Build a mapping of comment_id -> media_id from all processed clean CSV files."""
    target_dir = Path(processed_dir or PROCESSED_DATA_DIR).resolve()
    id_to_media: dict[str, str] = {}
    if not target_dir.exists():
        return id_to_media

    for fpath in target_dir.glob("comments_clean_*.csv"):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cid = row.get("comment_id", "").strip()
                    mid = row.get("media_id", "").strip()
                    if cid and mid:
                        id_to_media[cid] = mid
        except Exception as err:
            logger.warning("Gagal membaca file processed %s: %s", fpath.name, err)

    return id_to_media


def load_and_validate_training_data(
    annotated_csv_path: Path | None = None,
    processed_dir: Path | None = None,
) -> pd.DataFrame:
    """Load human-annotated dataset, validate schema, filter completed rows, and attach media_id.

    Args:
        annotated_csv_path: Path to comments_labeled.csv.
        processed_dir: Path to directory containing processed datasets for media_id resolution.

    Returns:
        pd.DataFrame: Cleaned DataFrame of completed human annotations with columns:
                      ['comment_id', 'media_id', 'clean_text', 'slang_forms_list', 'lang_funcs_list']

    Raises:
        AnnotationSchemaValidationError: If validation report contains errors or no completed rows.
        InsufficientDataForSplitError: If media_id cannot be resolved or is missing.
    """
    target_path = Path(annotated_csv_path or DEFAULT_ANNOTATED_PATH).resolve()
    if not target_path.exists():
        raise AnnotationSchemaValidationError(
            f"File anotasi belum ditemukan di: {target_path}. "
            "Silakan buat template anotasi (Menu 3) dan lakukan anotasi manual terlebih dahulu."
        )

    # 1. Run strict schema & consistency validation
    report = validate_annotated_dataset(target_path)
    if report.errors:
        err_sample = "\n  - ".join(report.errors[:5])
        raise AnnotationSchemaValidationError(
            f"Dataset anotasi memiliki {len(report.errors)} kesalahan validasi. "
            f"Pelatihan baseline tidak dapat dijalankan sebelum data diperbaiki:\n  - {err_sample}\n"
            f"Silakan periksa dan perbaiki file anotasi lalu jalankan validasi (Menu 4)."
        )

    if report.total_completed == 0:
        raise AnnotationSchemaValidationError(
            "Tidak ditemukan anotasi manusia yang berstatus 'selesai' (review_status='selesai'). "
            "Pelatihan baseline memerlukan minimal dataset ground-truth yang telah ditinjau manusia. "
            "Buka data/annotated/comments_labeled.csv dan beri label pada komentar sebelum melatih model."
        )

    # 2. Read dataset and filter completed rows
    media_map = load_media_id_mapping(processed_dir)
    records: list[dict[str, Any]] = []

    with open(target_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            status = row.get("review_status", "").strip().lower()
            if status != "selesai":
                continue

            cid = row.get("comment_id", "").strip()
            clean_text = row.get("clean_text", "").strip()
            slang_forms_raw = row.get("slang_forms", "")
            lang_funcs_raw = row.get("language_functions", "")

            # Resolve media_id
            mid = row.get("media_id", "").strip()
            if not mid:
                mid = media_map.get(cid, "")

            slang_list = parse_multilabel_field(slang_forms_raw)
            lang_list = parse_multilabel_field(lang_funcs_raw)

            records.append({
                "comment_id": cid,
                "media_id": mid,
                "clean_text": clean_text,
                "slang_forms_list": slang_list,
                "lang_funcs_list": lang_list,
            })

    df = pd.DataFrame(records)

    # Check media_id presence
    missing_media = df[df["media_id"] == ""]
    if not missing_media.empty:
        raise InsufficientDataForSplitError(
            f"Terdapat {len(missing_media)} komentar selesai tanpa 'media_id' "
            f"(contoh comment_id: {missing_media.iloc[0]['comment_id']}). "
            "Group split memerlukan informasi postingan asal untuk mencegah kebocoran data."
        )

    return df


def perform_group_split(
    df: pd.DataFrame,
    test_size: float = 0.25,
    random_seed: int = 42,
    min_samples: int = 6,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split dataset based on media_id groups to strictly avoid data leakage.

    Args:
        df: DataFrame of completed comments containing 'clean_text' and 'media_id'.
        test_size: Fraction of groups to hold out for evaluation.
        random_seed: Reproducibility seed.
        min_samples: Minimum completed sample count required for splitting.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: (train_df, test_df)

    Raises:
        InsufficientDataForSplitError: If group count < 2 or sample count < min_samples.
    """
    total_samples = len(df)
    if total_samples < min_samples:
        raise InsufficientDataForSplitError(
            f"Jumlah data teranotasi selesai ({total_samples}) terlalu sedikit untuk evaluasi split grup. "
            f"Diperlukan minimal {min_samples} komentar selesai dari beberapa postingan media."
        )

    groups = df["media_id"].tolist()
    unique_groups = sorted(list(set(groups)))

    if len(unique_groups) < 2:
        raise InsufficientDataForSplitError(
            f"Split evaluasi berbasis grup gagal: Dataset hanya memuat {len(unique_groups)} media_id "
            f"postingan unik ('{unique_groups[0] if unique_groups else 'None'}'). "
            "Group split memerlukan minimal 2 postingan media berbeda untuk mencegah kebocoran "
            "komentar dari postingan yang sama ke train dan test set."
        )

    # Calculate integer n_groups for test if needed, or use GroupShuffleSplit
    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=random_seed)
    train_idx, test_idx = next(gss.split(df, groups=groups))

    # Guard against degenerate split where test or train is completely empty
    if len(train_idx) == 0 or len(test_idx) == 0:
        # Fallback: force test set to hold out exactly 1 group (the last unique group)
        test_group = unique_groups[-1]
        test_mask = df["media_id"] == test_group
        train_mask = ~test_mask
        train_df = df[train_mask].copy().reset_index(drop=True)
        test_df = df[test_mask].copy().reset_index(drop=True)
    else:
        train_df = df.iloc[train_idx].copy().reset_index(drop=True)
        test_df = df.iloc[test_idx].copy().reset_index(drop=True)

    # Double check strict group separation
    train_groups = set(train_df["media_id"])
    test_groups = set(test_df["media_id"])
    assert train_groups.isdisjoint(test_groups), "Data leakage: overlap found between train and test groups!"

    return train_df, test_df


def evaluate_multilabel_task(
    task_name: str,
    y_train: np.ndarray,
    y_test: np.ndarray,
    y_pred: np.ndarray,
    class_names: list[str],
) -> TaskEvaluationMetrics:
    """Compute per-class and global metrics with transparent handling of rare/absent classes."""
    per_class: dict[str, dict[str, Any]] = {}
    absent_test: list[str] = []
    absent_train: list[str] = []

    for idx, cname in enumerate(class_names):
        n_train = int(y_train[:, idx].sum())
        n_test = int(y_test[:, idx].sum())

        p = float(precision_score(y_test[:, idx], y_pred[:, idx], zero_division=0))
        r = float(recall_score(y_test[:, idx], y_pred[:, idx], zero_division=0))
        f = float(f1_score(y_test[:, idx], y_pred[:, idx], zero_division=0))

        # Honest classification status
        if n_test == 0:
            status = "Tidak hadir di test set (support=0)"
            absent_test.append(cname)
        elif n_train == 0:
            status = "Tidak hadir di train set (train=0)"
            absent_train.append(cname)
        elif n_train < 3:
            status = "Kelas langka di train set (<3)"
        else:
            status = "Cukup data"

        per_class[cname] = {
            "train_count": n_train,
            "test_support": n_test,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f, 4),
            "status": status,
        }

    macro_p = float(precision_score(y_test, y_pred, average="macro", zero_division=0))
    macro_r = float(recall_score(y_test, y_pred, average="macro", zero_division=0))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))

    micro_p = float(precision_score(y_test, y_pred, average="micro", zero_division=0))
    micro_r = float(recall_score(y_test, y_pred, average="micro", zero_division=0))
    micro_f1 = float(f1_score(y_test, y_pred, average="micro", zero_division=0))

    h_loss = float(hamming_loss(y_test, y_pred))
    exact_match = float(accuracy_score(y_test, y_pred))

    return TaskEvaluationMetrics(
        task_name=task_name,
        per_class_metrics=per_class,
        macro_precision=round(macro_p, 4),
        macro_recall=round(macro_r, 4),
        macro_f1=round(macro_f1, 4),
        micro_precision=round(micro_p, 4),
        micro_recall=round(micro_r, 4),
        micro_f1=round(micro_f1, 4),
        hamming_loss=round(h_loss, 4),
        exact_match_ratio=round(exact_match, 4),
        absent_classes_test=absent_test,
        absent_classes_train=absent_train,
    )


def train_baseline_models(
    annotated_csv_path: Path | None = None,
    output_models_dir: Path | None = None,
    output_reports_dir: Path | None = None,
    processed_dir: Path | None = None,
    random_seed: int = 42,
    test_size: float = 0.25,
) -> BaselineTrainingReport:
    """Train baseline TF-IDF + One-vs-Rest Logistic Regression models.

    Workflow:
    1. Validate human-annotated dataset (rejects if errors or no completed annotations).
    2. Attach media_id and perform Group Split (rejects if <2 groups or insufficient data).
    3. Fit TfidfVectorizer ONLY on train data (never fit on test data).
    4. Fit separate multi-label classifiers for slang_forms and language_functions.
    5. Evaluate multi-label predictions with transparent metrics and rare class reporting.
    6. Save models to models/ and reports to reports/ (RAW immutable).

    Args:
        annotated_csv_path: Path to comments_labeled.csv.
        output_models_dir: Directory to save serialized models (models/).
        output_reports_dir: Directory to save evaluation reports (reports/).
        processed_dir: Directory to look up media_id if not present in annotated CSV.
        random_seed: Random state seed.
        test_size: Fraction of groups to hold out.

    Returns:
        BaselineTrainingReport: Detailed results, metrics, and artifact locations.
    """
    ensure_directories()
    models_dir = Path(output_models_dir or MODELS_DIR).resolve()
    reports_dir = Path(output_reports_dir or REPORTS_DIR).resolve()
    models_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    run_id = generate_run_id()
    timestamp_iso = datetime.now(timezone.utc).isoformat()

    # Step 1: Load and validate completed data
    df = load_and_validate_training_data(
        annotated_csv_path=annotated_csv_path,
        processed_dir=processed_dir,
    )

    # Step 2: Group Split strictly by media_id
    train_df, test_df = perform_group_split(
        df=df,
        test_size=test_size,
        random_seed=random_seed,
    )

    # Step 3: Feature Extraction (TF-IDF Vectorizer) - FIT ONLY ON TRAIN DATA!
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        max_features=10000,
        sublinear_tf=True,
    )
    X_train_vec = vectorizer.fit_transform(train_df["clean_text"])
    X_test_vec = vectorizer.transform(test_df["clean_text"])  # TRANSFORM ONLY, NEVER FIT ON TEST

    # Step 4: MultiLabel Binarization for Task A & Task B
    slang_classes = list(SLANG_FORMS)
    lang_classes = list(LANGUAGE_FUNCTIONS)

    mlb_slang = MultiLabelBinarizer(classes=slang_classes)
    mlb_slang.fit([])  # Predefined taxonomy classes
    y_train_slang = mlb_slang.transform(train_df["slang_forms_list"])
    y_test_slang = mlb_slang.transform(test_df["slang_forms_list"])

    mlb_lang = MultiLabelBinarizer(classes=lang_classes)
    mlb_lang.fit([])  # Predefined taxonomy classes
    y_train_lang = mlb_lang.transform(train_df["lang_funcs_list"])
    y_test_lang = mlb_lang.transform(test_df["lang_funcs_list"])

    # Step 5: Fit One-vs-Rest Logistic Regression Classifiers
    slang_clf = OneVsRestClassifier(
        LogisticRegression(
            solver="liblinear",
            class_weight="balanced",
            random_state=random_seed,
            max_iter=300,
        )
    )
    slang_clf.fit(X_train_vec, y_train_slang)

    lang_clf = OneVsRestClassifier(
        LogisticRegression(
            solver="liblinear",
            class_weight="balanced",
            random_state=random_seed,
            max_iter=300,
        )
    )
    lang_clf.fit(X_train_vec, y_train_lang)

    # Step 6: Multi-label Prediction on Holdout Test Set
    y_pred_slang = slang_clf.predict(X_test_vec)
    y_pred_lang = lang_clf.predict(X_test_vec)

    # Step 7: Metrics Computation
    slang_metrics = evaluate_multilabel_task(
        task_name="slang_forms",
        y_train=y_train_slang,
        y_test=y_test_slang,
        y_pred=y_pred_slang,
        class_names=slang_classes,
    )

    lang_metrics = evaluate_multilabel_task(
        task_name="language_functions",
        y_train=y_train_lang,
        y_test=y_test_lang,
        y_pred=y_pred_lang,
        class_names=lang_classes,
    )

    # Step 8: Save Model Artifacts
    vec_path = models_dir / "baseline_vectorizer.joblib"
    slang_path = models_dir / "baseline_slang_classifier.joblib"
    lang_path = models_dir / "baseline_lang_classifier.joblib"
    slang_mlb_path = models_dir / "baseline_slang_mlb.joblib"
    lang_mlb_path = models_dir / "baseline_lang_mlb.joblib"
    meta_path = models_dir / "baseline_metadata.json"

    joblib.dump(vectorizer, vec_path)
    joblib.dump(slang_clf, slang_path)
    joblib.dump(lang_clf, lang_path)
    joblib.dump(mlb_slang, slang_mlb_path)
    joblib.dump(mlb_lang, lang_mlb_path)

    metadata_payload = {
        "run_id": run_id,
        "trained_at": timestamp_iso,
        "random_seed": random_seed,
        "architecture": {
            "feature_extractor": "TfidfVectorizer(ngram_range=(1,2), sublinear_tf=True)",
            "classifier": "OneVsRestClassifier(LogisticRegression(solver='liblinear', class_weight='balanced'))",
        },
        "taxonomy": {
            "slang_forms": slang_classes,
            "language_functions": lang_classes,
        },
        "dataset_split": {
            "total_samples": len(df),
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "train_groups": sorted(list(set(train_df["media_id"]))),
            "test_groups": sorted(list(set(test_df["media_id"]))),
        },
        "disclaimer": BASELINE_DISCLAIMER,
    }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata_payload, f, indent=2, ensure_ascii=False)

    saved_models = {
        "vectorizer": str(vec_path),
        "slang_classifier": str(slang_path),
        "lang_classifier": str(lang_path),
        "slang_mlb": str(slang_mlb_path),
        "lang_mlb": str(lang_mlb_path),
        "metadata": str(meta_path),
    }

    # Step 9: Save Evaluation Reports (JSON and Markdown)
    report_json_path = reports_dir / f"baseline_evaluation_{run_id}.json"
    report_md_path = reports_dir / f"baseline_evaluation_{run_id}.md"

    report = BaselineTrainingReport(
        run_id=run_id,
        timestamp=timestamp_iso,
        random_seed=random_seed,
        total_samples=len(df),
        train_samples=len(train_df),
        test_samples=len(test_df),
        train_groups=sorted(list(set(train_df["media_id"]))),
        test_groups=sorted(list(set(test_df["media_id"]))),
        slang_metrics=slang_metrics,
        lang_metrics=lang_metrics,
        saved_model_paths=saved_models,
        report_json_path=str(report_json_path),
        report_md_path=str(report_md_path),
    )

    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(asdict(report), f, indent=2, ensure_ascii=False)

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(report.markdown_text())

    return report


def predict_single_comment(
    clean_text: str,
    vectorizer: TfidfVectorizer,
    slang_clf: OneVsRestClassifier,
    lang_clf: OneVsRestClassifier,
    slang_mlb: MultiLabelBinarizer,
    lang_mlb: MultiLabelBinarizer,
) -> dict[str, list[str]]:
    """Predict multi-label slang forms and language functions for a single cleaned comment text."""
    X_vec = vectorizer.transform([clean_text])
    pred_slang_raw = slang_clf.predict(X_vec)
    pred_lang_raw = lang_clf.predict(X_vec)

    slang_labels = list(slang_mlb.inverse_transform(pred_slang_raw)[0])
    lang_labels = list(lang_mlb.inverse_transform(pred_lang_raw)[0])

    return {
        "slang_forms": slang_labels,
        "language_functions": lang_labels,
    }
