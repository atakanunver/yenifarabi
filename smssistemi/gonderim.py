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


def metinden_ayristir(numaralar_metni: str) -> tuple[list[tuple], list[str]]:
    gecerli: list[tuple] = []
    gecersiz: list[str] = []
    for satir in numaralar_metni.splitlines():
        satir = satir.strip()
        if not satir:
            continue
        parcalar = [p.strip() for p in satir.split(",")]
        if len(parcalar) >= 3:
            isim, tel_ham, ogr_adi = parcalar[0], parcalar[1], parcalar[2]
            tel = normalize_phone(tel_ham)
            if tel and is_valid_phone(tel):
                gecerli.append((isim, tel, ogr_adi))
            else:
                gecersiz.append(satir)
        elif len(parcalar) == 2:
            isim, tel_ham = parcalar[0], parcalar[1]
            tel = normalize_phone(tel_ham)
            if tel and is_valid_phone(tel):
                gecerli.append((isim, tel))
            else:
                gecersiz.append(satir)
        else:
            tel = normalize_phone(satir)
            if tel and is_valid_phone(tel):
                gecerli.append(("", tel))
            else:
                gecersiz.append(satir)
    return gecerli, gecersiz


def csv_ayristir(icerik: bytes) -> list[tuple]:
    metin = icerik.decode("utf-8-sig")
    ornek = metin[:2048]
    ayirici = ";" if ornek.count(";") > ornek.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin), delimiter=ayirici)
    sonuc: list[tuple] = []
    for satir in okuyucu:
        satir = [c.strip() for c in satir if c.strip()]
        if not satir:
            continue
        if satir[0].lower() in ("isim", "ad", "name", "telefon", "phone"):
            continue
        if len(satir) >= 3:
            sonuc.append((satir[0], satir[1], satir[2]))
        elif len(satir) >= 2:
            sonuc.append((satir[0], satir[1]))
        else:
            sonuc.append(("", satir[0]))
    return sonuc


def kisisellestir(mesaj_sablonu: str, isim: str, ogrenci_adi: str = "") -> str:
    return (
        mesaj_sablonu
        .replace("{isim}", isim or "")
        .replace("{ogrenci_adi}", ogrenci_adi or "")
    )


# --- Rehber: CSV/Excel'den kişi çekme (Adı Soyadı + Telefonu + Öğrenci Adı) ---

_TELEFON_ANAHTAR_KELIMELERI = ("telefon", "gsm", "cep", "phone", "tel")
_SINIF_ANAHTAR_KELIMELERI = ("sınıf", "sinif", "class")
_OGRENCI_ANAHTAR_KELIMELERI = ("öğrenci", "ogrenci", "student")
_VELI_ANAHTAR_KELIMELERI = ("veli adı", "veli ad", "veli isim", "veli ad-soyad")
_GENEL_AD_ANAHTAR_KELIMELERI = ("soyad", "isim", "name", "ad", "adı")


def _baslik_telefon_sutunu_mu(baslik: str) -> bool:
    return any(k in baslik.strip().lower() for k in _TELEFON_ANAHTAR_KELIMELERI)


def _baslik_sinif_sutunu_mu(baslik: str) -> bool:
    return any(k in baslik.strip().lower() for k in _SINIF_ANAHTAR_KELIMELERI)


def _baslik_ogrenci_sutunu_mu(baslik: str) -> bool:
    b = baslik.strip().lower()
    if _baslik_telefon_sutunu_mu(b) or _baslik_sinif_sutunu_mu(b):
        return False
    return any(k in b for k in _OGRENCI_ANAHTAR_KELIMELERI)


def _baslik_veli_sutunu_mu(baslik: str) -> bool:
    b = baslik.strip().lower()
    if _baslik_telefon_sutunu_mu(b) or _baslik_sinif_sutunu_mu(b) or _baslik_ogrenci_sutunu_mu(b):
        return False
    if any(k in b for k in _VELI_ANAHTAR_KELIMELERI):
        return True
    if any(k in b for k in ("velisi", "yakın", "akraba", "derece")):
        return False
    return "veli" in b


def _baslik_genel_ad_sutunu_mu(baslik: str) -> bool:
    b = baslik.strip().lower()
    if (
        _baslik_telefon_sutunu_mu(b)
        or _baslik_sinif_sutunu_mu(b)
        or _baslik_ogrenci_sutunu_mu(b)
        or _baslik_veli_sutunu_mu(b)
    ):
        return False
    return b in ("ad", "adı") or any(k in b for k in _GENEL_AD_ANAHTAR_KELIMELERI)


