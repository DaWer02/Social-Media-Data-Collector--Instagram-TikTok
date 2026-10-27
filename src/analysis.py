"""Dataset analysis and reporting module for Instagram Slang NLP pipeline.

Generates comprehensive statistical reports comparing human ground-truth annotations
and model predictions across:
1. Pipeline data volumes (RAW, Processed, Annotated, Predictions).
2. Human annotation completion status and slang presence.
3. Multi-label frequency distributions for slang_forms and language_functions,
   strictly distinguishing document frequency (unique comments) vs label occurrences.
4. Media post distributions and data quality issues (duplicates, empty text, invalid labels).
5. Model evaluation metrics (Macro/Micro F1, Precision, Recall, Support).
6. Qualitative error analysis from holdout test set with PII sanitization.
7. Data limitations and rare class caveats.

Artifacts saved:
- CSV tables in reports/
- Markdown comprehensive report in reports/
- Headless bar chart visualizations in reports/ (PNG, no GUI/dashboard)
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.annotations import (
    DEFAULT_ANNOTATED_PATH,
    parse_multilabel_field,
    validate_annotated_dataset,
)
from src.config import (
    ANNOTATED_DATA_DIR,
    LANGUAGE_FUNCTIONS,
    PREDICTIONS_DATA_DIR,
    PROCESSED_DATA_DIR,
    RAW_DATA_DIR,
    REPORTS_DIR,
    SLANG_FORMS,
    ensure_directories,
)
from src.storage import generate_run_id

logger = logging.getLogger("analysis")

# Explicit methodological disclaimer for multi-label statistics
MULTILABEL_DISTINCTION_NOTE: str = (
    "CATATAN METODOLOGI MULTI-LABEL:\n"
    "- 'komentar_unik_count': Jumlah komentar unik yang memuat kategori ini (Document Frequency).\n"
    "  Persentase dihitung terhadap total komentar unik teranotasi (bisa melebihi 100% jika dijumlah).\n"
    "- 'total_kemunculan_label': Jumlah kemunculan label dalam keseluruhan korpus multi-label.\n"
    "  Persentase dihitung terhadap total seluruh label yang terpasang (pasti berjumlah 100%)."
)


def sanitize_comment_text(text: str) -> str:
    """Sanitize PII (emails, phone numbers, usernames) from text for error analysis reporting."""
    if not text:
        return ""
    # 1. Replace email addresses first (prevents @domain being captured as a mention)
    text = re.sub(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}", "[EMAIL]", text)
    # 2. Replace phone numbers (e.g. +62812..., 0812...)
    text = re.sub(r"(?:\+?62|08)[0-9\-\s]{8,14}", "[PHONE]", text)
    # 3. Replace @username mentions
    text = re.sub(r"@[A-Za-z0-9_.]+", "[@USER]", text)
    return text.strip()


def compute_multilabel_distribution(
    labels_list: list[list[str]],
    predefined_categories: tuple[str, ...] | list[str],
    total_comments: int,
) -> list[dict[str, Any]]:
    """Compute multi-label frequency distinguishing unique comments vs total label tokens.

    Args:
        labels_list: List of parsed label lists per comment (e.g. [['singkatan', 'plesetan'], ...]).
        predefined_categories: Official taxonomy categories in desired sort order.
        total_comments: Total number of valid comments evaluated.

    Returns:
        list[dict[str, Any]]: Distribution table with unique comment count/pct and label token count/pct.
    """
    total_label_tokens = sum(len(lbls) for lbls in labels_list)
    doc_freq: dict[str, int] = {cat: 0 for cat in predefined_categories}
    token_freq: dict[str, int] = {cat: 0 for cat in predefined_categories}

    for lbls in labels_list:
        seen_in_doc: set[str] = set()
        for lbl in lbls:
            cleaned = lbl.strip().lower()
            if cleaned:
                token_freq[cleaned] = token_freq.get(cleaned, 0) + 1
                if cleaned not in seen_in_doc:
                    seen_in_doc.add(cleaned)
                    doc_freq[cleaned] = doc_freq.get(cleaned, 0) + 1

    results: list[dict[str, Any]] = []
    for cat in predefined_categories:
        d_count = doc_freq.get(cat, 0)
        t_count = token_freq.get(cat, 0)

        d_pct = (d_count / total_comments * 100.0) if total_comments > 0 else 0.0
        t_pct = (t_count / total_label_tokens * 100.0) if total_label_tokens > 0 else 0.0

        results.append({
            "kategori": cat,
            "komentar_unik_count": d_count,
            "komentar_persentase": round(d_pct, 2),
            "total_kemunculan_label": t_count,
            "proporsi_dari_seluruh_label": round(t_pct, 2),
        })

    return results


@dataclass
class DatasetAnalysisReport:
    """Consolidated statistical analysis report for pipeline volumes, human labels, and model outputs."""

    run_id: str
    timestamp: str

    # 1. Pipeline Volume Stats
    total_raw_comments: int
    total_raw_files: int
    total_processed_comments: int
    total_processed_files: int
    total_annotated_comments: int

    # 2. Human Annotation Stats
    human_completed_count: int
    human_pending_count: int
    human_invalid_count: int
    human_slang_present_count: int
    human_slang_absent_count: int
    human_slang_present_pct: float
    human_slang_absent_pct: float
    human_slang_distribution: list[dict[str, Any]]
    human_lang_distribution: list[dict[str, Any]]
    media_distribution: list[dict[str, Any]]

    # 3. Data Quality & Missingness
    missing_id_count: int
    empty_clean_text_count: int
    duplicate_id_count: int
    invalid_schema_errors: list[str]

    # 4. Model Prediction Stats (if available)
    has_model_predictions: bool
    total_predicted_comments: int
    predictions_needs_review_count: int
    predictions_needs_review_pct: float
    pred_slang_distribution: list[dict[str, Any]]
    pred_lang_distribution: list[dict[str, Any]]

    # 5. Model Evaluation & Qualitative Errors (if available)
    has_model_evaluation: bool
    model_eval_summary: dict[str, Any]
    qualitative_error_samples: list[dict[str, Any]]

    # 6. Limitations & Saved Files
    limitations: list[str]
    saved_csv_paths: dict[str, str] = field(default_factory=dict)
    saved_plot_paths: dict[str, str] = field(default_factory=dict)
    report_md_path: str = ""

    def summary_text(self) -> str:
        """Render a readable, formatted text summary for terminal display."""
        lines = [
            "=" * 74,
            "               RINGKASAN ANALISIS DATASET & LAPORAN NLP",
            "=" * 74,
            f"Run ID    : {self.run_id}",
            f"Waktu     : {self.timestamp}",
            "-" * 74,
            "",
            "1. VOLUME DATA PIPELINE:",
            f"   - Komentar RAW          : {self.total_raw_comments} (dari {self.total_raw_files} file)",
            f"   - Komentar Processed    : {self.total_processed_comments} (dari {self.total_processed_files} file)",
            f"   - Komentar Annotated    : {self.total_annotated_comments} total",
            f"     * Selesai Ditinjau    : {self.human_completed_count}",
            f"     * Belum Ditinjau      : {self.human_pending_count}",
            f"     * Bermasalah / Invalid: {self.human_invalid_count}",
            "",
            "2. ANALISIS LABEL GROUND-TRUTH MANUSIA (Review Status = 'selesai'):",
            f"   - Komentar Berslang (ya)   : {self.human_slang_present_count} ({self.human_slang_present_pct:.1f}%)",
            f"   - Tanpa Slang (tidak)      : {self.human_slang_absent_count} ({self.human_slang_absent_pct:.1f}%)",
            "",
            "   A. Distribusi Bentuk Slang (Human Labels):",
            f"      {'Kategori':<15} | {'Komentar Unik':<14} | {'% Komentar':<10} | {'Total Label':<12} | % Seluruh Label",
            f"      {'-'*15}-+-{'-'*14}-+-{'-'*10}-+-{'-'*12}-+-{'-'*16}",
        ]

        for row in self.human_slang_distribution:
            lines.append(
                f"      {row['kategori']:<15} | {row['komentar_unik_count']:<14} | "
                f"{row['komentar_persentase']:<9.1f}% | {row['total_kemunculan_label']:<12} | "
                f"{row['proporsi_dari_seluruh_label']:.1f}%"
            )

        lines.extend([
            "",
            "   B. Distribusi Fungsi Bahasa (Human Labels):",
            f"      {'Kategori':<15} | {'Komentar Unik':<14} | {'% Komentar':<10} | {'Total Label':<12} | % Seluruh Label",
            f"      {'-'*15}-+-{'-'*14}-+-{'-'*10}-+-{'-'*12}-+-{'-'*16}",
        ])

        for row in self.human_lang_distribution:
            lines.append(
                f"      {row['kategori']:<15} | {row['komentar_unik_count']:<14} | "
                f"{row['komentar_persentase']:<9.1f}% | {row['total_kemunculan_label']:<12} | "
                f"{row['proporsi_dari_seluruh_label']:.1f}%"
            )

        lines.extend([
            "",
            "3. INTEGRITAS DATA & KUALITAS:",
            f"   - Komentar Teks Kosong  : {self.empty_clean_text_count}",
            f"   - Duplikasi Comment ID  : {self.duplicate_id_count}",
            f"   - ID Kosong             : {self.missing_id_count}",
            f"   - Galat Skema / Validasi: {len(self.invalid_schema_errors)}",
        ])

        if self.media_distribution:
            lines.extend([
                "",
                "4. DISTRIBUSI POSTINGAN / MEDIA ID:",
            ])
            for m in self.media_distribution[:5]:
                lines.append(f"   - Media ID {m['media_id']:<20}: {m['jumlah_komentar']} komentar ({m['persentase']:.1f}%)")
            if len(self.media_distribution) > 5:
                lines.append(f"   ... dan {len(self.media_distribution) - 5} postingan media lainnya.")

        if self.has_model_predictions:
            lines.extend([
                "",
                "5. ANALISIS HASIL PREDIKSI MODEL:",
                f"   - Total Komentar Diprediksi : {self.total_predicted_comments}",
                f"   - Perlu Tinjauan Manusia    : {self.predictions_needs_review_count} ({self.predictions_needs_review_pct:.1f}%)",
            ])

        if self.has_model_evaluation:
            lines.extend([
                "",
                "6. EVALUASI MODEL & ERROR ANALYSIS (HELD-OUT TEST SET):",
                f"   - Slang Forms Macro-F1      : {self.model_eval_summary.get('slang_macro_f1', 'N/A')}",
                f"   - Language Funcs Macro-F1   : {self.model_eval_summary.get('lang_macro_f1', 'N/A')}",
            ])
            if self.qualitative_error_samples:
                lines.append("   Contoh Galat Prediksi (Disanitasi dari PII):")
                for err in self.qualitative_error_samples[:3]:
                    lines.append(f"     * [{err['comment_id']}] \"{err['clean_text']}\"")
                    lines.append(f"       Aktual  : Slang={err['true_slang']} | Fungsi={err['true_lang']}")
                    lines.append(f"       Prediksi: Slang={err['pred_slang']} | Fungsi={err['pred_lang']}")

        if self.limitations:
            lines.extend([
                "",
                "7. KETERBATASAN DATASET & KELAS LANGKA:",
            ])
            for lim in self.limitations:
                lines.append(f"   [!] {lim}")

        lines.extend([
            "",
            "-" * 74,
            "Lokasi Berkas Laporan Tersimpan:",
            f"  Laporan Lengkap (MD): {self.report_md_path}",
        ])
        for name, p in self.saved_csv_paths.items():
            lines.append(f"  Tabel CSV ({name}) : {p}")
        for name, p in self.saved_plot_paths.items():
            lines.append(f"  Grafik PNG ({name}): {p}")
        lines.append("=" * 74)

        return "\n".join(lines)

    def markdown_text(self) -> str:
        """Format full persistent Markdown report with tables, notes, and citations."""
        return f"""# Laporan Analisis Dataset & Evaluasi Model NLP — Instagram Slang

