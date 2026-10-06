"""soruhavuzu/dersler.py — ders adı/dosya adı → (sınıf, ders anahtarı)."""

import re

_ESLEME = [  # (anahtar kelime, ders anahtarı) — sıra önemli: "temel matematik" → matematik
    ("edebiyat", "edebiyat"),
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
    ("waymark", "ingilizce"),
    ("almanca", "almanca"),
]


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
    m = re.match(r"^(9|10|11|12)(?=[^0-9])", k)
    sinif = int(m.group(1)) if m else None
    return sinif, ders_anahtari(k)