def _rehber_satirlarini_isle(satirlar: list[list[str]], tur: str | None = None) -> list[dict]:
    """`satirlar`: hücre metinlerinden oluşan satır listesi.
    Başlıktaki ad/öğrenci adı/telefon/sınıf sütunlarını geniş toleranslı tanır."""
    if not satirlar:
        return []

    en_iyi_baslik_idx = None
    en_iyi_skor = 0
    en_iyi_harita = None

    for satir_idx in range(min(len(satirlar), 5)):
        satir = satirlar[satir_idx]
        ad_idx = ogrenci_idx = tel_idx = sinif_idx = None
        tel_adaylari = []
        for i, hucre in enumerate(satir):
            hucre = (hucre or "").strip()
            if not hucre:
                continue
            if _baslik_telefon_sutunu_mu(hucre):
                tel_adaylari.append((i, hucre.lower()))
            elif sinif_idx is None and _baslik_sinif_sutunu_mu(hucre):
                sinif_idx = i
            elif ogrenci_idx is None and _baslik_ogrenci_sutunu_mu(hucre):
                ogrenci_idx = i
            elif ad_idx is None and _baslik_veli_sutunu_mu(hucre):
                ad_idx = i
            elif ad_idx is None and _baslik_genel_ad_sutunu_mu(hucre):
                ad_idx = i

        if tel_adaylari:
            if tur == "veli":
                secilen = next(
                    (i for i, h in tel_adaylari if any(k in h for k in ("veli", "anne", "baba"))),
                    tel_adaylari[0][0],
                )
            elif tur == "ogrenci":
                secilen = next(
                    (i for i, h in tel_adaylari if any(k in h for k in ("öğrenci", "ogrenci"))),
                    tel_adaylari[0][0],
                )
            else:
                secilen = tel_adaylari[0][0]
            tel_idx = secilen

        skor = (
            (1 if ad_idx is not None else 0)
            + (1 if ogrenci_idx is not None else 0)
            + (1 if tel_idx is not None else 0)
            + (1 if sinif_idx is not None else 0)
        )
        if skor > en_iyi_skor:
            en_iyi_skor = skor
            en_iyi_baslik_idx = satir_idx
            en_iyi_harita = (ad_idx, ogrenci_idx, tel_idx, sinif_idx)

    if en_iyi_skor > 0 and en_iyi_baslik_idx is not None:
        ad_idx, ogrenci_idx, tel_idx, sinif_idx = en_iyi_harita
        veri_satirlari = satirlar[en_iyi_baslik_idx + 1 :]
    else:
        ad_idx, tel_idx, ogrenci_idx, sinif_idx = 0, 1, None, None
        veri_satirlari = satirlar

    def _al(satir: list[str], idx: int | None) -> str:
        if idx is None or idx >= len(satir):
            return ""
        return (satir[idx] or "").strip()

    sonuc: list[dict] = []
    for satir in veri_satirlari:
        raw_ad = _al(satir, ad_idx) if (ad_idx is not None and ad_idx != ogrenci_idx) else ""
        raw_ogr = _al(satir, ogrenci_idx) if ogrenci_idx is not None else ""
        telefon_ham = _al(satir, tel_idx) if tel_idx is not None else ""
        sinif = _al(satir, sinif_idx) if sinif_idx is not None else ""

        if tur == "veli":
            if not raw_ad and raw_ogr:
                ad_soyad = f"{raw_ogr} Velisi"
            else:
                ad_soyad = raw_ad
            ogrenci_adi = raw_ogr or None
        elif tur == "ogrenci":
            ad_soyad = raw_ad or raw_ogr
            ogrenci_adi = raw_ogr or None
        else:
            ad_soyad = raw_ad or raw_ogr
            ogrenci_adi = raw_ogr if (ogrenci_idx is not None and ad_idx is not None and ogrenci_idx != ad_idx) else None

        if not ad_soyad and not telefon_ham and not ogrenci_adi:
            continue

        telefon = normalize_phone(telefon_ham) if telefon_ham else ""
        sonuc.append(
            {
                "ad_soyad": ad_soyad,
                "telefon": telefon,
                "sinif": sinif or None,
                "ogrenci_adi": ogrenci_adi or None,
            }
        )
    return sonuc


def rehber_dosyasindan_oku(dosya_adi: str, icerik: bytes, tur: str | None = None) -> list[dict]:
    """.csv/.xlsx dosyasından `{"ad_soyad", "telefon", "sinif", "ogrenci_adi"}`
    sözlükleri çıkarır."""
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
    return _rehber_satirlarini_isle(satirlar, tur=tur)
