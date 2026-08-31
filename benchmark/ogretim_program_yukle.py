#!/usr/bin/env python3
"""
benchmark/ogretim_program_yukle.py — /mnt/farabi-data/farabi/ogretim_program/
altındaki MEB "Türkiye Yüzyılı Maarif Modeli" ders öğretim programı
PDF'lerini `kazanim` tablosuna (kod, sinif, ders, unite, metin) yükler. Saf
ayrıştırma mantığı ogretim_program_parse.py'de; bu betik yalnızca dosya/DB
I/O yapar. `kazanim.kod` üzerine UNIQUE kısıt eklendi (2026-08-31,
`ALTER TABLE ... ADD CONSTRAINT kazanim_kod_key UNIQUE (kod)`) — klasörde
aynı dersin birden fazla neredeyse-özdeş dosyası var (ör. fizik.pdf +
fizikdöp.pdf, ikisi de birebir aynı 106 kazanımı üretiyor), ON CONFLICT DO
NOTHING ile tekrar yazılmıyor.

Kapsam (2026-08-31) — yalnızca TEMİZ ayrıştırılan dersler yüklenir:
    Fizik (fizik.pdf + fizikdöp.pdf, aynı içerik)
    Din Kültürü ve Ahlak Bilgisi (din kültürü 9_12.pdf + dkab912.pdf)
    T.C. İnkılap Tarihi ve Atatürkçülük (inkılap 12.pdf + ınkılaptarihi.pdf)
Şu dersler ŞİMDİLİK ATLANIYOR (kalite kapısını geçemedi — ölçüldü, sebep
ogretim_program_parse.py'nin `kazanimlari_ayir` fonksiyonundaki "a)" satır
sınırı sezgisi bu derslerde işlemiyor, muhtemelen farklı bir kod derinliği/
madde biçimi kullanıyorlar, ayrı bir inceleme gerektiriyor):
    Biyoloji, Coğrafya, Matematik (matedöp), Tarih — kısmen kirli (>%50
        satırda pedagojik anlatı bulaşmış)
    Kimya, Türk Dili ve Edebiyatı, İngilizce, Matematik Uygulamaları,
        Mantık — hiç kazanım bulunamadı (0), kod deseni hiç eşleşmedi

Kullanım:
    venv/bin/python ogretim_program_yukle.py
    venv/bin/python ogretim_program_yukle.py --dry-run
"""

import argparse
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # bkz. kazanim_test_yukle.py

import fitz
import psycopg2
import psycopg2.extras

from ogretim_program_parse import ders_adi_cikar, kazanimlari_ayir

KAYNAK_DIZIN = Path("/mnt/farabi-data/farabi/ogretim_program")

# Kalite kapısını geçen dersler — bkz. modül docstring'i. Elle seçildi,
# dosya adı DEĞİL ders adı üzerinden (aynı ders birden fazla dosyada olabilir).
KABUL_EDILEN_DERSLER = {
    "Fizik",
    "Din Kültürü Ve Ahlak Bilgisi",
    "T.C. İnkılap Tarihi Ve Atatürkçülük",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="ogretim_program/ PDF'lerini kazanim'a yükle")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--db-host", default="127.0.0.1")
    ap.add_argument("--db-name", default="farabi")
    ap.add_argument("--db-user", default="farabi")
    a = ap.parse_args()

    dosyalar = sorted(KAYNAK_DIZIN.glob("*.pdf"))
    print(f"{len(dosyalar)} öğretim programı PDF'i bulundu.")

    atlanan: list[tuple[str, str]] = []
    tum_kazanimlar: list[dict] = []

    for yol in dosyalar:
        doc = fitz.open(yol)
        tam = "\n".join(sayfa.get_text() for sayfa in doc)
        doc.close()

        ders = ders_adi_cikar(tam)
        if not ders:
            atlanan.append((yol.name, "başlıktan ders çıkarılamadı"))
            continue
        if ders not in KABUL_EDILEN_DERSLER:
            atlanan.append((yol.name, f"kalite kapısı dışı ders: {ders}"))
            continue

        kazanimlar = kazanimlari_ayir(tam)
        if not kazanimlar:
            atlanan.append((yol.name, "hiç kazanım ayrıştırılamadı"))
            continue

        for k in kazanimlar:
            tum_kazanimlar.append({**k, "ders": ders, "kaynak_dosya": yol.name})

    print(f"{len(tum_kazanimlar)} kazanım bulundu ({len(dosyalar) - len(atlanan)} dosyadan), "
          f"{len(atlanan)} dosya atlandı.")
    if atlanan:
        print("Atlanan dosyalar:")
        for ad, sebep in atlanan:
            print(f"  - {ad}: {sebep}")

    if a.dry_run or not tum_kazanimlar:
        print("--dry-run: DB'ye yazılmadı." if a.dry_run else "Yazılacak kazanım yok.")
        return 0

    conn = psycopg2.connect(host=a.db_host, dbname=a.db_name, user=a.db_user)
    yazilan = 0
    zaten_var = 0
    try:
        with conn.cursor() as cur:
            for k in tum_kazanimlar:
                cur.execute(
                    """
                    INSERT INTO kazanim (kod, sinif, ders, unite, metin)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (kod) DO NOTHING
                    """,
                    (k["kod"], k["sinif"], k["ders"], k["unite"], k["metin"]),
                )
                if cur.rowcount:
                    yazilan += 1
                else:
                    zaten_var += 1
        conn.commit()
        print(f"Bitti. {yazilan} yeni kazanım yazıldı, {zaten_var} zaten vardı (aynı kod).")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
