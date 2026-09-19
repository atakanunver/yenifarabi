"""BİR KEREYE MAHSUS: tahtayoklama'nın öğrenci roster JSON'larındaki
(ad_soyad, sınıf) verisini smssistemi rehberine (kisiler tablosu,
tur='ogrenci', telefon=NULL) aktarır. Telefon numaraları yok — kullanıcı
Excel'le yükleyene kadar boş kalır (bkz. /rehber toplu yükle).

Kullanım: smssistemi/ dizininden `venv/bin/python scripts/roster_ice_aktar.py`
Zaten aktarılmış (aynı isim+sınıf) kişileri tekrar eklemez — güvenle
tekrar çalıştırılabilir.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

ROSTER_DIZINI = (
    Path(__file__).resolve().parent.parent.parent / "tahtayoklama" / "data" / "roster"
)


def main() -> None:
    if not ROSTER_DIZINI.is_dir():
        print(f"Roster dizini bulunamadı: {ROSTER_DIZINI}", file=sys.stderr)
        sys.exit(1)

    db.semayi_kur()
    conn = db.baglanti()

    toplam_eklendi = toplam_atlandi = 0
    try:
        for dosya in sorted(ROSTER_DIZINI.glob("*.json")):
            if dosya.stem.endswith(".example"):
                continue
            veri = json.loads(dosya.read_text(encoding="utf-8"))
            sinif_ad = veri["sinif"]
            sinif_id = db.sinif_ekle(conn, sinif_ad)

            eklendi = atlandi = 0
            for ogrenci in veri["ogrenciler"]:
                ad_soyad = ogrenci["ad_soyad"].strip()
                if db.kisi_bul_isimle(conn, ad_soyad, sinif_id, "ogrenci") is not None:
                    atlandi += 1
                    continue
                db.kisi_ekle(conn, ad_soyad, None, sinif_id, "ogrenci")
                eklendi += 1

            print(f"{sinif_ad}: {eklendi} eklendi, {atlandi} zaten vardı")
            toplam_eklendi += eklendi
            toplam_atlandi += atlandi
    finally:
        conn.close()

    print(f"\nToplam: {toplam_eklendi} eklendi, {toplam_atlandi} zaten vardı.")


if __name__ == "__main__":
    main()
