"""kazanimtest/hedef.py — Bugün hangi (sınıf, ders) var + o haftanın yıllık plan kazanımı.

Saf fonksiyonlar `server/kazanim.py` (`_ders_adi`, `_hafta`, kazanım metni bölme) ve
`tahtayoklama/data/*.json`'dan kopyalandı: o modül `auth`/fastapi içe aktarır.

Ders adı eşlemesi: program/kazanimlar.json'daki ham ad ("hedef fizik", "türk dili ve
edebiyatı") `soruhavuzu.dersler.ders_anahtari` ile TEK anahtara ("fizik", "edebiyat")
çevrilir; beyaz liste, UNIQUE ve soru havuzu hep bu anahtarla çalışır.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from soruhavuzu.dersler import ders_anahtari

log = logging.getLogger("kazanimtest.hedef")

VERI_DIR = Path(__file__).resolve().parent.parent / "tahtayoklama" / "data"
_GUNLER = {1: "pazartesi", 2: "sali", 3: "carsamba", 4: "persembe", 5: "cuma"}


@dataclass
class Hedef:
    sinif: str  # "9-A"
    duzey: int  # 9
    ders: str  # ders anahtarı: "biyoloji"
    ders_adi: str  # programdaki ham ad
    hafta: int
    kazanimlar: list[str]
    tarih: date


def yukle(ad: str, dizin: Path | None = None) -> dict | None:
    try:
        veri = json.loads(((dizin or VERI_DIR) / ad).read_text(encoding="utf-8"))
        return veri if isinstance(veri, dict) else None
    except (OSError, ValueError):
        log.warning("veri okunamadı: %s", ad)
        return None


def hafta_no(kz: dict, gun: date) -> int | None:
    try:
        for no, pazartesi in kz.get("haftalar", {}).items():
            bas = date.fromisoformat(pazartesi)
            if bas <= gun < bas + timedelta(days=7):
                return int(no)
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def kazanim_satirlari(kz: dict, duzey: int, ders_adi: str, hafta: int) -> list[str]:
    try:
        metin = kz.get("kazanimlar", {}).get(str(duzey), {}).get(ders_adi, {}).get(str(hafta))
    except AttributeError:
        return []
    if not isinstance(metin, str):
        return []
    satirlar = [" ".join(s.split()) for s in metin.split("\n")]
    return [s for s in satirlar if s]


def hedefler(
    gun: date,
    ayar: dict,
    sinif: str | None = None,
    ders: str | None = None,
    program: dict | None = None,
    kz: dict | None = None,
) -> list[Hedef]:
    """Günün hedefleri; (sinif, ders anahtarı) başına tek kayıt, beyaz liste dışı atlanır."""
    program = program if program is not None else yukle("ders_programi.json")
    kz = kz if kz is not None else yukle("kazanimlar.json")
    gun_adi = _GUNLER.get(gun.isoweekday())
    if not program or not kz or not gun_adi:
        return []
    hafta = hafta_no(kz, gun)
    if hafta is None:
        return []
    izinli = {d for d in ayar.get("dersler", [])}
    sonuc: list[Hedef] = []
    for sn, gunler in sorted(program.get("siniflar", {}).items()):
        if sinif and sn != sinif:
            continue
        try:
            duzey = int(sn.split("-")[0])
        except ValueError:
            continue
        gders = gunler.get(gun_adi) if isinstance(gunler, dict) else None
        if not isinstance(gders, dict):
            continue
        gorulen: set[str] = set()
        for _no, ad in sorted(gders.items(), key=lambda x: int(x[0])):
            if not isinstance(ad, str):
                continue
            ad = ad.strip()
            anahtar = ders_anahtari(ad)
            if not anahtar or anahtar in gorulen or anahtar not in izinli:
                continue
            if ders and anahtar != ders:
                continue
            satirlar = kazanim_satirlari(kz, duzey, ad, hafta)
            if not satirlar:
                continue
            gorulen.add(anahtar)
            sonuc.append(Hedef(sn, duzey, anahtar, ad, hafta, satirlar, gun))
    return sonuc
