"""CLI interface module for Instagram Slang NLP pipeline."""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Callable

from src.collectors.base import (
    AuthenticationError,
    BaseCollector,
    CollectorError,
    CollectorValidationError,
    MediaUnavailableError,
    NetworkCollectorError,
    PermissionDeniedError,
    RateLimitError,
)
from src.collectors.browser_nlp import InstagramBrowserNLPCollector
from src.collectors.instagram_api import InstagramGraphAPICollector
from src.config import (
    RAW_DATA_DIR,
    AppConfig,
    ConfigValidationError,
    ensure_directories,
    mask_token,
    validate_target_comments,
)
from src.logging_config import setup_logger
from src.preprocessing import preprocess_raw_dataset
from src.storage import (
    calculate_file_sha256,
    generate_run_id,
    save_raw_comments,
    save_run_metadata,
    update_run_metadata,
)

logger = setup_logger("cli")


def print_banner(config: AppConfig) -> None:
    """Print the application header banner and current runtime configuration."""
    print("=" * 64)
    print("       INSTAGRAM SLANG NLP PIPELINE - WINDOWS CLI")
    print("=" * 64)
    print(f" Lingkungan      : {config.app_env}")
    print(f" Target Default  : {config.target_comments} komentar")
    print(f" Metode Koleksi  : {config.collector_method}")
    print(f" Versi Graph API : {config.graph_api_version}")
    print(f" Varian API      : {config.api_variant}")
    print(f" Access Token    : {mask_token(config.access_token)}")
    print("=" * 64)


def display_menu() -> None:
    """Display the required main CLI navigation menu."""
    print("\nMenu Utama:")
    print("  1. Kumpulkan komentar Instagram")
    print("  2. Jalankan NLP pada RAW yang sudah ada")
    print("  3. Buat template anotasi")
    print("  4. Validasi anotasi")
    print("  5. Latih model baseline")
    print("  6. Prediksi dataset")
    print("  7. Analisis hasil")
    print("  0. Keluar")
    print("-" * 64)


