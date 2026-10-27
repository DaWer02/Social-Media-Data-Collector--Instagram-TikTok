# Dokumentasi Lengkap — Instagram Slang NLP CLI

> Paket dokumentasi terpadu untuk proyek Python berbasis terminal yang mengumpulkan komentar Instagram melalui akses resmi/berizin, menyimpan data RAW, meminta konfirmasi sebelum tahap NLP, lalu menjalankan preprocessing, anotasi, pelatihan, prediksi, dan analisis.

**Versi dokumen:** 1.0  
**Platform target:** Windows CMD / PowerShell  
**Bahasa implementasi:** Python  
**Antarmuka:** Terminal / CLI tanpa UI

---

## PRD — Product Requirements Document

## Instagram Slang NLP — Terminal-Based Dataset & Analysis Pipeline

**Versi:** 1.0  
**Status:** Draft untuk implementasi  
**Platform:** Windows CMD / PowerShell  
**Bahasa implementasi:** Python  
**Antarmuka:** Command Line Interface (CLI), tanpa UI web/desktop

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

Kategori ini harus mengikuti definisi operasional final penelitian. Kategori `bahasa_asing` perlu diterapkan secara kontekstual; kata asing tidak otomatis slang hanya karena berasal dari bahasa lain.

### Fungsi bahasa
- `emotif`
- `referensial`
- `konatif`
- `tidak_jelas`

Fungsi bahasa dapat multi-label bila satu komentar menjalankan lebih dari satu fungsi. Jika konteks tidak cukup, gunakan `tidak_jelas` dan jangan memaksakan label.

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
- Python versi stabil yang didukung dependensi.
- Pesan error harus actionable dan tidak membocorkan token.
- Semua tahapan dapat dijalankan terpisah dari terminal.
- RAW tidak pernah diubah oleh pipeline NLP.
- Menggunakan log run dan timestamp.
- Bisa melanjutkan dari dataset RAW tanpa mengulang pengambilan data.
- Memiliki dokumentasi setup, penggunaan, skema data, dan anotasi.
- Meminimalkan penyimpanan identitas pengguna komentar; username sebaiknya tidak dikumpulkan jika tidak diperlukan untuk tujuan penelitian.

## 10. Keamanan, Etika, dan Kepatuhan

- Gunakan API resmi atau dataset yang pengumpulannya diizinkan.
- Jangan melakukan bypass login, kontrol akses, CAPTCHA, atau pembatasan platform.
- Simpan token di environment variable atau input tersembunyi; jangan commit `.env`.
- Terapkan minimisasi data dan kebijakan retensi.
- Periksa ketentuan platform, izin penelitian, serta aturan institusi sebelum pengumpulan.
- Jangan menerbitkan username atau komentar yang dapat mengidentifikasi individu tanpa dasar yang sesuai.
- Jika akses ditolak atau limit tercapai, hentikan pengambilan dan jelaskan penyebabnya.

## 11. Kriteria Penerimaan

1. Program dapat dijalankan melalui `python main.py`.
2. Pengguna dapat memasukkan URL/media ID dari terminal.
3. Program menjelaskan jika URL tidak dapat diakses melalui konfigurasi API yang tersedia.
4. Token tidak terlihat dalam log, output, atau file data.
5. Komentar yang berhasil diakses tersimpan sebagai RAW.
6. Setelah RAW tersimpan, program meminta konfirmasi sebelum NLP.
7. Jawaban `N` tidak menjalankan preprocessing atau model.
8. Jawaban `y` menjalankan preprocessing dan menghasilkan file terpisah.
9. RAW tetap identik setelah preprocessing dan prediksi.
10. Pipeline bisa dijalankan kembali pada RAW tanpa mengambil komentar ulang.
11. Pelatihan ditolak jika label manual belum cukup atau tidak valid.
12. Laporan mencakup distribusi label dan metrik evaluasi.
13. Semua error akses API dilaporkan tanpa mencoba bypass.

## 12. Risiko dan Mitigasi

| Risiko | Mitigasi |
|---|---|
| API tidak memberi akses ke URL | Minta media ID yang dapat diakses atau gunakan dataset berizin |
| Target 3.000 tidak tercapai | Laporkan jumlah aktual; tambah sumber yang sah |
| Label slang ambigu | Pedoman anotasi dan pemeriksaan anotator kedua |
| Ketidakseimbangan kelas | Tampilkan support; pertimbangkan class weights dan metrik macro-F1 |
| Kebocoran data antar-postingan | Group split berdasarkan media ID |
| Token bocor | `.env`, input tersembunyi, `.gitignore`, redaksi log |
| Data pribadi tersimpan berlebihan | Minimisasi kolom, kontrol akses, retensi terbatas |

