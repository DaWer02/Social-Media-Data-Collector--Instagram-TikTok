# Pipeline dataset REDAM.id

Dokumen kebutuhan produk untuk pipeline ini tersedia di [`PRD_PENGUMPULAN_DATA_REDAM.md`](PRD_PENGUMPULAN_DATA_REDAM.md).

Implementasi terpisah dari pipeline slang lama. Jalankan dari `D:\WEBKU\NLP` menggunakan Python 3.11+. Perintah Windows di bawah menggunakan `py -3.11` karena alias `python` pada mesin pengembangan tidak dapat dijalankan. Tidak mengubah aplikasi REDAM.id atau kontrak HTTP-nya.

## Alur penggunaan

### Menu terminal

Jalankan `py -3.11 main.py`, kemudian pilih **8. REDAM.id**. Untuk langsung membuka menu REDAM gunakan `py -3.11 main.py --redam` atau `py -3.11 -m src.redam` tanpa argumen. Perintah subcommand di bawah tetap tersedia untuk otomasi.

Menu menyediakan pembuatan demo, koleksi browser, impor/pembersihan, lokasi lembar anotasi, validasi, rilis, daftar paket, dan panduan. Folder paket dapat dipilih dengan nomor. Output memakai folder baru bertimestamp secara default. Masukkan `0` pada prompt path untuk batal. Jika secret belum tersedia di environment, menu meminta input tersembunyi dan menyimpannya hanya selama proses berjalan. Anotasi manusia tetap diisi melalui berkas CSV yang ditunjukkan menu 4.

1. `collect` (opsional): pengambilan browser dari manifest penelitian yang memiliki URL, hak akses, reviewer, dan lokator teruji.
2. `prepare`: impor CSV/array JSON, minimisasi identitas, normalisasi, audit duplikasi teknis, dan template anotasi.
3. Dua manusia mengisi `annotations.csv`; adjudikator ketiga menyelesaikan konflik di `adjudications.csv`.
4. `validate`: pemeriksaan integritas dan kesepakatan. Kelulusan anotasi belum berarti dataset siap latih.
5. Review manual PII/hak penggunaan, isi `audit.json` dari template.
6. `release`: memeriksa audit, hak retensi, anotasi, split temporal dan topik, serta kebocoran teks. Hanya tahap ini menyatakan `ready_for_training=true`.

```powershell
# Secret disediakan peneliti lewat environment; gunakan nilai acak minimal 32 karakter.
# Tidak disimpan ke file oleh pipeline. Pertahankan secret yang sama untuk reproduksi paket.
$env:REDAM_DATASET_SECRET = [Convert]::ToBase64String([System.Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
py -3.11 -m src.redam demo --out data/redam/demo_source_v1
py -3.11 -m src.redam prepare --manifest data/redam/demo_source_v1/manifest.json --out data/redam/demo_package_v1
py -3.11 -m src.redam validate --package data/redam/demo_package_v1

# Dataset riset berizin: gunakan direktori baru setiap kali.
py -3.11 -m src.redam prepare --manifest research_manifest.json --out data/redam/research_v1
py -3.11 -m src.redam validate --package data/redam/research_v1
py -3.11 -m src.redam release --package data/redam/research_v1 --audit data/redam/research_v1/audit.json --out data/redam/releases/v1
```

`validate` mengembalikan exit code 2 jika anotasi belum memenuhi syarat. Itu perilaku yang diharapkan pada paket baru. Seluruh direktori keluaran harus baru; RAW asli tidak ditulis ulang. Artefak lokal di `data/redam/` diabaikan Git.

## Manifest impor CSV lama / TikTok / Instagram

Satu entry manifest merepresentasikan satu postingan. Path input relatif terhadap file manifest. `select` memfilter sumber dengan beberapa postingan; gunakan `media_id` yang benar, jangan menggabungkan semua postingan sebagai satu kasus.

```json
{
  "version": "redam-dataset-1.0",
  "cases": [{
    "case_id": "ig_case_001",
    "platform": "instagram",
    "input": "data/raw/comments_example.csv",
    "select": {"media_id": "ID_POSTINGAN_ASLI"},
    "columns": {"text": "comment_text", "created_at": "timestamp", "account": "username", "likes_count": "like_count"},
    "source_type": "live",
    "origin": "research_collection",
    "topic_group": "topik_01",
    "period": "2026-10-01",
    "collected_at": "2026-10-02T00:00:00Z",
    "rights_reference": "GANTI dengan referensi izin penggunaan penelitian",
    "retention_until": "2026-12-01T00:00:00Z",
    "is_partial": true,
    "limitations": ["Urutan komentar dan cakupan pengambilan terbatas."]
  }]
}
```

Tanggal di atas hanya contoh, bukan keputusan retensi. `origin` menerima `research_collection`, `licensed`, `synthetic`. Synthetic wajib `demo`. Penyajian ulang dataset sebagai demo aplikasi harus menggunakan job DEMO baru; nilai provenance penelitian tidak boleh dianggap respons collect LIVE baru. File RAW lama tidak diimpor otomatis karena hak penggunaan, topik dan jangka retensinya belum dikonfirmasi. Label slang lama tidak menjadi gold REDAM.

