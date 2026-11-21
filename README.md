# Social Media Data Collector (Instagram & TikTok)

> **Privacy-First Open-Source Comment Harvester for Linguistic Research & NLP Datasets**

Alat penarikan data (*data collector / comment harvester*) berbasis peramban otomatis (*browser automation*) untuk mengumpulkan komentar publik dari platform **Instagram** (Post & Reels) dan **TikTok** (Video & tautan pendek `vt.tiktok.com`).

Dirancang khusus dengan standar **Privacy by Design** yang mematuhi prinsip etika pengumpulan data dan perlindungan data pribadi (UU PDP Indonesia & GDPR):
* **Peniadaan Nama Akun**: File dataset hasil penarikan tidak mencantumkan nama akun/username pembuat komentar.
* **Sanitasi Mention**: Setiap pola `@nama_orang` di dalam teks komentar disanitasi menjadi `[@USER]`.
* **Masking PII**: Email dan nomor telepon yang tercantum dalam komentar otomatis disamarkan.
* **Format Ganda**: Data langsung disimpan dalam bentuk **CSV** (UTF-8 with BOM) dan **Excel (.xlsx)**.

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
Jalankan perintah berikut untuk membuka menu navigasi di terminal:
```bash
python main.py
```
Menu utama yang tersedia:
```text
================================================================
       SOCIAL MEDIA DATA COLLECTOR (INSTAGRAM & TIKTOK)
       Privacy-First Comment Harvesting for NLP & Research
================================================================
Menu Utama:
  1. Kumpulkan komentar (Instagram / TikTok)
  2. Buka browser untuk login Instagram (Opsional)
  3. Buka browser untuk login TikTok (Opsional)
  4. Cek status profil browser lokal
  0. Keluar
----------------------------------------------------------------
```

### Mode Langsung dengan Argumen (Command-Line)
Anda juga dapat menjalankan penarikan data secara langsung tanpa masuk ke menu:

**Penarikan Komentar Instagram:**
```bash
python main.py --url "https://www.instagram.com/p/ABC123xyz/" --limit 300 --format both
```

**Penarikan Komentar TikTok:**
```bash
python main.py --url "https://vt.tiktok.com/ZSxyz123/" --limit 500 --format csv
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
| `source_type` | Asal platform koleksi | `browser_instagram` / `browser_tiktok` |

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
