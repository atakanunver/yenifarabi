#!/usr/bin/env python3
"""
benchmark/embed_tablo.py — tools/tablo_cikar.py çıktısını (icerik/tablolar/
<kitap>.json) embed edip chunk_tablo'ya (pgvector) yazar.

embed_kitap.py'nin BİREBİR aynı deseni: kitap'a upsert, kitap_id başına
tam yeniden-indeksleme (DELETE + INSERT), BAAI/bge-m3 CPU'da. Chunk'lama
yok — her tablo zaten kendi başına bir birim, sayfa gibi token pencerelemesi
gerekmiyor (tablolar çoğunlukla 400 token'ın altında).

Kullanım:
    venv/bin/python embed_tablo.py \
        --pdf ../client/kitaplar/biyoloji-9.pdf \
        --tablo-json ../client/icerik/tablolar/biyoloji-9.json \
        --sinif 9 --ders Biyoloji --yayinevi MEB

NOT: --pdf yalnızca hash + kitap.dosya_yolu için kullanılır — embed_kitap.py
zaten aynı kitabı aynı dosya_yolu ile kitap tablosuna yazmış olabilir,
ON CONFLICT (dosya_yolu) sayesinde AYNI kitap.id'ye düşer, iki tablo (kitap
+ chunk_tablo) aynı kitap_id'yi paylaşır — kasıtlı, chunk_egitim ile aynı
kitap_id uzayı.
"""

import argparse
import hashlib
import json
from pathlib import Path

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

MODEL_ADI = "BAAI/bge-m3"


def sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Tablo JSON -> embedding -> pgvector (chunk_tablo)")
    ap.add_argument("--pdf", required=True, help="Kaynak PDF (hash + dosya_yolu için)")
    ap.add_argument("--tablo-json", required=True, help="tools/tablo_cikar.py çıktısı json")
    ap.add_argument("--sinif", type=int, required=True)
    ap.add_argument("--ders", required=True)
    ap.add_argument("--yayinevi", default="MEB")
    ap.add_argument("--yayin-yili", type=int, default=None)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    a = ap.parse_args()

    pdf_yolu = Path(a.pdf).resolve()
    json_yolu = Path(a.tablo_json).resolve()
    if not pdf_yolu.exists():
        print(f"PDF bulunamadı: {pdf_yolu}")
        return 1
    if not json_yolu.exists():
        print(f"Tablo json bulunamadı: {json_yolu} — önce tools/tablo_cikar.py çalıştırılmalı.")
        return 1

    print(f"Hash hesaplanıyor: {pdf_yolu.name}")
    dosya_hash = sha256_dosya(pdf_yolu)

    veri = json.loads(json_yolu.read_text(encoding="utf-8"))
    tablolar = veri["tablolar"]
    print(f"{veri['kitap']}: {len(tablolar)} tablo (kaynak json: {json_yolu.name})")

    if not tablolar:
        print("Hiç tablo yok, çıkılıyor.")
        return 0

    print(f"Model yükleniyor ({MODEL_ADI}, CPU)…")
    model = SentenceTransformer(MODEL_ADI, device="cpu")

    conn = psycopg2.connect(host=a.db_host, dbname=a.db_name, user=a.db_user)
    register_vector(conn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO kitap (sinif, ders, yayinevi, yayin_yili, dosya_yolu, hash)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (dosya_yolu) DO UPDATE
                    SET sinif = EXCLUDED.sinif,
                        ders = EXCLUDED.ders,
                        yayinevi = EXCLUDED.yayinevi,
                        yayin_yili = EXCLUDED.yayin_yili,
                        hash = EXCLUDED.hash
                RETURNING id
                """,
                (a.sinif, a.ders, a.yayinevi, a.yayin_yili, str(pdf_yolu), dosya_hash),
            )
            kitap_id = cur.fetchone()[0]
            cur.execute("DELETE FROM chunk_tablo WHERE kitap_id = %s", (kitap_id,))
        conn.commit()
        print(f"kitap.id = {kitap_id} (dosya_yolu={pdf_yolu})")

        eklenen = 0
        with conn.cursor() as cur:
            for i in range(0, len(tablolar), a.batch):
                grup = tablolar[i:i + a.batch]
                metinler = [t["metin_ozet"] for t in grup]
                gomme = model.encode(metinler, normalize_embeddings=True, show_progress_bar=False)
                satirlar = [
                    (kitap_id, t["sayfa"], t.get("baslik") or None,
                     json.dumps({"headers": t["headers"], "rows": t["rows"]}, ensure_ascii=False),
                     t["metin_ozet"], vektor)
                    for t, vektor in zip(grup, gomme)
                ]
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO chunk_tablo (kitap_id, sayfa_no, baslik, tablo_json, metin_ozet, embedding) VALUES %s",
                    satirlar,
                )
                conn.commit()
                eklenen += len(grup)
                print(f"  {eklenen}/{len(tablolar)} tablo işlendi", end="\r")

        print(f"\nBitti. {eklenen} tablo yazıldı, kitap_id={kitap_id}.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