> [!NOTE]
> **Metodologi Multi-Label:**  
> Analisis frekuensi membedakan dua ukuran secara tegas:
> 1. **`komentar_unik_count` (Document Frequency):** Jumlah komentar unik yang memuat label tersebut.
> 2. **`total_kemunculan_label` (Label Occurrence Count):** Jumlah token label dalam keseluruhan korpus multi-label.

---

## 1. Ringkasan Volume Pipeline

| Tahap Pipeline | Total Komentar | Keterangan |
| :--- | :---: | :--- |
| **RAW Comments** | {self.total_raw_comments} | Dari {self.total_raw_files} file RAW (imutabel) |
| **Processed Comments** | {self.total_processed_comments} | Dari {self.total_processed_files} file hasil pembersihan |
| **Annotated Comments** | {self.total_annotated_comments} | Total baris dalam template |
| *-- Selesai Ditinjau* | {self.human_completed_count} | Label manusia lengkap dan terverifikasi |
| *-- Belum Selesai* | {self.human_pending_count} | Menunggu anotasi manusia |
| *-- Bermasalah (Invalid)*| {self.human_invalid_count} | Galat skema atau inkonsistensi label |

---

## 2. Analisis Ground-Truth Anotasi Manusia

- **Proporsi Slang:**
  - Komentar Mengandung Slang (`slang_present='ya'`): **{self.human_slang_present_count}** ({self.human_slang_present_pct:.2f}%)
  - Komentar Tanpa Slang (`slang_present='tidak'`): **{self.human_slang_absent_count}** ({self.human_slang_absent_pct:.2f}%)

