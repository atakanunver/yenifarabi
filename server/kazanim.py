"""server/kazanim.py — Bu haftanın yıllık plan kazanımı (tahta ders çerçevesi için).

`GET /api/egitim/kazanim?derslik=12-A&ders_no=5[&tarih=YYYY-MM-DD]`

Ders adı derslik + gün + ders_no'dan SUNUCUDA çözülür (tahtayoklama'daki
ders_programi.json "hedef fizik" gibi şube-özel adları içerir; tahtanın kendi
kopyası içermez). Mantık `tahtayoklama/yoklama.py::_ders_adi_ham/_kazanim` ile
aynıdır (o dosya içe aktarılmaz). Hiçbir durumda istisna fırlatmaz: eksik/bozuk
dosya, tatil haftası, bilinmeyen derslik → {"durum": "yok"}.
"""

import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

import auth

log = logging.getLogger("farabi.kazanim")

router = APIRouter(dependencies=[Depends(auth.dogrula_tahta)])

VERI_DIR = Path(__file__).resolve().parent.parent / "tahtayoklama" / "data"
_TZ = ZoneInfo("Europe/Istanbul")
_GUNLER = {1: "pazartesi", 2: "sali", 3: "carsamba", 4: "persembe", 5: "cuma"}

# dosya adı -> (mtime_ns, veri); mtime değişince yeniden okunur.
_ONBELLEK: dict[str, tuple[int, dict]] = {}


def _yukle(ad: str) -> dict | None:
    yol = VERI_DIR / ad
    try:
        mt = yol.stat().st_mtime_ns
        eski = _ONBELLEK.get(str(yol))
        if eski and eski[0] == mt:
            return eski[1]
        veri = json.loads(yol.read_text(encoding="utf-8"))
        if not isinstance(veri, dict):
            return None
        _ONBELLEK[str(yol)] = (mt, veri)
        return veri
    except (OSError, ValueError):
        log.warning("kazanım verisi okunamadı: %s", ad)
        return None


def _ders_adi(program: dict, derslik: str, gun: date, ders_no: int) -> str:
    try:
        g = program.get("siniflar", {}).get(derslik, {}).get(_GUNLER.get(gun.isoweekday()))
        if not isinstance(g, dict):
            return ""
        ad = g.get(str(ders_no))
        return ad.strip() if isinstance(ad, str) else ""
    except AttributeError:
        return ""


def _hafta(kz: dict, gun: date) -> int | None:
    try:
        for no, pazartesi in kz.get("haftalar", {}).items():
            bas = date.fromisoformat(pazartesi)
            if bas <= gun < bas + timedelta(days=7):
                return int(no)
    except (AttributeError, TypeError, ValueError):
        pass
    return None


def kazanim_bul(derslik: str, ders_no: int, gun: date) -> dict:
    program = _yukle("ders_programi.json")
    kz = _yukle("kazanimlar.json")
    if program is None or kz is None:
        return {"durum": "yok"}
    ders = _ders_adi(program, derslik, gun, ders_no)
    hafta = _hafta(kz, gun)
    yok = {"durum": "yok", "ders": ders or None, "hafta": hafta}
    if not ders or hafta is None:
        return yok
    try:
        duzey = derslik.split("-")[0]
        metin = kz.get("kazanimlar", {}).get(duzey, {}).get(ders, {}).get(str(hafta))
    except AttributeError:
        return yok
    if not isinstance(metin, str):
        return yok
    satirlar = [" ".join(s.split()) for s in metin.split("\n")]
    satirlar = [s for s in satirlar if s]
    if not satirlar:
        return yok
    return {"durum": "tamam", "ders": ders, "hafta": hafta, "kazanimlar": satirlar}


@router.get("/api/egitim/kazanim")
def kazanim(
    derslik: str = Query(..., pattern=r"^[A-Za-z0-9_-]{1,32}$"),
    ders_no: int = Query(..., ge=1, le=12),
    tarih: date | None = Query(None),
):
    try:
        gun = tarih or datetime.now(_TZ).date()
        return kazanim_bul(derslik, ders_no, gun)
    except Exception:  # asla ders akışını bozma
        log.exception("kazanım araması beklenmedik hata")
        return {"durum": "yok"}
