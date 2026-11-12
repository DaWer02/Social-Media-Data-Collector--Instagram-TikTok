"""Interactive navigation for the REDAM dataset pipeline."""
from __future__ import annotations

import getpass
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from . import pipeline

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data" / "redam"


def ask_path(prompt: str, input_fn: Callable[[str], str], default: Path | None = None) -> Path | None:
    suffix = f" [Enter: {default}]" if default else " (kosong untuk batal)"
    value = input_fn(prompt + suffix + ": ").strip().strip('"').strip("'")
    if value == "0":
        return None
    if not value:
        return default
    path = Path(value).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


def choose_package(root: Path, input_fn: Callable[[str], str]) -> Path | None:
    packages = sorted(p.parent for p in root.rglob("cases.json")) if root.exists() else []
    print("\nPaket dataset lokal:")
    for number, package in enumerate(packages, 1):
        print(f"  {number}. {package}")
    if not packages:
        print("  Belum ada paket. Pilih menu 3 untuk menyiapkan dataset.")
    print("  P. Masukkan path paket lain\n  0. Batal")
    value = input_fn("Pilih paket: ").strip()
    if value.lower() == "p":
        return ask_path("Folder paket", input_fn)
    if not value or value == "0":
        return None
    if value.isdigit() and 1 <= int(value) <= len(packages):
        return packages[int(value) - 1]
    print("[PERINGATAN] Pilihan paket tidak valid.")
    return None


def ensure_secret(secret_fn: Callable[[str], str]) -> bool:
    if len(os.environ.get("REDAM_DATASET_SECRET", "")) >= 32:
        return True
    print("Pseudonimisasi memerlukan secret minimal 32 karakter. Input disembunyikan;")
    print("secret hanya disimpan di sesi proses. Simpan sendiri secara aman untuk reproduksi.")
    value = secret_fn("Secret dataset (kosong untuk batal): ")
    if len(value) < 32:
        print("[BATAL] Secret belum diisi atau kurang dari 32 karakter.")
        return False
    os.environ["REDAM_DATASET_SECRET"] = value
    return True


def show_validation(result: dict) -> None:
    print(f"\nKasus: {result['case_count']} | Komentar: {result['comment_count']}")
    print(f"Weighted kappa: {result['weighted_kappa']}")
    print("Anotasi valid: " + ("YA" if result["annotations_valid"] else "BELUM"))
    for error in result["errors"]:
        print("  - " + error)
    print("Status siap latih hanya diberikan setelah menu Rilis berhasil.")


