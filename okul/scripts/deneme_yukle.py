"""Harici deneme sonucunu okul.db'ye yükler.

Kullanım (okul/ dizininden):
    venv/bin/python scripts/deneme_yukle.py deneme.json [--kuru] [--yayinla]
JSON: {"ad", "tarih"?, "ozet"?, "ogrenciler": [{okul_no, ad_soyad, sinif, girdi, veri, analiz, tavsiye}]}
--kuru: hiçbir şey yazmaz, yalnız eşleşen/eşleşmeyen/uyuşmayan sayısını yazar.
Varsayılan yayinda=0; --yayinla ile 1. Aynı ad tekrar yüklenirse güncellenir, hiçbir şey silinmez.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import denemeler
from ayarlar import AYAR


def main(argv: list[str]) -> int:
    bayrak = {a for a in argv if a.startswith("--")}
    yollar = [a for a in argv if not a.startswith("--")]
    if len(yollar) != 1 or not bayrak <= {"--kuru", "--yayinla"}:
        print(__doc__)
        return 2
    kuru, yayinla = "--kuru" in bayrak, "--yayinla" in bayrak
    belge = json.loads(Path(yollar[0]).read_text(encoding="utf-8"))
    if kuru:
        # Salt-okunur: şema göçü/dosya oluşturma yok.
        conn = sqlite3.connect(f"file:{AYAR.db_yolu}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    else:
        db.sema_kur()
        conn = db.baglanti()
    try:
        s = denemeler.yukle(conn, belge, kuru=kuru, yayinla=yayinla)
    finally:
        conn.close()
    print(
        f"{'[KURU] ' if kuru else ''}{s['ad']}: eşleşen={s['eslesen']}"
        f" eşleşmeyen={s['eslesmeyen']} uyuşmayan={s['uyusmayan']}"
    )
    if s["eslesmeyen_no"]:
        print("Eşleşmeyen okul_no:", *s["eslesmeyen_no"])
    if s["uyusmayan_no"]:
        print("Ad/sınıf uyuşmayan okul_no (uygulanmadı):", *s["uyusmayan_no"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
