"""Hızlı Etkinlik Atama rotaları (öğretmen/yönetici). Yetkisiz = 404, yalnızca kendi sınıf+dersine atama."""

import sqlite3

import analitik
import etkinlik
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from kaynaklar import KaynakHatasi, kazanim
from metin import sinif_seviyesi, tr_kucuk

router = APIRouter(prefix="/ogretmen/hizli")
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)


def _gorevler(conn: sqlite3.Connection, k: sqlite3.Row) -> list[tuple[str, str]]:
    if k["rol"] == "yonetici":
        return [(r[0], "") for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")]
    return yetki.ogretmen_gorevleri(conn, k["id"])


def _havuz_dersleri(sinif: str) -> tuple[list[str], bool]:
    try:
        return kazanim.havuz_dersleri(sinif_seviyesi(sinif)), False
    except KaynakHatasi:
        return [], True


@router.get("")
def form(
    request: Request, sinif: str = "", ders: str = "", k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    gorevler = _gorevler(conn, k)
    if not gorevler:
        return render(request, "ogretmen/hizli.html", gorevler=[], sinif="", ders="", havuz_dersleri=[], havuz_hata=False,
                      secili_havuz="", adetler=etkinlik.ADETLER, sureler=etkinlik.SURELER)
    if not sinif:
        sinif, ders = gorevler[0]
    if (sinif, ders) not in gorevler:
        raise HTTPException(404)
    havuz, hata = _havuz_dersleri(sinif)
    secili = tr_kucuk(ders) if tr_kucuk(ders) in havuz else ""
    return render(request, "ogretmen/hizli.html", gorevler=gorevler, sinif=sinif, ders=ders, havuz_dersleri=havuz,
                  havuz_hata=hata, secili_havuz=secili, adetler=etkinlik.ADETLER, sureler=etkinlik.SURELER)


@router.post("")
async def ata(request: Request, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)):
    f = await request.form()
    sinif = str(f.get("sinif", "")).strip()
    havuz_ders = str(f.get("havuz_ders", "")).strip()
    ders = str(f.get("ders", "")).strip()
    if k["rol"] == "yonetici":
        ders = ders or havuz_ders  # yöneticinin görevi yok: havuz dersi adı kullanılır
        yetkili = bool(sinif) and conn.execute("SELECT 1 FROM ogrenci WHERE sinif = ?", (sinif,)).fetchone() is not None
    else:
        yetkili = bool(sinif and ders) and yetki.sinif_ders_yetkili(conn, k, sinif, ders)
    if not yetkili:
        raise HTTPException(404)
    try:
        adet = int(str(f.get("adet", "")))
    except ValueError:
        raise HTTPException(400, "Geçersiz soru sayısı.") from None
    try:
        odev_id = etkinlik.hizli_ata(conn, k["id"], sinif, ders, havuz_ders, adet, str(f.get("sure", "")), str(f.get("not", "")))
    except (etkinlik.EtkinlikHatasi, KaynakHatasi) as e:
        raise HTTPException(400, str(e)) from e
    analitik.istekten(request, "ogretmen_hizli_etkinlik", str(odev_id))
    return RedirectResponse(f"/ogretmen/odev/{odev_id}", status_code=303)
