# Pedoman Anotasi Manual (Annotation Guide) — Instagram Slang NLP

Dokumen ini memandu peneliti dan anotator dalam melakukan pelabelan data komentar Instagram untuk penelitian bentuk slang dan fungsi bahasa.

---

## 1. Prinsip Validitas Ilmiah: Anotasi Wajib Ditinjau Manusia

> [!IMPORTANT]
> **Tidak Ada Auto-Labeling:**  
> Sistem ini **secara sengaja tidak melakukan pelabelan otomatis** menggunakan kamus slang atau aturan heuristik.  
> Slang media sosial sangat bergantung pada konteks situasional, pragmatik penutur, dan perubahan budaya internet yang dinamis. Oleh karena itu, seluruh label *ground truth* (gold standard) **wajib ditinjau, diberi label, dan divalidasi oleh manusia**.

---

## 2. Unit Anotasi & Skema File

- File target anotasi disimpan di: `data/annotated/comments_labeled.csv`.
- Unit analisis: Satu baris komentar unik (`clean_text`).
- Karakter pemisah multi-label: **Titik koma (`;`)**. Dilarang menggunakan tanda koma (`,`) agar tidak merusak format CSV.

| Kolom | Tipe Data | Contoh | Deskripsi |
| :--- | :--- | :--- | :--- |
| `comment_id` | string | `18001122` | ID unik komentar dari sumber |
| `clean_text` | string | `gws ya kak` | Teks bersih komentar yang akan dianotasi |
| `slang_present` | enum | `ya` / `tidak` | Menandai apakah komentar memuat bentuk slang |
| `slang_forms` | multi-label (`;`) | `singkatan;akronim` | Kategori bentuk slang (gunakan `tidak_ada` jika `slang_present=tidak`) |
| `slang_spans` | string | `GWS` | Kata atau frasa bukti slang yang ditemukan |
| `slang_meanings` | string | `get well soon` | Arti atau makna slang dalam konteks komentar |
| `language_functions`| multi-label (`;`) | `emotif;konatif` | Fungsi bahasa yang dijalankan oleh komentar |
| `annotator_id` | string | `A1` | Kode identitas anotator |
| `review_status` | enum | `belum` / `selesai` | Status proses anotasi (default: `belum`) |
| `adjudication_note` | string | `disepakati tim` | Catatan resolusi jika ada keraguan label |

---

## 3. Taksonomi Resmi Bentuk Slang

Kategori bentuk slang berikut harus dipisahkan dengan tanda `;` jika satu komentar memiliki lebih dari satu bentuk:

1. **`akronim`:** Bentuk gabungan huruf awal atau suku kata yang dibaca sebagai satu kata utuh (contoh: *curcol* $\rightarrow$ curhat colongan, *pansos* $\rightarrow$ panjat sosial, *mager* $\rightarrow$ malas gerak).
2. **`singkatan`:** Bentuk ringkas kata atau rangkaian kata yang dieja per huruf atau merupakan inisial (contoh: *GWS*, *BTW*, *OOT*, *TBH*, *CLBK*).
3. **`bahasa_asing`:** Kata atau frasa bahasa asing yang diserap dan difungsikan secara khusus sebagai slang percakapan (contoh: *bestie*, *slay*, *cringe*, *spill*).
4. **`plesetan`:** Permainan kata, substitusi fonetik, atau pembalikan suku kata yang disengaja (contoh: *ngab*, *kuy*, *santuy*, *sans*).
5. **`pemendekan`:** Kata baku yang dipotong suku katanya (contoh: *bgt* $\rightarrow$ banget, *tp* $\rightarrow$ tapi, *sdh* $\rightarrow$ sudah).
6. **`tidak_ada`:** Komentar tidak memuat bentuk slang apa pun.
7. **`lainnya`:** Bentuk slang yang valid namun belum terwadahi dalam kategori di atas.

---

## 4. Taksonomi Resmi Fungsi Bahasa (Roman Jakobson)

Satu komentar dapat memiliki lebih dari satu fungsi (multi-label dipisahkan dengan `;`):

1. **`emotif`:** Berfokus pada penutur; mengekspresikan perasaan, reaksi emosional, kegembiraan, kekesalan, atau sikap pribadi penutur (contoh: *"Keren bangeeet 🔥"*, *"Sedih bgt liatnya 😭"*).
2. **`referensial`:** Berfokus pada konteks atau topik; menyampaikan informasi, fakta objektif, rujukan, atau data (contoh: *"Lokasinya di jalan Sudirman nomor 5"*, *"Harganya 50 ribu per porsi"*).
3. **`konatif`:** Berfokus pada mitra tutur/pembaca; bertujuan memengaruhi, membujuk, mengajak, memerintah, atau menyarankan tindakan (contoh: *"Yuk buruan beli sebelum kehabisan!"*, *"Jangan lupa subscribe ya gaes"*).
4. **`tidak_jelas`:** Konteks komentar terlalu ambigu, tidak lengkap, atau tidak memungkinkan penentuan fungsi bahasa secara bertanggung jawab.

---

## 5. Aturan Konsistensi Validasi

Validator sistem ([`src/annotations.py`](file:///d:/WEBKU/NLP/src/annotations.py)) akan memeriksa aturan logika berikut:

1. **Korelasi Keberadaan Slang:**
   - Jika `slang_present = "tidak"`, maka `slang_forms` **wajib** bernilai `tidak_ada`.
   - Jika `slang_present = "ya"`, maka `slang_forms` **tidak boleh** bernilai `tidak_ada` (harus memuat minimal satu bentuk slang yang sah).
2. **Kelengkapan Anotasi Selesai (`review_status = "selesai"`):**
   - Kolom `slang_present` tidak boleh kosong (harus `ya` atau `tidak`).
   - Kolom `language_functions` tidak boleh kosong dan seluruh labelnya harus terdaftar dalam taksonomi resmi.
3. **Deduplikasi ID:**
   - Kolom `comment_id` harus unik. Jika terdapat ID duplikat, validator akan menolaknya.
4. **Non-Destructive Merge:**
   - Pembuatan ulang template melalui Menu 3 **tidak akan menghapus** baris yang sudah dianotasi sebelumnya. Data lama digabungkan berdasarkan `comment_id`.

---

## 6. Alur Kerja Praktis Anotator

1. **Buat / Perbarui Template:** Jalankan `python main.py` $\rightarrow$ pilih menu **`3. Buat template anotasi`**. File `data/annotated/comments_labeled.csv` akan dibuat.
2. **Buka di Spreadsheet:** Buka `comments_labeled.csv` di editor CSV/Excel/LibreOffice.
3. **Beri Label:**
   - Isi `slang_present` (`ya` atau `tidak`).
   - Isi `slang_forms` (contoh: `singkatan;plesetan`).
   - Isi `language_functions` (contoh: `emotif;konatif`).
   - Jika selesai ditinjau manusia, ubah `review_status` dari `belum` menjadi `selesai`.
4. **Simpan CSV dengan UTF-8.**
5. **Validasi:** Jalankan menu **`4. Validasi anotasi`** untuk memastikan tidak ada kesalahan ketik, label di luar taksonomi, atau inkonsistensi sebelum tahap pelatihan baseline model.
