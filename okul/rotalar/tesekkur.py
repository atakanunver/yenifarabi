"""Teşekkür Kartı rotaları: öğretmen gönderir (/ogretmen/tesekkur), öğrenci ve veli görür (/tesekkurler)."""

import sqlite3

import push
import tesekkur
import yetki
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter()
OGRETMEN = rol("ogretmen")
OGRETMEN_POST = rol("ogretmen", post=True)
ALICI = rol("ogrenci", "veli")


def _form(request: Request, conn, k, sinif: str | None, hata: str = "", durum: int = 200):
    siniflar = yetki.ogretmen_siniflari(conn, k["id"])
    if sinif is None:
        sinif = siniflar[0] if siniflar else ""
    elif sinif not in siniflar:
        raise HTTPException(404)
    ogrenciler = conn.execute("SELECT id, okul_no, ad_soyad FROM ogrenci WHERE sinif = ? ORDER BY okul_no", (sinif,)).fetchall() if sinif else []
    gonderilen = tesekkur.bugun_gonderilen(conn, k["id"])
    return render(
        request, "ogretmen/tesekkur.html", status_code=durum, siniflar=siniflar, sinif=sinif, ogrenciler=ogrenciler,
        sablonlar=tesekkur.SABLONLAR, gonderilen=gonderilen, bugun_alan={g["ogrenci_id"] for g in gonderilen},
        hata=hata, kart_xp=tesekkur.KART_XP,
    )


@router.get("/ogretmen/tesekkur")
def form(request: Request, sinif: str | None = None, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)):
    return _form(request, conn, k, sinif)


@router.post("/ogretmen/tesekkur")
def gonder(
    request: Request,
    arka: BackgroundTasks,
    sinif: str = Form(""),
    sablon: str = Form(""),
    ogrenci: list[int] = Form([]),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        yeni = tesekkur.gonder(conn, k, ogrenci, sablon)
    except tesekkur.TesekkurHatasi as e:
        if e.kod == 404:
            raise HTTPException(404) from None
        return _form(request, conn, k, sinif or None, hata=e.mesaj, durum=e.kod)
    if yeni:
        arka.add_task(push.tesekkur_bildir, yeni)
    return RedirectResponse(f"/ogretmen/tesekkur?sinif={sinif}&gonderildi={len(yeni)}", status_code=303)


@router.get("/tesekkurler")
def liste(request: Request, ogr: int | None = None, k=Depends(ALICI), conn: sqlite3.Connection = Depends(db_conn)):
    cocuklar = []
    if k["rol"] == "ogrenci":
        o = yetki.ogrenci_kaydi(conn, k["id"])
    else:
        cocuklar = yetki.veli_cocuklari(conn, k["id"])
        o = cocuklar[0] if cocuklar and ogr is None else next((c for c in cocuklar if c["id"] == ogr), None)
        if o is not None:
            yetki.erisim_kaydet(conn, k, "tesekkurler", o["id"], istemci_ip(request))
    if o is None:
        raise HTTPException(404)
    return render(
        request, "tesekkurler.html", ogrenci=o, cocuk=o if k["rol"] == "veli" else None,
        cocuklar=cocuklar, kartlar=tesekkur.ogrenci_kartlari(conn, o),
    )