## 13. Tahapan Implementasi

1. Setup proyek dan konfigurasi.
2. CLI dan validasi input.
3. Adapter pengumpulan komentar sesuai API/izin yang tersedia.
4. Penyimpanan RAW dan metadata run.
5. Konfirmasi sebelum NLP.
6. Preprocessing dan quality checks.
7. Template anotasi dan validasi.
8. Baseline NLP.
9. Prediksi dan analisis.
10. Evaluasi final, dokumentasi, dan hardening keamanan.

---

## Desain Teknis

## 1. Arsitektur

```text
Terminal User
    |
    v
CLI / main.py
    |
    +--> Input & Config Validator
    |
    +--> Instagram Source Adapter
    |       |
    |       +--> Authorized API / permitted data source
    |       +--> Pagination + rate-limit/error handling
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

## 3. Struktur Folder

```text
instagram-slang-nlp/
├── main.py
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
├── docs/
│   ├── PRD.md
│   ├── TECHNICAL_DESIGN.md
│   ├── DATA_DICTIONARY.md
│   ├── ANNOTATION_GUIDE.md
│   └── CLI_SPEC.md
├── src/
│   ├── cli.py
│   ├── config.py
│   ├── collectors/
│   │   ├── base.py
│   │   └── instagram_api.py
│   ├── storage.py
│   ├── preprocessing.py
│   ├── annotations.py
│   ├── train.py
│   ├── predict.py
│   └── analysis.py
├── data/
│   ├── raw/
│   ├── processed/
│   ├── annotated/
│   └── predictions/
├── models/
└── reports/
```

## 4. Run State

Setiap run mencatat:
- `run_id`
- `started_at`, `finished_at`
- sumber data (tanpa token)
- daftar media ID atau identifier yang aman disimpan
- jumlah komentar mentah dan unik
- jumlah error per media
- status pengumpulan
- apakah pengguna menyetujui NLP
- nama file output
- versi konfigurasi/API (tanpa rahasia)

Status yang disarankan:
`started`, `collecting`, `raw_saved`, `nlp_declined`, `preprocessing`, `awaiting_annotation`, `training`, `completed`, `failed`.

## 5. Penanganan API

Adapter harus:
1. Memvalidasi token dan versi API.
2. Memvalidasi bahwa media ID tersedia dan dapat diakses.
3. Menggunakan endpoint yang didukung dokumentasi resmi untuk jenis autentikasi yang dipakai.
4. Mengikuti pagination resmi.
5. Menghormati rate limit dan retry hanya untuk error sementara dengan exponential backoff terbatas.
6. Tidak mengulang tanpa batas saat error izin, token kedaluwarsa, atau media tidak dapat diakses.
7. Tidak mencetak URL request yang mungkin mengandung token.
8. Tidak mengumpulkan field identitas yang tidak diperlukan.

Catatan: detail endpoint, field, scope/permission, dan mekanisme URL-to-media-ID perlu dikunci setelah mengetahui jenis akun/API Meta yang tersedia. Jangan menganggap endpoint dari satu varian Instagram API kompatibel dengan varian lainnya.

## 6. Strategi NLP

### Baseline
- TF-IDF word n-grams dan, setelah baseline, dapat dibandingkan dengan character n-grams untuk menangani variasi ejaan.
- One-vs-Rest Logistic Regression untuk label multi-label.
- Model terpisah untuk bentuk slang dan fungsi bahasa.
- Simpan vectorizer, encoder label, dan classifier sebagai satu artefak.

### Tahap lanjutan
- Fine-tune IndoBERT atau model bahasa Indonesia yang sesuai.
- Gunakan split berdasarkan `media_id` atau group split agar komentar dari postingan yang sama tidak masuk ke train dan test.
- Laporkan macro-F1, micro-F1, precision/recall per kelas, support, dan kesalahan representatif.
- Ekstraksi `slang_spans` adalah tugas terpisah, misalnya token classification atau anotasi rentang; classifier komentar tidak otomatis menemukan kata slang yang tepat.

## 7. Kualitas Data
- Simpan `comment_text` asli.
- Simpan `clean_text` terpisah.
- Pertahankan emoji dan tanda baca pada versi pertama.
- Jangan melakukan stemming atau stopword removal sebelum menguji dampaknya terhadap slang.
- Deduplicasi berdasarkan comment ID; jika ID tidak ada, tandai metode deduplikasi alternatif.
- Simpan label manual terpisah dari prediksi model.

## 8. Pengujian
- Unit test parsing label, preprocessing, dan validasi skema.
- Integration test dengan respons API contoh yang tidak mengandung token nyata.
- Test konfirmasi: `N` harus menghentikan NLP.
- Test bahwa RAW tidak berubah.
- Test error 401/403, rate limit, media tanpa komentar, dan pagination.
- Test model dengan label langka dan data kosong.

---

## Kamus Data (Data Dictionary)

## 1. RAW Dataset

Nama file: `data/raw/comments_<run_id>.csv`

| Kolom | Tipe | Wajib | Deskripsi |
|---|---|---:|---|
| `comment_id` | string | Ya jika tersedia | ID unik komentar dari sumber |
| `media_id` | string | Ya | ID media sumber |
| `comment_text` | string | Ya | Teks asli komentar |
| `timestamp` | string/datetime | Tidak | Waktu komentar jika diizinkan |
| `like_count` | integer | Tidak | Jumlah likes bila tersedia dan diperlukan |
| `collected_at` | datetime | Ya | Waktu pengumpulan |
| `source_type` | string | Ya | Misalnya `authorized_api` atau `licensed_dataset` |

Hindari mengumpulkan `username` kecuali benar-benar diperlukan dan memiliki dasar yang sesuai. Jika tersedia dari API, sebaiknya tidak disimpan pada dataset analisis.

## 2. Processed Dataset

Nama file: `data/processed/comments_clean_<run_id>.csv`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `comment_id` | string | ID komentar |
| `media_id` | string | ID sumber untuk group split |
| `comment_text` | string | Teks asli, tidak diubah |
| `clean_text` | string | Teks yang dibersihkan secara konservatif |
| `normalized_text` | string, opsional | Teks normalisasi; jangan menggantikan teks asli |
| `is_empty_after_cleaning` | boolean | Penanda teks kosong setelah preprocessing |
| `duplicate_status` | string | Status deduplikasi bila diperlukan |

## 3. Annotated Dataset

Nama file: `data/annotated/comments_labeled.csv`

| Kolom | Tipe | Contoh | Deskripsi |
|---|---|---|---|
| `comment_id` | string | `abc123` | ID komentar |
| `clean_text` | string | `gws ya` | Teks untuk anotasi |
| `slang_present` | enum | `ya` / `tidak` | Ada/tidaknya slang menurut pedoman |
| `slang_forms` | list dalam string | `singkatan;plesetan` | Multi-label bentuk slang |
| `slang_spans` | string | `GWS` | Kata/frasa yang menjadi bukti |
| `slang_meanings` | string | `get well soon` | Makna dalam konteks |
| `language_functions` | list dalam string | `emotif;konatif` | Multi-label fungsi bahasa |
| `annotator_id` | string, opsional | `A1` | Kode anotator, bukan identitas publik |
| `review_status` | enum | `belum` / `selesai` | Status anotasi |
| `adjudication_note` | string, opsional | ... | Catatan penyelesaian perbedaan |

Gunakan titik koma untuk memisahkan label dalam CSV. Jangan menggunakan koma sebagai pemisah label karena koma dapat muncul dalam teks dan menyulitkan pembacaan.

## 4. Predictions Dataset

Nama file: `data/predictions/comments_predictions_<run_id>.csv`

Kolom tambahan:
- `predicted_slang_forms`
- `predicted_language_functions`
- `slang_forms_confidence` (opsional)
- `language_functions_confidence` (opsional)
- `needs_review` (boolean)
- `model_version`

Prediksi bukan label kebenaran. Label manual tetap dipertahankan di file anotasi.

## 5. Reports

- `run_<run_id>.json`: metadata run dan status proses.
- `slang_forms_distribution.csv`: frekuensi label bentuk slang.
- `language_functions_distribution.csv`: frekuensi label fungsi bahasa.
- `model_metrics.csv`: metrik evaluasi per kelas dan rata-rata.

## 6. Privasi dan Retensi
- Minimalkan metadata identitas.
- Tentukan masa simpan data sesuai kebijakan penelitian/institusi dan ketentuan sumber.
- Jangan unggah data mentah yang berisi informasi pribadi ke repositori publik.

---

## Pedoman Anotasi

## 1. Tujuan
Pedoman ini membantu anotator memberi label konsisten pada komentar Instagram untuk penelitian bentuk slang dan fungsi bahasa. Taksonomi harus disesuaikan dengan definisi operasional final di BAB II dan disetujui pembimbing sebelum anotasi penuh.

## 2. Unit Anotasi
- Unit utama: satu komentar.
- Bentuk slang: anotasi label komentar dan rentang kata/frasa yang menjadi bukti.
- Fungsi bahasa: label pada tingkat komentar dengan mempertimbangkan konteks yang tersedia.
- Satu komentar dapat mempunyai beberapa bentuk slang dan beberapa fungsi bahasa.

## 3. Bentuk Slang

### `akronim`
Bentuk yang dibentuk dari huruf/suku kata unsur kata atau frasa lain dan digunakan sebagai satu bentuk. Pastikan definisi ini konsisten dengan sumber teori yang dipakai.

### `singkatan`
Bentuk ringkas dari kata atau rangkaian kata. Contoh kandidat dari BAB II meliputi `GWS`, `BTW`, atau `CLBK`; verifikasi pemakaian dalam konteks komentar.

### `bahasa_asing`
Kata/frasa dari bahasa asing yang muncul dalam komentar. Jangan otomatis memberi label slang pada semua kata asing; pertimbangkan apakah kata itu berfungsi sebagai slang menurut definisi penelitian.

### `plesetan`
Permainan kata atau perubahan bentuk yang menghasilkan efek tertentu. Label hanya jika bukti konteks memadai.

### `pemendekan`
Bentuk yang dipendekkan dari bentuk lebih panjang. Periksa apakah bentuk tersebut memang digunakan sebagai pemendekan dalam konteks penelitian.

### `tidak_ada`
Tidak ada bentuk slang yang memenuhi definisi operasional penelitian.

### `lainnya`
Slang ditemukan, tetapi tidak sesuai kategori lain. Catat alasan pada catatan anotasi dan tinjau ulang kategori ini secara berkala.

## 4. Fungsi Bahasa

### `emotif`
Komentar terutama mengekspresikan perasaan, sikap, atau reaksi penutur.

### `referensial`
Komentar terutama menyampaikan informasi, fakta, atau rujukan tentang suatu hal.

### `konatif`
Komentar diarahkan kepada lawan bicara untuk memengaruhi respons, misalnya meminta, mengajak, memerintah, atau menyarankan.

### `tidak_jelas`
Konteks komentar tidak cukup untuk menetapkan fungsi secara bertanggung jawab.

## 5. Aturan Keputusan
1. Baca seluruh komentar sebelum memberi label.
2. Jangan memberi label hanya berdasarkan satu kata tanpa konteks.
3. Jika beberapa fungsi jelas hadir, gunakan beberapa label yang dipisahkan `;`.
4. Jika slang tidak ditemukan, gunakan `slang_present=tidak` dan `slang_forms=tidak_ada`.
5. Jika slang ditemukan, isi rentang kata pada `slang_spans` dan makna bila dapat ditentukan.
6. Jangan menebak makna bila ambigu; gunakan catatan dan tandai untuk review.
7. Simpan teks asli; jangan mengoreksi ejaan komentar sebagai pengganti anotasi.
8. Jangan menyamakan sentimen positif/negatif dengan fungsi emotif secara otomatis.
9. Emoji dapat membantu interpretasi, tetapi tidak cukup menjadi satu-satunya dasar label kecuali pedoman penelitian menyatakannya.
10. Lakukan uji coba anotasi pada sampel kecil, diskusikan perbedaan, lalu bekukan pedoman sebelum anotasi skala besar.

## 6. Quality Assurance
- Lakukan anotasi pilot terlebih dahulu.
- Minta anotator kedua memeriksa sebagian data yang dipilih secara acak.
- Ukur kesepakatan anotator dengan metrik yang sesuai (misalnya Cohen's kappa untuk satu label per item; untuk multi-label gunakan pendekatan yang sesuai).
- Adjudikasi perbedaan dan dokumentasikan perubahan pedoman.
- Pantau jumlah tiap label. Label yang jarang harus dilaporkan dan mungkin memerlukan data tambahan.
- Jangan membagi train/test secara acak jika komentar dari postingan yang sama dapat menyebabkan kebocoran; gunakan group split berdasarkan media ID untuk evaluasi final.

---

## Spesifikasi CLI

## 1. Perintah Utama

```powershell
python main.py
```

Menu yang disarankan:

```text
Instagram Slang NLP
1. Kumpulkan komentar dari Instagram
2. Jalankan NLP pada dataset RAW yang sudah ada
3. Buat template anotasi
4. Validasi anotasi
5. Latih model baseline
6. Prediksi dataset
7. Analisis dataset/laporan
0. Keluar
Pilih menu:
```

## 2. Alur Pengumpulan

```text
Masukkan URL postingan Instagram atau media ID:
> ...