def handle_collect_comments(
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
    prompt_token_fn: Callable[[str], str] = getpass.getpass,
    collector_instance: BaseCollector | None = None,
    preprocess_fn: Callable[[Path, str], Path] | None = None,
) -> None:
    """Orchestrate collection, RAW storage, and strict confirmation gate before NLP.

    Mandatory Workflow:
    1. Input URL or media ID.
    2. Input target comment count (default: 3000).
    3. Validate configuration & access.
    4. Run collector (Browser NLP by default, or Graph API if configured).
    5. Save RAW comments (data/raw/comments_<run_id>.csv) - immutable.
    6. Save run metadata JSON (reports/run_<run_id>.json) without tokens.
    7. Display collection summary and RAW location.
    8. Confirmation prompt: 'Lanjutkan ke tahap NLP sekarang? [y/N]: '
    9. If 'N' or empty: status='nlp_declined', stop safely. Preprocessing is NOT called.
    10. If 'y' or 'yes': run preprocessing only. Training is NOT executed automatically.
    """
    print("\n--- [1] Kumpulkan Komentar Instagram ---")
    if config.collector_method == "graph_api":
        print(InstagramGraphAPICollector.get_api_limitations())
    else:
        print("[METODE AKTIF] Browser Automation (Playwright) + NLP Extractor")
        print("  - Membuka browser langsung ke URL postingan publik Instagram.")
        print("  - Sesi login tersimpan permanen di folder .browser_profile/.")
        print("  - Ketik 'login' jika Anda ingin membuka browser untuk login akun terlebih dahulu.")
    print("-" * 64)

    try:
        target_input = input_fn("Masukkan URL postingan atau ketik 'login': ").strip()
        if not target_input:
            print("[INFO] Pengumpulan dibatalkan (input kosong).")
            return

        if target_input.lower() == "login":
            collector = InstagramBrowserNLPCollector(headless=False, input_fn=input_fn)
            collector.open_interactive_login(input_fn=input_fn)
            return

        target_count_str = input_fn(
            f"Masukkan target jumlah komentar [default: {config.target_comments}]: "
        ).strip()
        if target_count_str:
            try:
                target_count = validate_target_comments(target_count_str)
            except ConfigValidationError as e:
                print(f"\n[ERROR] {e}")
                return
        else:
            target_count = config.target_comments

        print(f"Target terpilih: {target_count} komentar untuk '{target_input}'")

        # Determine collector instance
        active_method = config.collector_method
        if collector_instance:
            collector = collector_instance
            token_used = config.access_token
        elif active_method == "browser_nlp":
            print("\n[INFO] Menggunakan mode Browser Automation (Playwright) + NLP Extractor.")
            print("[INFO] Membuka jendela browser untuk memuat halaman dan membaca komentar...")
            collector = InstagramBrowserNLPCollector(headless=False, input_fn=input_fn)
            token_used = None
        else:
            # Resolve access token safely for Graph API
            if not config.access_token:
                print("\nToken akses belum terkonfigurasi di environment/.env.")
                token = config.get_or_prompt_access_token(prompt_fn=prompt_token_fn)
                print(f"Token sesi berhasil disimpan di memori: {mask_token(token)}")
            else:
                token = config.access_token
                print(f"Menggunakan token terkonfigurasi: {mask_token(config.access_token)}")
            token_used = token

            collector = InstagramGraphAPICollector(
                access_token=token_used,
                api_version=config.graph_api_version,
                api_variant=config.api_variant,
            )

        run_id = generate_run_id()
        save_run_metadata(
            run_id=run_id,
            status="started",
            extra_data={
                "target_input": target_input,
                "target_comments": target_count,
                "collector_method": active_method,
                "api_variant": config.api_variant if active_method == "graph_api" else "n/a",
                "api_version": config.graph_api_version if active_method == "graph_api" else "n/a",
            },
        )

        print(f"\nMemulai pengumpulan data ({type(collector).__name__})...")
        result = collector.collect_comments(target=target_input, limit=target_count)

        # Handle empty collection safely
        if not result.comments or result.unique_collected == 0:
            update_run_metadata(
                run_id=run_id,
                updates={
                    "status": "empty_result",
                    "media_id": result.media_id,
                    "unique_collected": 0,
                },
            )
            print("\n[PERINGATAN] Tidak ada komentar yang berhasil diambil dari media ini.")
            print("[INFO] Pengumpulan selesai tanpa data. Tahap NLP tidak dimulai.")
            return

        # Save RAW dataset (guaranteed immutable)
        raw_filepath = save_raw_comments(run_id=run_id, comments=result.comments)
        raw_sha256 = calculate_file_sha256(raw_filepath)

        meta_filepath = update_run_metadata(
            run_id=run_id,
            updates={
                "status": "raw_saved",
                "media_id": result.media_id,
                "total_collected": result.total_collected,
                "unique_collected": result.unique_collected,
                "raw_filepath": str(raw_filepath),
                "raw_sha256": raw_sha256,
            },
        )

        # Display collection summary
        print("\n" + "=" * 64)
        print("PENGUMPULAN KOMENTAR SELESAI!")
        print(f"Media ID          : {result.media_id}")
        print(f"Komentar Diambil  : {result.total_collected}")
        print(f"Komentar Unik     : {result.unique_collected}")
        print(f"Status Kursor     : {'Lengkap (selesai)' if result.paging_completed else 'Mencapai target batas'}")
        print(f"Lokasi File RAW   : {raw_filepath}")
        print(f"Laporan Run (JSON): {meta_filepath}")
        print("=" * 64)

        # Mandatory confirmation gate before NLP
        confirm_input = input_fn("Lanjutkan ke tahap NLP sekarang? [y/N]: ").strip().lower()

        if confirm_input not in {"y", "yes"}:
            update_run_metadata(
                run_id=run_id,
                updates={"status": "nlp_declined", "nlp_confirmed": False},
            )
            print("\n[INFO] Tahap NLP dibatalkan oleh pengguna (status: nlp_declined).")
            print(f"[INFO] Dataset RAW tetap tersimpan utuh di: {raw_filepath}")
            print("[INFO] Anda dapat memproses dataset RAW ini kapan saja melalui menu 2.")
            return

        # User approved NLP: proceed strictly to preprocessing
        update_run_metadata(
            run_id=run_id,
            updates={"status": "preprocessing", "nlp_confirmed": True},
        )
        print("\n[INFO] Menjalankan tahap Preprocessing pada dataset RAW...")
        from src.preprocessing import preprocess_dataset_with_report

        if preprocess_fn:
            processed_path = preprocess_fn(raw_filepath, run_id)
        else:
            report = preprocess_dataset_with_report(raw_filepath, run_id=run_id)
            processed_path = report.processed_filepath
            print("\n" + report.summary_text())

        update_run_metadata(
            run_id=run_id,
            updates={
                "status": "preprocessed",
                "processed_filepath": str(processed_path),
            },
        )
        print(f"\n[SUKSES] Preprocessing selesai! File bersih tersimpan di: {processed_path}")
        print("[INFO] Model NLP TIDAK dilatih secara otomatis.")
        print("[INFO] Pelatihan baseline memerlukan label manual manusia yang tervalidasi (Sprint 5-6).")

    except AuthenticationError as err:
        print(f"\n[AUTH ERROR] {err}")
    except PermissionDeniedError as err:
        print(f"\n[PERMISSION ERROR] {err}")
    except MediaUnavailableError as err:
        print(f"\n[MEDIA ERROR] {err}")
    except RateLimitError as err:
        print(f"\n[RATE LIMIT ERROR] {err}")
    except NetworkCollectorError as err:
        print(f"\n[NETWORK ERROR] {err}")
    except CollectorValidationError as err:
        print(f"\n[VALIDATION ERROR] {err}")
    except CollectorError as err:
        print(f"\n[COLLECTOR ERROR] {err}")
    except ConfigValidationError as err:
        print(f"\n[CONFIG ERROR] {err}")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Input pengumpulan dibatalkan oleh pengguna.")


