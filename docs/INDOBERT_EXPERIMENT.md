# Eksperimen Model Bahasa Indonesia Pra-latih (IndoBERT) vs Baseline TF-IDF

Dokumen ini menjelaskan rancangan, metodologi, kebutuhan komputasi, sumber model, lisensi, serta tata cara pelaksanaan eksperimen perbandingan model bahasa pra-latih bahasa Indonesia (*Pretrained Language Model*) terhadap baseline TF-IDF pada klasifikasi multi-label bentuk slang dan fungsi bahasa.

---

## 1. Latar Belakang & Kejujuran Ilmiah

> [!IMPORTANT]
> **Tidak Menjanjikan Peningkatan Performa Otomatis:**  
> Arsitektur *deep learning* berbasis transformer (seperti IndoBERT) memiliki ~124 juta parameter. Pada domain teks informal berkarakteristik pendek (komentar media sosial) dengan ukuran dataset berlabel yang terbatas atau jumlah postingan yang sedikit, model transformer rentan terhadap *overfitting* atau *memorization*.  
> Baseline linear (TF-IDF + Logistic Regression dengan regularisasi L2) sering kali sangat kompetitif atau bahkan lebih stabil pada *low-data regime*. Eksperimen ini ditujukan sebagai **studi komparatif empiris yang adil dan objektif**, bukan untuk memaksakan superioritas transformer.

---

## 2. Profil Pretrained Model Terpilih

Model utama yang dipilih untuk eksperimen ini adalah **`indobenchmark/indobert-base-p1`**.

