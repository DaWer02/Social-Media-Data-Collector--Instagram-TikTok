# Desain Teknis — Instagram Slang NLP

## 1. Arsitektur

```text
Terminal User
    |
    v
CLI / main.py
    |
    +--> Input & Config Validator
    |
    +--> Instagram Source Adapters (Pluggable BaseCollector)
    |       |
    |       +--> [Default] Browser Automation + NLP Extractor (src/collectors/browser_nlp.py)
    |       |       - Membuka browser Playwright ke sembarang URL publik Instagram
    |       |       - NLP Information Extraction: membersihkan noise UI (balas/suka/timestamp)
    |       |       - In-flight quality: filter spam bot/iklan, deteksi bahasa & slang
    |       |
    |       +--> [Opsional] Meta Graph API Adapter (src/collectors/instagram_api.py)
    |               - Resmi untuk postingan akun Business/Creator terotorisasi
    |               - Pagination cursor + handling token & rate limit
    |
    +--> RAW Writer --------------------> data/raw/
    |       |
    |       +--> Run Metadata ----------> reports/run_<id>.json
    |
    +--> Explicit confirmation: Continue to NLP? [y/N]
            |
            +-- N --> Stop (RAW preserved)
            |
            +-- Y --> Preprocessing ------> data/processed/
                        |
                        +--> Annotation template/validation
                        |
                        +--> Baseline training <--> models/
                        |
                        +--> Prediction ------> data/predictions/
                        |
                        +--> Analysis --------> reports/
```

## 2. Prinsip Desain

- Pisahkan pengumpulan, preprocessing, anotasi, pelatihan, prediksi, dan analisis.
- RAW immutable: pipeline tidak boleh menimpa file RAW.
- Setiap eksekusi memiliki `run_id`.
- Konfigurasi nonrahasia dapat disimpan di `.env`; token jangan disimpan dalam source code.
- Adapter API dibuat terpisah karena endpoint dan izin berbeda menurut jenis login/API.
- URL Instagram tidak diasumsikan dapat langsung dipakai untuk endpoint komentar. Resolusi URL ke media ID harus mengikuti kemampuan API yang sah.
- Jika API tidak mendukung pengambilan komentar untuk media tersebut, program berhenti dengan instruksi yang jelas.

## 3. Penanganan API

Adapter harus:
1. Memvalidasi token dan versi API.
2. Memvalidasi bahwa media ID tersedia dan dapat diakses.
3. Menggunakan endpoint resmi (`/{ig-media-id}/comments`) untuk jenis autentikasi yang dipakai.
4. Mengikuti pagination resmi Meta Graph API (`paging.cursors.after`).
5. Menghormati rate limit dan retry hanya untuk error sementara dengan exponential backoff terbatas.
6. Tidak mengulang tanpa batas saat error izin (401/403), token kedaluwarsa, atau media tidak dapat diakses.
7. Tidak mencetak URL request yang mengandung token.
8. Tidak mengumpulkan field identitas yang tidak diperlukan.

## 4. Keamanan dan Sanitasi

- `src/logging_config.py` menyaring dan meredaksi access token dari semua level logging.
- `src/config.py` memuat kredensial menggunakan `pathlib.Path` untuk path `.env`.
- `main.py` dan CLI tidak menampilkan echo password saat input interaktif runtime (menggunakan `getpass`).
