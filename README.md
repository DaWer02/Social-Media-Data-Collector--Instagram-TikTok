# Instagram Slang NLP — Windows CLI Pipeline

> Pipeline Command Line Interface (CLI) berbasis Python untuk sistem operasi Windows (CMD & PowerShell) guna mengumpulkan komentar Instagram melalui Meta Graph API resmi/berizin, menyimpan dataset mentah (RAW) secara *immutable*, meminta konfirmasi eksplisit sebelum tahap pemrosesan NLP, serta memfasilitasi preprocessing konservatif, anotasi manual terstandardisasi, pelatihan model baseline multi-label (TF-IDF + One-vs-Rest Logistic Regression dengan GroupSplit), inferensi terisolasi, dan analisis distribusi linguistik.

[![Test Suite](https://img.shields.io/badge/tests-106%20passed-brightgreen.svg)](#8-pengujian-otomatis-test-suite)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](#3-instalasi-di-windows-cmd--powershell)
[![Platform](https://img.shields.io/badge/platform-Windows%20CMD%20%7C%20PowerShell-lightgrey.svg)](#3-instalasi-di-windows-cmd--powershell)
[![Meta Graph API](https://img.shields.io/badge/Meta%20Graph%20API-v21.0-blue.svg)](#4-panduan-meta-graph-api--konfigurasi-token)

---

## Daftar Isi

1. [Tujuan, Batasan Arsitektural, dan Alur Kerja](#1-tujuan-batasan-arsitektural-dan-alur-kerja)
2. [Perbedaan URL vs Media ID & Batasan Akses Data](#2-perbedaan-url-vs-media-id--batasan-akses-data)
3. [Instalasi di Windows (CMD & PowerShell)](#3-instalasi-di-windows-cmd--powershell)
4. [Panduan Meta Graph API & Konfigurasi Token](#4-panduan-meta-graph-api--konfigurasi-token)
5. [Contoh Eksekusi & Tampilan Output Terminal CLI](#5-contoh-eksekusi--tampilan-output-terminal-cli)
6. [Kamus Data & Skema Kolom Lengkap](#6-kamus-data--skema-kolom-lengkap)
7. [Taksonomi Label & Pedoman Anotasi Manual](#7-taksonomi-label--pedoman-anotasi-manual)
8. [Pengujian Otomatis (Test Suite)](#8-pengujian-otomatis-test-suite)
9. [Interpretasi Metrik Evaluasi & Keterbatasan Statistik](#9-interpretasi-metrik-evaluasi--keterbatasan-statistik)
10. [Keamanan Token, Privasi Data, Retensi, & Kepatuhan](#10-keamanan-token-privasi-data-retensi--kepatuhan)
11. [Eksperimen Model Bahasa Indonesia Pra-latih (IndoBERT)](#11-eksperimen-model-bahasa-indonesia-pra-latih-indobert)
12. [Daftar Fitur yang Belum Diimplementasikan](#12-daftar-fitur-yang-belum-diimplementasikan)
13. [Struktur Direktori Proyek](#13-struktur-direktori-proyek)

---

## 1. Tujuan, Batasan Arsitektural, dan Alur Kerja

### Tujuan Proyek
Proyek ini dikembangkan untuk kebutuhan penelitian linguistik komputasional dan pemrosesan bahasa alami (NLP) pada komentar Instagram berbahasa Indonesia. Tujuan utamanya meliputi:
- Mengumpulkan komentar media sosial melalui jalur resmi yang dapat dipertanggungjawabkan secara etik dan hukum.
- Mencegah kontaminasi data mentah melalui penyimpanan dataset RAW yang bersifat *immutable* (tidak dapat ditimpa).
- Memberikan kendali penuh kepada peneliti melalui konfirmasi interaktif sebelum melanjutkan ke proses NLP.
- Menyediakan alur anotasi manusia (*human-in-the-loop*) yang non-destruktif dan tervalidasi secara ketat.
- Melatih model baseline multi-label untuk mengklasifikasikan:
  1. **Bentuk Slang:** `akronim`, `singkatan`, `bahasa_asing`, `plesetan`, `pemendekan`, `tidak_ada`, `lainnya`.
  2. **Fungsi Bahasa:** `emotif`, `referensial`, `konatif`, `tidak_jelas`.
- Menyajikan evaluasi objektif bebas kebocoran data (*data leakage*) antar postingan serta laporan statistik distribusi linguistik.

### Batasan Arsitektural & Etika Platform
1. **Kepatuhan Meta Platform Terms of Service:**  
   Program ini **TIDAK MENGGUNAKAN** teknik *web scraping* HTML (seperti BeautifulSoup, Selenium, Puppeteer, atau Playwright) yang melanggar ketentuan Meta. Program ini sepenuhnya menggunakan Meta Graph API resmi (v21.0).
2. **Tidak Ada Bypass Akses:**  
   Program tidak memfasilitasi *credential stuffing*, pembobolan akun privat, bypass CAPTCHA, atau manipulasi *rate limit*. Jika Meta menolak izin akses (HTTP 401/403/429), sistem berhenti dengan aman (*fail-safe*) dan mencatat petunjuk solusi resmi.
3. **Validitas Ilmiah Anotasi:**  
   Sistem menolak melakukan *auto-labeling* atau pelabelan otomatis berbasis kamus slang tanpa tinjauan manusia. Label acuan (*ground truth*) wajib divalidasi oleh peneliti.

### Alur Kerja Program

```text
[1. Kumpulkan Komentar] ──> Masukkan URL / Media ID ──> Validasi Akses API Meta
                                                                  │
                                                                  ▼
                                                      Simpan data/raw/comments_<run_id>.csv
                                                      Simpan reports/run_<run_id>.json
                                                                  │
                                                                  ▼
                                                [Konfirmasi: Lanjutkan ke NLP? [y/N]]
                                                        │                     │
                                              Jawaban 'N' / Enter         Jawaban 'y'
                                                        │                     │
                                                        ▼                     ▼
                                                Status nlp_declined   [Preprocessing Saja]
                                                (Program Berhenti)            │
                                                                              ▼
                                                                  data/processed/comments_clean_<run_id>.csv
                                                                              │
                                                                              ▼
[3. Buat Template Anotasi] <──────────────────────────────────────────────────┘
            │
            ▼
data/annotated/comments_labeled.csv ──> Anotasi Manual oleh Peneliti
            │
            ▼
[4. Validasi Anotasi] ──> Lolos Validasi Konsistensi
                                  │
                                  ▼
[5. Latih Model Baseline] ──> GroupSplit by media_id (Zero Leakage)
                                  │
                                  ├──> models/baseline_slang_model.joblib
                                  ├──> models/baseline_functions_model.joblib
                                  ├──> models/tfidf_vectorizer.joblib
                                  └──> reports/evaluation_metrics.csv
                                  │
        ┌─────────────────────────┴────────────────────────┐
        ▼                                                  ▼
[6. Prediksi Dataset Baru]                        [7. Analisis Hasil]
        │                                                  │
        ▼                                                  ▼
data/predictions/comments_predictions_<run_id>.csv    Laporan CSV/MD & Grafik PNG
```

---

## 2. Perbedaan URL vs Media ID & Batasan Akses Data

| Aspek | URL Postingan Instagram | Media ID Meta Graph API |
|---|---|---|
| **Contoh Nilai** | `https://www.instagram.com/p/C_abc123/` atau `/reel/D_xyz987/` | `17970528943031455` (string numerik) |
| **Definisi** | Tautan web publik yang memuat *shortcode* postingan. | Pengenal unik internal dalam basis data Meta Platform. |
| **Mekanisme Resolusi** | Sistem mengekstrak *shortcode*, lalu mencocokkannya dengan daftar postingan milik akun profesional Anda via endpoint resmi `GET /me/media`. | Langsung digunakan untuk meminta endpoint `GET /{media-id}/comments`. |
| **Akses Akun Pihak Ketiga** | **TIDAK DIDUKUNG OLEH META GRAPH API.** Meta tidak mengizinkan pembacaan komentar publik dari akun orang lain tanpa otorisasi token akun tersebut. | Hanya berlaku untuk media yang berada di bawah kepemilikan akun pengembang/profesional yang terotorisasi. |

> [!IMPORTANT]
> Jika URL postingan yang Anda masukkan bukan milik akun Profesional Anda sendiri, sistem akan menolak dengan error `MediaUnavailableError` dan meminta Anda memasukkan Media ID numerik langsung dari akun Anda atau menggunakan dataset berizin yang telah diekspor secara sah.

---

## 3. Instalasi di Windows (CMD & PowerShell)

### Langkah 1: Pasang Python di Windows
1. Unduh installer resmi **Python 3.11 atau 3.12 (64-bit)** dari [python.org](https://www.python.org/downloads/windows/).
2. **PENTING:** Saat jendela instalasi terbuka, centang kotak **"Add python.exe to PATH"** sebelum mengklik *Install Now*.
3. Buka **Command Prompt (CMD)** atau **Windows PowerShell**, lalu verifikasi instalasi:
   ```cmd
   python --version
   where python
   ```
   *Pastikan versi Python minimal 3.10 (proyek ini diuji pada Python 3.11.9).*

### Langkah 2: Buat Virtual Environment
Buka folder proyek di Windows:
```cmd
cd /d d:\WEBKU\NLP
```

Buat lingkungan virtual terisolasi bernama `.venv`:
```cmd
python -m venv .venv
```

### Langkah 3: Aktifkan Virtual Environment
- **Jika menggunakan Command Prompt (CMD):**
  ```cmd
  .venv\Scripts\activate.bat
  ```
- **Jika menggunakan Windows PowerShell:**
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
  *Catatan untuk PowerShell:* Jika muncul pesan error *execution policy*, jalankan perintah izin sekali saja:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  .\.venv\Scripts\Activate.ps1
  ```
  *(Tanda `(.venv)` akan muncul di awal baris perintah terminal).*

### Langkah 4: Instal Dependensi Proyek
Tingkatkan pip dan instal seluruh paket dependensi:
```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Paket utama yang terpasang:
- `requests`: HTTP client resmi untuk komunikasi dengan Meta Graph API.
- `python-dotenv`: Pengelolaan variabel lingkungan `.env`.
- `scikit-learn`: Pelatihan baseline Logistic Regression OvR & TF-IDF Vectorizer.
- `joblib`: Serialisasi artefak model machine learning.
- `matplotlib`: Pembangkitan grafik visualisasi distribusi bentuk slang dan fungsi bahasa.
- `pytest`: Framework pengujian unit dan integrasi.

---

## 4. Panduan Meta Graph API & Konfigurasi Token

Untuk mengumpulkan komentar secara langsung dari Instagram, Anda memerlukan Access Token resmi dari Meta for Developers.

### Pilihan Varian API Meta
Aplikasi ini mendukung dua varian resmi Meta yang dikonfigurasi melalui `INSTAGRAM_API_VARIANT`:
1. **`facebook_login` (Rekomendasi Default):**
   - Host Base URL: `https://graph.facebook.com/v21.0/`
   - Membutuhkan akun Instagram Business/Creator yang ditautkan ke Facebook Page.
   - Izin yang dibutuhkan: `instagram_basic`, `instagram_manage_comments`, `pages_show_list`, `pages_read_engagement`.
2. **`instagram_login`:**
   - Host Base URL: `https://graph.instagram.com/v21.0/`
   - Menggunakan Instagram User Access Token langsung untuk akun Business/Creator mandiri.
   - Izin yang dibutuhkan: `instagram_business_basic`, `instagram_business_manage_comments`.

### Langkah Memperoleh Token Resmi
1. Masuk ke [Meta for Developers](https://developers.facebook.com/) dengan akun Anda.
2. Buat App baru: Pilih **Create App** $\rightarrow$ Jenis **Other** $\rightarrow$ Tipe **Business**.
3. Pastikan akun Instagram target telah diubah ke tipe **Profesional (Business atau Creator)** melalui aplikasi ponsel (gratis).
4. Hubungkan akun Instagram tersebut ke Facebook Page yang Anda kelola.
5. Buka [Graph API Explorer](https://developers.facebook.com/tools/explorer/).
6. Pilih App Anda, klik menu dropdown **User or Page**, pilih **User Token**, lalu tambahkan izin:
   - `instagram_basic`
   - `instagram_manage_comments`
   - `pages_show_list`
   - `pages_read_engagement`
7. Klik **Generate Access Token** dan setujui dialog otorisasi Meta.
8. Salin token yang dihasilkan ke file konfigurasi lokal.

### Setup File `.env`
Salin template konfigurasi:
```cmd
copy .env.example .env
```
Buka file `.env` menggunakan teks editor (misalnya Notepad), lalu isi:
```dotenv
# Kredensial Meta Graph API (JANGAN COMMIT FILE INI KE GIT!)
INSTAGRAM_ACCESS_TOKEN=EAAB...masukkan_token_di_sini...

# Konfigurasi Varian API & Versi
INSTAGRAM_API_VARIANT=facebook_login
GRAPH_API_VERSION=v21.0

# Target Jumlah Komentar Maksimum (Default: 3000)
TARGET_COMMENTS=3000

# Konfigurasi Runtime
APP_ENV=development
LOG_LEVEL=INFO
```

---

## 5. Contoh Eksekusi & Tampilan Output Terminal CLI

Jalankan program utama melalui terminal:
```cmd
python main.py
```
Atau untuk memeriksa kesiapan status konfigurasi tanpa masuk ke menu interaktif:
```cmd
python main.py --status
```

### Tampilan Menu Utama CLI
```text
================================================================
       INSTAGRAM SLANG NLP PIPELINE - WINDOWS CLI
================================================================
 Lingkungan      : development
 Target Default  : 3000 komentar
 Versi Graph API : v21.0
 Varian API      : facebook_login
 Access Token    : EAAm...Ukbw
================================================================

Menu Utama:
  1. Kumpulkan komentar Instagram
  2. Jalankan NLP pada RAW yang sudah ada
  3. Buat template anotasi
  4. Validasi anotasi
  5. Latih model baseline
  6. Prediksi dataset
  7. Analisis hasil
  0. Keluar
----------------------------------------------------------------
Pilih menu [0-7]: 
```

---

### Contoh Alur Menu 1: Pengumpulan, Penyimpanan RAW, & Prompt [y/N]

#### Skenario A: Pengguna Menolak Lanjut ke NLP (Tekan Enter atau `n`)
```text
--- Tahap 1: Pengumpulan Komentar Instagram ---
Masukkan URL Postingan atau Media ID: 17970528943031455
Target jumlah komentar [default 3000]: 100

Menghubungkan ke Meta Graph API v21.0...
Mengumpulkan komentar dari Media ID 17970528943031455...
Selesai mengumpulkan komentar. Total unik: 100

================================================================
HASIL PENGUMPULAN DATA MENTAH (RAW)
================================================================
 Media ID Terproses : 17970528943031455
 Total Dikumpulkan  : 100 komentar unik
 Error / Kendala    : Tidak ada
 File RAW Tersimpan : d:\WEBKU\NLP\data\raw\comments_20261027_210528_da0dcc.csv
 Checksum SHA256    : 4b9c5a17d848261e...
 Metadata Run JSON  : d:\WEBKU\NLP\reports\run_20261027_210528_da0dcc.json
================================================================

Lanjutkan ke tahap NLP sekarang? [y/N]: 

Proses NLP dihentikan atas permintaan pengguna (status: nlp_declined).
Dataset RAW Anda tersimpan aman dan tidak disentuh.
Kembali ke menu utama.
```

#### Skenario B: Pengguna Menyetujui Lanjut (`y`) $\rightarrow$ Preprocessing Saja
```text
Lanjutkan ke tahap NLP sekarang? [y/N]: y

Memulai tahap preprocessing pada dataset RAW...

================================================================
LAPORAN PREPROCESSING DATASET
================================================================
 File RAW Sumber      : comments_20261027_210845_a196d7.csv
 File Hasil Bersih    : d:\WEBKU\NLP\data\processed\comments_clean_20261027_210845_a196d7.csv
 Total Komentar Awal  : 100
 Komentar Kosong      : 0
 Komentar Duplikat    : 0
 Komentar Bersih Akhir: 100
 Kolom Hilang         : Tidak ada
================================================================
Tahap preprocessing selesai. Dataset siap untuk dianotasi atau diinferensi.
```

---

### Contoh Alur Menu 2: Menjalankan NLP pada RAW yang Sudah Ada
Menu ini memproses ulang file mentah di `data/raw/` tanpa memanggil API Meta kembali:
```text
--- Jalankan Preprocessing pada RAW yang Sudah Ada ---
Daftar file RAW yang tersedia:
  [1] comments_20261027_210528_da0dcc.csv (100 baris)
  [2] comments_20261027_210845_a196d7.csv (100 baris)
Pilih nomor file RAW yang akan diproses [1-2]: 1

Memproses file: comments_20261027_210528_da0dcc.csv...
Preprocessing selesai. Disimpan di: data/processed/comments_clean_20261027_210528_da0dcc.csv
```

---

### Contoh Alur Menu 3: Pembuatan Template Anotasi
Menggabungkan data processed terbaru dengan anotasi yang sudah ada tanpa menimpa label manual:
```text
--- Pembuatan Template Dataset Anotasi ---
Pilih file processed sumber:
  [1] comments_clean_20261027_210845_a196d7.csv
Pilih nomor file [1]: 1

Membuat template anotasi...
Template anotasi berhasil dibuat/diperbarui!
Lokasi file : d:\WEBKU\NLP\data\annotated\comments_labeled.csv
Total baris : 100 baris (30 selesai ditinjau, 70 belum ditinjau)
Label manual yang sudah ada sebelumnya tetap dipertahankan utuh.
```

---

### Contoh Alur Menu 4: Validasi Anotasi
```text
--- Validasi Kualitas Dataset Anotasi ---
Memvalidasi d:\WEBKU\NLP\data\annotated\comments_labeled.csv...

Status Validasi: LULUS (VALID)
- Total Komentar            : 100
- Selesai Ditinjau Manusia  : 80
- Belum Selesai Ditinjau    : 20
- Label Bentuk Slang Valid  : 100% sesuai taksonomi
- Label Fungsi Bahasa Valid : 100% sesuai taksonomi
- Duplikasi ID Komentar     : 0
- Konsistensi Slang Present : 100% konsisten (slang_present=tidak -> tidak_ada)
Dataset memenuhi syarat untuk digunakan dalam pelatihan model baseline!
```

---

### Contoh Alur Menu 5: Pelatihan Model Baseline NLP
```text
--- Pelatihan Model Baseline NLP ---
Memuat data dari data/annotated/comments_labeled.csv...
Jumlah komentar berlabel selesai: 80 baris dari 4 postingan berbeda.
Melakukan GroupSplit berdasarkan media_id (Test size: 30%, Train: 3 postingan, Test: 1 postingan)...

Fitting TF-IDF Vectorizer HANYA pada data latih (Zero Leakage)...
Melatih model bentuk slang (OneVsRest LogisticRegression)...
Melatih model fungsi bahasa (OneVsRest LogisticRegression)...

================================================================
EVALUASI MODEL PADA HELD-OUT TEST SET
================================================================
BENTUK SLANG:
- Micro-F1 : 0.8333
- Macro-F1 : 0.7619
Detail per kelas:
  akronim     : P=1.0000 | R=0.8000 | F1=0.8889 | Support=5
  singkatan   : P=0.8571 | R=0.8571 | F1=0.8571 | Support=7
  plesetan    : P=0.7500 | R=0.6000 | F1=0.6667 | Support=5
  tidak_ada   : P=0.8889 | R=1.0000 | F1=0.9412 | Support=8

FUNGSI BAHASA:
- Micro-F1 : 0.8125
- Macro-F1 : 0.7857
Detail per kelas:
  emotif      : P=0.8750 | R=0.8750 | F1=0.8750 | Support=8
  referensial : P=0.8000 | R=0.8000 | F1=0.8000 | Support=10
  konatif     : P=0.7500 | R=0.6000 | F1=0.6667 | Support=5
================================================================
Artefak model tersimpan di direktori models/
Laporan evaluasi tersimpan di reports/evaluation_metrics.csv
```

---

### Contoh Alur Menu 6: Prediksi Dataset Menggunakan Model
```text
--- Prediksi Dataset Menggunakan Model Baseline ---
Pilih file processed yang akan diprediksi:
  [1] comments_clean_20261027_210845_a196d7.csv
Pilih file [1]: 1

Memuat artefak model dari direktori models/...
Menjalankan inferensi multi-label...
Total data diprediksi: 100 baris.

Contoh Hasil Prediksi:
1. "gws ya kak semoga cepet sembuh"
   -> Bentuk: singkatan | Fungsi: emotif | Conf: 0.84 | Needs Review: False
2. "info harga dong min"
   -> Bentuk: singkatan | Fungsi: konatif;referensial | Conf: 0.79 | Needs Review: False
3. "wkwkwk mantul bgt nih"
   -> Bentuk: plesetan;singkatan | Fungsi: emotif | Conf: 0.52 | Needs Review: True

File prediksi tersimpan di: data/predictions/comments_predictions_20261027_212606_5f603f.csv
```

---

### Contoh Alur Menu 7: Analisis Hasil Komprehensif
```text
--- Analisis Hasil Anotasi & Prediksi ---
Menghitung distribusi frekuensi dan metrik data...

================================================================
RINGKASAN VOLUME DATASET
================================================================
 Total Komentar RAW         : 200
 Total Komentar Processed   : 200
 Total Komentar Dianotasi   : 100 (80 Selesai, 20 Belum)
 Total Komentar Diprediksi  : 100

DISTRIBUSI BENTUK SLANG (Anotasi Manusia):
  singkatan         : 35 komentar (43.8%)
  akronim           : 22 komentar (27.5%)
  plesetan          : 18 komentar (22.5%)
  bahasa_asing      : 12 komentar (15.0%)
  tidak_ada         : 15 komentar (18.8%)

DISTRIBUSI FUNGSI BAHASA (Anotasi Manusia):
  emotif            : 42 komentar (52.5%)
  referensial       : 31 komentar (38.8%)
  konatif           : 19 komentar (23.8%)
  tidak_jelas       : 3 komentar (3.8%)

Tabel analisis diekspor ke : reports/analysis_human_slang_forms_*.csv
Laporan naratif markdown   : reports/analysis_report_*.md
Grafik visualisasi         : reports/plot_slang_forms_*.png
                             reports/plot_language_functions_*.png
```

---

## 6. Kamus Data & Skema Kolom Lengkap

### 1. RAW Dataset (`data/raw/comments_<run_id>.csv`)
Menyimpan komentar mentah hasil tangkapan API sebelum proses pembersihan apa pun. Bersifat *immutable*.
| Kolom | Tipe Data | Wajib | Deskripsi |
|---|---|:---:|---|
| `comment_id` | string | Ya | ID unik komentar dari Instagram Graph API |
| `media_id` | string | Ya | ID media Instagram tempat komentar berada |
| `comment_text` | string | Ya | Teks mentah asli tanpa modifikasi |
| `timestamp` | string | Tidak | Waktu pembuatan komentar di Instagram (ISO-8601) |
| `like_count` | integer | Tidak | Jumlah like pada komentar saat dikumpulkan |
| `collected_at` | string | Ya | Timestamp lokal saat data diambil ke sistem |
| `source_type` | string | Ya | Sumber perolehan data (`authorized_api`) |

### 2. Processed Dataset (`data/processed/comments_clean_<run_id>.csv`)
Hasil preprocessing konservatif. `comment_text` asli tetap dipertahankan utuh berdampingan dengan `clean_text`.
| Kolom | Tipe Data | Deskripsi |
|---|---|---|
| `comment_id` | string | ID unik komentar dari sumber |
| `media_id` | string | ID media untuk pengelompokan GroupSplit cross-validation |
| `comment_text` | string | Teks asli yang tidak pernah dimodifikasi |
| `clean_text` | string | Teks bersih untuk anotasi (spasi dinormalisasi, URL $\rightarrow$ `[URL]`) |
| `normalized_text` | string | Teks normalisasi tambahan tanpa merusak teks asli |
| `is_empty_after_cleaning` | boolean | `true` jika teks menjadi kosong setelah pembersihan |
| `duplicate_status` | string | Status deduplikasi ID (`unique` atau `duplicate`) |

### 3. Annotated Dataset (`data/annotated/comments_labeled.csv`)
Dataset acuan kebenaran linguistik (*gold standard*) hasil telaah manusia.
| Kolom | Tipe Data | Contoh | Deskripsi |
|---|---|---|---|
| `comment_id` | string | `18001122` | ID unik komentar |
| `clean_text` | string | `gws ya kak` | Teks komentar yang dianotasi |
| `slang_present` | enum | `ya` / `tidak` | Indikator keberadaan bentuk slang |
| `slang_forms` | string multi-label (`;`) | `singkatan;akronim` | Kategori bentuk slang |
| `slang_spans` | string | `GWS` | Kata/frasa bukti slang dalam komentar |
| `slang_meanings` | string | `get well soon` | Makna kontekstual dari slang |
| `language_functions` | string multi-label (`;`) | `emotif;konatif` | Kategori fungsi bahasa Roman Jakobson |
| `annotator_id` | string | `A1` | Kode identitas anotator manusia |
| `review_status` | enum | `belum` / `selesai` | Status telaah (`selesai` diikutsertakan di training) |
| `adjudication_note` | string | `disepakati tim` | Catatan rekonsiliasi jika terjadi perbedaan pendapat |

### 4. Predictions Dataset (`data/predictions/comments_predictions_<run_id>.csv`)
Hasil inferensi model baseline pada data komentar baru.
| Kolom | Tipe Data | Deskripsi |
|---|---|---|
| `comment_id` | string | ID unik komentar |
| `clean_text` | string | Teks komentar yang diuji |
| `predicted_slang_forms` | string (`;`) | Prediksi kategori bentuk slang |
| `predicted_language_functions` | string (`;`) | Prediksi fungsi bahasa |
| `slang_forms_confidence` | float | Skor keyakinan sigmoid rata-rata untuk bentuk slang |
| `language_functions_confidence` | float | Skor keyakinan sigmoid rata-rata untuk fungsi bahasa |
| `needs_review` | boolean | Penanda apakah prediksi memiliki skor rendah/ambigu |
| `model_version` | string | Identifier nama dan versi model yang digunakan |

### 5. Run Metadata (`reports/run_<run_id>.json`)
Mencatat informasi eksekusi pipeline tanpa pernah menyimpan token kredensial:
```json
{
  "run_id": "20261027_210845_a196d7",
  "status": "completed",
  "created_at": "2026-10-27T21:08:45.123456",
  "total_collected": 100,
  "unique_collected": 100,
  "media_id": "17970528943031455",
  "raw_filepath": "d:\\WEBKU\\NLP\\data\\raw\\comments_20261027_210845_a196d7.csv",
  "raw_sha256": "4b9c5a17d848261e..."
}
```

---

## 7. Taksonomi Label & Pedoman Anotasi Manual

### Taksonomi Bentuk Slang (7 Kategori)
Gunakan tanda titik koma (`;`) untuk memisahkan multi-label jika satu komentar memuat lebih dari satu jenis slang:
1. **`akronim`:** Gabungan suku kata atau huruf awal yang dilafalkan sebagai kata utuh (contoh: *pansos*, *mager*, *curcol*, *baper*).
2. **`singkatan`:** Singkatan huruf-huruf inisial yang dieja per karakter (contoh: *GWS*, *TBH*, *BTW*, *OOT*, *CLBK*).
3. **`bahasa_asing`:** Kata/frasa asing yang diserap ke ragam percakapan slang santai (contoh: *bestie*, *slay*, *cringe*, *spill*).
4. **`plesetan`:** Permainan bunyi, substitusi fonem, atau pembalikan suku kata yang disengaja (contoh: *kuy*, *ngab*, *santuy*, *sans*).
5. **`pemendekan`:** Pemotongan fonem/suku kata dari kata baku (contoh: *bgt* $\rightarrow$ banget, *tp* $\rightarrow$ tapi, *sdh* $\rightarrow$ sudah).
6. **`tidak_ada`:** Komentar tidak memuat elemen slang ragam santai apa pun.
7. **`lainnya`:** Bentuk slang yang sah namun belum tercakup dalam 5 kelompok di atas.

### Taksonomi Fungsi Bahasa Roman Jakobson (4 Kategori)
1. **`emotif`:** Berfokus pada penutur; menyampaikan luapan emosi, kegembiraan, kekesalan, rasa syukur, atau sikap pribadi (contoh: *"Keren parah! 🔥"*, *"Sedih bgt dengernya 😭"*).
2. **`referensial`:** Berfokus pada konteks/topik; menyampaikan informasi faktual, data, rujukan objektif, atau deskripsi keadaan (contoh: *"Buka cabang di Bandung jam 10 pagi"*, *"Harganya 25 ribu"*).
3. **`konatif`:** Berfokus pada mitra tutur/pembaca; memengaruhi, memerintah, menyarankan, atau mengajak melakukan tindakan (contoh: *"Jangan lupa mampir ya!"*, *"Ketik 1 di kolom komentar"*).
4. **`tidak_jelas`:** Konteks komentar terlalu samar, terpotong, atau tidak memungkinkan penentuan fungsi bahasa secara bertanggung jawab.

### Aturan Validasi Konsistensi
- **Konsistensi `slang_present`:**  
  Jika `slang_present = "tidak"`, maka `slang_forms` **wajib** bernilai `tidak_ada`.  
  Jika `slang_present = "ya"`, maka `slang_forms` **tidak boleh** hanya berisi `tidak_ada`.
- **Kelengkapan Status Selesai:**  
  Jika `review_status = "selesai"`, maka kolom `slang_present`, `slang_forms`, dan `language_functions` wajib terisi dan memenuhi taksonomi.
- **Pemisah Karakter:**  
  Seluruh multi-label **wajib** dipisahkan dengan tanda titik koma (`;`). Dilarang memakai koma (`,`) agar struktur CSV tidak rusak.

---

## 8. Pengujian Otomatis (Test Suite)

Pengujian pipeline dilakukan secara komprehensif menggunakan **106 unit dan integration tests**. Seluruh pengujian API eksternal menggunakan **fixtures dan mock response**, sehingga:
- Pengujian **tidak pernah** melakukan request berulang ke API live Meta.
- Pengujian **tidak pernah** membutuhkan token nyata atau membocorkan kredensial.
- Pengujian dapat dijalankan secara instan dan *offline*.

Jalankan seluruh test suite dari terminal:
```cmd
python -m unittest discover tests
```

Atau menggunakan pytest:
```cmd
pytest -v
```

Hasil eksekusi test suite:
```text
Ran 106 tests in 2.298s

OK (106 tests passed, 0 failures, 0 errors)
```

Untuk menjalankan file audit dan hardening 17-poin secara spesifik:
```cmd
python -m unittest tests/test_audit_hardening.py
```

---

## 9. Interpretasi Metrik Evaluasi & Keterbatasan Statistik

### Arsitektur Baseline Model
- **Ekstraksi Fitur:** TF-IDF Vectorizer dengan rentang n-gram `(1, 2)`, batas frekuensi dokumen minimum `min_df=2`, dan maksimum fitur `max_features=5000`.
- **Klasifikasi:** Multi-label One-vs-Rest (OvR) Logistic Regression dengan pembobotan kelas seimbang (`class_weight='balanced'`) untuk mengatasi ketidakseimbangan frekuensi data teks.
- **Pencegahan Data Leakage (GroupSplit):**  
  Pembagian train/test split **wajib** dikelompokkan berdasarkan `media_id` menggunakan `GroupShuffleSplit`. Hal ini menjamin komentar dari postingan yang sama tidak akan terbagi ke data latih dan data uji sekaligus.

### Cara Menafsirkan Metrik
- **Precision (Presisi):** Dari seluruh komentar yang diprediksi memiliki label $X$, berapa proporsi yang benar-benar memiliki label $X$? Presisi tinggi meminimalkan *false positives*.
- **Recall (Daya Ingat):** Dari seluruh komentar yang sesungguhnya memuat label $X$, berapa proporsi yang berhasil terdeteksi oleh model? Recall tinggi meminimalkan *false negatives*.
- **F1-Score:** Rata-rata harmonik antara Precision dan Recall.
- **Macro-F1:** Rata-rata F1 per kelas tanpa memperhitungkan jumlah sampel (*unweighted mean*). Sangat sensitif terhadap kinerja kelas langka.
- **Micro-F1:** Metrik F1 global yang dihitung dari total kumulatif true positives, false positives, dan false negatives seluruh kelas.

### Interpretasi Confidence Score
- Nilai keyakinan model dihasilkan dari transformasi fungsi sigmoid margin keputusan Logistic Regression:
  $$\text{Confidence} = \frac{1}{1 + e^{-\text{margin}}}$$
- **Penting:** Skor ini **bukan probabilitas terkalibrasi secara formal** (kecuali telah dikalibrasi dengan Platt Scaling atau Isotonic Regression). Nilai ini merepresentasikan derajat keyakinan relatif model terhadap batas keputusan (*decision boundary*).
- **Flag `needs_review`:** Prediksi diberi penanda `needs_review = true` apabila skor keyakinan berada di bawah ambang batas (default `< 0.60`) atau jika tidak ada satu pun label yang melewati ambang batas.

### Keterbatasan Statistik
1. **Ketidakseimbangan Kelas (Class Imbalance):**  
   Bentuk slang seperti `singkatan` dan `akronim` jauh lebih dominan di media sosial daripada `plesetan` atau `bahasa_asing`. Evaluasi wajib merujuk pada Macro-F1 per kelas.
2. **Ketergantungan Konteks Kultural:**  
   Model baseline n-gram tidak menangkap makna semantik mendalam atau sarkasme seperti halnya model transformer besar.
3. **Representasi Postingan Terbatas:**  
   Jika data anotasi berasal dari sedikit postingan ($< 3$ media ID), variasi topik postingan dalam evaluasi held-out test akan terbatas.

---

## 10. Keamanan Token, Privasi Data, Retensi, & Kepatuhan

### Mekanisme Keamanan Token
1. **Penyaringan Otomatis Log (`SecretRedactingFilter`):**  
   Setiap pesan logging yang memuat pola URL `access_token=...` atau string token Meta (`EAAB...`) secara otomatis disensor menjadi `***REDACTED***` sebelum dicetak ke terminal atau ditulis ke disk.
2. **Pembersihan Metadata JSON:**  
   Fungsi penyimpanan metadata ([`src/storage.py`](file:///d:/WEBKU/NLP/src/storage.py)) secara rekursif menghapus *key* sensitif seperti `access_token`, `api_secret`, dan `token`.
3. **Pengecualian File Git:**  
   File `.env`, `.env.local`, dan direktori dataset (`data/raw/`, `data/processed/`, `data/annotated/`, `data/predictions/`) sepenuhnya dikecualikan oleh [.gitignore](file:///d:/WEBKU/NLP/.gitignore).

### Perlindungan Privasi Komentator
- **Tanpa Identitas Pribadi di RAW:**  
   File RAW komentar **hanya** menyimpan `comment_id`, `media_id`, `comment_text`, `timestamp`, dan `like_count`. Nama akun (`username`), URL foto profil, dan identitas pribadi pengguna Instagram **tidak pernah disimpan**.
- **Sanitasi PII pada Analisis Error:**  
   Laporan analisis kesalahan kualitatif model secara otomatis menyensor alamat email, nomor telepon, dan mention `@username` menjadi `[EMAIL]`, `[PHONE]`, dan `[USER]` guna melindungi privasi publik.

### Retensi Data
- Seluruh file dataset dan laporan disimpan secara lokal pada hard disk komputer Anda. Tidak ada data yang dikirimkan ke server pihak ketiga mana pun di luar endpoint resmi Meta Graph API.

---

---

## 11. Eksperimen Model Bahasa Indonesia Pra-latih (IndoBERT)

Proyek ini menyediakan modul eksperimen perbandingan menggunakan model transformer bahasa Indonesia pra-latih: **`indobenchmark/indobert-base-p1`** (lisensi BSD-3-Clause, Indo4B / IndoLEM, Koto et al., 2020).

Panduan teknis lengkap dapat dibaca di: [docs/INDOBERT_EXPERIMENT.md](file:///d:/WEBKU/NLP/docs/INDOBERT_EXPERIMENT.md).

### Ringkasan Desain Eksperimen:
- **Baseline Tetap Utuh:** Model baseline TF-IDF pada `models/baseline_*.joblib` **tidak dihapus atau ditimpa**.
- **Partisi 3-Way GroupSplit:** Data dibagi menjadi Train (60%), Validation (20%), dan Held-out Test (20%) secara ketat berdasarkan `media_id` (zero data leakage). Minimal membutuhkan 3 postingan berbeda.
- **Pencegahan Tuning pada Test Set:** Validation set digunakan untuk early stopping / seleksi checkpoint model. Held-out test set hanya dievaluasi satu kali di akhir.
- **Optimasi Hardware 4GB VRAM:** Fine-tuning dioptimasi untuk GPU laptop pengguna (**NVIDIA GeForce RTX 3050 Ti 4GB VRAM**) menggunakan `batch_size = 8`, `max_length = 128`, dan mixed precision FP16 (`torch.cuda.amp.autocast()`).
- **Pelaporan Komparatif:** Hasil perbandingan disimpan secara terpisah di `reports/comparison_baseline_vs_indobert_<run_id>.json`, `.csv`, dan `.md`.

### Perintah Menjalankan Eksperimen:
1. **Periksa Kesiapan Hardware & Dependensi:**
   ```powershell
   python -m src.experiments.indobert_experiment --check-env
   ```
2. **Buat Dataset Demo Multi-Post Sintesis (Jika Data Riil Belum Cukup):**
   ```powershell
   python -m src.experiments.indobert_experiment --create-demo
   ```
3. **Eksekusi Eksperimen Fine-Tuning & Komparasi:**
   ```powershell
   python -m src.experiments.indobert_experiment --data data/annotated/comments_labeled_demo.csv --epochs 3 --batch-size 8
   ```
   *Atau jalankan melalui Menu CLI Utama (`python main.py`), pilih menu **`5. Latih model baseline`**, dan jawab `y` pada konfirmasi perbandingan IndoBERT.*

---

## 12. Daftar Fitur yang Belum Diimplementasikan

Sebagai bentuk kejujuran teknis, berikut adalah batasan dan fitur yang **belum diimplementasikan** pada versi rilis ini:
1. **Kalibrasi Probabilitas Formal:**  
   Skor keyakinan inferensi saat ini menggunakan uncalibrated sigmoid margin dari Logistic Regression dan belum menerapkan kalibrasi probabilitas formal (seperti CalibratedClassifierCV dengan Platt Scaling atau Isotonic Regression).
2. **Antarmuka Grafis Pengguna (GUI / Web Dashboard):**  
   Aplikasi ini dirancang murni berbasis Command Line Interface (CLI) terminal Windows tanpa antarmuka berbasis web.
3. **Ekstraksi Span Slang Otomatis (Token-Level NER):**  
   Model saat ini melakukan klasifikasi multi-label di tingkat komentar penuh (*document-level multi-label classification*). Deteksi batas kata slang (`slang_spans`) pada tahap anotasi masih memerlukan input manusia dan belum diekstraksi secara otomatis oleh model urutan (*sequence labeling*).

---

## 13. Struktur Direktori Proyek

```text
d:\WEBKU\NLP/
├── .env.example                # Template konfigurasi variabel lingkungan tanpa rahasia
├── .gitignore                  # Pengecualian Git untuk keamanan kredensial & dataset
├── README.md                   # Dokumentasi teknis & panduan operasional lengkap
├── requirements.txt            # Daftar paket dependensi Python
├── main.py                     # Entry point eksekusi pipeline
├── doc/                        # Master dokumentasi komprehensif
│   └── Instagram_Slang_NLP_Dokumentasi_Lengkap.md
├── docs/                       # Dokumentasi modular teknis
│   ├── ANNOTATION_GUIDE.md     # Pedoman pelabelan manual & taksonomi slang
│   ├── CLI_SPEC.md             # Spesifikasi antarmuka terminal
│   ├── DATA_DICTIONARY.md      # Kamus data seluruh skema CSV
│   ├── INDOBERT_EXPERIMENT.md  # Panduan teknis & metodologi eksperimen IndoBERT
│   ├── INSTAGRAM_API_GUIDE.md  # Panduan integrasi Meta Graph API
│   ├── PRD.md                  # Product Requirements Document
│   ├── PREPROCESSING_DECISIONS.md # Keputusan linguistik preprocessing
│   └── TECHNICAL_DESIGN.md     # Desain arsitektur teknis
├── src/                        # Kode sumber inti modular
│   ├── collectors/             # Adapter pengumpul data
│   │   ├── base.py             # Interface abstrak & dataclass komentar
│   │   └── instagram_api.py    # Adapter resmi Meta Graph API v21.0
│   ├── config.py               # Pengelola path & validasi parameter
│   ├── logging_config.py       # Logger terpusat dengan filter sensor kredensial
│   ├── cli.py                  # Antarmuka CLI interaktif 7 menu
│   ├── storage.py              # Penyimpanan RAW immutable & metadata
│   ├── preprocessing.py        # Pembersihan teks komentar konservatif
│   ├── annotations.py          # Generator template & validator dataset anotasi
│   ├── train.py                # Pelatihan baseline model NLP & GroupSplit
│   ├── predict.py              # Inferensi dataset processed & skor keyakinan
│   ├── analysis.py             # Analisis distribusi linguistik & laporan
│   └── experiments/            # Modul eksperimen model bahasa pra-latih
│       ├── __init__.py         # Package init
│       ├── indobert_experiment.py # Pipeline fine-tuning & komparasi IndoBERT
│       └── synthetic_demo.py   # Pembangkit dataset demo multi-post sintesis
├── tests/                      # Rangkaian pengujian terisolasi (115 tests)
│   ├── test_indobert_experiment.py # Pengujian unit pipeline eksperimen IndoBERT
│   ├── test_audit_hardening.py # Audit ketat 17 item robustness
│   ├── test_cli.py             # Pengujian antarmuka CLI
│   ├── test_instagram_collector.py # Pengujian mocked adapter Meta API
│   ├── test_preprocessing.py   # Pengujian aturan pembersihan teks
│   ├── test_annotations.py     # Pengujian validasi & merging anotasi
│   ├── test_train.py           # Pengujian pelatihan model & zero-leakage
│   ├── test_predict.py         # Pengujian inferensi & ambang batas
│   └── test_analysis.py        # Pengujian analisis statistik & sanitasi PII
├── data/                       # Direktori penyimpanan data lokal
│   ├── raw/                    # File CSV mentah (immutable)
│   ├── processed/              # File CSV hasil preprocessing
│   ├── annotated/              # File CSV anotasi manusia (gold standard & demo)
│   └── predictions/            # File CSV hasil inferensi model
├── models/                     # Artefak serialisasi model baseline (.joblib)
│   └── experiments/            # Artefak model IndoBERT (.pt & tokenizer)
└── reports/                    # Metadata run JSON, metrik evaluasi CSV, MD, & grafik PNG
```
#   i g - n l p  
 