from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

from backend_ai.features.detection import (
    MasukanKomentar,
    MetadataSumberMasukan,
    PenyediaEmbeddingDeterministikUji,
    PenyediaEmbeddingSentenceTransformer,
    PermintaanDeteksi,
)
from backend_ai.pipelines import jalankan_pipeline_deteksi

DIREKTORI_DASAR = Path(__file__).resolve().parent
PATH_CSV = DIREKTORI_DASAR / "dataset_saya.csv"

# False = Encoder deterministik instan (< 1 detik, tanpa unduhan jaringan)
# True  = Model SentenceTransformer asli (paraphrase-multilingual-MiniLM-L12-v2)
GUNAKAN_MODEL_TRANSFORMER_ASLI = False


def pseudonimkan_akun(username_mentah: str | None) -> str | None:
    """Mengubah username mentah menjadi pseudonim satu arah sesuai aturan privasi AGENTS.md Bagian 7."""
    if not username_mentah or not username_mentah.strip():
        return None
    intisari = hashlib.blake2b(
        username_mentah.strip().lower().encode("utf-8"), digest_size=6
    ).hexdigest()
    return f"acct_{intisari}"


def muat_komentar_dari_csv(path_file: Path) -> list[MasukanKomentar]:
    if not path_file.exists():
        print(f"File tidak ditemukan: {path_file.resolve()}")
        sys.exit(1)

    daftar_komentar: list[MasukanKomentar] = []
    with path_file.open(mode="r", encoding="utf-8-sig", newline="") as berkas:
        pembaca = csv.DictReader(berkas)
        for indeks, baris in enumerate(pembaca, start=1):
            teks = (
                baris.get("comment_text")
                or baris.get("text")
                or baris.get("komentar")
                or baris.get("comment")
                or ""
            )
            ref = (
                baris.get("comment_id")
                or baris.get("comment_ref")
                or baris.get("id")
                or f"comment_{indeks:03d}"
            )
            waktu = (
                baris.get("timestamp")
                or baris.get("created_at")
                or None
            )
            akun_mentah = (
                baris.get("account_ref")
                or baris.get("username")
                or None
            )
            suka_mentah = baris.get("like_count") or baris.get("likes_count")
            jumlah_suka = (
                int(suka_mentah)
                if suka_mentah and str(suka_mentah).strip().isdigit()
                else None
            )

            daftar_komentar.append(
                MasukanKomentar(
                    comment_ref=str(ref).strip(),
                    text=str(teks),
                    created_at=str(waktu).strip() if waktu else None,
                    account_ref=pseudonimkan_akun(str(akun_mentah)) if akun_mentah else None,
                    likes_count=jumlah_suka,
                )
            )
    return daftar_komentar


def main() -> None:
    komentar = muat_komentar_dari_csv(PATH_CSV)
    print(f"Berhasil memuat {len(komentar)} baris dari {PATH_CSV.name}...")

    permintaan = PermintaanDeteksi(
        analysis_id="uji-dataset-mandiri-001",
        source_type="demo",
        source_post_id=None,
        comments=komentar,
        source_metadata=MetadataSumberMasukan(
            items_seen=len(komentar),
            comments_collected=len(komentar),
            is_partial=False,
            fixture_id=PATH_CSV.stem,
        ),
    )

    penyedia = (
        PenyediaEmbeddingSentenceTransformer()
        if GUNAKAN_MODEL_TRANSFORMER_ASLI
        else PenyediaEmbeddingDeterministikUji()
    )

    hasil = jalankan_pipeline_deteksi(permintaan, penyedia_embedding=penyedia)

    print("\n=== RINGKASAN HASIL DETEKSI ===")
    print(f"Komentar Diperiksa : {hasil.items_seen}")
    print(f"Komentar Valid     : {hasil.comments_valid}")
    print(f"Komentar Dianalisis: {hasil.comments_analyzed}")
    print(f"Komentar Dibuang   : {hasil.excluded_count} ({hasil.excluded_reasons})")
    print(f"Sampel Parsial     : {hasil.is_partial}")
    print(f"Label Kualitas     : {hasil.quality_label}")
    print(
        f"Skor Indikasi      : {hasil.detection.risk_score} ({hasil.detection.risk_category})"
    )
    print(f"Tingkat Keyakinan  : {hasil.detection.confidence_label}")
    print(f"Jumlah Klaster     : {len(hasil.detection.clusters)}")
    print(f"Jumlah Noise       : {hasil.detection.noise_count}")
    print(f"Ringkasan          : {hasil.detection.summary}")

    print("\n=== CATATAN KETERBATASAN (LIMITATIONS) ===")
    for catatan in hasil.limitations:
        print(f"- {catatan}")

    print("\n=== RINCIAN 4 SINYAL ===")
    for sinyal in hasil.detection.signals:
        print(
            f"- {sinyal.signal_id}: status={sinyal.assessment_status}, nilai={sinyal.value}"
        )
        print(f"  Penjelasan: {sinyal.explanation}")

    print("\n=== KLASTER NARASI TERBENTUK ===")
    peta_bukti = {b.evidence_ref: b for b in hasil.detection.evidence}
    for klaster in hasil.detection.clusters:
        print(f"- [{klaster.cluster_id}] ({klaster.size} komentar) -> {klaster.label}")
        for ref_bukti in klaster.evidence_refs:
            bukti = peta_bukti.get(ref_bukti)
            if bukti is not None:
                print(f"  * {ref_bukti} ({bukti.comment_ref}): {bukti.text_excerpt}")

    path_output = DIREKTORI_DASAR / "hasil_uji_dataset.json"
    path_output.write_text(
        json.dumps(hasil.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nOutput JSON lengkap tersimpan di: {path_output.resolve()}")


if __name__ == "__main__":
    main()
