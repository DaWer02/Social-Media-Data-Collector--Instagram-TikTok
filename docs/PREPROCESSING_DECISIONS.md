# Dokumentasi Keputusan Desain Preprocessing — Instagram Slang NLP

Dokumen ini mencatat rasionalisasi linguistik dan teknis di balik tahapan preprocessing data komentar Instagram, sesuai spesifikasi PRD dan Kamus Data (*Data Dictionary*).

---

## 1. Prinsip Utama: Konservatif & Non-Destruktif

Pemrosesan bahasa alami (NLP) pada ragam bahasa slang media sosial memiliki karakteristik unik dibandingkan teks formal. Penerapan teknik preprocessing konvensional secara membabi buta dapat menghilangkan fitur linguistik paling berharga.

Oleh karena itu, preprocessing pada pipeline ini menganut prinsip:
> **"Preservasi Maksimal, Pembersihan Terkendali, RAW Immutable."**

---

## 2. Rincian Keputusan Teknis

### A. Preservasi Teks Asli (`comment_text`)
- Kolom `comment_text` menyimpan teks komentar mentah persis seperti yang dikembalikan oleh API atau sumber data.
- Nilai ini **tidak boleh dimodifikasi sedikit pun** (termasuk spasi, kapitalisasi, dan karakter khusus). Hal ini esensial untuk keperluan validasi manusia dan reproduktibilitas penelitian.

### B. Normalisasi URL (`[URL]`)
- Tautan web (misalnya `https://bit.ly/xyz` atau `www.tokopedia.com/...`) dinormalisasi menjadi token kanonikal `[URL]`.
- **Rasional:** URL tidak merepresentasikan bentuk slang dan dapat menimbulkan ledakan *vocabulary* (out-of-vocabulary noise). Namun, keberadaan tautan tetap perlu dicatat karena komentar yang memuat tautan sering kali menjalankan fungsi bahasa tertentu (misalnya referensial atau konatif/promosi).

### C. Mengapa Emoji Dipertahankan?
- Emoji (seperti 🔥, 😂, 🙏, 😭, 💀) **tetap dipertahankan** di dalam `clean_text`.
- **Rasional:** Dalam interaksi media sosial, emoji merupakan penanda modalitas, ekspresi emosional, dan sarkasme. Penghapusan emoji akan mendegradasi kemampuan model dalam mengklasifikasikan **fungsi bahasa** (terutama fungsi emotif dan konatif).

### D. Mengapa Tanda Baca dan Huruf Berulang Dipertahankan?
- Tanda baca (seperti `!`, `?`, `...`, `-`) dan huruf yang dipanjangkan (misalnya `bangeeet`, `kuyyy`, `loool`, `huwaaa`) **tidak dihapus atau dipangkas secara otomatis**.
- **Rasional:** Pemanjangan huruf (*elongation*) adalah salah satu bentuk ekspresi fonetik paling produktif dalam slang digital Indonesia untuk menegaskan intensitas. Memangkas huruf berulang pada tahap awal berisiko merusak identifikasi bentuk slang.

### E. Mengapa Stemming & Stopword Removal Dilarang pada Versi Pertama?
- **Stemming (seperti algoritma Nazief-Adriani / Sastrawi):** Algoritma stemming formal dirancang untuk bahasa Indonesia baku. Ketika diterapkan pada slang:
  - `mager` (malas gerak) dapat salah dipotong menjadi `pagar`.
  - `baper` (bawa perasaan) dapat rusak menjadi bentuk dasar yang tidak relevan.
  - Bentuk akronim dan singkatan (`GWS`, `BTW`, `OOT`) berisiko mengalami *over-stemming*.
- **Stopword Removal:** Kata-kata seperti `di`, `ke`, `yang`, `sih`, `dong`, `nih`, `ya` sering kali berfungsi sebagai penanda wacana percakapan (*discourse markers*) yang krusial untuk menganalisis fungsi pragmatik bahasa slang.

### F. Kolom Tambahan `normalized_text`
- Menampung versi teks yang telah dibersihkan dan diubah menjadi huruf kecil (*lowercase*).
- Disimpan pada kolom terpisah sehingga pengguna dapat memilih antara representasi teks asli, teks bersih berkasing asli (`clean_text`), atau teks normalisasi huruf kecil (`normalized_text`).

### G. Penanganan Duplikasi & Teks Kosong
- **Deduplikasi berbasis Comment ID:** Komentar dengan `comment_id` yang sama ditandai statusnya (`duplicate_status = "duplicate"`), sedangkan kemunculan pertama ditandai `"unique"`.
- **Deteksi Teks Kosong:** Baris yang setelah pembersihan hanya menyisakan spasi kosong ditandai `is_empty_after_cleaning = "true"`.
- Pelaporan kuantitatif menyajikan: jumlah awal, jumlah kosong, jumlah duplikat, dan jumlah akhir yang siap dianalisis.

### H. Integritas & Immutability RAW
- Modul preprocessing membuka file RAW **hanya dalam mode baca (*read-only*)**.
- Integritas data diverifikasi menggunakan *cryptographic hash* SHA-256 yang dibuktikan tidak mengalami perubahan sebelum dan sesudah tahap preprocessing dijalankan.
