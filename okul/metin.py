"""Türkçe metin, isim, telefon ve şifre yardımcıları (saf fonksiyonlar)."""

import re

_ASCII = str.maketrans("çğıöşü", "cgiosu")


def tr_kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def normalize_isim(s: str) -> str:
    return " ".join(tr_kucuk(s).split())


def ilk_sifre(ad_soyad: str) -> str:
    ilk = normalize_isim(ad_soyad).split(" ")[0]
    sade = re.sub(r"[^a-z]", "", ilk.translate(_ASCII))
    return f"{sade}123"


def normalize_telefon(s: str | None) -> str | None:
    if not s:
        return None
    rakam = re.sub(r"\D", "", str(s))
    if rakam.startswith("90") and len(rakam) == 12:
        rakam = "0" + rakam[2:]
    elif len(rakam) == 10 and rakam.startswith("5"):
        rakam = "0" + rakam
    return rakam if re.fullmatch(r"05\d{9}", rakam) else None


def sinif_seviyesi(sinif: str) -> int:
    return int(sinif.split("-", 1)[0])


def kisa_ad(ad_soyad: str) -> str:
    """Liderlik tablosu için "Ali Veli" -> "Ali V." (ad + soyadın baş harfi)."""
    parca = ad_soyad.split()
    if len(parca) < 2:
        return ad_soyad.strip()
    bas = parca[-1][:1].replace("i", "İ").replace("ı", "I").upper()
    return f"{' '.join(parca[:-1])} {bas}."
