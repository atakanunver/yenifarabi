#!/usr/bin/env python3
"""
tools/yks_metin.py — YKS (TYT/AYT) çıkmış soru PDF'lerini düz metne çevirir (offline, API yok)

`kitap_metin.py`'nin YKS/ klasörü için karşılığı: sorular ders sırasında
PDF'ten değil, önceden çıkarılmış düz metinden okunur
(`icerik/yks_metin/<dosya>.txt`, `actions/yks_sorulari.py` bunu okur).

Kitap metnindeki gibi bir sembol-onarım katmanı YOK: `kitap_metin.py`'deki
#/$ onarımı belirli MEB ders kitabı fontlarında doğrulandı, bu PDF'lerin
kaynağı farklı — kör uygulanmaz. Bozuk sembol varsa olduğu gibi kalır.

Sayfa sınırları `\n\n===SAYFA <n>===\n\n` işaretiyle korunur, böylece bir
eşleşmenin hangi dosyanın hangi sayfasından geldiği kaybolmaz.

Kullanım:
    python tools/yks_metin.py YKS/ --txt icerik/yks_metin
    python tools/yks_metin.py YKS/tyt-dkab.pdf --txt icerik/yks_metin

Varsayılan olarak hedefte zaten .txt'si olan bir PDF atlanır (--zorla ile
yeniden işlenir) — kitap_metin.py ile aynı gerekçe: betiği her seferinde
bütün klasöre çağırmak ucuz kalsın, yalnızca yeni PDF işlensin.
"""

import argparse
import sys
from pathlib import Path

try:
    import fcntl
except ImportError:      # Windows — kilitsiz devam (yalnız POSIX tahtalarda gerekli)
    fcntl = None

BASE_DIR = Path(__file__).resolve().parent.parent

SAYFA_ISARETI = "\n\n===SAYFA {n}===\n\n"


def pdfyi_cevir(pdf_yolu: Path, hedef_dizin: Path) -> dict:
    import pdfplumber

    parcalar = []
    bos_sayfa = 0
    sayfa_sayisi = 0

    with pdfplumber.open(pdf_yolu) as pdf:
        for i, sayfa in enumerate(pdf.pages, start=1):
            sayfa_sayisi += 1
            try:
                metin = (sayfa.extract_text() or "").strip()
            except Exception as e:
                print(f"    s.{i}: okunamadı ({type(e).__name__})")
                metin = ""
            if not metin:
                bos_sayfa += 1
                continue
            parcalar.append(SAYFA_ISARETI.format(n=i) + metin)

    tam_metin = "".join(parcalar).strip()
    hedef_dizin.mkdir(parents=True, exist_ok=True)
    hedef = hedef_dizin / f"{pdf_yolu.stem}.txt"
    hedef.write_text(tam_metin, encoding="utf-8")

    boyut = hedef.stat().st_size / 1024
    print(f"  {pdf_yolu.name:42} {sayfa_sayisi:4} sayfa · "
          f"{bos_sayfa:3} boş · {boyut:7.0f} KB")
    return {"sayfa_sayisi": sayfa_sayisi, "bos_sayfa": bos_sayfa}


def main() -> int:
    ap = argparse.ArgumentParser(description="YKS çıkmış soru PDF -> düz metin (API yok)")
    ap.add_argument("kaynak", help="PDF dosyası ya da klasör")
    ap.add_argument("--txt", default="icerik/yks_metin",
                    help="Hedef klasör (varsayılan: icerik/yks_metin)")
    ap.add_argument("--zorla", action="store_true",
                    help="Zaten dönüştürülmüş (hedefte aynı adla .txt'si olan) "
                         "dosyaları da yeniden işle. Varsayılan: atla.")
    a = ap.parse_args()

    kaynak = Path(a.kaynak)
    hedef  = BASE_DIR / a.txt if not Path(a.txt).is_absolute() else Path(a.txt)
    hedef.mkdir(parents=True, exist_ok=True)

    # kitap_metin.py'deki gibi: aynı hedefe iki süreç birden yazmasın.
    _kilit_tut = None
    if fcntl is not None:
        kilit_dosyasi = open(hedef / ".yks_metin.lock", "w")
        try:
            fcntl.flock(kilit_dosyasi, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _kilit_tut = kilit_dosyasi          # süreç bitene kadar açık tut
        except OSError:
            print(f"Bu hedef için başka bir dönüştürme süreci zaten çalışıyor "
                  f"({hedef}), çıkılıyor.")
            return 0

    if kaynak.is_dir():
        pdfler = sorted(kaynak.glob("*.pdf"))
    elif kaynak.exists():
        pdfler = [kaynak]
    else:
        print(f"Bulunamadı: {kaynak}")
        return 1

    if not pdfler:
        print(f"{kaynak} içinde PDF yok.")
        return 1

    if not a.zorla:
        atlanan = [p for p in pdfler if (hedef / f"{p.stem}.txt").exists()]
        if atlanan:
            print(f"{len(atlanan)} dosya zaten dönüştürülmüş, atlanıyor "
                  f"(yeniden işlemek için --zorla):")
            for p in atlanan:
                print(f"  = {p.name}")
            pdfler = [p for p in pdfler if p not in atlanan]
        if not pdfler:
            print("Dönüştürülecek yeni dosya yok.")
            return 0

    print(f"{len(pdfler)} dosya metne çevriliyor (yerel, API çağrısı yok)…\n")
    for pdf in pdfler:
        try:
            pdfyi_cevir(pdf, hedef)
        except Exception as e:
            print(f"  ✖ {pdf.name}: {type(e).__name__}: {str(e)[:90]}")

    print(f"\nBitti → {hedef}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
