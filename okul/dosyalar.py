"""Yüklenen dosyalar (vesikalık, yıllık plan): içerik doğrulama + güvenli saklama.

- Dosyalar static/ altında DEĞİL, AYAR.dosya_dizini altında rastgele adlarla tutulur;
  yalnızca yetki kontrolü yapan rotalar üzerinden sunulur.
- Tür uzantıya göre değil, dosyanın ilk baytlarına (imza) göre belirlenir; uzantı ile imza uyuşmazsa reddedilir.
"""

import io
import secrets
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ayarlar import AYAR

FOTO_AZAMI = 5 * 1024 * 1024
PLAN_AZAMI = 10 * 1024 * 1024

MIME = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "doc": "application/msword",
    "xls": "application/vnd.ms-excel",
}


class DosyaHatasi(ValueError):
    pass


@dataclass(frozen=True)
class Dosya:
    depo_adi: str
    tur: str
    boyut: int


def _uzanti(ad: str) -> str:
    ad = (ad or "").lower().rsplit(".", 1)
    return ad[1] if len(ad) == 2 else ""


def foto_turu(veri: bytes) -> str | None:
    if veri[:3] == b"\xff\xd8\xff":
        return "jpg"
    if veri[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if veri[:4] == b"RIFF" and veri[8:12] == b"WEBP":
        return "webp"
    return None


def plan_turu(veri: bytes, dosya_adi: str) -> str | None:
    uzanti = _uzanti(dosya_adi)
    if veri[:5] == b"%PDF-":
        return "pdf"
    if veri[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":  # eski Office (OLE)
        return uzanti if uzanti in ("doc", "xls") else None
    if veri[:4] == b"PK\x03\x04":  # yeni Office (zip); içeriğe bakarak Word mü Excel mi
        try:
            adlar = zipfile.ZipFile(io.BytesIO(veri)).namelist()
        except zipfile.BadZipFile:
            return None
        if any(a.startswith("word/") for a in adlar):
            return "docx"
        if any(a.startswith("xl/") for a in adlar):
            return "xlsx"
    return None


def _kaydet(klasor: str, veri: bytes, tur: str) -> Dosya:
    hedef = AYAR.dosya_dizini / klasor
    hedef.mkdir(parents=True, exist_ok=True)
    ad = f"{secrets.token_hex(16)}.{tur}"
    gecici = hedef / f".{ad}.yukleniyor"
    gecici.write_bytes(veri)
    gecici.replace(hedef / ad)  # yarım dosya hiçbir zaman gerçek adla görünmez
    return Dosya(ad, tur, len(veri))


def foto_kaydet(veri: bytes) -> Dosya:
    if not veri:
        raise DosyaHatasi("Bir fotoğraf seçin.")
    if len(veri) > FOTO_AZAMI:
        raise DosyaHatasi("Fotoğraf en fazla 5 MB olabilir.")
    tur = foto_turu(veri)
    if tur is None:
        raise DosyaHatasi("Yalnızca JPG, PNG ya da WEBP fotoğraf yükleyebilirsiniz.")
    return _kaydet("foto", veri, tur)


def plan_kaydet(veri: bytes, dosya_adi: str) -> Dosya:
    if not veri:
        raise DosyaHatasi("Bir dosya seçin.")
    if len(veri) > PLAN_AZAMI:
        raise DosyaHatasi("Yıllık plan dosyası en fazla 10 MB olabilir.")
    tur = plan_turu(veri, dosya_adi)
    if tur is None or tur != _uzanti(dosya_adi):  # uzantı ile gerçek içerik aynı olmalı
        raise DosyaHatasi(
            "Yalnızca Excel (xlsx, xls), Word (docx, doc) ya da PDF dosyası yükleyebilirsiniz."
        )
    return _kaydet("plan", veri, tur)


def yol(klasor: str, depo_adi: str) -> Path:
    # depo_adi her zaman bizim ürettiğimiz ad; yine de yol dışına çıkmayı engelle
    if not depo_adi or "/" in depo_adi or "\\" in depo_adi or depo_adi.startswith("."):
        raise DosyaHatasi("Geçersiz dosya.")
    return AYAR.dosya_dizini / klasor / depo_adi


def sil(klasor: str, depo_adi: str | None) -> None:
    if depo_adi:
        try:
            yol(klasor, depo_adi).unlink(missing_ok=True)
        except DosyaHatasi:
            pass