def handle_run_nlp_on_raw(
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
    preprocess_fn: Callable[[Path, str], Path] | None = None,
) -> None:
    """Handle menu option 2: Run preprocessing on existing RAW datasets."""
    from src.config import RAW_DATA_DIR
    from src.preprocessing import PreprocessingValidationError, preprocess_dataset_with_report

    print("\n--- [2] Jalankan NLP pada RAW yang Sudah Ada ---")
    raw_files = sorted(
        list({p for p in RAW_DATA_DIR.iterdir() if p.is_file() and p.suffix.lower() in {".csv", ".xlsx", ".xls"}}),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not raw_files:
        print(f"[INFO] Tidak ada file data di folder: {RAW_DATA_DIR}")
        print("[INFO] Anda dapat meletakkan file CSV/Excel hasil export atau kumpulkan via menu 1.")
        return

    print("Daftar file yang tersedia di data/raw/:")
    for idx, f in enumerate(raw_files, start=1):
        file_size_kb = f.stat().st_size / 1024
        tag = "[RAW]" if f.name.startswith("comments_") and f.suffix == ".csv" else "[EKSTERNAL]"
        print(f"  {idx}. {tag} {f.name} ({file_size_kb:.1f} KB)")

    try:
        choice = input_fn(f"\nPilih nomor file [1-{len(raw_files)}] atau masukkan path file, (0 untuk batal): ").strip()
        if choice in {"0", ""}:
            print("[INFO] Dibatalkan.")
            return

        selected_raw: Path
        if choice.isdigit():
            choice_idx = int(choice) - 1
            if not (0 <= choice_idx < len(raw_files)):
                print("[ERROR] Nomor pilihan di luar rentang.")
                return
            selected_raw = raw_files[choice_idx]
        else:
            custom_path = Path(choice).resolve()
            if not custom_path.exists():
                print(f"[ERROR] File '{custom_path}' tidak ditemukan.")
                return
            selected_raw = custom_path

        run_id = selected_raw.stem.replace("comments_", "")

        print(f"\n[INFO] Memproses dataset: {selected_raw.name}")
        if preprocess_fn:
            processed_path = preprocess_fn(selected_raw, run_id)
            print(f"[SUKSES] Preprocessing selesai. Output tersimpan di: {processed_path}")
        else:
            try:
                report = preprocess_dataset_with_report(selected_raw, run_id=run_id)
                print("\n" + report.summary_text())
                print(f"[SUKSES] Preprocessing selesai. Output tersimpan di: {report.processed_filepath}")
            except PreprocessingValidationError as val_err:
                # Coba auto-convert jika ini file eksternal dengan nama kolom berbeda
                from src.tools.import_external_csv import convert_external_file_to_raw

                print(f"\n[INFO] Deteksi kolom standar: {val_err}")
                print("[INFO] File terdeteksi sebagai format eksternal. Mengonversi struktur kolom secara otomatis...")
                try:
                    converted_raw, count = convert_external_file_to_raw(selected_raw)
                    print(f"[SUKSES] Berhasil dikonversi! {count} komentar tersimpan di file RAW: {converted_raw.name}")
                    new_run_id = converted_raw.stem.replace("comments_", "")
                    report = preprocess_dataset_with_report(converted_raw, run_id=new_run_id)
                    print("\n" + report.summary_text())
                    print(f"[SUKSES] Preprocessing selesai! Output tersimpan di: {report.processed_filepath}")
                except Exception as conv_err:
                    print(f"[VALIDASI ERROR] Konversi otomatis gagal: {conv_err}")
                    print(f"[INFO] Harap pastikan file memiliki kolom teks komentar.")

    except PreprocessingValidationError as err:
        print(f"\n[VALIDASI ERROR] {err}")
    except (ValueError, TypeError):
        print("[ERROR] Masukkan pilihan yang valid.")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Dibatalkan oleh pengguna.")


def handle_create_annotation_template(
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
) -> None:
    """Handle menu option 3: Generate or update annotation template CSV."""
    from src.annotations import generate_annotation_template
    from src.config import PROCESSED_DATA_DIR

    print("\n--- [3] Buat / Perbarui Template Anotasi ---")
    proc_files = sorted(list(PROCESSED_DATA_DIR.glob("comments_clean_*.csv")), key=lambda p: p.stat().st_mtime, reverse=True)

    if not proc_files:
        print(f"[INFO] Tidak ada file hasil preprocessing di: {PROCESSED_DATA_DIR}")
        print("[INFO] Jalankan pengumpulan (menu 1) atau preprocessing RAW (menu 2) terlebih dahulu.")
        return

    print("Daftar file processed yang tersedia:")
    for idx, f in enumerate(proc_files, start=1):
        print(f"  {idx}. {f.name}")

    try:
        choice = input_fn(f"\nPilih nomor file processed [1-{len(proc_files)}] (default 1, 0 untuk batal): ").strip()
        if choice == "0":
            print("[INFO] Dibatalkan.")
            return

        choice_idx = 0
        if choice and choice.isdigit():
            choice_idx = int(choice) - 1
            if not (0 <= choice_idx < len(proc_files)):
                print("[ERROR] Nomor pilihan di luar rentang.")
                return

        selected_proc = proc_files[choice_idx]
        print(f"\n[INFO] Memproses penggabungan template dari: {selected_proc.name}")
        output_template = generate_annotation_template(selected_proc)

        print(f"[SUKSES] Template anotasi siap di: {output_template}")
        print("[PENTING] Penggabungan bersifat non-destruktif: label lama tidak akan terhapus.")
        print("[PANDUAN] Buka file tersebut dan lakukan anotasi manual. Seluruh label harus ditinjau manusia.")

    except (ValueError, TypeError):
        print("[ERROR] Masukkan angka pilihan yang valid.")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Dibatalkan oleh pengguna.")


def handle_validate_annotations(
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
) -> None:
    """Handle menu option 4: Validate annotation taxonomy, consistency, and completeness."""
    from src.annotations import DEFAULT_ANNOTATED_PATH, validate_annotated_dataset

    print("\n--- [4] Validasi Dataset Anotasi ---")
    if not DEFAULT_ANNOTATED_PATH.exists():
        print(f"[INFO] File anotasi belum dibuat di: {DEFAULT_ANNOTATED_PATH}")
        print("[INFO] Silakan buat template terlebih dahulu melalui menu 3.")
        return

    try:
        custom_input = input_fn(
            f"Gunakan file '{DEFAULT_ANNOTATED_PATH.name}'? [Y/n atau masukkan path custom]: "
        ).strip()
        target_path = DEFAULT_ANNOTATED_PATH
        if custom_input and custom_input.lower() not in {"y", "yes"}:
            c_path = Path(custom_input).resolve()
            if c_path.exists():
                target_path = c_path
            else:
                print(f"[ERROR] File '{custom_input}' tidak ditemukan.")
                return

        print(f"\n[INFO] Menjalankan validasi skema dan konsistensi pada: {target_path.name}...")
        report = validate_annotated_dataset(target_path)
        print("\n" + report.summary_text())

        if not report.is_valid_for_training:
            print("\n[PERINGATAN] Dataset belum siap untuk pelatihan baseline model.")
            print("[INFO] Pastikan seluruh review_status='selesai' telah divalidasi dan bebas dari error.")

    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Dibatalkan oleh pengguna.")


def handle_train_baseline_model(
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
) -> None:
    """Handle menu option 5: Train baseline multi-label classifiers only after validation."""
    from src.annotations import DEFAULT_ANNOTATED_PATH
    from src.train import (
        AnnotationSchemaValidationError,
        BaselineTrainingError,
        InsufficientDataForSplitError,
        train_baseline_models,
    )

    print("\n--- [5] Latih Model Baseline (TF-IDF + One-vs-Rest) ---")
    if not DEFAULT_ANNOTATED_PATH.exists():
        print(f"[INFO] File anotasi belum ditemukan di: {DEFAULT_ANNOTATED_PATH}")
        print("[INFO] Silakan buat template (menu 3) dan lengkapi anotasi manual terlebih dahulu.")
        return

    try:
        confirm = input_fn(
            f"Mulai pelatihan baseline dengan file '{DEFAULT_ANNOTATED_PATH.name}'? [Y/n]: "
        ).strip().lower()
        if confirm and confirm not in {"y", "yes"}:
            print("[INFO] Pelatihan baseline dibatalkan oleh pengguna.")
            return

        print("\n[INFO] Menjalankan validasi anotasi manusia sebelum pelatihan...")
        print("[INFO] Menyiapkan group split berdasarkan media_id untuk mencegah data leakage...")
        report = train_baseline_models(annotated_csv_path=DEFAULT_ANNOTATED_PATH)

        print("\n" + report.summary_text())
        print(f"\n[SUKSES] Pelatihan baseline selesai. Artefak tersimpan di folder models/ dan reports/.")
        print("[PENTING] Model ini adalah benchmark awal untuk perbandingan, bukan model final.")

        # Optional comparative experiment with IndoBERT
        exp_choice = input_fn(
            "\nJalankan perbandingan dengan model bahasa pra-latih (IndoBERT) pada split ini? [y/N]: "
        ).strip().lower()
        if exp_choice in {"y", "yes"}:
            from src.experiments.indobert_experiment import (
                InsufficientGroupsForThreeWaySplitError,
                MissingDeepLearningDependenciesError,
                run_indobert_experiment,
            )
            print("\n[INFO] Menyiapkan eksperimen komparasi IndoBERT vs Baseline...")
            try:
                exp_rep = run_indobert_experiment(annotated_csv_path=DEFAULT_ANNOTATED_PATH)
                print("\n" + exp_rep.summary_markdown())
            except MissingDeepLearningDependenciesError as dl_err:
                print(f"\n[DEPENDENSI BELUM TERPASANG]\n{dl_err}")
            except InsufficientGroupsForThreeWaySplitError as split_err:
                print(f"\n[DATASET KELAYAKAN SPLIT]\n{split_err}")
            except Exception as exp_err:
                print(f"\n[ERROR EKSPERIMEN] {exp_err}")

    except AnnotationSchemaValidationError as err:
        print(f"\n[VALIDASI ERROR] {err}")
    except InsufficientDataForSplitError as err:
        print(f"\n[DATASET ERROR] {err}")
    except BaselineTrainingError as err:
        print(f"\n[TRAINING ERROR] {err}")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Pelatihan dibatalkan oleh pengguna.")


def handle_predict_dataset(
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
) -> None:
    """Handle menu option 6: Run multi-label inference on processed comments."""
    from src.config import PROCESSED_DATA_DIR
    from src.predict import (
        DEFAULT_REVIEW_THRESHOLD,
        EmptyInputDatasetError,
        ModelCompatibilityError,
        ModelNotFoundError,
        predict_processed_dataset,
    )

    print("\n--- [6] Prediksi Dataset Menggunakan Model Baseline ---")
    proc_files = sorted(
        list(PROCESSED_DATA_DIR.glob("comments_clean_*.csv")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    if not proc_files:
        print(f"[INFO] Tidak ada file hasil preprocessing di: {PROCESSED_DATA_DIR}")
        print("[INFO] Kumpulkan data (menu 1) atau jalankan preprocessing (menu 2) terlebih dahulu.")
        return

    print("Daftar file processed yang tersedia untuk diprediksi:")
    for idx, f in enumerate(proc_files, start=1):
        file_size_kb = f.stat().st_size / 1024
        print(f"  {idx}. {f.name} ({file_size_kb:.1f} KB)")

    try:
        choice = input_fn(
            f"\nPilih nomor file processed [1-{len(proc_files)}] (default 1, 0 untuk batal): "
        ).strip()
        if choice == "0":
            print("[INFO] Prediksi dibatalkan.")
            return

        choice_idx = 0
        if choice and choice.isdigit():
            choice_idx = int(choice) - 1
            if not (0 <= choice_idx < len(proc_files)):
                print("[ERROR] Nomor pilihan di luar rentang.")
                return

        selected_proc = proc_files[choice_idx]

        thresh_str = input_fn(
            f"Masukkan ambang batas review_threshold [0.0 - 1.0, default {DEFAULT_REVIEW_THRESHOLD}]: "
        ).strip()
        threshold = DEFAULT_REVIEW_THRESHOLD
        if thresh_str:
            try:
                val = float(thresh_str)
                if 0.0 <= val <= 1.0:
                    threshold = val
                else:
                    print("[PERINGATAN] Threshold harus antara 0.0 dan 1.0. Menggunakan default 0.60.")
            except ValueError:
                print("[PERINGATAN] Nilai tidak valid. Menggunakan default 0.60.")

        print(f"\n[INFO] Memuat model dan menjalankan prediksi pada: {selected_proc.name}...")
        result = predict_processed_dataset(
            processed_csv_path=selected_proc,
            review_threshold=threshold,
        )

        print("\n" + result.summary_text())
        print(f"\n[SUKSES] Hasil prediksi multi-label berhasil disimpan di:")
        print(f"  {result.output_csv_path}")

    except ModelNotFoundError as err:
        print(f"\n[MODEL ERROR] {err}")
    except ModelCompatibilityError as err:
        print(f"\n[COMPATIBILITY ERROR] {err}")
    except EmptyInputDatasetError as err:
        print(f"\n[INPUT ERROR] {err}")
    except (KeyboardInterrupt, EOFError):
        print("\n[INFO] Dibatalkan oleh pengguna.")


def handle_analyze_results(
    config: AppConfig,
    input_fn: Callable[[str], str] = input,
) -> None:
    """Handle menu option 7: Run statistical analysis across pipeline datasets and generate reports."""
    from src.analysis import run_comprehensive_analysis

    print("\n--- [7] Analisis Dataset & Laporan Hasil ---")
    print("[INFO] Mengumpulkan data dari folder RAW, Processed, Annotated, dan Predictions...")

    try:
        report = run_comprehensive_analysis()
        print("\n" + report.summary_text())
        print("\n[SUKSES] Laporan analisis dan berkas CSV berhasil disimpan di folder reports/.")

    except Exception as err:
        print(f"\n[ERROR ANALISIS] Terjadi kesalahan saat memproses laporan: {err}")


def run_cli(
    non_interactive: bool = False,
    input_fn: Callable[[str], str] = input,
    prompt_token_fn: Callable[[str], str] = getpass.getpass,
    collector_instance: BaseCollector | None = None,
    preprocess_fn: Callable[[Path, str], Path] | None = None,
) -> int:
    """Run the interactive terminal CLI loop.

    Args:
        non_interactive: If True, only prints banner and validates configuration.
        input_fn: Function to read user choice (mockable for testing).
        prompt_token_fn: Function to read masked token (mockable for testing).
        collector_instance: Optional injected BaseCollector instance.
        preprocess_fn: Optional injected preprocessing function.

    Returns:
        int: Exit status code (0 for clean exit).
    """
    ensure_directories()
    try:
        config = AppConfig.from_env()
    except ConfigValidationError as e:
        print(f"\n[FATAL] Kesalahan konfigurasi: {e}")
        return 1

    print_banner(config)

    if non_interactive:
        print("\nMode non-interaktif: Konfigurasi valid & CLI siap digunakan.")
        return 0

    while True:
        display_menu()
        try:
            choice = input_fn("Pilih menu [0-7]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nOperasi dibatalkan oleh pengguna. Keluar dengan aman.")
            return 0

        if choice == "0":
            print("\nKeluar dari program. Sampai jumpa!")
            return 0
        elif choice == "1":
            handle_collect_comments(
                config,
                input_fn=input_fn,
                prompt_token_fn=prompt_token_fn,
                collector_instance=collector_instance,
                preprocess_fn=preprocess_fn,
            )
        elif choice == "2":
            handle_run_nlp_on_raw(
                config,
                input_fn=input_fn,
                preprocess_fn=preprocess_fn,
            )
        elif choice == "3":
            handle_create_annotation_template(
                config,
                input_fn=input_fn,
            )
        elif choice == "4":
            handle_validate_annotations(
                config,
                input_fn=input_fn,
            )
        elif choice == "5":
            handle_train_baseline_model(
                config,
                input_fn=input_fn,
            )
        elif choice == "6":
            handle_predict_dataset(
                config,
                input_fn=input_fn,
            )
        elif choice == "7":
            handle_analyze_results(
                config,
                input_fn=input_fn,
            )
        else:
            print(f"\n[PERINGATAN] Pilihan '{choice}' tidak valid. Silakan pilih nomor menu 0 sampai 7.")
