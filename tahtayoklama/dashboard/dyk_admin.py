"""DYK kursu öğrenci listeleri paneli (/admin/dyk) — config/dyk.json, veri katmanı dyk.py.

Kulüp panelinin (admin.py /admin/kulupler) eşi: yalnız öğretmen ve öğrenci listesi düzenlenir;
kod ve program değişmez. Tahtalara istemci /yapilandirma ile ≤10 dk'da ulaşır (SSH senkronu yok).
"""

import auth
import db
import dyk
import menu
import zil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/admin/dyk")
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

_GUNLER = {"pazartesi": "Pazartesi", "sali": "Salı", "carsamba": "Çarşamba",
           "persembe": "Perşembe", "cuma": "Cuma", "cumartesi": "Cumartesi", "pazar": "Pazar"}
_SIRA = list(_GUNLER)


def _oturum_sarti(request: Request) -> None:
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()


def _gruplar() -> list[dict]:
    """Sınıf grubu başına {grup, ad, derslik, dersler, program}; program salt-okunur özet."""
    veri = dyk.yukle()
    sonuc = []
    for grup, sinif in sorted(veri["siniflar"].items()):
        if not isinstance(sinif, dict):
            continue
        dersler = [d for d in sinif.get("dersler") or [] if isinstance(d, dict) and d.get("kod")]
        adlar = {d["kod"]: d.get("ad", d["kod"]) for d in dersler}
        satirlar = [o for o in veri["program"].get(grup, []) if isinstance(o, dict)]
        satirlar.sort(key=lambda o: (_SIRA.index(o.get("gun")) if o.get("gun") in _SIRA else 99, o.get("bas", "")))
        program = [{"gun": _GUNLER.get(o.get("gun"), o.get("gun", "")), "bas": o.get("bas", ""),
                    "bit": o.get("bit", ""), "ders": adlar.get(o.get("kod"), o.get("kod", ""))}
                   for o in satirlar]
        sonuc.append({"grup": grup, "ad": sinif.get("ad", f"{grup}. Sınıf DYK"),
                      "derslik": sinif.get("derslik", ""), "dersler": dersler, "program": program})
    return sonuc


@router.get("", response_class=HTMLResponse)
async def dyk_listesi(request: Request):
    _oturum_sarti(request)
    return templates.TemplateResponse(request, "admin_dyk.html", {"gruplar": _gruplar()})


@router.get("/{kod}", response_class=HTMLResponse)
async def dyk_uyeleri(request: Request, kod: str):
    _oturum_sarti(request)
    ders = dyk.bul(kod)
    if ders is None:
        raise HTTPException(404, "Ders bulunamadı.")
    return templates.TemplateResponse(request, "admin_dyk_uyeler.html", {"ders": ders})


@router.post("/{kod}")
async def dyk_uyelerini_kaydet(request: Request, kod: str):
    _oturum_sarti(request)
    form = await request.form()
    try:
        uyeler = dyk.uyeleri_ayristir(form.getlist("no"), form.getlist("ad_soyad"))
        dyk.guncelle(kod, form.get("ogretmen", ""), uyeler)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError:
        raise HTTPException(404, "Ders bulunamadı.")
    return RedirectResponse(f"/admin/dyk/{kod}?kaydedildi=1", status_code=303)
