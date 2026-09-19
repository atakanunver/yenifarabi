"""Numara ayrıştırma/doğrulama + CSV içe aktarma + mesaj kişiselleştirme.

C:\\Users\\exa\\Desktop\\sms sistemi\\app.py'deki normalize_phone/
is_valid_phone/_load_csv mantığının web sürümü — Tkinter'a özgü hiçbir şey
yok, saf fonksiyonlar, app.py tarafından çağrılır.
"""

import csv
import io
import re

_TELEFON_RE_ULUSAL = re.compile(r"05\d{9}")
_TELEFON_RE_ULUSLARARASI = re.compile(r"\+905\d{9}")


def normalize_phone(raw: str) -> str:
    raw = raw.strip()
    digits = re.sub(r"[^\d+]", "", raw)
    if digits.startswith("0090"):
        digits = "+90" + digits[4:]
    if digits.startswith("90") and len(digits) == 12:
        digits = "+" + digits
    if digits.startswith("5") and len(digits) == 10:
        digits = "0" + digits
    return digits


def is_valid_phone(tel: str) -> bool:
    if tel.startswith("+90"):
        return bool(_TELEFON_RE_ULUSLARARASI.fullmatch(tel))
    return bool(_TELEFON_RE_ULUSAL.fullmatch(tel))


def is_ascii(text: str) -> bool:
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def metinden_ayristir(numaralar_metni: str) -> tuple[list[tuple[str, str]], list[str]]:
    gecerli: list[tuple[str, str]] = []
    gecersiz: list[str] = []
    for satir in numaralar_metni.splitlines():
        satir = satir.strip()
        if not satir:
            continue
        if "," in satir:
            isim, tel_ham = satir.split(",", 1)
        else:
            isim, tel_ham = "", satir
        tel = normalize_phone(tel_ham)
        if tel and is_valid_phone(tel):
            gecerli.append((isim.strip(), tel))
        else:
            gecersiz.append(satir)
    return gecerli, gecersiz


def csv_ayristir(icerik: bytes) -> list[tuple[str, str]]:
    metin = icerik.decode("utf-8-sig")
    ornek = metin[:2048]
    ayirici = ";" if ornek.count(";") > ornek.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin), delimiter=ayirici)
    sonuc: list[tuple[str, str]] = []
    for satir in okuyucu:
        satir = [c.strip() for c in satir if c.strip()]
        if not satir:
            continue
        if satir[0].lower() in ("isim", "ad", "name", "telefon", "phone"):
            continue
        if len(satir) >= 2:
            sonuc.append((satir[0], satir[1]))
        else:
            sonuc.append(("", satir[0]))
    return sonuc


def kisisellestir(mesaj_sablonu: str, isim: str) -> str:
    return mesaj_sablonu.replace("{isim}", isim or "")