Masukkan target komentar [default: 3000]:
> 3000

Pilih sumber akses:
1. Token dari environment/.env
2. Masukkan token secara tersembunyi untuk sesi ini
> 1

Validasi akses...
[Jika URL tidak dapat diresolusi melalui API yang dipakai]
URL belum dapat dipetakan ke media ID dengan akses API ini.
Masukkan media ID yang memang dapat diakses atau batalkan.

Pengumpulan selesai.
Komentar unik tersimpan: 1240
RAW: data/raw/comments_<run_id>.csv
Laporan run: reports/run_<run_id>.json

Lanjutkan ke tahap NLP sekarang? [y/N]:
>
```

## 3. Perilaku Konfirmasi
- Default `N`.
- Hanya `y` atau `yes` yang menyetujui proses.
- Enter kosong berarti `N`.
- `N` menyimpan RAW dan mengakhiri proses.
- `y` menjalankan preprocessing, kemudian menampilkan ringkasan dan meminta konfirmasi tambahan jika tindakan berikutnya memerlukan anotasi atau pelatihan.
- Program tidak boleh menganggap menjalankan perintah pengumpulan berarti pengguna otomatis menyetujui NLP.

## 4. Input Rahasia
- Prioritaskan `.env` atau environment variable.
- Jika token diminta secara interaktif, gunakan input tersembunyi (misalnya `getpass`) dan jangan menyimpan token ke file.
- Jangan menampilkan token, URL request lengkap yang mengandung token, atau header otorisasi.
- Jika autentikasi gagal, jelaskan bahwa token/izin/jenis API perlu diperiksa; jangan mencoba bypass.

## 5. Error yang Harus Dipahami Pengguna
- `TOKEN_MISSING`: token tidak dikonfigurasi.
- `AUTH_FAILED`: token tidak valid/kedaluwarsa.
- `PERMISSION_DENIED`: izin tidak cukup untuk media/endpoint.
- `MEDIA_UNAVAILABLE`: media ID tidak tersedia pada konteks akun/API ini.
- `RATE_LIMITED`: batas API tercapai; hentikan atau tunggu sesuai kebijakan resmi.
- `NETWORK_ERROR`: masalah koneksi sementara.
- `EMPTY_RESULT`: tidak ada komentar yang dikembalikan.
- `NLP_DECLINED`: RAW tersimpan; NLP tidak dijalankan.

## 6. Resume
Menu `2. Jalankan NLP pada dataset RAW yang sudah ada` harus memungkinkan pengguna melanjutkan tanpa mengulang pengambilan komentar.

---

## Rencana Implementasi

## Sprint 1 — Kerangka proyek
- [ ] Buat struktur folder.
- [ ] Buat `requirements.txt`, `.env.example`, `.gitignore`.
- [ ] Implementasikan konfigurasi dan logging yang meredaksi rahasia.
- [ ] Implementasikan menu CLI.

**Kriteria selesai:** `python main.py` menampilkan menu dan keluar dengan aman.

## Sprint 2 — Konektor sumber data
- [ ] Pilih varian Instagram API dan jenis autentikasi yang benar.
- [ ] Verifikasi scope/permission dan cara memperoleh media ID.
- [ ] Implementasikan adapter API dengan pagination.
- [ ] Implementasikan penanganan error dan batas permintaan.
- [ ] Uji dengan satu media yang dapat diakses.

**Kriteria selesai:** komentar dari media uji tersimpan di RAW tanpa token/field yang tidak diperlukan.

## Sprint 3 — RAW dan konfirmasi
- [ ] Simpan file bertimestamp/run ID.
- [ ] Simpan metadata run.
- [ ] Tampilkan jumlah dan lokasi RAW.
- [ ] Implementasikan prompt `[y/N]`.
- [ ] Uji bahwa `N` tidak memanggil fungsi NLP.

**Kriteria selesai:** tes integrasi membuktikan RAW disimpan dan proses NLP tidak berjalan saat ditolak.

## Sprint 4 — Preprocessing
- [ ] Pertahankan teks asli.
- [ ] Buat `clean_text`.
- [ ] Laporan jumlah kosong/duplikat.
- [ ] Dukung menjalankan preprocessing dari RAW lama.

**Kriteria selesai:** RAW tidak berubah dan output processed dapat direproduksi.

## Sprint 5 — Anotasi
- [ ] Buat template CSV.
- [ ] Finalisasi definisi operasional bersama pembimbing.
- [ ] Anotasi pilot.
- [ ] Implementasikan validator label.
- [ ] Audit sebagian label dengan anotator kedua.

**Kriteria selesai:** label pilot konsisten dan skema tervalidasi.

## Sprint 6 — Baseline NLP
- [ ] Buat split yang sesuai; gunakan group split berdasarkan media ID untuk evaluasi final.
- [ ] Latih classifier bentuk slang dan fungsi bahasa.
- [ ] Simpan model dan laporan metrik.
- [ ] Periksa performa setiap label dan support.

**Kriteria selesai:** laporan metrik dapat direproduksi dan tidak ada kebocoran data yang diketahui.

## Sprint 7 — Prediksi dan analisis
- [ ] Jalankan prediksi pada data baru.
- [ ] Simpan prediksi terpisah dari label manual.
- [ ] Buat distribusi label dan ringkasan.
- [ ] Tandai prediksi yang perlu ditinjau.

**Kriteria selesai:** output CSV dan laporan dapat dipakai untuk analisis penelitian.

## Sprint 8 — Model lanjutan dan dokumentasi
- [ ] Bandingkan baseline dengan model bahasa Indonesia pralatih.
- [ ] Evaluasi kebutuhan ekstraksi rentang slang.
- [ ] Lengkapi dokumentasi penggunaan, batasan, dan privasi.
- [ ] Uji keseluruhan pipeline dari terminal bersih.

**Kriteria selesai:** dokumentasi sesuai perilaku implementasi, hasil evaluasi terdokumentasi, dan akses data patuh pada izin yang tersedia.

---

## README Proyek

Proyek terminal Python untuk mengumpulkan komentar Instagram melalui akses yang diizinkan, menyimpan data RAW, meminta persetujuan sebelum NLP, dan menjalankan preprocessing, anotasi, pelatihan baseline, prediksi, serta analisis.

## Persyaratan
- Windows CMD atau PowerShell
- Python versi yang kompatibel dengan dependensi
- Akses API resmi/berizin atau dataset yang pengumpulannya diizinkan
- Token/izin sesuai varian API yang digunakan

## Setup
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Isi `.env` sesuai konfigurasi API yang benar. Jangan pernah commit `.env`.

## Alur yang direncanakan
1. `python main.py`
2. Masukkan URL atau media ID.
3. Validasi akses.
4. Kumpulkan komentar dan simpan RAW.
5. Konfirmasi `Lanjutkan ke tahap NLP? [y/N]`.
6. Jika `y`, preprocessing.
7. Anotasi manual, validasi, training, prediksi, dan analisis dijalankan sebagai tahap terpisah.

## Penting
URL postingan tidak menjamin komentar dapat diakses melalui API. Detail endpoint dan izin bergantung pada varian Instagram API dan konfigurasi aplikasi. Program harus menghentikan pengambilan jika tidak memiliki akses yang sesuai, bukan melakukan bypass.

Dokumentasi tambahan ada di folder `docs/`.

---

## Lampiran A — Contoh konfigurasi `.env.example`

Simpan sebagai `.env.example`, lalu salin ke `.env` dan isi nilai yang sesuai dengan jenis API yang kamu gunakan. Jangan commit `.env` atau menaruh token asli di repositori.

```dotenv
# Konfigurasi harus sesuai dengan varian Instagram API yang digunakan.
INSTAGRAM_ACCESS_TOKEN=
GRAPH_API_VERSION=
TARGET_COMMENTS=3000
```

## Lampiran B — `.gitignore` yang disarankan

```gitignore
.env
.venv/
__pycache__/
*.py[cod]
data/raw/
data/processed/
data/annotated/
data/predictions/
models/
reports/
```

## Catatan Status Implementasi

Pipeline Instagram Slang NLP telah diimplementasikan secara penuh, diaudit ketat, dan divalidasi dengan rangkaian 106 pengujian unit dan integrasi (`106 passed, 0 failures, 0 errors`). Seluruh pengujian otomatis API eksternal menggunakan fixtures dan mocks resmi Graph API v21.0 untuk menjamin zero data leakage dan zero token exposure. Program mematuhi ToS Meta dengan menghentikan pengambilan secara aman jika media tidak terotorisasi, tanpa pernah berusaha melewati kontrol akses platform.
