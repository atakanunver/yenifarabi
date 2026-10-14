"""Kişisel Gelişim rotaları (yalnızca öğrenci; yalnızca kendi verisi). Diğer roller 404."""

import sqlite3

import arena
import kisisel
import oduller
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/ogrenci")
OGRENCI = rol("ogrenci")


def _kendisi(conn: sqlite3.Connection, k: sqlite3.Row) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None or o["kullanici_id"] is None:
        raise HTTPException(404)
    return o


def _sayfa(request, conn, o, hata: str = "", status: int = 200):
    kisisel.rozet_kontrol(conn, o)
    return render(
        request, "ogrenci/hedefim.html", status_code=status, hafta=kisisel.bu_hafta(conn, o),
        gecmis=kisisel.gecmis(conn, o), rozetler=arena.rozetler(conn, o["kullanici_id"]), hata=hata,
        min_hedef=kisisel.MIN_HEDEF, max_hedef=kisisel.MAX_HEDEF,
        oduller=oduller.ogrenci_oduller(conn, o), odul_kurallari=(oduller.MIN_ETKINLIK, oduller.MIN_GUN, oduller.MIN_KATILAN),
    )


@router.get("/hedefim")
def hedefim(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    return _sayfa(request, conn, _kendisi(conn, k))


@router.post("/hedefim")
async def hedef_koy(request: Request, k=Depends(rol("ogrenci", post=True)), conn: sqlite3.Connection = Depends(db_conn)):
    o = _kendisi(conn, k)
    form = await request.form()
    try:
        kisisel.hedef_koy(conn, o, int(str(form.get("hedef", ""))))
    except ValueError:
        return _sayfa(request, conn, o, "Hedef bir sayı olmalı.", 400)
    except kisisel.HedefHatasi as e:
        return _sayfa(request, conn, o, str(e), 400)
    return RedirectResponse("/ogrenci/hedefim", status_code=303)