### A. Frekuensi Bentuk Slang (`slang_forms`)

| Bentuk Slang | Komentar Unik | % Komentar | Total Kemunculan Label | % Seluruh Label |
| :--- | :---: | :---: | :---: | :---: |
""" + "\n".join(
            f"| `{r['kategori']}` | {r['komentar_unik_count']} | {r['komentar_persentase']:.2f}% | {r['total_kemunculan_label']} | {r['proporsi_dari_seluruh_label']:.2f}% |"
            for r in self.human_slang_distribution
        ) + f"""

### B. Frekuensi Fungsi Bahasa (`language_functions`)

| Fungsi Bahasa | Komentar Unik | % Komentar | Total Kemunculan Label | % Seluruh Label |
| :--- | :---: | :---: | :---: | :---: |
""" + "\n".join(
            f"| `{r['kategori']}` | {r['komentar_unik_count']} | {r['komentar_persentase']:.2f}% | {r['total_kemunculan_label']} | {r['proporsi_dari_seluruh_label']:.2f}% |"
            for r in self.human_lang_distribution
        ) + f"""

---

## 3. Distribusi Postingan Asal (`media_id`)

| Media ID Postingan | Jumlah Komentar | Persentase (%) |
| :--- | :---: | :---: |
""" + "\n".join(
            f"| `{m['media_id']}` | {m['jumlah_komentar']} | {m['persentase']:.2f}% |"
            for m in self.media_distribution
        ) + f"""