| Atribut | Rincian |
|---|---|
| **Identifier Hugging Face** | [`indobenchmark/indobert-base-p1`](https://huggingface.co/indobenchmark/indobert-base-p1) |
| **Sumber & Pengembang** | Indo4B / IndoLEM Project (Koto, Mahendra, Fitri, et al., 2020: *"Indo4B: The First Large-Scale Indonesian Language Dataset for Transformers"*) |
| **Lisensi** | **BSD-3-Clause** (Open-source permisif, terverifikasi untuk riset akademis dan komersial) |
| **Arsitektur Dasar** | BERT-base (Bidirectional Encoder Representations from Transformers) |
| **Jumlah Parameter** | ~124.5 Juta Parameter |
| **Ukuran Bobot Model** | ~498 MB (file `pytorch_model.bin` / `model.safetensors`) |
| **Kosakata Tokenizer** | 30.521 subword tokens (WordPiece) yang dilatih khusus pada korpus teks bahasa Indonesia |
| **Model Ringan Alternatif** | [`indobenchmark/indobert-lite-base-p1`](https://huggingface.co/indobenchmark/indobert-lite-base-p1) (ALBERT-based, 11M parameter, lisensi BSD-3-Clause) |

---

## 3. Analisis Resource Komputer & Kompatibilitas Hardware

Pemeriksaan spesifikasi perangkat lokal pengguna:
- **Sistem Operasi**: Windows 11 Home 64-bit
- **Prosesor**: Intel Core (MSI GF63 Thin 11UD)
- **RAM Sistem**: 16 GB DDR4 (tersedia > 10 GB)
- **Kartu Grafis (GPU)**: **NVIDIA GeForce RTX 3050 Ti Laptop GPU**
  - **Kapasitas VRAM**: **4096 MiB (4 GB GDDR6)**
  - **Versi Driver NVIDIA**: 617.14
  - **Dukungan CUDA Runtime**: Hingga CUDA 12.x / 13.x
- **Sisa Ruang Disk**: 51 GB pada Drive `D:`

### Kebutuhan RAM / VRAM & Ukuran Dependensi
1. **Strategi Efisiensi VRAM 4 GB (RTX 3050 Ti):**
   - VRAM 4 GB mencukupi untuk fine-tuning BERT-base asalkan:
     - Panjang sekuens dibatasi: `max_length = 128` (sangat memadai karena komentar Instagram mayoritas pendek).
     - Ukuran batch: `batch_size = 8` (atau 16 jika sequence length 64).
     - **Mixed Precision FP16**: Menggunakan `torch.cuda.amp.autocast()` yang memangkas kebutuhan memori aktivasi hingga ~50% dan mempercepat komputasi pada Tensor Cores RTX 3050 Ti.
2. **Ukuran Dependensi:**
   - **PyTorch dengan CUDA 12.1**: Ukuran unduhan ~2.5 GB, ukuran instalasi di disk ~4-5 GB.
   - **PyTorch CPU-Only**: Ukuran unduhan ~200 MB, ukuran instalasi di disk ~800 MB.
   - Keduanya dapat diakomodasi dengan aman oleh sisa ruang disk 51 GB.

---

## 4. Metodologi Eksperimen & Desain Bebas Kebocoran Data (Zero Leakage)

### Multi-Label Text Classification
Model IndoBERT diintegrasikan dengan dua *classification heads* terpisah di atas representasi `[CLS]`:
1. **Tugas A — Bentuk Slang (7 Kelas):** `akronim`, `singkatan`, `bahasa_asing`, `plesetan`, `pemendekan`, `tidak_ada`, `lainnya`.
2. **Tugas B — Fungsi Bahasa (4 Kelas):** `emotif`, `referensial`, `konatif`, `tidak_jelas`.
- **Fungsi Loss**: `torch.nn.BCEWithLogitsLoss()` diterapkan secara independen per label.

### Partisi 3-Way GroupSplit Berdasarkan `media_id`
Untuk menjaga validitas ilmiah dan mencegah manipulasi hasil:
1. **Pemisahan Berdasarkan Postingan (`media_id`):**  
   Seluruh data dibagi menjadi 3 himpunan bagian:
   - **Train Set (60%)**: Digunakan untuk pembaruan bobot (*backpropagation*).
   - **Validation Set (20%)**: Digunakan untuk memantau performa di setiap epoch dan memilih *checkpoint* model terbaik (*early stopping*).
   - **Held-Out Test Set (20%)**: **TIDAK PERNAH DISENTUH** selama pelatihan atau pemilihan hyperparameter. Hanya dievaluasi satu kali di akhir.
2. **Syarat Minimal Kelayakan Split:**  
   Sistem mewajibkan minimal **3 postingan (`media_id`) berbeda**. Jika postingan $< 3$, sistem menolak mengeksekusi dengan error `InsufficientGroupsForThreeWaySplitError`.

### Perbandingan Apel-ke-Apel (*Apple-to-Apple*)
Pada split Train dan Test yang **persis sama**:
- Model Baseline TF-IDF + Logistic Regression dilatih pada data latih yang sama.
- Model Baseline dan IndoBERT dievaluasi pada data uji *held-out* yang sama.
- Metrik yang dibandingkan:
  - **Macro-F1** (rata-rata unweighted, sensitif terhadap kelas langka)
  - **Micro-F1** (agregat global)
  - **Precision & Recall per label**
  - **Waktu Pelatihan** (detik)
  - **Footprint Komputasi** (alokasi memori VRAM/RAM)

---

## 5. Tata Cara Instalasi Dependensi Deep Learning

### Opsi A: Dukungan GPU CUDA (Rekomendasi untuk RTX 3050 Ti)
Jalankan di Command Prompt / PowerShell dalam `.venv`:
```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install transformers accelerate
```

### Opsi B: CPU-Only
```powershell
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install transformers accelerate
```

---

## 6. Cara Menjalankan Eksperimen via Command Line

Modul eksperimen terletak di [`src/experiments/indobert_experiment.py`](file:///d:/WEBKU/NLP/src/experiments/indobert_experiment.py).

### 1. Memeriksa Kesiapan Environment & Hardware
```powershell
python -m src.experiments.indobert_experiment --check-env
```
*Output menampilkan status PyTorch, ketersediaan CUDA, tipe GPU, dan VRAM.*

### 2. Membuat Dataset Demo Multi-Post Sintesis
Jika Anda belum memiliki data anotasi manual dari minimal 3 postingan:
```powershell
python -m src.experiments.indobert_experiment --create-demo
```
*File `data/annotated/comments_labeled_demo.csv` akan dibuat memuat 30 komentar teranotasi lengkap dari 5 postingan berbeda.*

### 3. Menjalankan Eksperimen Fine-Tuning & Komparasi
```powershell
python -m src.experiments.indobert_experiment --data data/annotated/comments_labeled_demo.csv --epochs 3 --batch-size 8 --lr 2e-5
```

Parameter yang didukung:
- `--data <path>`: Lokasi dataset berlabel CSV (default: `data/annotated/comments_labeled_demo.csv` atau `comments_labeled.csv`).
- `--model <name>`: Nama model Hugging Face (default: `indobenchmark/indobert-base-p1`).
- `--epochs <int>`: Jumlah epoch (default: `3`).
- `--batch-size <int>`: Ukuran batch (default: `8`, optimal untuk VRAM 4GB).
- `--max-length <int>`: Batas token (default: `128`).
- `--lr <float>`: Learning rate AdamW (default: `2e-5`).
- `--seed <int>`: Random seed (default: `42`).

### 4. Menjalankan Melalui Menu CLI Utama
Jalankan program utama:
```powershell
python main.py
```
Pilih menu **`5. Latih model baseline`**. Setelah model baseline selesai dievaluasi, sistem akan menampilkan prompt:
```text
Jalankan perbandingan dengan model bahasa pra-latih (IndoBERT) pada split ini? [y/N]: 
```
Ketik `y` untuk mengeksekusi komparasi IndoBERT.

---

## 7. Format Laporan Hasil Eksperimen

Laporan perbandingan disimpan secara terpisah di direktori `reports/` tanpa menimpa laporan baseline:
1. **Laporan JSON**: `reports/comparison_baseline_vs_indobert_<run_id>.json`
2. **Laporan CSV**: `reports/comparison_baseline_vs_indobert_<run_id>.csv`
3. **Laporan Markdown**: `reports/comparison_baseline_vs_indobert_<run_id>.md`

Contoh format tabel komparasi pada laporan Markdown:
```markdown
## Hasil Evaluasi pada Held-Out Test Set

### 1. Bentuk Slang (7 Kelas)
| Metrik | Baseline (TF-IDF) | IndoBERT | Selisih (Diff) |
|---|---|---|---|
| **Macro-F1** | 0.7619 | 0.8055 | +0.0436 |
| **Micro-F1** | 0.8333 | 0.8571 | +0.0238 |
| **Macro-Precision** | 0.8250 | 0.8125 | -0.0125 |
| **Macro-Recall** | 0.7440 | 0.8000 | +0.0560 |

### 2. Fungsi Bahasa (4 Kelas)
| Metrik | Baseline (TF-IDF) | IndoBERT | Selisih (Diff) |
|---|---|---|---|
| **Macro-F1** | 0.7857 | 0.8214 | +0.0357 |
| **Micro-F1** | 0.8125 | 0.8462 | +0.0337 |
| **Macro-Precision** | 0.8083 | 0.8333 | +0.0250 |
| **Macro-Recall** | 0.7667 | 0.8125 | +0.0458 |
```

---

## 8. Lokasi Penyimpanan Model

- Artefak IndoBERT terbaik disimpan di: `models/experiments/indobert_<run_id>/`
  - `indobert_best_model.pt` (state_dict bobot model terfine-tune)
  - File tokenizer (`vocab.txt`, `tokenizer_config.json`, `special_tokens_map.json`)
- **Penting:** Model baseline TF-IDF pada `models/baseline_slang_model.joblib` dan `models/baseline_functions_model.joblib` **tetap dipertahankan utuh dan tidak ditimpa**.
