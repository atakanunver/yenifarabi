"""Haftalık ödül yönetimi (yalnızca yönetici): geçmiş haftalar, kazananlar, haftanın Nescafe'sinin teslim takibi."""

import sqlite3

import oduller
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/yonetici/oduller")


@router.get("")
def liste(request: Request, k=Depends(rol("yonetici")), conn: sqlite3.Connection = Depends(db_conn)):
    simdi = oduller.hafta_basi()
    # biten ama henüz kaydedilmemiş son haftayı kaydet (kiosk pazartesi bakmadıysa da sonuç yazılsın)
    onceki = oduller.onceki_hafta(simdi)
    oduller.kapat(conn, onceki)
    haftalar = []
    hb = onceki
    for _ in range(8):
        kayit = oduller.kayitli(conn, hb)
        if kayit or hb == onceki:
            haftalar.append({"hafta_basi": hb, "kayitlar": kayit, "adlar": oduller.KATEGORILER})
        hb = oduller.onceki_hafta(hb)
    gecici = oduller.siralama(conn, simdi)
    return render(
        request, "yonetici/oduller.html", haftalar=haftalar, gecici=gecici, bu_hafta=simdi, kategoriler=oduller.KATEGORILER,
        min_etkinlik=oduller.MIN_ETKINLIK, min_gun=oduller.MIN_GUN, min_katilan=oduller.MIN_KATILAN,
    )


@router.post("/{odul_id}/kahve")
async def kahve(
    odul_id: int, request: Request, k=Depends(rol("yonetici", post=True)), conn: sqlite3.Connection = Depends(db_conn)
):
    form = await request.form()
    try:
        oduller.kahve_teslim(conn, odul_id, form.get("teslim") == "1")
    except ValueError as e:
        raise HTTPException(404) from e
    return RedirectResponse("/yonetici/oduller", status_code=303)