---

## 4. Kualitas Data & Integritas Nilai

- Komentar teks kosong: **{self.empty_clean_text_count}**
- Duplikasi `comment_id`: **{self.duplicate_id_count}**
- `comment_id` kosong: **{self.missing_id_count}**
- Kesalahan validasi skema: **{len(self.invalid_schema_errors)}**

---

## 5. Analisis Hasil Prediksi Model Baseline

- Status Prediksi Tersedia: **{'Ya' if self.has_model_predictions else 'Belum Ada'}**
- Total Komentar Diprediksi: **{self.total_predicted_comments}**
- Memerlukan Tinjauan Manusia (`needs_review=True`): **{self.predictions_needs_review_count}** ({self.predictions_needs_review_pct:.2f}%)

---

## 6. Analisis Galat Kualitatif (Disanitasi dari PII)

| Comment ID | Teks Komentar (Sanitasi) | Aktual Slang | Prediksi Slang | Aktual Fungsi | Prediksi Fungsi |
| :--- | :--- | :--- | :--- | :--- | :--- |
""" + "\n".join(
            f"| `{e['comment_id']}` | \"{e['clean_text']}\" | `{e['true_slang']}` | `{e['pred_slang']}` | `{e['true_lang']}` | `{e['pred_lang']}` |"
            for e in self.qualitative_error_samples
        ) + f"""

---

## 7. Keterbatasan Dataset & Kelas Langka

