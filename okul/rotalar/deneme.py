"""Denemeler: öğrenci kendi sonuçlarını, veli yalnızca çocuğununkini görür (yayında olanlar)."""

import sqlite3

import denemeler
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request

from rotalar import veli as veli_rota
from rotalar.ogrenci import _kendisi

router = APIRouter()
OGRENCI = rol("ogrenci")
VELI = rol("veli")


@router.get("/ogrenci/deneme")
def ogrenci_liste(
    request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    o = _kendisi(conn, k)
    return render(
        request,
        "ogrenci/deneme.html",
        denemeler=denemeler.ogrenci_denemeleri(conn, o["okul_no"]),
    )


@router.get("/ogrenci/deneme/{deneme_id}")
def ogrenci_tek(
    deneme_id: int,
    request: Request,
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    d = denemeler.ogrenci_denemesi(conn, o["okul_no"], deneme_id)
    if d is None:
        raise HTTPException(404)
    return render(request, "ogrenci/deneme.html", denemeler=[d])


@router.get("/veli/deneme")
def veli_liste(
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = veli_rota._cocuk(request, conn, k, ogr, "veli_deneme")
    if c is None:
        raise HTTPException(404)
    return render(
        request,
        "veli/deneme.html",
        cocuklar=cocuklar,
        cocuk=c,
        denemeler=denemeler.ogrenci_denemeleri(conn, c["okul_no"]),
    )


@router.get("/veli/deneme/{deneme_id}")
def veli_tek(
    deneme_id: int,
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = veli_rota._cocuk(request, conn, k, ogr, "veli_deneme")
    if c is None:
        raise HTTPException(404)
    d = denemeler.ogrenci_denemesi(conn, c["okul_no"], deneme_id)
    if d is None:
        raise HTTPException(404)
    return render(request, "veli/deneme.html", cocuklar=cocuklar, cocuk=c, denemeler=[d])
