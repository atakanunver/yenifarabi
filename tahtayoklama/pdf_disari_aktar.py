"""
tahtayoklama/pdf_disari_aktar.py — e-Okul/MEB sınıf listesi PDF'ini
`data/roster/<sinif>.json`'a çevirir.

**BEST-EFFORT, GERÇEK BİR ÖRNEK PDF'E KARŞI DOĞRULANMADI (2026-08-18).**
e-Okul sınıf listesi çıktısı henüz elde yoktu; bu script "Sıra No — Adı
Soyadı" tarzı, satır başına bir öğrenci olan tipik bir tablo varsayıyor
(regex: `_SATIR_RE`). Gerçek PDF elinize geçince BUNU o dosyayla test edin
— `kitap_index.py`'nin fizik-10.pdf'te yaşadığı gibi, publisher/okul
sistemi başlık/tablo biçimini bekleneni kırabilir. Otomatik ayrıştırma
yanlış çıkarsa, roster JSON'ı doğrudan elle de yazabilirsiniz (aynı şema,
aşağıya bkz.) — `yoklama.py` kaynağın nasıl üretildiğini bilmez, yalnızca
JSON'u okur.

Çıktı şeması:
    {"sinif": "9-A", "ogrenciler": [{"no": 1, "ad_soyad": "Ahmet Yılmaz"}, ...]}

Kullanım:
    python pdf_disari_aktar.py sinif_listesi.pdf --sinif 9-A
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

BASE_DIR = Path(__file__).resolve().parent
ROSTER_DIR = BASE_DIR / "data" / "roster"

# "1  Ahmet Yılmaz", "12- Ayşe Demir", "3. Mehmet Kaya" gibi satırları
# yakalar — sıra numarası + isim. Yalnızca harf/boşluk/Türkçe karakterden
# oluşan bir isim bekler; T.C. kimlik no gibi ekstra sütunlar varsa isim
# kısmını (son alfabetik grup) almaya çalışır.
_SATIR_RE = re.compile(
    r"^\s*(\d{1,3})[.\-–\s]+([A-ZÇĞİÖŞÜ][A-Za-zçğıöşüÇĞİÖŞÜ' ]{2,60})\s*$"
)


def pdfden_cikar(pdf_yolu: Path) -> list[dict]:
    ogrenciler: list[dict] = []
    with pdfplumber.open(pdf_yolu) as pdf:
        for sayfa in pdf.pages:
            metin = sayfa.extract_text() or ""
            for satir in metin.splitlines():
                m = _SATIR_RE.match(satir)
                if not m:
                    continue
                no = int(m.group(1))
                ad_soyad = " ".join(m.group(2).split())  # fazla boşlukları sadeleştir
                ogrenciler.append({"no": no, "ad_soyad": ad_soyad})
    return ogrenciler


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", help="e-Okul/MEB sınıf listesi PDF dosyası")
    ap.add_argument("--sinif", required=True, help="Sınıf adı, örn. 9-A")
    a = ap.parse_args()

    pdf_yolu = Path(a.pdf)
    if not pdf_yolu.exists():
        print(f"PDF bulunamadı: {pdf_yolu}", file=sys.stderr)
        return 1

    ogrenciler = pdfden_cikar(pdf_yolu)
    if not ogrenciler:
        print(
            "UYARI: Hiçbir öğrenci satırı ayrıştırılamadı — bu PDF'in biçimi "
            "_SATIR_RE'nin varsaydığından farklı. `python -c \"import "
            "pdfplumber; print(pdfplumber.open('"
            + str(pdf_yolu)
            + "').pages[0].extract_text())\"` ile ham metni görüp deseni "
            "elle ayarlayın, ya da roster JSON'ı doğrudan elle yazın.",
            file=sys.stderr,
        )
        return 1

    ROSTER_DIR.mkdir(parents=True, exist_ok=True)
    hedef = ROSTER_DIR / f"{a.sinif}.json"
    hedef.write_text(
        json.dumps({"sinif": a.sinif, "ogrenciler": ogrenciler}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(ogrenciler)} öğrenci bulundu → {hedef}")
    print("KONTROL EDİN: liste doğru mu? Yanlışsa JSON'ı elle düzeltin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
