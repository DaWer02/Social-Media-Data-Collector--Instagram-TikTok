<div align="center">

# Social Media Data Collector (Instagram & TikTok)

**Privacy-First Open-Source Comment Harvester for Linguistic Research & NLP Datasets**

<br>

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Browser%20Automation-green?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Chromium](https://img.shields.io/badge/Engine-Chromium-red?logo=googlechrome&logoColor=white)](https://www.chromium.org/)
[![Pandas](https://img.shields.io/badge/Data-Pandas%20%7C%20OpenPyXL-150458?logo=pandas&logoColor=white)](https://pandas.pydata.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Privacy Compliance](https://img.shields.io/badge/Privacy-UU%20PDP%20%26%20GDPR%20Ready-brightgreen)](https://github.com/)

</div>

Alat penarikan data (*data collector / comment harvester*) berbasis peramban otomatis (*browser automation*) untuk mengumpulkan komentar publik dari platform **Instagram** (Post & Reels) dan **TikTok** (Video & tautan pendek `vt.tiktok.com`).

Dirancang khusus dengan standar **Privacy by Design** yang mematuhi prinsip etika pengumpulan data dan perlindungan data pribadi (UU PDP Indonesia & GDPR):
* **Peniadaan Nama Akun**: File dataset hasil penarikan tidak mencantumkan nama akun/username pembuat komentar.
* **Sanitasi Mention**: Setiap pola `@nama_orang` di dalam teks komentar disanitasi menjadi `[@USER]`.
* **Masking PII**: Email dan nomor telepon yang tercantum dalam komentar otomatis disamarkan.
* **Format Ganda**: Data langsung disimpan dalam bentuk **CSV** (UTF-8) dan **Excel (.xlsx)**.

---

## 🛠️ Teknologi yang Digunakan (*Tech Stack*)

Proyek ini dibangun menggunakan teknologi dan pustaka modern untuk menjamin performa penarikan data yang stabil, tahan terhadap perubahan antarmuka platform, serta kepatuhan privasi yang ketat:

| Teknologi / Pustaka | Versi | Peran & Fungsi Utama |
| :--- | :--- | :--- |
| **Python** | `3.10+` | Bahasa pemrograman utama untuk logika inti, CLI interaktif, dan arsitektur pengumpulan data. |
| **Playwright** | `>=1.40.0` | Otomasi peramban web (*headless & headful*) untuk mengeksekusi scrolling dinamis, *event network interception*, dan ekspansi balasan komentar (*replies*). |
| **Chromium Engine** | *Bundled Playwright* | Mesin peramban untuk merender JavaScript kompleks, menangani verifikasi keamanan/CAPTCHA interaktif, dan menyimpan sesi profil lokal. |
| **Pandas** | `>=2.0.0` | Pemrosesan data tabular, deduplikasi komentar secara efisien, dan konversi format dataset. |
| **OpenPyXL** | `>=3.1.0` | Mesin serialisasi dan ekspor dataset ke dalam format berkas Microsoft Excel (`.xlsx`). |
| **Python-Dotenv** | `>=1.0.0` | Pengelolaan konfigurasi lingkungan dan variabel *runtime* lokal. |
| **Regex (Regular Expression)** | *Python Built-in* | Mesin pembersihan teks berbasis pola untuk menyamarkan `@mentions` $\rightarrow$ `[@USER]`, nomor telepon, dan email. |
| **Pytest** | `>=8.0.0` | Kerangka kerja pengujian unit otomatis (*automated testing*) untuk memastikan keandalan seluruh komponen sistem. |

---

## Fitur Utama

1. **Dukungan Multi-Platform Terpadu**:
   - Mendeteksi platform secara otomatis cukup dengan memasukkan tautan postingan/video.
   - Mendukung Instagram (`/p/`, `/reel/`, `/tv/`).
   - Mendukung TikTok (`/@user/video/`, `vt.tiktok.com`, `vm.tiktok.com`).
2. **Penanganan Verifikasi Manusia (CAPTCHA / Puzzle Slider)**:
   - Jika platform meminta verifikasi keamanan (puzzle penggeser / human check), program akan memberi petunjuk di terminal dan menjeda proses agar pengguna dapat menyelesaikannya di jendela browser yang terbuka sebelum melanjutkan penarikan data secara otomatis.
3. **Penyimpanan Sesi Lokal Aman**:
   - Sesi login disimpan secara lokal di folder `.browser_profile/` yang diabaikan oleh Git (`.gitignore`). Kredensial tidak pernah tersimpan di kode atau terunggah ke repositori.
4. **Scrolling & Balasan Komentar (Replies)**:
   - Mengambil komentar utama beserta ekspansi balasan (*reply threads*) secara otomatis hingga batas target tercapai.
5. **Jeda Ramah Server (Polite Jitter Rate-Limiting)**:
   - Memberikan jeda manusiawi antar aksi scroll untuk mencegah beban berlebih pada server penyedia layanan.

---

## Struktur Repositori

```text
├── .env.example              # Contoh konfigurasi lingkungan
├── .gitignore                 # Konfigurasi pengabaian file privat, cache, dan data
├── README.md                  # Dokumentasi proyek
├── requirements.txt           # Daftar dependensi utama
├── main.py                    # Titik masuk utama aplikasi (CLI & argumen)
├── src/
│   ├── collectors/
│   │   ├── __init__.py        # Ekspor modul kolektor
│   │   ├── base.py            # Model CommentRecord & antarmuka BaseCollector
│   │   ├── browser_nlp.py     # Kolektor peramban Instagram
│   │   ├── tiktok.py          # Kolektor peramban TikTok
│   │   └── unified.py         # Detektor platform otomatis & router penarikan
│   ├── privacy.py             # Modul kepatuhan privasi (sanitasi mention & PII)
│   ├── storage.py             # Penyimpanan dataset (CSV & Excel) bebas PII
│   ├── config.py              # Konfigurasi path, batas komentar, dan profil
│   └── cli.py                 # Antarmuka CLI terminal interaktif
└── tests/
    ├── test_privacy.py        # Pengujian sanitasi mention & PII
    ├── test_unified_collector.py # Pengujian parser URL Instagram & TikTok
    ├── test_storage_export.py # Pengujian ekspor CSV & Excel bebas username
    └── test_cli.py            # Pengujian navigasi CLI terminal
```

---

## Panduan Instalasi

### 1. Prasyarat
* Python versi 3.10 atau yang lebih baru.
* Sistem Operasi: Windows, macOS, atau Linux.

### 2. Kloning & Pasang Dependensi
```bash
# Pasang paket dependensi Python
pip install -r requirements.txt

# Pasang browser Chromium untuk Playwright
playwright install chromium
```

---

## Panduan Penggunaan

### Mode Interaktif (Menu CLI)

Mode interaktif sangat cocok untuk pengguna yang ingin panduan langkah demi langkah langsung di terminal.

#### 1. Jalankan Program
Buka terminal (Command Prompt, PowerShell, atau Terminal Linux/macOS) pada folder proyek, lalu jalankan:
```bash
python main.py
```
Layar akan menampilkan banner dan menu navigasi:
```text
================================================================
       SOCIAL MEDIA DATA COLLECTOR (INSTAGRAM & TIKTOK)
       Privacy-First Comment Harvesting for NLP & Research
================================================================
 Target Komentar Default : 300 komentar
 Kepatuhan Privasi       : AKTIF (Nama Akun Disembunyikan & PII Dimask)
 Profil Browser Lokal    : .browser_profile
================================================================

Menu Utama:
  1. Kumpulkan komentar (Instagram / TikTok)
  2. Buka browser untuk login Instagram (Opsional)
  3. Buka browser untuk login TikTok (Opsional)
  4. Cek status profil browser lokal
  0. Keluar
----------------------------------------------------------------
Pilih menu [0-4]: 
```

#### 2. Alur Pengumpulan Komentar (Langkah Demi Langkah Menu 1)

1. **Pilih Menu 1**:
   Ketik `1` lalu tekan `[Enter]`.
2. **Masukkan URL Postingan / Video**:
   Tempel (*paste*) tautan postingan Instagram atau video TikTok yang ingin diambil komentarnya.
   ```text
   Masukkan URL postingan atau video (0 untuk batal): https://www.instagram.com/p/DF123abc/
   ```
   *Sistem akan otomatis mendeteksi platform (`[TERDETEKSI] Platform: INSTAGRAM` atau `TIKTOK`).*
3. **Tentukan Jumlah Target Komentar**:
   Ketik angka jumlah komentar yang ingin diambil (contoh: `500`), atau langsung tekan `[Enter]` untuk menggunakan nilai *default* (300).
   ```text
   Jumlah target komentar [Enter: 300]: 500
   ```
4. **Pilih Format File Penyimpanan**:
   Pilih format berkas yang diinginkan:
   ```text
   Pilih format penyimpanan:
     1. Keduanya (CSV & Excel .xlsx) [Default]
     2. CSV saja
     3. Excel (.xlsx) saja
   Pilihan format [1/2/3]: 1
   ```
5. **Proses Penarikan Otomatis**:
   Browser akan terbuka dan otomatis menggulir (*scroll*) halaman serta membuka balasan komentar (*replies*). Terminal menampilkan progres penarikan secara *real-time*:
   ```text
   [INFO] + [1/500] Pendapat publik yang sangat menarik...
   [INFO] + [2/500] [@USER] sepakat sekali dengan narasi ini...
   ```
   *(Opsional jika muncul CAPTCHA)*: Jika platform memunculkan teka-teki geser (*puzzle slider*), cukup selesaikan teka-teki di jendela browser, lalu tekan `[Enter]` di terminal untuk melanjutkan pengumpulan otomatis.
6. **Selesai & File Siap Digunakan**:
   Setelah target tercapai, terminal menampilkan laporan ringkasan beserta lokasi lengkap file hasil ekspor:
   ```text
   ================================================================
                PENARIKAN DATA SELESAI
   ================================================================
    Platform             : INSTAGRAM
    ID Media/Konten      : DF123abc
    Total Komentar       : 500
    Standar Privasi      : Memenuhi UU PDP / GDPR (Tanpa Nama Akun)
    Berkas CSV           : D:\WEBKU\NLP\data\raw\comments_20261121_220928_b0061e.csv
    Berkas Excel         : D:\WEBKU\NLP\data\raw\comments_20261121_220928_b0061e.xlsx
   ================================================================
   ```
   Tekan `[Enter]` untuk kembali ke menu utama, atau ketik `0` untuk keluar.

---

#### 3. Menu Lainnya (Bantuan Login & Profil)
* **Menu 2 & 3 (Login Instagram / TikTok)**: Digunakan jika platform membatasi komentar untuk pengguna non-login. Jendela browser akan terbuka agar Anda dapat login sekali saja. Sesi login akan tersimpan permanen di folder lokal `.browser_profile/` sehingga penarikan selanjutnya tidak perlu login lagi.
* **Menu 4 (Cek Status Profil)**: Melihat apakah folder sesi browser lokal Anda sudah aktif dan terkonfigurasi dengan aman.

### Mode Langsung dengan Argumen (Command-Line)
Anda juga dapat menjalankan penarikan data secara langsung tanpa masuk ke menu:

**Penarikan Komentar Instagram:**
```bash
python main.py --url "https://www.instagram.com/p/ABC123xyz/" --limit 300 --format both
```

**Penarikan Komentar TikTok:**
```bash
python main.py --url "https://vt.tiktok.com/ZSxyz123/" --limit 500 --format both
```

**Buka Browser untuk Login Sekali (Sesi Tersimpan Lokal):**
```bash
python main.py --login-instagram
# atau
python main.py --login-tiktok
```

**Cek Status Profil Browser:**
```bash
python main.py --status
```

---

## Struktur Data Hasil Penarikan

Hasil penarikan tersimpan di direktori `data/raw/` dengan penamaan `comments_<RUN_ID>.csv` dan `comments_<RUN_ID>.xlsx`.

Kolom data yang dihasilkan:
| Nama Kolom | Deskripsi | Standar Privasi |
| :--- | :--- | :--- |
| `comment_id` | ID unik internal komentar | Anonim / Terenkripsi |
| `media_id` | ID postingan / video asal | Publik |
| `comment_text` | Isi teks komentar | Mention `@user` disanitasi menjadi `[@USER]` |
| `timestamp` | Waktu pembuatan komentar | Format ISO 8601 UTC |
| `like_count` | Jumlah suka (*likes*) | Metrik publik numerik |
| `collected_at` | Waktu pengambilan data | Format ISO 8601 UTC |
| `source_type` | Platform asal pengumpulan data | `instagram` / `tiktok` |

> Kolom nama pengguna (`username`, `author`, `user_id`) **TIDAK PERNAH DISIMPAN** demi menjaga privasi pengguna media sosial.

---

## Pengujian (Testing)

Jalankan test suite untuk memastikan seluruh fungsi berjalan dengan baik:
```bash
pytest tests/
```

---

## Etika & Batasan Hukum

* Alat ini dibuat untuk tujuan **penelitian akademis, kajian linguistik, dan analisis sentimen publik**.
* Pengguna bertanggung jawab penuh untuk mematuhi ketentuan layanan (*Terms of Service*) masing-masing platform.
* Dilarang menggunakan alat ini untuk aktivitas *spamming*, peretasan, pelecehan (*harassment*), atau pengumpulan data pribadi ilegal.
