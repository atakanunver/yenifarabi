"""soruhavuzu/dersler.py — ders adı/dosya adı → (sınıf, ders anahtarı)."""

import re

_ESLEME = [  # (anahtar kelime, ders anahtarı) — sıra önemli: "temel matematik" → matematik
    ("edebiyat", "edebiyat"),
    ("edebıyat", "edebiyat"),
    ("matematik", "matematik"),
    ("fizik", "fizik"),
    ("kimya", "kimya"),
    ("biyoloji", "biyoloji"),
    ("inkılap", "tarih"),
    ("tarih", "tarih"),
    ("coğrafya", "cografya"),
    ("cografya", "cografya"),
    ("din", "din"),
    ("dkab", "din"),
    ("felsefe", "felsefe"),
    ("ingilizce", "ingilizce"),
    ("görsel", "gorsel_sanatlar"),
    ("gorsel", "gorsel_sanatlar"),
    ("sanat", "gorsel_sanatlar"),
    ("waymark", "ingilizce"),
    ("almanca", "almanca"),
    ("bilişim", "bilisim"),
    ("bilisim", "bilisim"),
    ("yapay zeka", "bilisim"),
    ("yapazeka", "bilisim"),
]

_FIZIK_KONULARI = (
    "cembersel_hareket",
    "basit_harmonik_hareket",
    "dalga_mekanigi",
    "atom_fizigi",
    "modern_fizik",
    "modern_fizig",
)

_EDEBIYAT_KONULARI = (
    "giris-",
    "hikaye-",
    "siir-",
    "roman-",
    "tiyatro-",
    "deneme-soylev-",
)


def _kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def ders_anahtari(ad: str) -> str | None:
    k = _kucuk(ad)
    for kelime, anahtar in _ESLEME:
        if kelime in k:
            return anahtar
    return None


def dosyadan_cozumle(dosya_adi: str) -> tuple[int | None, str | None]:
    k = _kucuk(dosya_adi)

    # 1. Başlangıçtaki sınıf rakamı (örn. '12sinif_...', '9_sinif_...')
    m = re.match(r"^(9|10|11|12)(?=[^0-9])", k)
    if not m:
        m = re.search(r"^(9|10|11|12)_sinif", k)
    if not m:
        m = re.search(r"\b(9|10|11|12)\.s[ıi]n[ıi]f", k)
    sinif = int(m.group(1)) if m else None
    ders = ders_anahtari(k)

    # 2. MEB konu bazlı isimlendirmeler (12. sınıf fizik/edebiyat serisi)
    if any(f in k for f in _FIZIK_KONULARI):
        return 12, "fizik"
    if any(e in k for e in _EDEBIYAT_KONULARI):
        return 12, "edebiyat"
    if k.startswith("mat_"):
        return 12, "matematik"
    if "edebiyat" in k and "12" in k:
        return 12, "edebiyat"

    return sinif, ders
