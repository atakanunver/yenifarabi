"""Velilerden gelen SMS'ler (`/veli-mesajlari`) — veri smssistemi'nde (port 8020) durur.

Dashboard o DB'yi PAYLAŞMAZ: smssistemi/panel_api.py'yi HTTP ile çağırır
(başlık X-Sms-Panel-Key, anahtar config/sms_panel.json {"anahtar": ...}, gitignore'lu).
Anahtar yok / servis kapalı / zaman aşımı → istemci None döner, sayfa çökmez
("Mesaj servisine ulaşılamıyor"), menü sayacı sessizce gizlenir (Farabi dersi bozmaz).
Telefonlar smssistemi'nde zaten maskelenir; mesaj metni log'a YAZILMAZ (bu modül hiç log atmaz).
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import auth
import db
import menu
import zil

AYAR_YOLU = Path(__file__).resolve().parent / "config" / "sms_panel.json"
TABAN_URL = "http://127.0.0.1:8020/api/panel/veli-mesajlari"
ZAMAN_ASIMI_SN = 3
SAYAC_ONBELLEK_SN = 30
LISTE_LIMITI = 200

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

_sayac_onbellek: dict = {}
_TUR_ETIKET = {"ogrenci": "Öğrenci", "veli": "Veli", "personel": "Personel"}


def _anahtar() -> str:
    try:
        return str(json.loads(AYAR_YOLU.read_text(encoding="utf-8")).get("anahtar") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def _istek(yontem: str, yol: str = "", sorgu: str = "", govde: dict | None = None):
    """smssistemi panel API'sine tek istek. Başarıda çözülmüş JSON, her hatada None."""
    anahtar = _anahtar()
    if not anahtar:
        return None
    basliklar = {"X-Sms-Panel-Key": anahtar}
    veri = None
    if govde is not None:
        veri = json.dumps(govde).encode("utf-8")
        basliklar["Content-Type"] = "application/json"
    istek = urllib.request.Request(TABAN_URL + yol + sorgu, method=yontem, headers=basliklar, data=veri)
    try:
        with urllib.request.urlopen(istek, timeout=ZAMAN_ASIMI_SN) as yanit:
            return json.loads(yanit.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):  # HTTPError URLError alt sınıfı
        return None


def mesajlari_getir(sadece_okunmamis: bool = False, limit: int = LISTE_LIMITI,
                    spam: bool = False) -> list[dict] | None:
    veri = _istek("GET", "", f"?okunmamis={1 if sadece_okunmamis else 0}&limit={int(limit)}"
                  f"&spam={1 if spam else 0}")
    if not isinstance(veri, dict) or not isinstance(veri.get("mesajlar"), list):
        return None
    return [m for m in veri["mesajlar"] if isinstance(m, dict)]


def sayac_getir(simdi: float | None = None) -> dict | None:
    """{'okunmamis': n, 'cikis_talebi_okunmamis': c} ya da None; ≤30 sn önbellekli (hata da)."""
    simdi = time.monotonic() if simdi is None else simdi
    if "t" in _sayac_onbellek and simdi - _sayac_onbellek["t"] < SAYAC_ONBELLEK_SN:
        return _sayac_onbellek["v"]
    veri = _istek("GET", "/sayac")
    if not (isinstance(veri, dict) and isinstance(veri.get("okunmamis"), int)):
        veri = None
    _sayac_onbellek.update(t=simdi, v=veri)
    return veri


def onbellegi_sifirla() -> None:
    _sayac_onbellek.clear()


def okundu_isaretle(mesaj_id: int) -> bool:
    ok = isinstance(_istek("POST", f"/{int(mesaj_id)}/okundu"), dict)
    onbellegi_sifirla()
    return ok


def mesaj_sil(mesaj_id: int) -> bool:
    ok = isinstance(_istek("DELETE", f"/{int(mesaj_id)}"), dict)
    onbellegi_sifirla()
    return ok


def engelle(mesaj_id: int, neden: str = "") -> bool:
    govde = {"neden": neden.strip()[:80]} if neden and neden.strip() else {}
    ok = isinstance(_istek("POST", f"/{int(mesaj_id)}/engelle", govde=govde), dict)
    onbellegi_sifirla()
    return ok


def engeli_kaldir(mesaj_id: int) -> bool:
    ok = isinstance(_istek("POST", f"/{int(mesaj_id)}/engeli-kaldir", govde={}), dict)
    onbellegi_sifirla()
    return ok


