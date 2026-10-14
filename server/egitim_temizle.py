#!/usr/bin/env python3
"""server/egitim_temizle.py — farabi_agy veritabanındaki chunk_egitim temizleme betiği.

1. Soft-hyphen (\xad) ve satır sonu kelime bölmelerini (\w+-\n\w+) birleştirir.
2. \x08, \ufffd ve 'l l l l' çizim/ızgara artıklarını temizler.
3. Tamamen boşalan (<30 karakter) ızgara parçalarını siler.
4. Ağır çöp temizlenen (~736 parça) parçaların embedding'lerini bilgehan üzerinden yeniden hesaplar.
"""

import os
import re
import sys
import time
from pathlib import Path
import psycopg2
from pgvector.psycopg2 import register_vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import uzak_model


def temizle(m: str) -> str:
    m = m.replace("\x00", "")
    m = m.replace("\xad", "")
    m = re.sub(r"(\w+)-\s*\n\s*(\w+)", r"\1\2", m)
    m = m.replace("\x08", "").replace("\ufffd", "")
    lines = []
    for line in m.splitlines():
        if re.match(r"^[\s.lI1\u200c–\-_]+$", line):
            continue
        line = re.sub(r"(?:\s*l\s*){4,}", " ", line)
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-name", default=os.environ.get("FARABI_DB_NAME", "farabi_agy"))
    ap.add_argument("--canli", action="store_true", help="Canlı farabi veritabanında çalıştırmaya izin ver")
    a = ap.parse_args()

    db_name = a.db_name
    if db_name == "farabi" and not a.canli:
        print("UYARI: Canlı 'farabi' veritabanında çalıştırmak için --canli bayrağı gereklidir.")
        return 1

    print(f"chunk_egitim temizliği başlatılıyor ({db_name})...")
    conn = psycopg2.connect(host="127.0.0.1", dbname=db_name, user="farabi")
    register_vector(conn)

    with conn.cursor() as cur:
        cur.execute("SELECT id, metin FROM chunk_egitim ORDER BY id")
        rows = cur.fetchall()

    silinecek = []
    reembed = []
    sadece_metin = []

    for cid, raw in rows:
        c = temizle(raw)
        if len(c) < 30:
            silinecek.append(cid)
        elif abs(len(raw) - len(c)) > 80 or "l l l l" in raw or "\ufffd" in raw:
            reembed.append((cid, c))
        elif raw != c:
            sadece_metin.append((cid, c))

    print(f"Toplam parça:        {len(rows)}")
    print(f"Silinecek (boş çöp): {len(silinecek)}")
    print(f"Re-embed (ağır çöp): {len(reembed)}")
    print(f"Metin güncelleme:    {len(sadece_metin)}")

    # 1. Boş parçaları sil
    if silinecek:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunk_egitim WHERE id = ANY(%s)", (silinecek,))
        conn.commit()
        print(f"{len(silinecek)} boş/çöp parça silindi.")

    # 2. Sadece metin güncellemesi gerekenleri topluca güncelle
    if sadece_metin:
        with conn.cursor() as cur:
            cur.executemany("UPDATE chunk_egitim SET metin = %s WHERE id = %s",
                            [(c, cid) for cid, c in sadece_metin])
        conn.commit()
        print(f"{len(sadece_metin)} parçanın metni (soft-hyphen / tire) temizlendi.")

    # 3. Ağır çöp temizlenenleri re-embed et
    if reembed:
        url, key = uzak_model.ayar_oku()
        model = uzak_model.toplu_gomme_modeli("BAAI/bge-m3")
        adim = 16
        print(f"{len(reembed)} parça için embedding yeniden hesaplanıyor (batch_size={adim})...")
        for i in range(0, len(reembed), adim):
            parti = reembed[i : i + adim]
            cids = [cid for cid, _ in parti]
            metinler = [c for _, c in parti]
            vektorler = model.encode(metinler, normalize_embeddings=True,
                                     batch_size=adim, show_progress_bar=False)
            with conn.cursor() as cur:
                cur.executemany(
                    "UPDATE chunk_egitim SET metin = %s, embedding = %s WHERE id = %s",
                    [(c, v, cid) for (cid, c), v in zip(parti, vektorler)],
                )
            conn.commit()
            print(f"  İşlendi: {min(i + adim, len(reembed))} / {len(reembed)}")

    print(f"Tüm chunk_egitim temizliği başarıyla tamamlandı ({db_name}).")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
