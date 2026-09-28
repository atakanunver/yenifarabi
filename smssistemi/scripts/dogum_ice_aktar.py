"""BİR KEREYE MAHSUS VEYA GÜNCELLEME: dogum/Dogum.xlsx verisini smssistemi'ne aktarır.

Kullanıcının talimatı doğrultusunda:
- Zaten öğrencimiz olanlar (101 öğrenciyle eşleşen 67 kişi): Doğrudan bağlanır, onaya gerek yoktur.
- Personel adayları (23 kişi): Personel sınıfına eklenir.
- Kurumdan ayrılan / listede olmayan öğrenciler (42 kişi): Varsayılan olarak ATLANIR,
  istendiğinde --ayrilanlar-dahil ile eklenebilir.

Kullanım:
    venv/bin/python scripts/dogum_ice_aktar.py --kuru-calistir
    venv/bin/python scripts/dogum_ice_aktar.py
    venv/bin/python scripts/dogum_ice_aktar.py --ayrilanlar-dahil
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import dogum_mantik


def main() -> None:
    ayristirici = argparse.ArgumentParser(description=__doc__)
    ayristirici.add_argument(
        "--dosya",
        type=Path,
        default=dogum_mantik.VARSAYILAN_EXCEL,
        help="Dogum.xlsx yolu (varsayılan: dogum/Dogum.xlsx)",
    )
    ayristirici.add_argument(
        "--kuru-calistir",
        action="store_true",
        help="DB'ye hiçbir şey yazmaz, yalnızca özet basar.",
    )
    ayristirici.add_argument(
        "--ayrilanlar-dahil",
        action="store_true",
        help="Mevcut 101 öğrenci arasında bulunmayan 42 eski/ayrılan öğrenciyi de Bilinmeyen Sınıf'a ekler.",
    )
    args = ayristirici.parse_args()

    if not args.dosya.is_file():
        print(f"Dosya bulunamadı: {args.dosya}", file=sys.stderr)
        sys.exit(1)

    db.semayi_kur()
    conn = db.baglanti()
    try:
        analiz = dogum_mantik.excel_analiz_et(args.dosya, conn=conn)
        if "hata" in analiz:
            print(f"Hata: {analiz['hata']}", file=sys.stderr)
            sys.exit(1)

        ozet = analiz["ozet"]
        print(f"Excel'den okunan toplam geçerli kişi: {ozet['toplam_okunan']}")
        print(f"  • Zaten öğrencimiz olanlar (doğrudan eşleşen): {ozet['eslesen']}")
        print(f"  • Personel adayları: {ozet['personel']}")
        print(f"  • Ayrılan / listede olmayan öğrenciler: {ozet['ayrilan']}")

        if args.kuru_calistir:
            print("\n[KURU ÇALIŞTIRMA — DB'ye hiçbir şey yazılmadı]")
            print(f"  Uygulanacak işlem: {ozet['eslesen']} öğrencinin doğum tarihi güncellenecek,")
            print(f"  {ozet['personel']} personel eklenecek,")
            if args.ayrilanlar_dahil:
                print(f"  {ozet['ayrilan']} eski öğrenci Bilinmeyen Sınıf'a eklenecek.")
            else:
                print(f"  {ozet['ayrilan']} eski öğrenci ATLANACAK (DB temiz tutulacak).")
            return

        secilen_personeller = [p["ad_soyad"] for p in analiz["personel_adaylari"]]
        secilen_ayrilanlar = (
            [a["ad_soyad"] for a in analiz["ayrilan_ogrenci_adaylari"]]
            if args.ayrilanlar_dahil
            else []
        )

        sonuc = dogum_mantik.aktarim_uygula(
            conn,
            secilen_personeller=secilen_personeller,
            secilen_ayrilanlar=secilen_ayrilanlar,
            dosya_yolu=args.dosya,
        )

        print("\n[İŞLEM TAMAMLANDI]")
        print(f"  • Eşleşen öğrenci tarihi güncellendi: {sonuc['eslesen_guncellendi']}")
        print(f"  • Yeni personel eklendi: {sonuc['personel_eklendi']} (zaten varsa güncellenen: {sonuc['personel_guncellendi']})")
        print(f"  • Eklenen ayrılan öğrenci: {sonuc['ayrilan_eklendi']}")
        print(f"  • Atlanan ayrılan öğrenci: {sonuc['atlanan_ayrilan']}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
