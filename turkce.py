"""turkce.py - Türkçe'ye duyarlı küçük harf / başlık harfi yardımcıları.

Python'un str.lower()/capitalize()/title() "I" ve "İ" harflerini yanlış çevirir
("İngilizce".lower() -> "i̇ngilizce" birleşik noktalı, "ingilizce".capitalize() -> "Ingilizce").
KAPSAM_ESLEME anahtarları Türkçe-küçük harfli olduğundan aramalar tr_kucuk() ile yapılır.
"""

_KUCUK_CEVIRI = str.maketrans({"İ": "i", "I": "ı"})
_BUYUK_ILK = {"i": "İ", "ı": "I"}
_KUCUK_KALANLAR = {"ve", "ile"}


def tr_kucuk(s: str) -> str:
    """Türkçe-güvenli küçük harf: İ->i, I->ı sonra lower()."""
    return (s or "").translate(_KUCUK_CEVIRI).lower()


def tr_ilk_buyuk(kelime: str) -> str:
    """Tek kelimeyi baş harf büyük, kalanı küçük yapar (i->İ, ı->I)."""
    if not kelime:
        return kelime
    k = tr_kucuk(kelime)
    if "." in k and len(k) <= 5:  # kısaltma: t.c. -> T.C.
        return k.upper()
    ilk = _BUYUK_ILK.get(k[0], k[0].upper())
    return ilk + k[1:]


def tr_baslik(s: str) -> str:
    """'ingilizce' -> 'İngilizce', 'türk dili ve edebiyatı' -> 'Türk Dili ve Edebiyatı'."""
    kelimeler = (s or "").split()
    return " ".join(
        k if tr_kucuk(k) in _KUCUK_KALANLAR else tr_ilk_buyuk(k)
        for k in (tr_kucuk(w) for w in kelimeler)
    )


def kapsam_anahtari(s: str) -> str:
    """Ders adını KAPSAM_ESLEME aramasına uygun biçime getirir."""
    return tr_kucuk(s).strip()
