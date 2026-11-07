# Pedoman anotasi REDAM v1

Unit utama adalah satu kasus/postingan beserta komentar yang tersedia. Anotator menilai bukti dalam sampel. Kemiripan opini, kata populer, kritik dan dukungan tidak membuktikan pengendalian terpusat atau pembayaran.

## Label kasus

- `none`: sampel cukup untuk diperiksa, tidak ditemukan kombinasi bukti koordinasi yang memadai. Tidak membuktikan diskusi pasti organik.
- `uncertain`: ada indikasi pengulangan/konsentrasi, tetapi penyebab dan konteks belum cukup. Slogan sukarela sering masuk kategori ini jika ada repetisi tetapi niat tidak diketahui.
- `strong`: beberapa sinyal teramati saling mendukung, misalnya pengulangan spesifik bersamaan dengan pola waktu atau akun. Tetap bukan identifikasi buzzer.
- `not_assessable`: kurang dari 20 komentar valid, atau konteks sangat tidak memadai untuk penilaian kasus. Jangan memperlakukan kelas ini sebagai level ordinal di atas strong.

## Bukti

`exact_text_repetition`: teks sama pada record berbeda. `semantic_concentration`: banyak parafrasa narasi tertentu. `temporal_burst`: konsentrasi timestamp terverifikasi; tidak boleh berasal dari waktu scrape. `within_case_account_repetition`: pengulangan oleh pseudonim sama dalam kasus. `community_slogan` dan `legitimate_criticism` menyatakan konteks pembanding; tidak berarti koordinasi berbahaya. `insufficient_context`, `missing_temporal_data`, `missing_account_data` mendokumentasikan keterbatasan.

Isi `evidence_refs` dengan comment_ref yang ada (misal `c_0001;c_0007`); jangan menciptakan komentar. Wajib beri note alasan, termasuk alternatif penjelasan yang masuk akal. Gunakan lebih dari satu bukti untuk strong. Hindari salinan PII di catatan. Caption yang tidak tersedia tidak boleh direka.

## Proses

1. Dua penilai A/B membaca kasus yang sama secara independen; tidak diperlihatkan skor model atau jawaban penilai lain.
2. Selesaikan semua baris annotations.csv. Jangan menambah label pada komentar individual.
3. Ukur weighted kappa sebelum adjudikasi; target >=0,70. Evidence binary kappa >=0,60 untuk evidence yang muncul. Target ini gate proyek awal, bukan standar universal.
4. Konflik label/evidence diselesaikan orang ketiga. Isi adjudications.csv dengan identitas kode selain A/B, evidence, refs dan alasan keputusan. Penilaian asli tidak ditimpa.
5. Jika agreement rendah/tidak terdefinisi, diskusikan rubric, tambah keragaman kasus bila diperlukan, dan anotasi ulang secara independen. Adjudikasi tidak digunakan untuk menaikkan angka agreement secara palsu.

## Tugas pasangan dan cluster (persiapan tahap lanjutan)

Pasangan memakai exact_duplicate, same_narrative_paraphrase, related_different_message, unrelated, uncertain. Pesan mendukung versus menyangkal klaim dapat membahas topik sama tetapi merupakan related_different_message. Untuk cluster, setiap komentar mendapat satu cluster_id per anotator; gunakan `noise` jika tidak ada kelompok yang memadai, serta ringkasan netral untuk kelompok. Ekspor gold tugas ini memerlukan evaluator/adjudikasi lanjutan dan belum diaktifkan oleh release v1.
