"""tahtayoklama/data/ders_programi.json okuma + ders adı/kısaltma yardımcıları.

data/ders_programi.json, mudur/ders_programi.json'dan alınmış KASITLI
BAĞIMSIZ bir kopya (bkz. CLAUDE.md, zil.json'la aynı desen) — ders programı
değiştiğinde bu dosya elle güncellenmeli, iki proje arasında canlı bir bağ
yok.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path
import json

DERS_PROGRAMI_DOSYASI = (
    Path(__file__).resolve().parent.parent / "data" / "ders_programi.json"
)

_GUN_ADLARI = {
    1: "pazartesi",
    2: "sali",
    3: "carsamba",
    4: "persembe",
    5: "cuma",
}

# Tam ders adı (data/ders_programi.json'daki hâliyle, küçük harf) -> panoda
# gösterilecek kısaltma (büyük harf). Kaynak: dosyadaki tüm sınıfların ders
# adları taranarak çıkarıldı (2026-09-14, 24 farklı ders). Yeni bir ders adı
# eklenirse burada da eklenmeli — yoksa `_buyuk_harf()` ile ham ad
# büyütülerek gösterilir (eksik kısaltma sessizce yutulmaz).
KISALTMALAR = {
    "ingilizce": "İNG",
    "din kültürü ve ahlak bilgisi": "DKAB",
    "görsel sanatlar": "GÖR SAN",
    "spor etkinlikleri": "SPOR",
    "sağlık bilgisi ve trafik kültürü": "SBTK",
    "tarih": "TARİH",
    "türk dili ve edebiyatı": "TDE",
    "biyoloji": "BİYOLOJİ",
    "kimya": "KİM",
    "almanca": "ALM",
    "matematik": "MAT",
    "rehberlik": "REHB",
    "fizik": "FİZ",
    "coğrafya": "COĞ",
    "beden eğitimi": "BED",
    "felsefe": "FEL",
    "peygamberimizin hayatı": "PEY",
    "osmanlı türkçesi": "OSM TÜRKÇE",
    "matematik uygulamaları": "MAT UYG",
    "psikoloji": "PSİ",
    "bilişim teknolojileri ve yazılım": "BTY",
    "sınav hazırlık çalışması": "SHÇ",
    "inkılap tarihi ve atatürkçülük": "İTA",
    "çağdaş türk ve dünya tarihi": "ÇTDT",
}


def _buyuk_harf(ad: str) -> str:
    """Türkçe-doğru büyütme — str.upper() 'i'yi 'I' yapar (nokta kaybolur),
    kısaltma tablosunda olmayan bir ders adı için fallback."""
    return ad.replace("i", "İ").replace("ı", "I").upper()


@lru_cache(maxsize=1)
def _yukle() -> dict:
    if not DERS_PROGRAMI_DOSYASI.exists():
        return {}
    return json.loads(DERS_PROGRAMI_DOSYASI.read_text(encoding="utf-8")).get("siniflar", {})


def yenile() -> None:
    """Dosya elle değiştiyse önbelleği temizler."""
    _yukle.cache_clear()


def ders_adi(sinif: str, tarih: date, ders_no: int) -> str | None:
    gun = _GUN_ADLARI.get(tarih.isoweekday())
    if gun is None:  # hafta sonu — programda hiç yok
        return None
    return _yukle().get(sinif, {}).get(gun, {}).get(str(ders_no))


def ders_kisa_adi(sinif: str, tarih: date, ders_no: int) -> str | None:
    ad = ders_adi(sinif, tarih, ders_no)
    if ad is None:
        return None
    return KISALTMALAR.get(ad, _buyuk_harf(ad))