def run_menu(input_fn: Callable[[str], str] = input,
             secret_fn: Callable[[str], str] = getpass.getpass,
             data_dir: Path | None = None) -> int:
    root = data_dir or DATA_DIR
    while True:
        print("\n" + "=" * 64)
        print("REDAM.id - Pengumpulan dan Penyiapan Dataset")
        print("=" * 64)
        print("  1. Buat data DEMO sintetis (12 kasus / 509 komentar)")
        print("  2. Kumpulkan komentar browser Playwright (URL langsung -> CSV)")
        print("  3. Impor / bersihkan dataset dan buat template anotasi")
        print("  4. Lihat lokasi anotasi dan panduan penilaian")
        print("  5. Validasi paket dan anotasi")
        print("  6. Rilis dataset train / validation / test")
        print("  7. Lihat paket dataset lokal")
        print("  8. Panduan alur REDAM")
        print("  0. Kembali / keluar")
        try:
            choice = input_fn("Pilih menu REDAM [0-8]: ").strip()
            if choice == "0":
                return 0
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6]
            if choice == "1":
                output = ask_path("Folder baru untuk sumber DEMO", input_fn, root / f"demo_source_{stamp}")
                if output is not None:
                    result = pipeline.demo(output)
                    print(f"[SUKSES] {result['cases']} kasus / {result['comments']} komentar sintetis.")
                    print(f"Manifest: {output / 'manifest.json'}")
                    print("Lanjutkan menu 3 menggunakan manifest tersebut. Belum berlabel manusia.")
            elif choice == "2":
                raw_input = input_fn("Masukkan URL postingan (Instagram / TikTok) [atau path file manifest JSON, 0 untuk batal]: ").strip().strip('"').strip("'")
                if not raw_input or raw_input == "0":
                    continue
                # If user entered a .json file path, use legacy manifest collection
                if raw_input.lower().endswith(".json"):
                    manifest_path = Path(raw_input).expanduser()
                    manifest_path = manifest_path if manifest_path.is_absolute() else BASE_DIR / manifest_path
                    if not manifest_path.is_file():
                        print("[ERROR] File manifest tidak ditemukan.")
                        continue
                    output = ask_path("Folder keluaran baru", input_fn, root / f"collection_{stamp}")
                    if output is None or not ensure_secret(secret_fn):
                        continue
                    from .collect import collect
                    result = collect(manifest_path, output)
                    print(json.dumps(result, ensure_ascii=True, indent=2))
                    print(f"Laporan koleksi: {output / 'collection_report.json'}")
                else:
                    # Direct URL collection with Playwright -> CSV (like Main Menu 1)
                    from .collect import collect_browser_comments_to_csv, extract_clean_url
                    target_url = extract_clean_url(raw_input)
                    if target_url != raw_input.strip():
                        print(f"[INFO] Tautan dibersihkan (nama akun/teks pembuka dilewati): {target_url}")
                    limit_str = input_fn("Target jumlah komentar [default: 300, tekan Enter untuk default]: ").strip()
                    limit = int(limit_str) if limit_str.isdigit() and int(limit_str) > 0 else 300
                    default_csv = root / "raw" / f"comments_{stamp}.csv"
                    csv_path = ask_path("Lokasi file CSV output", input_fn, default_csv)
                    if csv_path is None:
                        continue
                    result = collect_browser_comments_to_csv(
                        target_url=target_url,
                        output_csv_path=csv_path,
                        limit=limit,
                        headless=False,
                        input_fn=input_fn,
                        include_usernames=False,
                    )
                    print("\n" + "=" * 64)
                    print("          PENGUMPULAN KOMENTAR SELESAI")
                    print("=" * 64)
                    print(f"URL Target       : {result['url']}")
                    print(f"Platform         : {result['platform']}")
                    print(f"Total Terkumpul  : {result['total_collected']} komentar")
                    print(f"File CSV Hasil   : {result['csv_path']}")
                    if result.get("manifest_path"):
                        print(f"Manifest REDAM   : {result['manifest_path']}")
                    print("=" * 64)
                    if result['total_collected'] == 0:
                        print("\n[PERINGATAN] Tidak ada komentar yang berhasil dikumpulkan.")
                        print("Pastikan pemeriksaan keamanan/cek human telah diselesaikan di browser.")
                    else:
                        print("[INFO] File CSV siap digunakan untuk Menu 3 REDAM (Anotasi) atau Menu Utama 2 (NLP).")
            elif choice == "3":
                manifest = ask_path("Path file manifest JSON", input_fn)
                if manifest is None:
                    continue
                if not manifest.is_file():
                    print("[ERROR] File manifest tidak ditemukan.")
                    continue
                output = ask_path("Folder keluaran baru", input_fn, root / f"package_{stamp}")
                if output is None or not ensure_secret(secret_fn):
                    continue
                result = pipeline.prepare(manifest, output)
                print(f"[SUKSES] {result['cases']} kasus / {result['comments']} komentar disiapkan.")
                print(f"Paket: {output}\nStatus: menunggu anotasi manusia (menu 4).")
            elif choice in {"4", "5", "6", "7"}:
                package = choose_package(root, input_fn)
                if package is None:
                    continue
                if choice == "4":
                    print("Dua penilai mengisi annotations.csv secara independen; konflik diselesaikan penilai ketiga.")
                    for name in ["comments.json", "annotations.csv", "adjudications.csv", "pairs.csv", "clusters.csv", "audit.template.json"]:
                        print(f"  {name}: {package / name}")
                    print(f"Pedoman: {BASE_DIR / 'docs' / 'REDAM_ANNOTATION_GUIDE.md'}")
                    print("pairs.csv dan clusters.csv adalah persiapan tugas lanjutan; rilis v1 untuk label kasus.")
                elif choice == "5":
                    show_validation(pipeline.validate(package)[0])
                elif choice == "6":
                    audit = ask_path("File audit yang telah diisi reviewer", input_fn, package / "audit.json")
                    if audit is None:
                        continue
                    output = ask_path("Folder rilis baru", input_fn, root / "releases" / f"release_{stamp}")
                    if output is not None:
                        pipeline.release(package, output, audit)
                        print(f"[SUKSES] Dataset kasus siap latih: {output}")
                        print("Format: train.jsonl, validation.jsonl, test.jsonl; lihat dataset_card.md.")
                else:
                    cases = pipeline.read_json(package / "cases.json")
                    print(f"\nPaket: {package}\nKasus: {len(cases)}")
                    print(f"Komentar valid: {sum(c['comments_valid'] for c in cases)}")
                    print("Asal: " + ", ".join(sorted({c['origin'] for c in cases})))
                    print("Kesiapan belum diperiksa ulang. Gunakan menu 5, kemudian menu 6.")
            elif choice == "8":
                print("\nAlur: manifest sumber -> koleksi/impor -> anotasi A/B -> adjudikasi -> validasi -> audit -> rilis.")
                print("Untuk mencoba: menu 1 -> menu 3 -> menu 4 -> menu 5.")
                print("Data sintetis hanya DEMO dan tidak dapat dirilis sebagai dataset riset.")
                print("Koleksi browser memerlukan manifest URL, reviewer akses dan lokator teruji.")
                print("Masukkan 0 pada prompt path untuk batal; path relatif dihitung dari root proyek.")
                print(f"Panduan dan contoh manifest: {BASE_DIR / 'docs' / 'REDAM_DATASET.md'}")
            else:
                print("[PERINGATAN] Pilihan tidak valid. Pilih nomor 0 sampai 8.")
        except (KeyboardInterrupt, EOFError):
            print("\nMenu REDAM ditutup dengan aman.")
            return 0
        except (ValueError, OSError, KeyError, TypeError, ImportError) as exc:
            print(f"[ERROR] {exc}")
            print("Periksa input dan coba kembali; folder yang sudah ada tidak ditimpa.")
