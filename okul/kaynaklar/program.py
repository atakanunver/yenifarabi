"""mudur/ders_programi.json — salt-okunur, dosya değişince yeniden okunur."""

import json
from datetime import date

from ayarlar import AYAR
from metin import normalize_isim

from kaynaklar import KaynakHatasi

GUNLER = ["pazartesi", "sali", "carsamba", "persembe", "cuma", "cumartesi", "pazar"]
OKUL_GUNLERI = GUNLER[:5]
GUN_ADLARI = {
    "pazartesi": "Pazartesi",
    "sali": "Salı",
    "carsamba": "Çarşamba",
    "persembe": "Perşembe",
    "cuma": "Cuma",
    "cumartesi": "Cumartesi",
    "pazar": "Pazar",
}

_onbellek: dict = {"yol": None, "mtime": None, "veri": {}}


def _siniflar() -> dict:
    yol = AYAR.program_yolu
    try:
        mtime = yol.stat().st_mtime
        if _onbellek["yol"] != yol or _onbellek["mtime"] != mtime:
            veri = json.loads(yol.read_text(encoding="utf-8"))
            _onbellek.update(yol=yol, mtime=mtime, veri=veri.get("siniflar", {}))
    except (OSError, ValueError) as e:
        raise KaynakHatasi(f"ders programı okunamadı: {e}") from e
    return _onbellek["veri"]


def gun_dersleri(sinif: str, gun: str) -> list[tuple[int, str]]:
    gunluk = _siniflar().get(sinif, {}).get(gun, {})
    return sorted((int(no), ders) for no, ders in gunluk.items())


def bugun(sinif: str, tarih: date) -> list[tuple[int, str]]:
    return gun_dersleri(sinif, GUNLER[tarih.weekday()])


def haftalik(sinif: str) -> list[tuple[str, list[tuple[int, str]]]]:
    return [(g, gun_dersleri(sinif, g)) for g in OKUL_GUNLERI]


def ogretmen_haftalik(
    gorevler: list[tuple[str, str]],
) -> list[tuple[str, list[tuple[int, str, str]]]]:
    sonuc = []
    for g in OKUL_GUNLERI:
        dersler = []
        for sinif, ders in gorevler:
            hedef = normalize_isim(ders)
            for no, d in gun_dersleri(sinif, g):
                if normalize_isim(d) == hedef:
                    dersler.append((no, sinif, d))
        sonuc.append((g, sorted(dersler)))
    return sonuc
