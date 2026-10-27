# PRD — Product Requirements Document

## Instagram Slang NLP — Terminal-Based Dataset & Analysis Pipeline

**Versi:** 1.0  
**Status:** Draft untuk implementasi  
**Platform:** Windows CMD / PowerShell  
**Bahasa implementasi:** Python  
**Antarmuka:** Command Line Interface (CLI), tanpa UI web/desktop

---

## 1. Ringkasan Produk

Instagram Slang NLP adalah program berbasis terminal yang menerima URL postingan Instagram dan/atau informasi akses API dari pengguna, mengambil komentar melalui jalur akses yang diizinkan, menyimpan data mentah (RAW), lalu meminta konfirmasi eksplisit sebelum menjalankan tahap NLP. Setelah disetujui, program melakukan preprocessing, menghasilkan dataset hasil pemrosesan dan prediksi NLP, serta menyimpan laporan analisis.

Program tidak boleh menganggap URL Instagram saja cukup untuk mengambil komentar. Ketersediaan data bergantung pada API resmi, jenis akun, otorisasi, izin aplikasi, endpoint yang tersedia, dan batasan platform. Jika URL tidak dapat dipetakan ke media ID melalui jalur yang diizinkan, program harus meminta media ID atau memberi instruksi cara memperolehnya secara sah.

## 2. Tujuan

1. Mengumpulkan komentar Instagram melalui API resmi atau sumber data yang pengguna berhak akses.
2. Menyimpan hasil pengumpulan sebagai dataset RAW yang tidak ditimpa oleh proses lanjutan.
3. Meminta konfirmasi pengguna sebelum menjalankan NLP.
4. Membuat dataset terproses dan dataset prediksi NLP secara terpisah.
5. Menyediakan alur anotasi manual agar model dapat dilatih dan dievaluasi dengan label yang tervalidasi.
6. Menghasilkan laporan frekuensi bentuk slang, fungsi bahasa, serta metrik evaluasi model.
7. Menjalankan seluruh proses dari terminal Windows.

## 3. Di Luar Cakupan

- UI web, dashboard interaktif, atau aplikasi desktop.
- Mengakali login, CAPTCHA, rate limit, private account, atau kontrol akses Instagram.
- Mengambil komentar dari sembarang URL tanpa akses dan izin yang sesuai.
- Mengklaim label prediksi model sebagai kebenaran linguistik tanpa validasi manusia.
- Melatih model bahasa dari nol.
- Menghapus atau mengubah dataset RAW secara otomatis.

## 4. Pengguna Sasaran

Mahasiswa/peneliti yang ingin mengumpulkan dan menganalisis bentuk bahasa slang serta fungsi bahasa dalam komentar Instagram.

## 5. Alur Pengguna Utama

1. Pengguna menjalankan `python main.py`.
2. Program menampilkan menu terminal:
   - Kumpulkan komentar dari URL/media ID.
   - Proses dataset RAW yang sudah ada.
   - Jalankan anotasi/pelatihan/evaluasi.
   - Keluar.
3. Untuk pengumpulan data, program meminta URL postingan atau media ID.
4. Program memeriksa konfigurasi akses API dan meminta token secara aman bila belum disediakan melalui environment variable.
5. Program memvalidasi input dan akses. Token tidak boleh dicetak ke terminal atau disimpan di CSV.
6. Program mengumpulkan komentar yang tersedia, menangani pagination, duplikasi, error, dan batas jumlah.
7. Program menyimpan RAW, menampilkan jumlah data, lokasi file, dan keterbatasan pengambilan.
8. Program bertanya: `Lanjutkan ke tahap NLP sekarang? [y/N]`.
9. Jika pengguna menjawab `N`, program berhenti setelah RAW disimpan.
10. Jika `y`, program melakukan preprocessing dan menyimpan data processed terpisah.
11. Program bertanya lagi sebelum tindakan yang membutuhkan label manusia atau pelatihan model, bila dataset berlabel belum tersedia.
12. Program menyimpan prediksi dan laporan secara terpisah.

## 6. Persyaratan Fungsional

### FR-01 — Input URL/media
- Program menerima satu atau beberapa URL postingan atau media ID.
- Program tidak boleh mengklaim URL otomatis dapat diakses sebelum memvalidasi jalur akses.
- Jika URL tidak bisa diubah menjadi media ID melalui mekanisme resmi, minta media ID dari pengguna.

### FR-02 — Konfigurasi API
- Mendukung token melalui environment variable atau input tersembunyi saat runtime.
- Token tidak boleh ditulis ke source code, log, output terminal, CSV, atau Git.
- Mendukung konfigurasi versi API melalui `.env`/environment variable.
- Menampilkan pesan konfigurasi yang aman dan jelas jika token/izin tidak tersedia.