""" + "\n".join(f"- {lim}" for lim in self.limitations) + f"""
"""


def generate_distribution_plots(
    slang_dist: list[dict[str, Any]],
    lang_dist: list[dict[str, Any]],
    output_dir: Path,
    run_id: str,
) -> dict[str, str]:
    """Generate clean headless matplotlib bar charts without GUI or dashboards.

    Args:
        slang_dist: Slang forms distribution table.
        lang_dist: Language functions distribution table.
        output_dir: Output directory for saving PNGs.
        run_id: Run identifier for filename uniqueness.

    Returns:
        dict[str, str]: Map of plot names to saved file paths.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # Strictly headless backend
        import matplotlib.pyplot as plt

        saved_plots: dict[str, str] = {}
        output_dir.mkdir(parents=True, exist_ok=True)

        # 1. Slang Forms Plot
        fig, ax = plt.subplots(figsize=(9, 5))
        cats = [item["kategori"] for item in slang_dist]
        counts = [item["komentar_unik_count"] for item in slang_dist]
        ax.bar(cats, counts, color="#2b5c8f", edgecolor="black", alpha=0.85)
        ax.set_title("Distribusi Bentuk Slang (Document Frequency)", fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("Bentuk Slang", fontsize=10, labelpad=8)
        ax.set_ylabel("Jumlah Komentar Unik", fontsize=10, labelpad=8)
        plt.xticks(rotation=25, ha="right")
        plt.tight_layout()

        slang_plot_path = output_dir / f"plot_slang_forms_{run_id}.png"
        fig.savefig(slang_plot_path, dpi=150)
        plt.close(fig)
        saved_plots["slang_forms"] = str(slang_plot_path)

        # 2. Language Functions Plot
        fig, ax = plt.subplots(figsize=(7, 5))
        l_cats = [item["kategori"] for item in lang_dist]
        l_counts = [item["komentar_unik_count"] for item in lang_dist]
        ax.bar(l_cats, l_counts, color="#2e7d32", edgecolor="black", alpha=0.85)
        ax.set_title("Distribusi Fungsi Bahasa (Document Frequency)", fontsize=13, fontweight="bold", pad=12)
        ax.set_xlabel("Fungsi Bahasa", fontsize=10, labelpad=8)
        ax.set_ylabel("Jumlah Komentar Unik", fontsize=10, labelpad=8)
        plt.tight_layout()

        lang_plot_path = output_dir / f"plot_language_functions_{run_id}.png"
        fig.savefig(lang_plot_path, dpi=150)
        plt.close(fig)
        saved_plots["language_functions"] = str(lang_plot_path)

        return saved_plots

    except Exception as err:
        logger.warning("Gagal membuat plot visualisasi matplotlib: %s", err)
        return {}


def run_comprehensive_analysis(
    annotated_csv_path: Path | None = None,
    output_reports_dir: Path | None = None,
    raw_dir: Path | None = None,
    processed_dir: Path | None = None,
    predictions_dir: Path | None = None,
) -> DatasetAnalysisReport:
    """Execute complete dataset analysis and generate persistent reports and CSVs.

    Args:
        annotated_csv_path: Path to comments_labeled.csv.
        output_reports_dir: Destination directory for reports (reports/).
        raw_dir: Directory containing RAW datasets (data/raw/).
        processed_dir: Directory containing processed datasets (data/processed/).
        predictions_dir: Directory containing predictions (data/predictions/).

    Returns:
        DatasetAnalysisReport: Consolidated data structures with summary text and file references.
    """
    ensure_directories()
    reports_dir = Path(output_reports_dir or REPORTS_DIR).resolve()
    reports_dir.mkdir(parents=True, exist_ok=True)

    target_raw_dir = Path(raw_dir or RAW_DATA_DIR).resolve()
    target_proc_dir = Path(processed_dir or PROCESSED_DATA_DIR).resolve()
    target_pred_dir = Path(predictions_dir or PREDICTIONS_DATA_DIR).resolve()
    target_annotated = Path(annotated_csv_path or DEFAULT_ANNOTATED_PATH).resolve()

    run_id = generate_run_id()
    timestamp_iso = datetime.now(timezone.utc).isoformat()

    # 1. Count RAW Comments & Files
    raw_files = list(target_raw_dir.glob("comments_*.csv")) if target_raw_dir.exists() else []
    total_raw_comments = 0
    for rf in raw_files:
        try:
            with open(rf, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                total_raw_comments += sum(1 for row in reader if row.get("comment_id"))
        except Exception:
            pass

    # 2. Count Processed Comments & Files
    proc_files = list(target_proc_dir.glob("comments_clean_*.csv")) if target_proc_dir.exists() else []
    total_proc_comments = 0
    media_map: dict[str, str] = {}
    for pf in proc_files:
        try:
            with open(pf, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cid = row.get("comment_id", "").strip()
                    mid = row.get("media_id", "").strip()
                    if cid:
                        total_proc_comments += 1
                        if mid:
                            media_map[cid] = mid
        except Exception:
            pass

    # 3. Read and Validate Annotated Data
    total_annotated_comments = 0
    completed_comments: list[dict[str, Any]] = []
    pending_count = 0
    invalid_schema_errors: list[str] = []
    empty_clean_text_count = 0
    missing_id_count = 0
    duplicate_id_count = 0
    seen_cids: set[str] = set()

    if target_annotated.exists():
        val_report = validate_annotated_dataset(target_annotated)
        invalid_schema_errors = val_report.errors

        with open(target_annotated, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_annotated_comments += 1
                cid = row.get("comment_id", "").strip()
                clean_text = row.get("clean_text", "").strip()
                status = row.get("review_status", "").strip().lower()

                if not cid:
                    missing_id_count += 1
                elif cid in seen_cids:
                    duplicate_id_count += 1
                else:
                    seen_cids.add(cid)

                if not clean_text:
                    empty_clean_text_count += 1

                if status == "selesai":
                    # Attach media_id
                    mid = row.get("media_id", "").strip() or media_map.get(cid, "unknown_media")
                    completed_comments.append({
                        "comment_id": cid,
                        "media_id": mid,
                        "clean_text": clean_text,
                        "slang_present": row.get("slang_present", "").strip().lower(),
                        "slang_forms_list": parse_multilabel_field(row.get("slang_forms", "")),
                        "lang_funcs_list": parse_multilabel_field(row.get("language_functions", "")),
                    })
                else:
                    pending_count += 1

    human_completed_count = len(completed_comments)
    human_invalid_count = val_report.total_invalid if target_annotated.exists() else 0

    # 4. Slang Presence Proportions
    slang_yes = sum(1 for c in completed_comments if c["slang_present"] == "ya")
    slang_no = sum(1 for c in completed_comments if c["slang_present"] == "tidak")
    slang_yes_pct = (slang_yes / human_completed_count * 100.0) if human_completed_count > 0 else 0.0
    slang_no_pct = (slang_no / human_completed_count * 100.0) if human_completed_count > 0 else 0.0

    # 5. Multi-label Distributions (Human)
    slang_forms_labels = [c["slang_forms_list"] for c in completed_comments]
    lang_funcs_labels = [c["lang_funcs_list"] for c in completed_comments]

    human_slang_dist = compute_multilabel_distribution(
        labels_list=slang_forms_labels,
        predefined_categories=SLANG_FORMS,
        total_comments=human_completed_count,
    )

    human_lang_dist = compute_multilabel_distribution(
        labels_list=lang_funcs_labels,
        predefined_categories=LANGUAGE_FUNCTIONS,
        total_comments=human_completed_count,
    )

    # 6. Media Distribution
    media_counts: dict[str, int] = {}
    for c in completed_comments:
        m = c["media_id"]
        media_counts[m] = media_counts.get(m, 0) + 1

    media_dist = [
        {
            "media_id": mid,
            "jumlah_komentar": count,
            "persentase": round(count / human_completed_count * 100.0, 2) if human_completed_count > 0 else 0.0,
        }
        for mid, count in sorted(media_counts.items(), key=lambda item: item[1], reverse=True)
    ]

    # 7. Model Predictions Distribution
    pred_files = (
        sorted(list(target_pred_dir.glob("comments_predictions_*.csv")), key=lambda p: p.stat().st_mtime, reverse=True)
        if target_pred_dir.exists()
        else []
    )

    has_model_predictions = len(pred_files) > 0
    total_predicted = 0
    needs_review_count = 0
    pred_slang_lists: list[list[str]] = []
    pred_lang_lists: list[list[str]] = []
    predictions_map: dict[str, dict[str, Any]] = {}

    if has_model_predictions:
        latest_pred_file = pred_files[0]
        try:
            with open(latest_pred_file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cid = row.get("comment_id", "").strip()
                    if cid:
                        total_predicted += 1
                        is_rev = row.get("needs_review", "").lower() == "true"
                        if is_rev:
                            needs_review_count += 1
                        s_list = parse_multilabel_field(row.get("predicted_slang_forms", ""))
                        l_list = parse_multilabel_field(row.get("predicted_language_functions", ""))
                        pred_slang_lists.append(s_list)
                        pred_lang_lists.append(l_list)
                        predictions_map[cid] = {
                            "predicted_slang": s_list,
                            "predicted_lang": l_list,
                            "needs_review": is_rev,
                        }
        except Exception as err:
            logger.warning("Gagal membaca file prediksi %s: %s", latest_pred_file.name, err)

    pred_needs_review_pct = (needs_review_count / total_predicted * 100.0) if total_predicted > 0 else 0.0

    pred_slang_dist = compute_multilabel_distribution(
        labels_list=pred_slang_lists,
        predefined_categories=SLANG_FORMS,
        total_comments=total_predicted,
    )
    pred_lang_dist = compute_multilabel_distribution(
        labels_list=pred_lang_lists,
        predefined_categories=LANGUAGE_FUNCTIONS,
        total_comments=total_predicted,
    )

    # 8. Model Evaluation & Qualitative Error Samples
    eval_files = (
        sorted(list(reports_dir.glob("baseline_evaluation_*.json")), key=lambda p: p.stat().st_mtime, reverse=True)
        if reports_dir.exists()
        else []
    )
    has_model_eval = len(eval_files) > 0
    model_eval_summary: dict[str, Any] = {}

    if has_model_eval:
        try:
            with open(eval_files[0], "r", encoding="utf-8") as f:
                eval_data = json.load(f)
            model_eval_summary = {
                "slang_macro_f1": eval_data.get("slang_metrics", {}).get("macro_f1", 0.0),
                "slang_micro_f1": eval_data.get("slang_metrics", {}).get("micro_f1", 0.0),
                "lang_macro_f1": eval_data.get("lang_metrics", {}).get("macro_f1", 0.0),
                "lang_micro_f1": eval_data.get("lang_metrics", {}).get("micro_f1", 0.0),
            }
        except Exception as err:
            logger.warning("Gagal membaca laporan evaluasi baseline %s: %s", eval_files[0].name, err)

    # Compare completed human annotations with predictions to find qualitative error samples
    qualitative_errors: list[dict[str, Any]] = []
    for c in completed_comments:
        cid = c["comment_id"]
        if cid in predictions_map:
            p_info = predictions_map[cid]
            true_slang_set = set(c["slang_forms_list"])
            pred_slang_set = set(p_info["predicted_slang"])
            true_lang_set = set(c["lang_funcs_list"])
            pred_lang_set = set(p_info["predicted_lang"])

            # Check if there is any mismatch in slang or language function
            if true_slang_set != pred_slang_set or true_lang_set != pred_lang_set:
                qualitative_errors.append({
                    "comment_id": cid,
                    "clean_text": sanitize_comment_text(c["clean_text"]),
                    "true_slang": ";".join(c["slang_forms_list"]) or "tidak_ada",
                    "pred_slang": ";".join(p_info["predicted_slang"]) or "(kosong)",
                    "true_lang": ";".join(c["lang_funcs_list"]) or "tidak_jelas",
                    "pred_lang": ";".join(p_info["predicted_lang"]) or "(kosong)",
                })

    # 9. Limitations & Rare Class Warnings
    limitations: list[str] = []
    if human_completed_count < 30:
        limitations.append(
            f"Jumlah sampel teranotasi selesai masih terbatas (N={human_completed_count}). "
            "Diperlukan penambahan anotasi sebelum menarik generalisasi statistik."
        )

    rare_slang = [item["kategori"] for item in human_slang_dist if item["komentar_unik_count"] < 5]
    if rare_slang:
        limitations.append(
            f"Kategori bentuk slang dengan jumlah kemunculan rendah (<5): {', '.join(rare_slang)}. "
            "Evaluasi pada kelas ini rentan memiliki variansi tinggi."
        )

    rare_lang = [item["kategori"] for item in human_lang_dist if item["komentar_unik_count"] < 5]
    if rare_lang:
        limitations.append(
            f"Kategori fungsi bahasa dengan jumlah kemunculan rendah (<5): {', '.join(rare_lang)}."
        )

    limitations.append(
        "Komentar media sosial sangat kontekstual dan dinamis. Model baseline linier CPU (TF-IDF) "
        "tidak memodelkan semantik urutan kata mendalam sebagaimana transformer model."
    )

    # 10. Save Tables as CSV in reports/
    saved_csv_paths: dict[str, str] = {}

    def _write_csv(filename: str, fieldnames: list[str], rows: list[dict[str, Any]]) -> str:
        fpath = reports_dir / filename
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return str(fpath)

    # Pipeline Overview Table
    saved_csv_paths["pipeline_overview"] = _write_csv(
        f"analysis_pipeline_overview_{run_id}.csv",
        ["metric", "count", "keterangan"],
        [
            {"metric": "total_raw_comments", "count": total_raw_comments, "keterangan": f"{len(raw_files)} files"},
            {"metric": "total_processed_comments", "count": total_proc_comments, "keterangan": f"{len(proc_files)} files"},
            {"metric": "total_annotated_comments", "count": total_annotated_comments, "keterangan": "in template"},
            {"metric": "human_completed_count", "count": human_completed_count, "keterangan": "review_status=selesai"},
            {"metric": "human_pending_count", "count": pending_count, "keterangan": "review_status=belum"},
            {"metric": "human_invalid_count", "count": human_invalid_count, "keterangan": "validation errors"},
        ],
    )

    # Slang Forms Distribution Table
    saved_csv_paths["human_slang_forms"] = _write_csv(
        f"analysis_human_slang_forms_{run_id}.csv",
        ["kategori", "komentar_unik_count", "komentar_persentase", "total_kemunculan_label", "proporsi_dari_seluruh_label"],
        human_slang_dist,
    )

    # Language Functions Distribution Table
    saved_csv_paths["human_language_functions"] = _write_csv(
        f"analysis_human_language_functions_{run_id}.csv",
        ["kategori", "komentar_unik_count", "komentar_persentase", "total_kemunculan_label", "proporsi_dari_seluruh_label"],
        human_lang_dist,
    )

    # Media Distribution Table
    if media_dist:
        saved_csv_paths["media_distribution"] = _write_csv(
            f"analysis_media_distribution_{run_id}.csv",
            ["media_id", "jumlah_komentar", "persentase"],
            media_dist,
        )

    # Error Samples Table
    if qualitative_errors:
        saved_csv_paths["error_samples"] = _write_csv(
            f"analysis_error_samples_{run_id}.csv",
            ["comment_id", "clean_text", "true_slang", "pred_slang", "true_lang", "pred_lang"],
            qualitative_errors,
        )

    # 11. Generate Visualizations (PNG)
    saved_plot_paths = generate_distribution_plots(
        slang_dist=human_slang_dist,
        lang_dist=human_lang_dist,
        output_dir=reports_dir,
        run_id=run_id,
    )

    # 12. Save Full Markdown Report
    report_md_path = reports_dir / f"analysis_report_{run_id}.md"

    report = DatasetAnalysisReport(
        run_id=run_id,
        timestamp=timestamp_iso,
        total_raw_comments=total_raw_comments,
        total_raw_files=len(raw_files),
        total_processed_comments=total_proc_comments,
        total_processed_files=len(proc_files),
        total_annotated_comments=total_annotated_comments,
        human_completed_count=human_completed_count,
        human_pending_count=pending_count,
        human_invalid_count=human_invalid_count,
        human_slang_present_count=slang_yes,
        human_slang_absent_count=slang_no,
        human_slang_present_pct=slang_yes_pct,
        human_slang_absent_pct=slang_no_pct,
        human_slang_distribution=human_slang_dist,
        human_lang_distribution=human_lang_dist,
        media_distribution=media_dist,
        missing_id_count=missing_id_count,
        empty_clean_text_count=empty_clean_text_count,
        duplicate_id_count=duplicate_id_count,
        invalid_schema_errors=invalid_schema_errors,
        has_model_predictions=has_model_predictions,
        total_predicted_comments=total_predicted,
        predictions_needs_review_count=needs_review_count,
        predictions_needs_review_pct=pred_needs_review_pct,
        pred_slang_distribution=pred_slang_dist,
        pred_lang_distribution=pred_lang_dist,
        has_model_evaluation=has_model_eval,
        model_eval_summary=model_eval_summary,
        qualitative_error_samples=qualitative_errors,
        limitations=limitations,
        saved_csv_paths=saved_csv_paths,
        saved_plot_paths=saved_plot_paths,
        report_md_path=str(report_md_path),
    )

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(report.markdown_text())

    return report
