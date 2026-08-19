"""
tahtayoklama/pdf_disari_aktar.py — e-Okul/MEB sınıf listesi PDF'ini
`data/roster/<sinif>.json`'a çevirir.

**Gerçek bir örnek PDF'e karşı DOĞRULANDI (2026-08-19, 9-A sınıf listesi.pdf,
Çankırı Valiliği / Kurşunlu Şehit Murat Ustaoğlu Anadolu Lisesi çıktısı).**
Satır biçimi: `<S.No> <Öğrenci No> <AD SOYAD (TAMAMI BÜYÜK HARF)> <Cinsiyet>
[Pansiyon Durumu]` — örn. `1 1002 MUSTAFA EMİR TOKMAKOĞLU Erkek` ya da
`6 220 ÖZLEM DOĞAN Kız Yatılı`. Roster'daki `no` alanı **Öğrenci No**'dur
(S.No değil) — okulun kalıcı öğrenci numarası, sınıf listesindeki sıradan
daha stabil bir kimlik (öğrenci nakil olursa S.No değişir, Öğrenci No
değişmez).

**KRİTİK BULGU (2026-08-19): dosya adı "9-A sınıf listesi.pdf" olsa da PDF
İKİ ŞUBEYİ birden içeriyordu** — sayfa 1 "A Şubesi" (20 öğrenci), sayfa 2
"B Şubesi" (20 öğrenci, farklı bir sınıf). İlk sürüm tüm sayfaları körlemesine
tarayıp 9-B öğrencilerini yanlışlıkla 9-A roster'ına karıştırmıştı (38
öğrenci — yanlış). Artık her sayfanın başlığındaki "... Şubesi" satırı
okunuyor (`_SUBE_BASLIK_RE`) ve yalnızca `--sinif`'e uyan şubenin sayfaları
işleniyor — okulun aynı PDF'te birden fazla şubeyi tek dosyada dışa
aktarması normal, her sınıf için AYNI PDF'i farklı `--sinif` değeriyle
tekrar çalıştırın (`python pdf_disari_aktar.py dosya.pdf --sinif 9-B`).

Başka bir okulun/sistemin PDF'i bu biçimden FARKLI çıkabilir — bu script
yalnızca Çankırı ili e-Okul çıktısıyla doğrulandı. Ayrıştırma boş dönerse
(`_SATIR_RE` hiçbir satırı yakalamazsa ya da hiçbir sayfa şube başlığıyla
eşleşmezse), ham metni görüp deseni elle ayarlayın (aşağıdaki hata mesajı
bunu nasıl yapacağınızı gösterir), ya da roster JSON'ı doğrudan elle yazın
— `yoklama.py` kaynağın nasıl üretildiğini bilmez, yalnızca JSON'u okur.

AD-SOYAD BİÇİMLENDİRME: kaynak TAMAMI BÜYÜK HARF geldiği için Türkçe-doğru
başlık biçimine çevrilir (`_ad_bicimlendir`) — Python'un varsayılan
`str.title()`/`str.lower()`'ı Türkçe İ/I harflerini YANLIŞ çevirir
('İ'.lower() → 'i̇' iki kod noktalı, 'I'.lower() → 'i' — 'ı' değil);
bu yüzden bu iki harf için elle eşleme kullanılıyor.

Çıktı şeması:
    {"sinif": "9-A", "ogrenciler": [{"no": 1002, "ad_soyad": "Mustafa Emir Tokmakoğlu", "cinsiyet": "Erkek"}, ...]}

Kullanım:
    python pdf_disari_aktar.py "9-A sınıf listesi.pdf" --sinif 9-A
"""

import argparse
import json
import re
import sys
from pathlib import Path

import pdfplumber

BASE_DIR = Path(__file__).resolve().parent
ROSTER_DIR = BASE_DIR / "data" / "roster"

# S.No · Öğrenci No · AD SOYAD (büyük harf, birden çok kelime) · Cinsiyet
# · isteğe bağlı sondaki "Yatılı" gibi pansiyon durumu (görülürse yok say).
_SATIR_RE = re.compile(
    r"^\s*(\d{1,3})\s+(\d{2,10})\s+([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ' ]+?)\s+(Erkek|Kız)(?:\s+\S.*)?\s*$"
)

# "AL - 9. Sınıf / A Şubesi (ALANI YOK) Sınıf Listesi" → şube harfi "A".
_SUBE_BASLIK_RE = re.compile(r"Sınıf\s*/\s*([A-ZÇĞİÖŞÜ])\s*Şubesi", re.IGNORECASE)


def _sube_harfi(sinif: str) -> str:
    """'9-A' -> 'A', '10-B' -> 'B' — sınıf adının son harfi şube kabul edilir."""
    return sinif.strip()[-1:].upper()

# Python'un varsayılan case-fold'u Türkçe İ/I'yı doğru çevirmiyor — elle eşleme.
_TR_BUYUK_KUCUK = {"İ": "i", "I": "ı"}


def _turkce_kelime_bicimlendir(kelime: str) -> str:
    if not kelime:
        return kelime
    ilk, kalan = kelime[0], kelime[1:]
    kalan_kucuk = "".join(_TR_BUYUK_KUCUK.get(c, c.lower()) for c in kalan)
    return ilk + kalan_kucuk


def _ad_bicimlendir(ad_soyad_buyuk: str) -> str:
    return " ".join(_turkce_kelime_bicimlendir(k) for k in ad_soyad_buyuk.split())


def pdfden_cikar(pdf_yolu: Path, sinif: str) -> list[dict]:
    """Yalnızca `sinif`in şubesine (son harf) uyan sayfaları işler — bir PDF
    birden fazla şubeyi birden içerebilir (bkz. modül dokümanı)."""
    hedef_sube = _sube_harfi(sinif)
    ogrenciler: list[dict] = []
    with pdfplumber.open(pdf_yolu) as pdf:
        for sayfa in pdf.pages:
            metin = sayfa.extract_text() or ""
            sube_m = _SUBE_BASLIK_RE.search(metin)
            if not sube_m or sube_m.group(1).upper() != hedef_sube:
                continue
            for satir in metin.splitlines():
                m = _SATIR_RE.match(satir)
                if not m:
                    continue
                _sira_no, ogrenci_no, ad_soyad_buyuk, cinsiyet = m.groups()
                ogrenciler.append({
                    "no": int(ogrenci_no),
                    "ad_soyad": _ad_bicimlendir(ad_soyad_buyuk),
                    "cinsiyet": cinsiyet,
                })
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

    ogrenciler = pdfden_cikar(pdf_yolu, a.sinif)
    if not ogrenciler:
        print(
            f"UYARI: '{a.sinif}' (şube '{_sube_harfi(a.sinif)}') için hiçbir "
            "öğrenci satırı ayrıştırılamadı — ya bu PDF'te o şube yok, ya da "
            "PDF'in biçimi _SATIR_RE/_SUBE_BASLIK_RE'nin varsaydığından "
            "farklı. `python -c \"import pdfplumber; print(pdfplumber.open('"
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
