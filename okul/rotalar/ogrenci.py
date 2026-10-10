"""Öğrenci sayfaları: ana sayfa, ödevler (klasik + test çözme), kazanımlar, program."""

import json
import sqlite3

import duyurular
import odevler
import sinavlar
import yetki
import zaman
from ayarlar import AYAR
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from rotalar import ortak

router = APIRouter(prefix="/ogrenci")
OGRENCI = rol("ogrenci")


def _kendisi(conn: sqlite3.Connection, k: sqlite3.Row) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    return o


def _odev(conn: sqlite3.Connection, ogrenci: sqlite3.Row, odev_id: int) -> sqlite3.Row:
    odev = odevler.odev_getir(conn, odev_id)
    if odev is None or odev["sinif"] != ogrenci["sinif"]:
        raise HTTPException(404)
    return odev


@router.get("")
def ana(
    request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    o = _kendisi(conn, k)
    ozet, _, erisildi = ortak.kazanim_ozeti(conn, o)
    return render(
        request,
        "ogrenci/ana.html",
        ogrenci=o,
        dersler=ortak.bugunku_dersler(o["sinif"]),
        odevler=ortak.bekleyen_odevler(conn, o)[:4],
        duyurular=duyurular.gorunur_duyurular(conn, k, 3),
        ders_ozeti=ortak.ders_ozeti(ozet),
        kazanim_erisildi=erisildi,
        simdi=zaman.simdi_str(),
        sinavlar=ortak.yaklasan_sinavlar(conn, o["sinif"]),
        kalan=sinavlar.kalan_gun,
    )


@router.get("/odevler")
def odev_listesi(
    request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    o = _kendisi(conn, k)
    return render(
        request,
        "ogrenci/odevler.html",
        odevler=odevler.ogrenci_odevleri(conn, o),
        simdi=zaman.simdi_str(),
    )


@router.get("/odev/{odev_id}")
def odev_detay(
    odev_id: int,
    request: Request,
    k=Depends(OGRENCI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    odev = _odev(conn, o, odev_id)
    teslim = odevler.teslim_getir(conn, odev_id, o["id"])
    sorular = odevler.sorular(conn, odev_id) if odev["tur"] == "test" else []
    cevaplar = {}
    if teslim and teslim["cevaplar"]:
        cevaplar = {int(a): v for a, v in json.loads(teslim["cevaplar"]).items()}
    return render(
        request,
        "ogrenci/odev.html",
        odev=odev,
        teslim=teslim,
        sorular=sorular,
        cevaplar=cevaplar,
    )


@router.post("/odev/{odev_id}/yapti")
def odev_yapti(
    odev_id: int,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    try:
        odevler.yapti_isaretle(conn, _odev(conn, o, odev_id), o["id"])
    except odevler.OdevHatasi as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(f"/ogrenci/odev/{odev_id}", status_code=303)


@router.post("/odev/{odev_id}/test")
async def odev_test(
    odev_id: int,
    request: Request,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _kendisi(conn, k)
    odev = _odev(conn, o, odev_id)
    form = await request.form()
    cevaplar = {}
    for s in odevler.sorular(conn, odev_id):
        deger = form.get(f"s{s['id']}")
        cevaplar[s["id"]] = (
            int(deger) if deger not in (None, "") and str(deger).isdigit() else None
        )
    try:
        odevler.test_teslim_et(conn, odev, o["id"], cevaplar)
    except odevler.OdevHatasi as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse(f"/ogrenci/odev/{odev_id}", status_code=303)


@router.get("/kazanimlar")
def kazanimlar(
    request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    o = _kendisi(conn, k)
    ozet, form, erisildi = ortak.kazanim_ozeti(conn, o)
    return render(
        request,
        "kazanimlar.html",
        ozet=ozet,
        form=form,
        erisildi=erisildi,
        esik=AYAR.kazanim_esik,
        kim="Kazanımlarım",
    )


@router.get("/program")
def ders_programi(
    request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    o = _kendisi(conn, k)
    return render(
        request,
        "program.html",
        program=ortak.haftalik_program(o["sinif"]),
        sinif=o["sinif"],
    )
