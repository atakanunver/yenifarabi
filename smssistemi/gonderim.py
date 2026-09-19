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


# --- Rehber: CSV/Excel'den kişi çekme (Adı Soyadı + Telefonu, geniş toleranslı) ---

_AD_ANAHTAR_KELIMELERI = ("soyad", "isim", "name", "veli ad", "öğrenci ad", "ogrenci ad")
_TELEFON_ANAHTAR_KELIMELERI = ("telefon", "gsm", "cep", "phone", "tel")
_SINIF_ANAHTAR_KELIMELERI = ("sınıf", "sinif", "class")


def _baslik_ad_sutunu_mu(baslik: str) -> bool:
    b = baslik.strip().lower()
    return b in ("ad", "adı") or any(k in b for k in _AD_ANAHTAR_KELIMELERI)


def _baslik_telefon_sutunu_mu(baslik: str) -> bool:
    return any(k in baslik.strip().lower() for k in _TELEFON_ANAHTAR_KELIMELERI)


def _baslik_sinif_sutunu_mu(baslik: str) -> bool:
    return any(k in baslik.strip().lower() for k in _SINIF_ANAHTAR_KELIMELERI)


def _rehber_satirlarini_isle(satirlar: list[list[str]]) -> list[dict]:
    """`satirlar`: hücre metinlerinden oluşan satır listesi (ilk satır
    başlık olabilir). Başlıktaki ad/telefon/sınıf sütunlarını geniş
    toleranslı tanır (Adı Soyadı/İsim/Name, Telefon/Cep/GSM,
    Sınıf/Sinif/Class); hiçbiri eşleşmezse ilk iki sütunu
    (ad_soyad, telefon) sayar, başlık satırı atlanmaz."""
    if not satirlar:
        return []
    baslik = satirlar[0]
    ad_idx = tel_idx = sinif_idx = None
    for i, hucre in enumerate(baslik):
        hucre = (hucre or "").strip()
        if ad_idx is None and _baslik_ad_sutunu_mu(hucre):
            ad_idx = i
        elif tel_idx is None and _baslik_telefon_sutunu_mu(hucre):
            tel_idx = i
        elif sinif_idx is None and _baslik_sinif_sutunu_mu(hucre):
            sinif_idx = i

    if ad_idx is not None or tel_idx is not None:
        veri_satirlari = satirlar[1:]
    else:
        ad_idx, tel_idx = 0, 1
        veri_satirlari = satirlar

    def _al(satir: list[str], idx: int | None) -> str:
        if idx is None or idx >= len(satir):
            return ""
        return (satir[idx] or "").strip()

    sonuc: list[dict] = []
    for satir in veri_satirlari:
        ad_soyad = _al(satir, ad_idx)
        telefon_ham = _al(satir, tel_idx)
        sinif = _al(satir, sinif_idx) if sinif_idx is not None else ""
        if not ad_soyad and not telefon_ham:
            continue
        telefon = normalize_phone(telefon_ham) if telefon_ham else ""
        sonuc.append({"ad_soyad": ad_soyad, "telefon": telefon, "sinif": sinif or None})
    return sonuc


def rehber_dosyasindan_oku(dosya_adi: str, icerik: bytes) -> list[dict]:
    """.csv/.xlsx dosyasından `{"ad_soyad", "telefon", "sinif"}` sözlükleri
    çıkarır — `sinif` dosyada bir sütun varsa doldurulur, yoksa `None`
    (çağıran taraf formda seçilen sınıfı kullanır)."""
    ad_kucuk = dosya_adi.lower()
    if ad_kucuk.endswith((".xlsx", ".xlsm")):
        import openpyxl

        calisma_kitabi = openpyxl.load_workbook(io.BytesIO(icerik), read_only=True, data_only=True)
        try:
            sayfa = calisma_kitabi.active
            satirlar = [
                ["" if h is None else str(h) for h in satir]
                for satir in sayfa.iter_rows(values_only=True)
            ]
        finally:
            calisma_kitabi.close()
    else:
        metin = icerik.decode("utf-8-sig")
        ornek = metin[:2048]
        ayirici = ";" if ornek.count(";") > ornek.count(",") else ","
        satirlar = list(csv.reader(io.StringIO(metin), delimiter=ayirici))
    return _rehber_satirlarini_isle(satirlar)