### FR-03 — Pengumpulan komentar
- Mengambil hanya data yang tersedia melalui akses yang diizinkan.
- Mendukung pagination API.
- Menerapkan target jumlah komentar yang dapat dikonfigurasi, misalnya 3.000.
- Menghindari duplikasi berdasarkan ID komentar.
- Mencatat media sumber, waktu pengambilan, status, dan error tanpa token.
- Menghormati limit API, menghentikan permintaan saat error otorisasi atau limit, dan tidak mencoba melewatinya.

### FR-04 — Penyimpanan RAW
- Menyimpan hasil ke `data/raw/`.
- RAW tidak ditimpa oleh preprocessing atau prediksi.
- Gunakan nama file bertimestamp atau ID run.
- Simpan metadata run dalam JSON tanpa token.

### FR-05 — Konfirmasi NLP
- Setelah RAW disimpan, program menampilkan jumlah komentar dan path file.
- Program meminta konfirmasi eksplisit sebelum NLP.
- Default harus `N` jika pengguna menekan Enter.
- Jawaban `N` menghentikan proses setelah RAW tersimpan.
- Jika pengguna menjawab `y`, proses berlanjut ke preprocessing.

### FR-06 — Preprocessing
- Mempertahankan teks asli.
- Membuat kolom teks bersih terpisah.
- Tidak menghapus emoji/tanda baca/huruf berulang secara membabi buta.
- Menghapus atau menandai komentar kosong dan duplikat dengan aturan yang terdokumentasi.
- Menyimpan hasil ke `data/processed/`.

### FR-07 — Dataset anotasi
- Menyediakan template CSV untuk label manual.
- Mendukung multi-label untuk bentuk slang dan fungsi bahasa.
- Memiliki status anotasi `belum`/`selesai`.
- Menyediakan validasi skema label sebelum pelatihan.

### FR-08 — Pelatihan NLP
- Baseline pertama menggunakan TF-IDF + Logistic Regression/One-vs-Rest.
- Model bentuk slang dan fungsi bahasa dilatih sebagai tugas terpisah.
- Pelatihan hanya dilakukan jika label manusia tersedia dan tervalidasi.
- Data uji tidak boleh dipakai saat fitting vectorizer.
- Versi lanjutan harus memisahkan data berdasarkan postingan untuk mengurangi kebocoran.

### FR-09 — Prediksi
- Menerapkan model tersimpan pada data baru.
- Menyimpan prediksi dalam `data/predictions/`.
- Tidak menimpa teks asli atau label manual.
- Prediksi harus dibedakan jelas dari label gold/manual.

### FR-10 — Laporan
- Menyimpan distribusi label, jumlah data, dan metrik model.
- Melaporkan precision, recall, F1 per kelas serta macro/micro average jika sesuai.
- Menandai kategori dengan data terlalu sedikit.
- Menyediakan laporan yang dapat dibaca dari terminal dan CSV.

## 7. Taksonomi Awal

### Bentuk slang
- `akronim`
- `singkatan`
- `bahasa_asing`
- `plesetan`
- `pemendekan`
- `tidak_ada`
- `lainnya`

### Fungsi bahasa
- `emotif`
- `referensial`
- `konatif`
- `tidak_jelas`

## 8. Dataset dan Artefak

- `data/raw/comments_<run_id>.csv`
- `data/processed/comments_clean_<run_id>.csv`
- `data/annotated/comments_labeled.csv`
- `data/predictions/comments_predictions_<run_id>.csv`
- `reports/run_<run_id>.json`
- `reports/slang_forms_distribution.csv`
- `reports/language_functions_distribution.csv`
- `reports/model_metrics.csv`
- `models/slang_forms_model.joblib`
- `models/language_functions_model.joblib`

## 9. Persyaratan Nonfungsional

- Kompatibel dengan Windows CMD dan PowerShell.
- Python versi stabil yang didukung dependensi (Python 3.10+).
- Pesan error harus actionable dan tidak membocorkan token.
- Semua tahapan dapat dijalankan terpisah dari terminal.
- RAW tidak pernah diubah oleh pipeline NLP.
- Menggunakan log run dan timestamp.
- Bisa melanjutkan dari dataset RAW tanpa mengulang pengambilan data.
- Memiliki dokumentasi setup, penggunaan, skema data, dan anotasi.
- Meminimalkan penyimpanan identitas pengguna komentar; username tidak dikumpulkan jika tidak diperlukan.

## 10. Keamanan, Etika, dan Kepatuhan

- Gunakan API resmi atau dataset yang pengumpulannya diizinkan.
- Jangan melakukan bypass login, kontrol akses, CAPTCHA, atau pembatasan platform.
- Simpan token di environment variable atau input tersembunyi; jangan commit `.env`.
- Terapkan minimisasi data dan kebijakan retensi.
- Periksa ketentuan platform, izin penelitian, serta aturan institusi sebelum pengumpulan.
- Jika akses ditolak atau limit tercapai, hentikan pengambilan dan jelaskan penyebabnya.
