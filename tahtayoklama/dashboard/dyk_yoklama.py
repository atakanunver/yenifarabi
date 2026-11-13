"""DYK kursu yoklaması (`/dyk-yoklama?tarih=`) — salt okunur. Veri dyk_yoklama
tablosunda (sınıf devamsızlığından AYRI; bkz. yoklayici.itilen_kaydi_yaz)."""

import json
from datetime import date

import auth
import db
import dyk
import menu
import zil
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk
templates.env.globals["menu_agaci"] = menu.menu_agaci


@router.get("/dyk-yoklama", response_class=HTMLResponse)
async def dyk_yoklama_sayfa(request: Request, tarih: str | None = None):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
        try:
            tarih = date.fromisoformat(tarih).isoformat() if tarih else None
        except ValueError:
            tarih = None
        tarih = tarih or zil.simdi_istanbul().date().isoformat()
        dersler = {d["kod"]: d for d in dyk.dersler()}

        def _ad(kod):
            d = dersler.get(kod)
            return f"{d['sinif_grubu']}. sınıf {d['ad']}" if d else kod

        kayitlar = [
            {
                "ders": _ad(r["sinif"]), "ogretmen": (dersler.get(r["sinif"]) or {}).get("ogretmen") or "",
                "ders_no": r["ders_no"],
                "yok": json.loads(r["yok_isimleri"] or "[]"),
                "izinli": json.loads(r["izinli_isimleri"] or "[]"),
                "saat": r["kaydedilme_saati"], "tahta": r["kaynak_tahta"],
            }
            for r in conn.execute(
                "SELECT * FROM dyk_yoklama WHERE tarih = ? ORDER BY sinif, ders_no", (tarih,))
        ]
    finally:
        conn.close()
    return templates.TemplateResponse(request, "dyk_yoklama.html", {"tarih": tarih, "kayitlar": kayitlar})
