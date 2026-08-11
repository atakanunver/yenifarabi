#!/usr/bin/env python3
"""
benchmark/embed_kitap.py — tek bir kitabın sayfa metnini (tools/kitap_metin.py
çıktısı) chunk'lara böler, bge-m3 ile embed eder, pgvector'a yazar.

Faz 0a kapsamı — docs/mimari.md §6/§7:
  kitap + chunk_egitim, kazanim eşleştirme YOK (kazanim_kod NULL kalır,
  kazanim tablosu Faz 1'de gelecek).

Kullanım:
    venv/bin/python embed_kitap.py \
        --pdf ../client/kitaplar/biyoloji-9.pdf \
        --metin-json metin/biyoloji-9.json \
        --sinif 9 --ders Biyoloji --yayinevi MEB \
        --haric-sayfalar "1-14,190-191"

ÖN/ARKA-MATTER KİRLİLİĞİ (2026-08-10'da bulundu, biyoloji-9.pdf) — bu betik
başta kitabın HER sayfasını chunk'lıyordu: kapak, ISBN/baskı bilgisi,
İstiklal Marşı + Gençliğe Hitabe (s.4-5), içindekiler ve kitap tanıtımı
(s.6-14) chunk_egitim'e girmişti. Sonuç: bir öğrenci biyoloji sorusu sorsa
bile retrieval bazen bu sayfalara düşebiliyordu — ölçüldü, benchmark/sorular.json
içinde en az 5 taslak soru bu sayfalardan üretilmişti (mimari.md'ye alakasız).
Aynı şekilde s.190-191 bir dünya atlası eki (OCR bozuk). --haric-sayfalar bu
yüzden eklendi; her yeni kitapta gerçek müfredatın nerede başlayıp bittiği
elle kontrol edilmeli (tools/kitap_index.py'nin ünite tespiti burada
kullanılmıyor — bu ayrı, daha basit bir betik).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from transformers import AutoTokenizer
from sentence_transformers import SentenceTransformer

MODEL_ADI = "BAAI/bge-m3"
CHUNK_TOKEN = 400
ORTUSME_ORANI = 0.15


def sha256_dosya(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for blok in iter(lambda: f.read(1 << 20), b""):
            h.update(blok)
    return h.hexdigest()


def haric_sayfalari_coz(ifade: str) -> set[int]:
    """'1-14,190-191' -> {1,2,...,14,190,191}. Boş girdi -> boş küme."""
    sonuc: set[int] = set()
    for parca in (p.strip() for p in ifade.split(",")):
        if not parca:
            continue
        if "-" in parca:
            bas, son = parca.split("-", 1)
            sonuc.update(range(int(bas), int(son) + 1))
        else:
            sonuc.add(int(parca))
    return sonuc


def sayfayi_boluml(metin: str, tokenizer, chunk_token: int, ortusme: int) -> list[str]:
    """Bir sayfanın tokenlarını (chunk_token, ortusme) pencereleriyle böler.
    Sayfa sınırını hiç aşmaz — çağıran zaten sayfa başına çağırır."""
    ids = tokenizer.encode(metin, add_special_tokens=False)
    if not ids:
        return []
    if len(ids) <= chunk_token:
        return [metin]
    adim = chunk_token - ortusme
    parcalar = []
    i = 0
    while i < len(ids):
        pencere = ids[i:i + chunk_token]
        parcalar.append(tokenizer.decode(pencere))
        if i + chunk_token >= len(ids):
            break
        i += adim
    return parcalar


def main() -> int:
    ap = argparse.ArgumentParser(description="Kitap -> chunk -> embedding -> pgvector")
    ap.add_argument("--pdf", required=True, help="Kaynak PDF (hash + dosya_yolu için)")
    ap.add_argument("--metin-json", required=True, help="tools/kitap_metin.py çıktısı json")
    ap.add_argument("--sinif", type=int, required=True)
    ap.add_argument("--ders", required=True)
    ap.add_argument("--yayinevi", default="MEB")
    ap.add_argument("--yayin-yili", type=int, default=None)
    ap.add_argument("--chunk-token", type=int, default=CHUNK_TOKEN)
    ap.add_argument("--ortusme-orani", type=float, default=ORTUSME_ORANI)
    ap.add_argument("--batch", type=int, default=32, help="embedding batch boyutu")
    ap.add_argument("--haric-sayfalar", default="",
                    help="Chunk'lanmayacak sayfalar — kapak/ISBN/İstiklal Marşı/"
                         "içindekiler gibi ön-matter ve atlas eki gibi arka-matter "
                         "için (ölçüldü: biyoloji-9.pdf'de gerçek müfredat s.15'te "
                         "başlıyor, s.190-191 bir atlas eki). Tek sayfa ve aralık "
                         "karışık, virgülle ayrılmış: '1-14,190-191'. Sayfa "
                         "numaraları PDF sayfası, kitabın basılı numarası değil.")
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    a = ap.parse_args()

    pdf_yolu = Path(a.pdf).resolve()
    json_yolu = Path(a.metin_json).resolve()
    if not pdf_yolu.exists():
        print(f"PDF bulunamadı: {pdf_yolu}")
        return 1
    if not json_yolu.exists():
        print(f"Metin json bulunamadı: {json_yolu} — önce tools/kitap_metin.py çalıştırılmalı.")
        return 1

    ortusme_token = int(a.chunk_token * a.ortusme_orani)
    print(f"Hash hesaplanıyor: {pdf_yolu.name}")
    dosya_hash = sha256_dosya(pdf_yolu)

    veri = json.loads(json_yolu.read_text(encoding="utf-8"))
    sayfalar = veri["sayfalar"]
    haric = haric_sayfalari_coz(a.haric_sayfalar)
    print(f"{veri['kitap']}: {len(sayfalar)} sayfa (kaynak json: {json_yolu.name})")
    if haric:
        print(f"Hariç tutulan {len(haric)} sayfa (ön/arka-matter): {sorted(haric)}")

    print(f"Tokenizer + model yükleniyor ({MODEL_ADI}, CPU)…")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ADI)
    model = SentenceTransformer(MODEL_ADI, device="cpu")

    # ── Chunk'lama: sayfa sırasına göre, sayfa sınırı aşılmaz ──────────────
    chunklar = []  # (sayfa_no, metin)
    for sayfa_no in sorted(sayfalar, key=int):
        if int(sayfa_no) in haric:
            continue
        metin = sayfalar[sayfa_no]["metin"]
        for parca in sayfayi_boluml(metin, tokenizer, a.chunk_token, ortusme_token):
            if parca.strip():
                chunklar.append((int(sayfa_no), parca))
    print(f"{len(chunklar)} chunk üretildi (~{a.chunk_token} token, %{int(a.ortusme_orani*100)} örtüşme).")

    if not chunklar:
        print("Hiç chunk üretilemedi, çıkılıyor.")
        return 1

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
                        hash = EXCLUDED.hash,
                        indekslendi_at = NULL
                RETURNING id
                """,
                (a.sinif, a.ders, a.yayinevi, a.yayin_yili, str(pdf_yolu), dosya_hash),
            )
            kitap_id = cur.fetchone()[0]
            cur.execute("DELETE FROM chunk_egitim WHERE kitap_id = %s", (kitap_id,))
        conn.commit()
        print(f"kitap.id = {kitap_id} (dosya_yolu={pdf_yolu})")

        eklenen = 0
        with conn.cursor() as cur:
            for i in range(0, len(chunklar), a.batch):
                grup = chunklar[i:i + a.batch]
                metinler = [m for _, m in grup]
                gomme = model.encode(metinler, normalize_embeddings=True, show_progress_bar=False)
                satirlar = [
                    (kitap_id, sayfa_no, metin, vektor)
                    for (sayfa_no, metin), vektor in zip(grup, gomme)
                ]
                psycopg2.extras.execute_values(
                    cur,
                    "INSERT INTO chunk_egitim (kitap_id, sayfa_no, metin, embedding) VALUES %s",
                    satirlar,
                )
                conn.commit()
                eklenen += len(grup)
                print(f"  {eklenen}/{len(chunklar)} chunk işlendi", end="\r")

        with conn.cursor() as cur:
            cur.execute("UPDATE kitap SET indekslendi_at = now() WHERE id = %s", (kitap_id,))
        conn.commit()
        print(f"\nBitti. {eklenen} chunk yazıldı, kitap_id={kitap_id}, indekslendi_at güncellendi.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
