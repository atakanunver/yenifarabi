#!/usr/bin/env python3
"""Doğrulanmış TYT manifestini soru arşivine aktar; varsayılan yalnız kontroldür."""
import argparse
import hashlib
import json
from pathlib import Path

import psycopg2
from psycopg2.extras import Json


def _oku(klasor):
    root = Path(klasor).resolve()
    v = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    sha = v.get("pdf_sha256", "")
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError("PDF özeti geçersiz")
    rows = v.get("sorular")
    beklenen = {"turkce": 40, "sosyal": 25, "matematik": 40, "fen": 20}
    if not isinstance(rows, list) or len(rows) != sum(beklenen.values()):
        raise ValueError("Soru sayısı beklenen 125 değil")
    uniq = set()
    for r in rows:
        test, no = r["test"], r["no"]
        if test not in beklenen or not isinstance(no, int) or not 1 <= no <= beklenen[test] or (test, no) in uniq:
            raise ValueError("Soru numarası geçersiz veya tekrarlı")
        uniq.add((test, no))
        if r["kaynak_kimligi"] != f"yks:{sha}:{test}:{no}" or r["secenek_tespit"] != list("ABCDE"):
            raise ValueError("Soru kimliği veya beş seçenek doğrulanamadı")
        if not 0 <= r["dogru_index"] <= 4 or r["sinif"] != 12 or r["ders"] not in {"turkce", "matematik", "tarih", "cografya", "felsefe", "din", "fizik", "kimya", "biyoloji"}:
            raise ValueError("Cevap, sınıf veya ders geçersiz")
        name = r["gorsel"]
        if Path(name).name != name or not name.endswith(".png"):
            raise ValueError("Görsel yolu geçersiz")
        image = (root / name).read_bytes()
        if not image.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Görsel PNG değil")
        r["_gorsel"] = image
    return sha, rows


def aktar(conn, sha, rows):
    eklenen = var = 0
    # Tek transaction: yarıda kalırsa hiçbir soru yayınlanmaz.
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("tyt_arsiv:" + sha,))
            for r in rows:
                kimlik = r["kaynak_kimligi"]
                cur.execute("SELECT id FROM kaynak_birim WHERE anahtar=%s", (kimlik,))
                birim = cur.fetchone()
                if birim:
                    cur.execute("SELECT s.dogru_index, g.icerik FROM soru s LEFT JOIN soru_gorsel g ON g.soru_id=s.id WHERE s.birim_id=%s", (birim[0],))
                    kayitlar = cur.fetchall()
                    if len(kayitlar) != 1 or kayitlar[0][0] != r["dogru_index"] or kayitlar[0][1] is None or hashlib.sha256(bytes(kayitlar[0][1])).digest() != hashlib.sha256(r["_gorsel"]).digest():
                        raise ValueError(f"Önceki kayıt uyuşmuyor: {r['test']} {r['no']}")
                    var += 1
                    continue
                kaynak = f"MEBİ TYT 2. Deneme, {r['test']} {r['no']}. soru"
                cur.execute("INSERT INTO kaynak_birim(tur,anahtar,ders,sinif,etiket,metin,durum) VALUES ('yks',%s,%s,12,%s,'PDF arşiv sorusu','islendi') RETURNING id", (kimlik, r["ders"], kaynak))
                bid = cur.fetchone()[0]
                secenekler = [f"{x} seçeneği" for x in "ABCDE"]
                cur.execute("INSERT INTO soru(birim_id,ders,sinif,konu,soru,kisa_cevap,secenekler,dogru_index,zorluk,kaynak,durum) VALUES (%s,%s,12,%s,%s,%s,%s,%s,2,%s,'onayli') RETURNING id", (bid, r["ders"], "YKS TYT denemesi", "Soruyu görselden inceleyiniz.", "ABCDE"[r["dogru_index"]], Json(secenekler), r["dogru_index"], kaynak))
                sid = cur.fetchone()[0]
                cur.execute("INSERT INTO soru_gorsel(soru_id,icerik,mime,kaynak_sha256,kaynak_sayfa) VALUES (%s,%s,'image/png',%s,%s)", (sid, psycopg2.Binary(r["_gorsel"]), sha, r["sayfa"]))
                eklenen += 1
    return eklenen, var


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("klasor", type=Path)
    p.add_argument("--uygula", action="store_true")
    a = p.parse_args()
    sha, rows = _oku(a.klasor)
    if not a.uygula:
        print(f"{len(rows)} soru ve görsel doğrulandı; veritabanına yazılmadı.")
        return
    from soruhavuzu import vt
    conn = vt.baglan()
    try:
        n, eski = aktar(conn, sha, rows)
        print(f"{n} soru eklendi, {eski} mevcut kayıt korundu.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