## Kolektor browser

Tambahkan `url`, `access_reviewed_by`, `adapter_version` dan `locators` dengan `item`, `text`, `id_attribute`; opsional `time`, `account`, `access_barrier`, `scroll_container`. Lokator adalah selector CSS hasil pemeriksaan halaman, bukan selector generik yang diasumsikan berfungsi. `id_attribute` wajib benar-benar ID komentar sumber, bukan ID container yang didaur ulang. Adapter ini belum diuji live pada Instagram/TikTok.

```powershell
py -3.11 -m src.redam collect --manifest approved_collection.json --out data/redam/collection_001
py -3.11 -m src.redam prepare --manifest data/redam/collection_001/manifest.json --out data/redam/research_001
```

Maksimal 200 komentar/kasus, 20 scroll, 3 putaran stagnan. Deadline diperiksa antar iterasi; timeout operasi browser 3 detik dan navigasi 30 detik. Ini bukan deadline proses OS yang keras. Kolektor menggunakan context baru tanpa login/stealth, membatasi request ke host platform, berhenti saat barrier terdeteksi, dan melaporkan hasil parsial. Isolasi jaringan/container eksternal tetap diperlukan sebelum penggunaan sebagai layanan publik. Tidak ada klaim akses platform selalu berhasil. Tidak mengunduh media atau menjalankan instruksi komentar. Data yang tersimpan sudah dipseudonimkan dan dibersihkan; raw HTML, cookie, dan username tidak dipersist.

## Anotasi

Lihat `REDAM_ANNOTATION_GUIDE.md`. `comments.json` menyediakan konteks lengkap setiap kasus. Anotator A/B harus dua orang berbeda; kode A/B bukan bukti identitas otomatis. Kerjakan salinan terpisah tanpa melihat jawaban satu sama lain, kemudian gabungkan baris dengan kunci `(case_id, annotator_id)`. CSV menggunakan delimiter koma dan multi-label/ref menggunakan titik koma. Jangan membuka teks tak tepercaya sebagai formula spreadsheet; gunakan impor semua kolom sebagai teks.

Template `pairs.csv` menyediakan maksimal 30 pasangan acak deterministik/kasus; `clusters.csv` menyediakan keanggotaan setiap komentar per anotator. Keduanya belum termasuk gate atau ekspor gold. Rilis saat ini khusus tugas label kasus; tidak mengklaim dataset pasangan/cluster siap melatih embedding.

## Artefak dan batas kualitas

- Paket: cases/comments, exclusions, lineage checksum sumber, schema, checksum hasil, template anotasi, audit, laporan persiapan.
- Rilis: train/validation/test JSONL, manifest split, label map, audit, laporan kualitas, dataset card, checksum.
- Format JSONL langsung dapat dimuat sebagai record kasus. Label kasus tidak boleh disalin menjadi label per komentar. Parquet belum menjadi dependensi wajib; tidak ada konversi terselubung atau file JSON berekstensi Parquet.
- Split membutuhkan minimal 7 grup topik independen; rasio mendekati 70/15/15 berdasarkan grup, bukan jumlah komentar. Rentang waktu antar split wajib tidak tumpang tindih. Konflik memblokir rilis dan perlu perbaikan sampling.
- Pemeriksaan kebocoran: exact match dan kemiripan karakter >=0,90 untuk teks >=20 karakter. Perbandingan berpasangan cocok untuk pilot, tetapi perlu indeks kandidat sebelum ekspansi besar. Tidak menjamin deteksi parafrasa semantik; lakukan review manual kasus lintas split.
- Weighted kappa ordinal hanya untuk none/uncertain/strong. Kappa tidak terdefinisi (misalnya hanya satu kelas) tidak otomatis dianggap sempurna; perlu tambahan sampel. Evidence yang sama sekali tidak muncul dilaporkan null.
- PII regex membantu redaksi mention/email/telepon/URL, tetapi tidak mampu mengenali semua nama/alamat pada teks bebas. Audit manual wajib sebelum rilis. Pseudonim tetap data terbatas dan bukan anonimisasi sempurna.
- Hak retensi diperiksa sebelum rilis; tidak ada penghapusan otomatis. Operator bertanggung jawab menghapus artefak saat tenggat termasuk backup yang dikendalikan.
- Fixture generator menghasilkan 12 kasus/509 komentar sintetis. Tidak mengisi label manusia dan tidak menghasilkan klaim akurasi. Perubahan bobot scoring aplikasi tetap tugas terpisah setelah benchmark dinilai.

## Kondisi untuk melanjutkan ke data nyata

Sediakan manifest sumber berizin (URL/lokator atau CSV/JSON), topik/periode dan jangka retensi; isi dua anotasi serta audit. Pipeline tidak dapat menggantikan keputusan manusia itu. Data penelitian 8.000 komentar dan benchmark gold belum terwujud hanya karena generator/test berhasil.
