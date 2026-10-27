# Kamus Data (Data Dictionary)

## 1. RAW Dataset

Nama file: `data/raw/comments_<run_id>.csv`

| Kolom | Tipe | Wajib | Deskripsi |
|---|---|---:|---|
| `comment_id` | string | Ya jika tersedia | ID unik komentar dari sumber |
| `media_id` | string | Ya | ID media sumber |
| `comment_text` | string | Ya | Teks asli komentar (tidak diubah) |
| `timestamp` | string/datetime | Tidak | Waktu komentar jika diizinkan |
| `like_count` | integer | Tidak | Jumlah likes bila tersedia |
| `collected_at` | datetime | Ya | Waktu pengumpulan data (ISO format) |
| `source_type` | string | Ya | `authorized_api` atau `licensed_dataset` |

## 2. Processed Dataset

Nama file: `data/processed/comments_clean_<run_id>.csv`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `comment_id` | string | ID unik komentar |
| `media_id` | string | ID sumber untuk group split cross-validation |
| `comment_text` | string | Teks asli, tidak diubah |
| `clean_text` | string | Teks yang dibersihkan secara konservatif |
| `normalized_text` | string, opsional | Teks normalisasi tanpa menggantikan teks asli |
| `is_empty_after_cleaning` | boolean | Penanda teks kosong setelah preprocessing |
| `duplicate_status` | string | Status deduplikasi berdasarkan `comment_id` |

## 3. Annotated Dataset

Nama file: `data/annotated/comments_labeled.csv`

| Kolom | Tipe | Contoh | Deskripsi |
|---|---|---|---|
| `comment_id` | string | `abc123` | ID komentar |
| `clean_text` | string | `gws ya` | Teks untuk anotasi |
| `slang_present` | enum | `ya` / `tidak` | Ada/tidaknya slang menurut pedoman |
| `slang_forms` | list dalam string | `singkatan;plesetan` | Multi-label bentuk slang (pemisah `;`) |
| `slang_spans` | string | `GWS` | Kata/frasa bukti slang |
| `slang_meanings` | string | `get well soon` | Makna dalam konteks |
| `language_functions` | list dalam string | `emotif;konatif` | Multi-label fungsi bahasa (pemisah `;`) |
| `annotator_id` | string, opsional | `A1` | Kode anotator |
| `review_status` | enum | `belum` / `selesai` | Status anotasi |
| `adjudication_note` | string, opsional | ... | Catatan penyelesaian perbedaan |

## 4. Predictions Dataset

Nama file: `data/predictions/comments_predictions_<run_id>.csv`

| Kolom | Tipe | Deskripsi |
|---|---|---|
| `comment_id` | string | ID komentar |
| `clean_text` | string | Teks yang dievaluasi |
| `predicted_slang_forms` | string | Multi-label prediksi bentuk slang (pemisah `;`) |
| `predicted_language_functions` | string | Multi-label prediksi fungsi bahasa (pemisah `;`) |
| `slang_forms_confidence` | float | Tingkat keyakinan prediksi bentuk slang |
| `language_functions_confidence` | float | Tingkat keyakinan prediksi fungsi bahasa |
| `needs_review` | boolean | Penanda prediksi yang memerlukan verifikasi manusia |
| `model_version` | string | Identitas versi model |
