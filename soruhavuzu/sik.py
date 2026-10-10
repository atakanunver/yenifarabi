"""soruhavuzu/sik.py — şıkları kanonik (deterministik, idempotent) sıraya dizer.
Model doğru şıkkı çoğunlukla A/B'ye koyuyordu (%46 A, %36 B, %15 C, %2,4 D); metin hash'ine
göre sıralamak dağılımı dengeler. Konuma atıf yapan şıklar ("A ve B", "hepsi") ve sayısal
şıklar (küçükten büyüğe) için sıra korunur/anlamlıdır."""

import hashlib
import re

ATIF = re.compile(r"^(yalnız )?[A-D]( ve | - |, )[A-D]", re.IGNORECASE)
ATIF_KELIME = re.compile(r"(yukarıdakiler|hepsi|hiçbiri|tümü|her ikisi)", re.IGNORECASE)
# "A) Mitokondri" gibi harf önekli şıklar: sıra değişirse önek konumla çelişir
HARF_ONEK = re.compile(r"^\s*[A-Da-d][\).]\s")
SAYISAL = re.compile(r"^\s*-?[0-9]+([.,][0-9]+)?\s*[%°a-zA-ZçğıöşüÇĞİÖŞÜ²³/ ]{0,8}$")
SAYI = re.compile(r"-?[0-9]+(?:[.,][0-9]+)?")


def _deger(secenek: str) -> float:
    return float(SAYI.search(secenek).group().replace(",", "."))


def kanonik_sira(soru: str, secenekler: list[str], dogru_index: int) -> tuple[list[str], int]:
    if any(ATIF.search(s.strip()) or ATIF_KELIME.search(s) or HARF_ONEK.match(s) for s in secenekler):
        return secenekler, dogru_index
    if all(SAYISAL.match(s) for s in secenekler):
        anahtar = lambda s: (_deger(s), s)  # noqa: E731
    else:
        anahtar = lambda s: hashlib.sha256(  # noqa: E731
            (soru.strip() + "\x1f" + s.strip()).encode()
        ).hexdigest()
    yeni = sorted(secenekler, key=anahtar)
    return yeni, yeni.index(secenekler[dogru_index])