def gonderen_etiketi(m: dict) -> tuple[str, str]:
    """(ad, alt satır): kayıtlı kişi → ad + 'Tür · sınıf'; yoksa 'Bilinmeyen numara …son4'."""
    ad = str(m.get("kisi_ad") or "").strip()
    if ad:
        parcalar = [_TUR_ETIKET.get(str(m.get("kisi_tur") or ""), str(m.get("kisi_tur") or "")),
                    str(m.get("sinif") or "")]
        return ad, " · ".join(p for p in parcalar if p)
    rakamlar = re.sub(r"\D", "", str(m.get("telefon") or ""))
    return (f"Bilinmeyen numara …{rakamlar[-4:]}" if rakamlar else "Bilinmeyen numara"), ""


def goruntule(mesajlar: list[dict]) -> list[dict]:
    """Şablon satırları: çıkış talepleri üstte (sıra kendi içinde API sırası = yeni→eski)."""
    satirlar = []
    for m in mesajlar:
        ad, alt = gonderen_etiketi(m)
        satirlar.append({
            "id": m.get("id"),
            "ad": ad,
            "alt": alt,
            "metin": str(m.get("metin") or ""),
            "zaman": str(m.get("zaman") or ""),
            "cikis": bool(m.get("cikis_talebi")),
            "okundu": bool(m.get("okundu")),
            "spam_neden": str(m.get("spam_neden") or ""),
        })
    satirlar.sort(key=lambda s: not s["cikis"])  # kararlı sıralama
    return satirlar


def _oturum_gerekli(request: Request) -> None:
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()


@router.get("/veli-mesajlari", response_class=HTMLResponse)
async def sayfa(request: Request, okunmamis: int = 0, engellenen: int = 0):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    ham = mesajlari_getir(bool(okunmamis) and not engellenen, spam=bool(engellenen))
    return templates.TemplateResponse(request, "veli_mesajlari.html", {
        "ulasilamiyor": ham is None,
        "mesajlar": goruntule(ham or []),
        "sadece_okunmamis": bool(okunmamis) and not engellenen,
        "engellenen": bool(engellenen),
    })


@router.get("/api/veli-mesajlari/sayac")
async def api_sayac(request: Request):
    _oturum_gerekli(request)
    veri = sayac_getir()
    if veri is None:
        return JSONResponse({"okunmamis": None, "cikis_talebi_okunmamis": None})
    return JSONResponse({"okunmamis": veri["okunmamis"],
                         "cikis_talebi_okunmamis": veri.get("cikis_talebi_okunmamis")})


@router.post("/api/veli-mesajlari/{mesaj_id}/okundu")
async def api_okundu(request: Request, mesaj_id: int):
    _oturum_gerekli(request)
    if not okundu_isaretle(mesaj_id):
        raise HTTPException(502, "Mesaj servisine ulaşılamadı ya da mesaj bulunamadı.")
    return JSONResponse({"ok": True})


@router.post("/api/veli-mesajlari/{mesaj_id}/sil")
async def api_sil(request: Request, mesaj_id: int):
    """Tarayıcıdan POST (SameSite=lax çerez çapraz-site POST'ta gitmez); smssistemi'ne DELETE gider."""
    _oturum_gerekli(request)
    if not mesaj_sil(mesaj_id):
        raise HTTPException(502, "Mesaj servisine ulaşılamadı ya da mesaj bulunamadı.")
    return JSONResponse({"ok": True})


class _EngelGovde(BaseModel):
    neden: str | None = None


@router.post("/api/veli-mesajlari/{mesaj_id}/engelle")
async def api_engelle(request: Request, mesaj_id: int, govde: _EngelGovde | None = None):
    _oturum_gerekli(request)
    if not engelle(mesaj_id, (govde.neden if govde else "") or ""):
        raise HTTPException(502, "Mesaj servisine ulaşılamadı, mesaj bulunamadı ya da numara engellenemez.")
    return JSONResponse({"ok": True})


@router.post("/api/veli-mesajlari/{mesaj_id}/engeli-kaldir")
async def api_engeli_kaldir(request: Request, mesaj_id: int):
    _oturum_gerekli(request)
    if not engeli_kaldir(mesaj_id):
        raise HTTPException(502, "Mesaj servisine ulaşılamadı ya da mesaj bulunamadı.")
    return JSONResponse({"ok": True})
