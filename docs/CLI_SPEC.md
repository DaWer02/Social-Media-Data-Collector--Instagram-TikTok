# Spesifikasi Antarmuka Baris Perintah (CLI Specification)

## 1. Perintah Utama
```powershell
python main.py
```
Atau untuk memeriksa status konfigurasi secara non-interaktif:
```powershell
python main.py --status
```

Tampilan menu utama persis pada runtime:
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

## 2. Alur Pengumpulan & Prompt Konfirmasi
1. Pengguna memasukkan URL postingan atau Media ID.
2. Validasi kredensial (tanpa mencetak token).
3. Pengumpulan komentar dengan cursor pagination dan deduplikasi in-stream.
4. Penyimpanan dataset ke `data/raw/comments_<run_id>.csv` dan metadata ke `reports/run_<run_id>.json`.
5. **Prompt Konfirmasi Eksplisit:**
   ```text
   Lanjutkan ke tahap NLP sekarang? [y/N]: 
   ```
   - Input kosong (Enter) -> default `N`
   - Input `N` / `n` atau teks lain -> Berhenti dengan aman. Data RAW utuh. Status tercatat `nlp_declined`.
   - Input `y` / `yes` -> Lanjut ke tahap preprocessing saja (tanpa menjalankan training otomatis).

## 3. Penanganan Error Standar
- `AuthenticationError`: Token akses Meta tidak diset, tidak valid, atau kedaluwarsa.
- `PermissionDeniedError`: Akun bukan akun Profesional atau token tidak memiliki izin komentar yang sah (`instagram_manage_comments` / `instagram_business_manage_comments`).
- `MediaUnavailableError`: Postingan tidak dapat diakses atau bukan milik akun profesional yang terotorisasi.
- `RateLimitError`: Batas panggilan API Meta terlampaui.
- `NetworkCollectorError`: Gangguan konektivitas internet atau kegagalan koneksi ke server Meta setelah percobaan berulang (*exponential backoff*).
- `AnnotationSchemaValidationError`: Format atau konsistensi dataset anotasi manual tidak memenuhi aturan.
- `InsufficientDataForSplitError`: Dataset anotasi memiliki kurang dari 2 postingan berbeda (`media_id`), sehingga GroupSplit held-out test tidak dapat dilakukan secara valid.
