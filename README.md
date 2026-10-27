# Instagram Slang NLP — Windows CLI Pipeline

<div align="center">

### Pipeline Pemrosesan Bahasa Alami (NLP) Berbasis CLI Windows untuk Analisis Bentuk Slang & Fungsi Bahasa Komentar Instagram

[![Test Suite](https://img.shields.io/badge/Tests-120%20passed-brightgreen.svg?style=flat-square&logo=pytest)](tests/)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20CMD%20%7C%20PowerShell-0078D6.svg?style=flat-square&logo=windows)](https://microsoft.com)
[![Meta Graph API](https://img.shields.io/badge/Meta%20Graph%20API-v21.0-blue.svg?style=flat-square&logo=meta)](docs/INSTAGRAM_API_GUIDE.md)
[![Baseline](https://img.shields.io/badge/Baseline-TF--IDF%20%2B%20Logistic%20Regression-orange.svg?style=flat-square)](#10-interpretasi-metrik-evaluasi-keterbatasan-statistik)
[![Pretrained LM](https://img.shields.io/badge/Pretrained-IndoBERT%20Base-purple.svg?style=flat-square)](docs/INDOBERT_EXPERIMENT.md)
[![License](https://img.shields.io/badge/License-Academic%20%2F%20Research-lightgrey.svg?style=flat-square)](LICENSE)

</div>

---

Pipeline Command Line Interface (CLI) berbasis Python untuk sistem operasi Windows (CMD & PowerShell) guna mengumpulkan komentar Instagram melalui Meta Graph API resmi atau mengimpor ekspor CSV/Excel eksternal, menyimpan dataset mentah (RAW) secara *immutable*, meminta konfirmasi eksplisit sebelum tahap pemrosesan NLP, serta memfasilitasi preprocessing konservatif, anotasi manual terstandardisasi, pelatihan model baseline multi-label (TF-IDF + One-vs-Rest Logistic Regression dengan GroupSplit bebas kebocoran), perbandingan eksperimen dengan model bahasa pra-latih (**IndoBERT**), inferensi terisolasi, dan analisis distribusi linguistik.

---

## Daftar Isi

1. [Tujuan, Batasan Arsitektural, dan Alur Kerja](#1-tujuan-batasan-arsitektural-dan-alur-kerja)
2. [Perbedaan URL vs Media ID & Batasan Akses Data](#2-perbedaan-url-vs-media-id-batasan-akses-data)
3. [Instalasi di Windows (CMD & PowerShell)](#3-instalasi-di-windows-cmd-powershell)
4. [Panduan Meta Graph API & Konfigurasi Token](#4-panduan-meta-graph-api-konfigurasi-token)
5. [Panduan Impor Komentar Eksternal (CSV / Excel)](#5-panduan-impor-komentar-eksternal-csv-excel)
6. [Contoh Eksekusi & Tampilan Output Terminal CLI](#6-contoh-eksekusi-tampilan-output-terminal-cli)
7. [Kamus Data & Skema Kolom Lengkap](#7-kamus-data-skema-kolom-lengkap)
8. [Taksonomi Label & Pedoman Anotasi Manual](#8-taksonomi-label-pedoman-anotasi-manual)
9. [Pengujian Otomatis (Test Suite)](#9-pengujian-otomatis-test-suite)
10. [Interpretasi Metrik Evaluasi & Keterbatasan Statistik](#10-interpretasi-metrik-evaluasi-keterbatasan-statistik)
11. [Keamanan Token, Privasi Data, Retensi, & Kepatuhan](#11-keamanan-token-privasi-data-retensi-kepatuhan)
12. [Eksperimen Model Bahasa Indonesia Pra-latih (IndoBERT)](#12-eksperimen-model-bahasa-indonesia-pra-latih-indobert)
13. [Daftar Fitur yang Belum Diimplementasikan](#13-daftar-fitur-yang-belum-diimplementasikan)
14. [Struktur Direktori Proyek](#14-struktur-direktori-proyek)

---

## 1. Tujuan, Batasan Arsitektural, dan Alur Kerja

### Tujuan Proyek
Proyek ini dikembangkan untuk kebutuhan penelitian linguistik komputasional dan pemrosesan bahasa alami (NLP) pada komentar Instagram berbahasa Indonesia. Tujuan utamanya meliputi:
- Mengumpulkan komentar media sosial melalui jalur resmi atau file ekspor terstruktur secara etik dan hukum.
- Mencegah kontaminasi data mentah melalui penyimpanan dataset RAW yang bersifat *immutable* (tidak dapat ditimpa, diverifikasi dengan checksum SHA-256).
- Memberikan kendali penuh kepada peneliti melalui konfirmasi interaktif `[y/N]` sebelum melanjutkan ke pemrosesan NLP.
- Menyediakan alur anotasi manusia (*human-in-the-loop*) yang non-destruktif dan tervalidasi secara otomatis.
- Melatih model multi-label untuk mengklasifikasikan:
  1. **Bentuk Slang:** `akronim`, `singkatan`, `bahasa_asing`, `plesetan`, `pemendekan`, `tidak_ada`, `lainnya`.
  2. **Fungsi Bahasa:** `emotif`, `referensial`, `konatif`, `tidak_jelas`.
- Menyajikan evaluasi komparatif antara model baseline (TF-IDF + Logistic Regression) dan model pra-latih (*IndoBERT*) pada split yang sama tanpa kebocoran data (*zero leakage*).

### Batasan Arsitektural & Etika Platform
1. **Kepatuhan Meta Platform Terms of Service:**  
   Kolektor bawaan program ini **TIDAK MENGGUNAKAN** teknik *automated browser scraping* (seperti BeautifulSoup, Selenium, Puppeteer, atau Playwright) pada API resmi, melainkan menggunakan Meta Graph API resmi (v21.0).
2. **Fleksibilitas Data Pihak Ketiga:**  
   Tersedia konverter otomatis di `src/tools/import_external_csv.py` agar peneliti dapat menggunakan dataset eksternal (hasil ekspor resmi, riset terdahulu, atau ekstensi browser) secara aman ke dalam pipeline tanpa melanggar batasan runtime.
3. **Validitas Ilmiah Anotasi:**  
   Sistem menolak melakukan *auto-labeling* heuristik tanpa tinjauan manusia. Label acuan (*ground truth*) wajib divalidasi oleh peneliti sebelum model dapat dilatih.

### Diagram Alur Kerja Sistem

```mermaid
flowchart TD
    subgraph Pengumpulan ["1. Sumber Data Mentah"]
        A1[Meta Graph API v21.0] --> S1[Kolektor Resmi]
        A2[Ekspor CSV / Excel Eksternal] --> S2[Konverter Impor]
    end

    S1 --> RAW[(data/raw/comments_*.csv)]
    S2 --> RAW
    RAW --> META[Laporan Metadata Run JSON]

    subgraph Gatekeeper ["2. Konfirmasi Peneliti"]
        RAW --> PROMPT{Lanjutkan ke NLP? [y/N]}
        PROMPT -->|N / Enter| DECLINED[Status: nlp_declined<br/>Berhenti Aman]
        PROMPT -->|y / yes| PREP[Preprocessing Konservatif]
    end

    subgraph Pemrosesan ["3. Preprocessing & Anotasi"]
        PREP --> PROC[(data/processed/comments_clean_*.csv)]
        PROC --> TEMPLATE[3. Buat Template Anotasi]
        TEMPLATE --> ANNOT[(data/annotated/comments_labeled.csv)]
        ANNOT --> HUMAN[Anotasi Manual Peneliti]
        HUMAN --> VAL[4. Validasi Anotasi Ketat]
    end

    subgraph Pemodelan ["4. Pelatihan & Eksperimen"]
        VAL --> SPLIT[GroupSplit by media_id<br/>Zero Data Leakage]
        SPLIT --> BASELINE[5. Baseline TF-IDF + Logistic Regression]
        SPLIT --> INDOBERT[Eksperimen IndoBERT Pretrained]
        BASELINE --> MOD_SAVE[(models/baseline_*.joblib)]
        INDOBERT --> BERT_SAVE[(models/experiments/indobert_*.pt)]
    end

    subgraph Inferensi ["5. Prediksi & Analisis"]
        MOD_SAVE --> PRED[6. Prediksi Dataset Baru]
        PRED --> OUT_PRED[(data/predictions/)]
        MOD_SAVE --> REPORT[7. Analisis Statistik & Visualisasi]
        BERT_SAVE --> REPORT
        REPORT --> OUT_REP[reports/ *.csv, *.md, *.png]
    end
```

---

## 2. Perbedaan URL vs Media ID & Batasan Akses Data

| Aspek | URL Postingan Instagram | Media ID Meta Graph API |
|---|---|---|
| **Contoh Nilai** | `https://www.instagram.com/p/DeRfCHemNKL/` atau `/reel/D_xyz987/` | `17970528943031455` (string numerik) |
| **Definisi** | Tautan web publik yang memuat *shortcode* postingan. | Pengenal unik internal dalam basis data Meta Platform. |
| **Mekanisme Resolusi** | Sistem mengekstrak *shortcode*, lalu mencocokkannya dengan postingan akun profesional Anda via `GET /me/media`. | Langsung digunakan untuk meminta endpoint `GET /{media-id}/comments`. |
| **Akses Akun Pihak Ketiga** | **TIDAK DIDUKUNG OLEH META GRAPH API.** Meta membatasi pembacaan komentar publik dari akun orang lain tanpa izin otorisasi token akun tersebut. | Hanya berlaku untuk media yang berada di bawah kepemilikan akun pengembang/profesional yang terotorisasi. |

> [!IMPORTANT]
> Jika URL postingan yang dimasukkan pada **Menu 1** bukan milik akun Profesional Anda sendiri, sistem akan memberikan peringatan `MediaUnavailableError`. Untuk menganalisis komentar dari postingan publik pihak ketiga, gunakan **[Panduan Impor Komentar Eksternal](#5-panduan-impor-komentar-eksternal-csv-excel)** di bawah.

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

### Langkah 2: Buat Virtual Environment
Buka direktori proyek:
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
  *Jika muncul pesan error script execution policy di PowerShell, jalankan:*
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  .\.venv\Scripts\Activate.ps1
  ```

### Langkah 4: Instal Dependensi Proyek
```cmd
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> [!TIP]
> Jika ingin menjalankan eksperimen **IndoBERT** dengan akselerasi GPU NVIDIA (RTX 3050 Ti):
> ```powershell
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
> pip install transformers accelerate
> ```

---

## 4. Panduan Meta Graph API & Konfigurasi Token

Untuk mengumpulkan komentar secara langsung dari akun Instagram yang Anda kelola:

### Pilihan Varian API Meta
Dikonfigurasi melalui variabel lingkungan `INSTAGRAM_API_VARIANT` di `.env`:
1. **`facebook_login` (Rekomendasi Default):**
   - Host: `https://graph.facebook.com/v21.0/`
   - Membutuhkan akun Instagram Business/Creator yang ditautkan ke Facebook Page.
   - Izin: `instagram_basic`, `instagram_manage_comments`, `pages_show_list`, `pages_read_engagement`.
2. **`instagram_login`:**
   - Host: `https://graph.instagram.com/v21.0/`
   - Menggunakan Instagram User Access Token langsung.
   - Izin: `instagram_business_basic`, `instagram_business_manage_comments`.

### Setup File `.env`
Salin template konfigurasi:
```cmd
copy .env.example .env
```
Sesuaikan nilai pada file `.env`:
```dotenv
# Kredensial Meta Graph API (JANGAN PERNAH COMMIT KE GIT!)
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

## 5. Panduan Impor Komentar Eksternal (CSV / Excel)

Jika Anda ingin menganalisis komentar dari postingan akun lain / publik yang tidak terhubung ke token Meta Anda:

1. **Unduh Komentar:** Gunakan ekstensi browser (misal *IG Comment Exporter* di Chrome Web Store) atau layanan ekspor online untuk mendapatkan file `.csv` atau `.xlsx`.
2. **Cara A (Otomatis via Menu CLI):**
   - Letakkan file hasil unduhan ke dalam folder `data/raw/` (misalnya `data/raw/komentar_eksternal.csv`).
   - Jalankan `python main.py` lalu pilih **Menu 2: "Jalankan NLP pada RAW yang sudah ada"**.
   - Sistem akan menandai file tersebut sebagai `[EKSTERNAL]`, otomatis memetakan kolom teks komentar, mengonversi ke format RAW standar, dan langsung menjalankan preprocessing.
3. **Cara B (Via Perintah Mandiri):**
   ```powershell
   python -m src.tools.import_external_csv "C:\path\ke\file_unduhan.csv" --media-id DeRfCHemNKL
   ```

---

## 6. Contoh Eksekusi & Tampilan Output Terminal CLI

Jalankan program utama melalui terminal:
```cmd
python main.py
```
Atau untuk memeriksa status kesiapan konfigurasi tanpa menu interaktif:
```cmd
python main.py --status
```

<details>
<summary><b>Lihat Contoh Tampilan Menu Utama CLI</b></summary>

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
</details>

<details>
<summary><b>Lihat Contoh Alur Menu 1 (Pengumpulan, RAW & Prompt Konfirmasi)</b></summary>

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
 File RAW Tersimpan : data\raw\comments_20261027_210528_da0dcc.csv
 Checksum SHA256    : 4b9c5a17d848261e...
 Metadata Run JSON  : reports\run_20261027_210528_da0dcc.json
================================================================

Lanjutkan ke tahap NLP sekarang? [y/N]: 

Proses NLP dihentikan atas permintaan pengguna (status: nlp_declined).
Dataset RAW Anda tersimpan aman dan tidak disentuh.
Kembali ke menu utama.
```
</details>

<details>
<summary><b>Lihat Contoh Alur Menu 5 (Pelatihan Model Baseline & Evaluasi)</b></summary>

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
</details>

---

## 7. Kamus Data & Skema Kolom Lengkap

### 1. RAW Dataset (`data/raw/comments_<run_id>.csv`)
Menyimpan komentar mentah hasil tangkapan API sebelum pembersihan. Bersifat *immutable*.
| Kolom | Tipe Data | Wajib | Deskripsi |
|---|---|:---:|---|
| `comment_id` | string | Ya | ID unik komentar dari Instagram Graph API |
| `media_id` | string | Ya | ID media Instagram tempat komentar berada |
| `comment_text` | string | Ya | Teks mentah asli tanpa modifikasi apa pun |
| `timestamp` | string | Tidak | Waktu pembuatan komentar di Instagram (ISO-8601) |
| `like_count` | integer | Tidak | Jumlah like pada komentar saat dikumpulkan |
| `collected_at` | string | Ya | Timestamp lokal saat data diambil ke sistem |
| `source_type` | string | Ya | Sumber perolehan data (`authorized_api` / `external_import`) |

### 2. Processed Dataset (`data/processed/comments_clean_<run_id>.csv`)
Hasil preprocessing konservatif. `comment_text` asli dipertahankan berdampingan dengan `clean_text`.
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

---

## 8. Taksonomi Label & Pedoman Anotasi Manual

Panduan lengkap anotasi: [docs/ANNOTATION_GUIDE.md](docs/ANNOTATION_GUIDE.md).

### Taksonomi Bentuk Slang (7 Kategori)
Gunakan tanda titik koma (`;`) untuk memisahkan multi-label jika satu komentar memuat lebih dari satu jenis slang:
1. **`akronim`:** Gabungan suku kata atau huruf awal yang dilafalkan sebagai kata utuh (*pansos*, *mager*, *curcol*, *baper*).
2. **`singkatan`:** Singkatan inisial yang dieja per karakter (*GWS*, *TBH*, *BTW*, *OOT*, *CLBK*).
3. **`bahasa_asing`:** Kata/frasa asing yang diserap ke ragam percakapan santai (*bestie*, *slay*, *cringe*, *spill*).
4. **`plesetan`:** Permainan bunyi, substitusi fonem, atau pembalikan suku kata (*kuy*, *ngab*, *santuy*, *sans*).
5. **`pemendekan`:** Pemotongan fonem/suku kata dari kata baku (*bgt* $\rightarrow$ banget, *tp* $\rightarrow$ tapi).
6. **`tidak_ada`:** Komentar tidak memuat elemen slang ragam santai apa pun.
7. **`lainnya`:** Bentuk slang yang sah namun belum tercakup dalam 5 kelompok di atas.

### Taksonomi Fungsi Bahasa Roman Jakobson (4 Kategori)
1. **`emotif`:** Berfokus pada penutur; menyampaikan luapan emosi, kegembiraan, atau sikap pribadi (*"Keren parah! 🔥"*, *"Sedih bgt 😭"*).
2. **`referensial`:** Berfokus pada konteks/topik; menyampaikan informasi faktual, harga, atau deskripsi keadaan (*"Buka jam 10 pagi"*, *"Harganya 25 ribu"*).
3. **`konatif`:** Berfokus pada mitra tutur; memengaruhi, menyarankan, atau mengajak bertindak (*"Jangan lupa mampir ya!"*, *"Ketik 1 di kolom komentar"*).
4. **`tidak_jelas`:** Konteks komentar terlalu samar, terpotong, atau tidak memungkinkan penentuan fungsi bahasa secara objektif.

---

## 9. Pengujian Otomatis (Test Suite)

Pengujian pipeline dilakukan secara komprehensif menggunakan **120 unit dan integration tests**. Pengujian API eksternal menggunakan fixtures dan mock response sehingga tidak memboroskan kuota rate-limit dan dapat dijalankan secara instan offline.

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
Ran 120 tests in 2.729s

OK (120 tests passed, 0 failures, 0 errors)
```

---

## 10. Interpretasi Metrik Evaluasi & Keterbatasan Statistik

### Arsitektur Baseline Model
- **Ekstraksi Fitur:** TF-IDF Vectorizer dengan rentang n-gram `(1, 2)`, `min_df=2`, dan `max_features=5000`.
- **Klasifikasi:** Multi-label One-vs-Rest (OvR) Logistic Regression dengan `class_weight='balanced'`.
- **Pencegahan Data Leakage (GroupSplit):** Pembagian train/test split dikelompokkan berdasarkan `media_id` menggunakan `GroupShuffleSplit` untuk menjamin komentar dari postingan yang sama tidak terbagi ke data latih dan data uji sekaligus.

### Cara Menafsirkan Metrik
- **Precision:** Proporsi prediksi label $X$ yang benar-benar tepat (meminimalkan *false positives*).
- **Recall:** Proporsi sampel riil berlabel $X$ yang berhasil dideteksi (meminimalkan *false negatives*).
- **Macro-F1:** Rata-rata F1 per kelas tanpa pembobotan frekuensi (*unweighted mean*), sangat penting untuk mendeteksi kinerja kelas langka.
- **Micro-F1:** Metrik F1 global yang dihitung dari total kumulatif true positives, false positives, dan false negatives.

### Keterbatasan Statistik
1. **Ketidakseimbangan Kelas (Class Imbalance):** Bentuk `singkatan` dan `akronim` jauh lebih dominan di Instagram daripada `plesetan` atau `bahasa_asing`.
2. **Representasi Postingan Terbatas:** Jika data anotasi berasal dari sedikit postingan ($< 3$ media ID), variasi topik postingan dalam evaluasi held-out test akan terbatas.

---

## 11. Keamanan Token, Privasi Data, Retensi, & Kepatuhan

1. **Penyaringan Otomatis Log (`SecretRedactingFilter`):** Setiap log yang memuat token Meta (`EAAB...`) secara otomatis disensor menjadi `***REDACTED***` sebelum dicetak ke terminal atau file log.
2. **Pembersihan Metadata JSON:** Modul [src/storage.py](src/storage.py) secara rekursif menyaring kunci sensitif seperti `access_token` dan `token`.
3. **Pengecualian File Git:** File `.env` dan direktori data (`data/raw/`, `data/processed/`, dll.) sepenuhnya dikecualikan oleh [.gitignore](.gitignore).
4. **Perlindungan Privasi Komentator:** File RAW tidak menyimpan nama akun (`username`), foto profil, atau data pribadi komentator Instagram.
5. **Sanitasi PII pada Laporan:** Analisis kesalahan menyensor email, nomor telepon, dan mention `@username` menjadi `[EMAIL]`, `[PHONE]`, dan `[USER]`.

---

## 12. Eksperimen Model Bahasa Indonesia Pra-latih (IndoBERT)

Proyek ini menyediakan modul eksperimen komparasi menggunakan model transformer bahasa Indonesia pra-latih: **`indobenchmark/indobert-base-p1`** (lisensi BSD-3-Clause, Indo4B / IndoLEM, Koto et al., 2020).

Panduan teknis lengkap: [docs/INDOBERT_EXPERIMENT.md](docs/INDOBERT_EXPERIMENT.md).

### Ringkasan Desain Eksperimen:
- **Baseline Tetap Utuh:** Model baseline TF-IDF pada `models/baseline_*.joblib` **tidak dihapus atau ditimpa**.
- **Partisi 3-Way GroupSplit:** Data dibagi menjadi Train (60%), Validation (20%), dan Held-out Test (20%) secara ketat berdasarkan `media_id` (zero data leakage).
- **Pencegahan Tuning pada Test Set:** Validation set digunakan untuk early stopping / seleksi checkpoint. Held-out test set hanya dievaluasi satu kali di akhir.
- **Optimasi Hardware 4GB VRAM:** Fine-tuning dioptimasi untuk GPU laptop (**NVIDIA GeForce RTX 3050 Ti 4GB VRAM**) dengan `batch_size = 8`, `max_length = 128`, dan mixed precision FP16 (`torch.cuda.amp.autocast()`).
- **Pelaporan Komparatif:** Hasil perbandingan disimpan terpisah di `reports/comparison_baseline_vs_indobert_<run_id>.json`, `.csv`, dan `.md`.

### Perintah Menjalankan Eksperimen:
```powershell
# 1. Periksa Kesiapan Hardware & Dependensi
python -m src.experiments.indobert_experiment --check-env

# 2. Buat Dataset Demo Multi-Post Sintesis (30 sampel, 5 postingan)
python -m src.experiments.synthetic_demo

# 3. Eksekusi Eksperimen Fine-Tuning & Komparasi
python -m src.experiments.indobert_experiment --data data/annotated/comments_labeled_demo.csv --epochs 3 --batch-size 8
```

---

## 13. Daftar Fitur yang Belum Diimplementasikan

Sebagai bentuk kejujuran teknis, berikut adalah batasan yang **belum diimplementasikan** pada versi rilis ini:
1. **Kalibrasi Probabilitas Formal:** Skor keyakinan inferensi saat ini menggunakan uncalibrated sigmoid margin dari Logistic Regression.
2. **Antarmuka Grafis Pengguna (GUI / Web Dashboard):** Aplikasi ini dirancang murni berbasis Command Line Interface (CLI) terminal Windows.
3. **Ekstraksi Span Slang Otomatis (Token-Level NER):** Model melakukan klasifikasi multi-label di tingkat komentar penuh. Deteksi batas kata slang (`slang_spans`) masih memerlukan input manusia.

---

## 14. Struktur Direktori Proyek

```text
.
├── .env.example                # Template konfigurasi variabel lingkungan tanpa rahasia
├── .gitignore                  # Pengecualian Git untuk keamanan kredensial & dataset
├── README.md                   # Dokumentasi teknis & panduan operasional lengkap
├── requirements.txt            # Daftar paket dependensi Python
├── main.py                     # Entry point eksekusi pipeline CLI
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
│   ├── tools/                  # Utilitas dataset eksternal
│   │   ├── __init__.py
│   │   └── import_external_csv.py # Konverter CSV/Excel eksternal ke format RAW
│   ├── experiments/            # Modul eksperimen model bahasa pra-latih
│   │   ├── __init__.py
│   │   ├── indobert_experiment.py # Pipeline fine-tuning & komparasi IndoBERT
│   │   └── synthetic_demo.py   # Pembangkit dataset demo multi-post sintesis
│   ├── config.py               # Pengelola path & validasi parameter
│   ├── logging_config.py       # Logger terpusat dengan filter sensor kredensial
│   ├── cli.py                  # Antarmuka CLI interaktif 7 menu
│   ├── storage.py              # Penyimpanan RAW immutable & metadata
│   ├── preprocessing.py        # Pembersihan teks komentar konservatif
│   ├── annotations.py          # Generator template & validator dataset anotasi
│   ├── train.py                # Pelatihan baseline model NLP & GroupSplit
│   ├── predict.py              # Inferensi dataset processed & skor keyakinan
│   └── analysis.py             # Analisis distribusi linguistik & laporan
├── tests/                      # Rangkaian pengujian terisolasi (120 tests)
│   ├── test_import_external_csv.py # Pengujian konverter dataset eksternal
│   ├── test_indobert_experiment.py # Pengujian pipeline eksperimen IndoBERT
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