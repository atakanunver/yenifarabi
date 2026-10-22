"""Kulüp yoklaması (`/kulup-yoklama?tarih=`) — salt okunur. Veri kulup_yoklama
tablosunda (sınıf devamsızlığından AYRI; bkz. yoklayici.itilen_kaydi_yaz)."""

import json
from datetime import date

import auth
import db
import kulupler
import menu
import zil
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk
templates.env.globals["menu_agaci"] = menu.menu_agaci


@router.get("/kulup-yoklama", response_class=HTMLResponse)
async def kulup_yoklama_sayfa(request: Request, tarih: str | None = None):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
        try:
            tarih = date.fromisoformat(tarih).isoformat() if tarih else None
        except ValueError:
            tarih = None
        tarih = tarih or zil.simdi_istanbul().date().isoformat()
        adlar = {k["kod"]: k["ad"] for k in kulupler.yukle()}
        kayitlar = [
            {
                "kulup": adlar.get(r["sinif"], r["sinif"]), "ders_no": r["ders_no"],
                "yok": json.loads(r["yok_isimleri"] or "[]"),
                "izinli": json.loads(r["izinli_isimleri"] or "[]"),
                "saat": r["kaydedilme_saati"], "tahta": r["kaynak_tahta"],
            }
            for r in conn.execute(
                "SELECT * FROM kulup_yoklama WHERE tarih = ? ORDER BY sinif, ders_no", (tarih,))
        ]
    finally:
        conn.close()
    return templates.TemplateResponse(request, "kulup_yoklama.html", {"tarih": tarih, "kayitlar": kayitlar})
