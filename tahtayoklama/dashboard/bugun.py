"""Bugün ekranı (`/bugun`, 2026-10-23): müdür için tek sayfalık günlük özet.

Yalnızca panonun kendi verisini salt-okunur toplar: bugünün yoklama önbelleği
(`yoklama_onbellek`), tahta nabzı/sağlığı (`tahta_saglik.liste`) ve veli mesajı sayacı
(`veli_mesajlari.sayac_getir`, ulaşılamazsa None). Öğrenci adı gösterilmez; isimli döküm
`/admin/rapor`'dadır. SMS taslağı ve EBYS bu sürümde YOK (başka servislerin verisi).
"""

import json
import time
import urllib.error
import urllib.request

import auth
import db
import menu
import tahta_saglik
import veli_mesajlari
import zil
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

_SORUNLU = {"hata": "Hata", "uyari": "Uyarı", "cevrimdisi": "Çevrimdışı"}
_SMS_URL = "http://127.0.0.1:8020/api/panel/otomasyon-durum"
_SMS_ONBELLEK_SN = 30
_sms_onbellek: dict = {}
_SEBEP = {
    "alinmadi": "yoklama alınmamış", "tahta_ulasilamaz": "tahtaya ulaşılamadı", "veri_yok": "yoklama kaydı yok",
    "henuz_baslamadi": "ders başlamamış", "tahta_atanmamis": "tahta atanmamış", "ders_yok_o_gun": "o gün ders yok",
}


def _sinif_sirasi(ad: str) -> tuple:
    sayi = "".join(c for c in ad if c.isdigit())
    return (int(sayi) if sayi else 999, ad)


def yoklama_ozeti(conn, tarih: str) -> dict:
    """Bugünün sınıf bazlı yoklama durumu: kaç ders alındı, kaç öğrenci en az bir derste yok."""
    sinif_ders: dict[str, list[str]] = {}
    sinif_yok: dict[str, set[str]] = {}
    for r in conn.execute(
        "SELECT sinif, durum, yok_isimleri FROM yoklama_onbellek "
        "WHERE tarih = ? AND durum != 'ders_yok_o_gun'",
        (tarih,),
    ):
        sinif_ders.setdefault(r["sinif"], []).append(r["durum"])
        try:
            isimler = json.loads(r["yok_isimleri"] or "[]")
        except ValueError:
            isimler = []
        sinif_yok.setdefault(r["sinif"], set()).update(isimler)

    siniflar = []
    for ad in sorted(sinif_ders, key=_sinif_sirasi):
        durumlar = sinif_ders[ad]
        siniflar.append({
            "ad": ad,
            "alindi": durumlar.count("alindi"),
            "alinmadi": durumlar.count("alinmadi"),
            "ulasilamaz": durumlar.count("tahta_ulasilamaz"),
            "yok": len(sinif_yok[ad]),
        })
    return {
        "siniflar": siniflar,
        "toplam_yok": sum(s["yok"] for s in siniflar),
        "alinmayan_ders": sum(s["alinmadi"] for s in siniflar),
        "ulasilamayan_ders": sum(s["ulasilamaz"] for s in siniflar),
    }


def sms_ozeti(simdi: float | None = None) -> dict | None:
    """Bugünkü devamsızlık SMS'i çalışmalarının özeti (smssistemi panel API, 30 sn önbellekli). Ulaşılamazsa None."""
    simdi = time.monotonic() if simdi is None else simdi
    if "t" in _sms_onbellek and simdi - _sms_onbellek["t"] < _SMS_ONBELLEK_SN:
        return _sms_onbellek["v"]
    veri = None
    anahtar = veli_mesajlari._anahtar()
    if anahtar:
        try:
            istek = urllib.request.Request(_SMS_URL, headers={"X-Sms-Panel-Key": anahtar})
            with urllib.request.urlopen(istek, timeout=veli_mesajlari.ZAMAN_ASIMI_SN) as y:
                veri = json.loads(y.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError):
            veri = None
    if isinstance(veri, dict):
        for servis, ad in (("ilk_ders", "Sabah 09:00 SMS'i"), ("ogle", "Öğleden sonra 14:00 SMS'i")):
            s = veri.get(servis)
            if isinstance(s, dict):
                s["ad"] = ad
                s["sebepler"] = ", ".join(
                    f"{n} sınıf {_SEBEP.get(k, k)}" for k, n in sorted((s.get("haric_sebepleri") or {}).items())
                )
    else:
        veri = None
    _sms_onbellek.update(t=simdi, v=veri)
    return veri


def tahta_ozeti(conn) -> dict:
    """Tahta sağlığı sayıları + sorunlu olanların listesi (iyi olanlar listelenmez)."""
    tahtalar = tahta_saglik.liste(conn)
    sorunlu = [
        {"ad": t["tahta_ad"], "durum": _SORUNLU[t["durum"]], "seviye": t["durum"]}
        for t in tahtalar
        if t["durum"] in _SORUNLU
    ]
    return {"toplam": len(tahtalar), "sorunlu": sorunlu}


@router.get("/bugun", response_class=HTMLResponse)
async def bugun_sayfa(request: Request):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
        tarih = zil.simdi_istanbul().date().isoformat()
        yoklama = yoklama_ozeti(conn, tarih)
        tahta = tahta_ozeti(conn)
    finally:
        conn.close()
    return templates.TemplateResponse(
        request,
        "bugun.html",
        {"tarih": tarih, "yoklama": yoklama, "tahta": tahta, "veli": veli_mesajlari.sayac_getir(), "sms": sms_ozeti()},
    )
