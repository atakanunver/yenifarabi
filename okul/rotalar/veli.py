"""Veli sayfaları — yalnızca veli_ogrenci'deki çocuklar; her görüntüleme erisim_log'a."""

import sqlite3

import duyurular
import odevler
import sinavlar
import yetki
import zaman
from ayarlar import AYAR
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request

from rotalar import ortak

router = APIRouter(prefix="/veli")
VELI = rol("veli")


def _cocuk(
    request: Request,
    conn: sqlite3.Connection,
    k: sqlite3.Row,
    ogr: int | None,
    eylem: str,
):
    cocuklar = yetki.veli_cocuklari(conn, k["id"])
    if not cocuklar:
        return cocuklar, None
    if ogr is None:
        secili = cocuklar[0]
    else:
        secili = next((c for c in cocuklar if c["id"] == ogr), None)
        if secili is None:
            raise HTTPException(404)
    yetki.erisim_kaydet(conn, k, eylem, secili["id"], istemci_ip(request))
    return cocuklar, secili


@router.get("")
def ana(
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_ana")
    if c is None:
        return render(request, "veli/ana.html", cocuklar=[], cocuk=None)
    ozet, form, erisildi = ortak.kazanim_ozeti(conn, c)
    return render(
        request,
        "veli/ana.html",
        cocuklar=cocuklar,
        cocuk=c,
        devamsizlik=ortak.devamsizlik(c, 30),
        bugun=zaman.simdi().strftime("%Y-%m-%d"),
        son_testler=form[:3],
        kazanim_erisildi=erisildi,
        ders_ozeti=ortak.ders_ozeti(ozet),
        odevler=ortak.bekleyen_odevler(conn, c)[:4],
        duyurular=duyurular.gorunur_duyurular(conn, k, 3),
        sinavlar=ortak.yaklasan_sinavlar(conn, c["sinif"]),
        cocuk_foto=conn.execute("SELECT foto FROM kullanici WHERE id = ?", (c["kullanici_id"],)).fetchone()["foto"]
        if c["kullanici_id"]
        else None,
        kalan=sinavlar.kalan_gun,
    )


@router.get("/devamsizlik")
def devamsizlik(
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_devamsizlik")
    if c is None:
        raise HTTPException(404)
    kayitlar = ortak.devamsizlik(c)
    return render(
        request,
        "veli/devamsizlik.html",
        cocuklar=cocuklar,
        cocuk=c,
        gunler=ortak.devamsizlik_gunlere_gore(kayitlar)
        if kayitlar is not None
        else None,
        yok=sum(1 for d in kayitlar or [] if d.tur == "yok"),
        izinli=sum(1 for d in kayitlar or [] if d.tur == "izinli"),
    )


@router.get("/kazanim")
def kazanim(
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_kazanim")
    if c is None:
        raise HTTPException(404)
    ozet, form, erisildi = ortak.kazanim_ozeti(conn, c)
    return render(
        request,
        "kazanimlar.html",
        cocuklar=cocuklar,
        cocuk=c,
        ozet=ozet,
        form=form,
        erisildi=erisildi,
        esik=AYAR.kazanim_esik,
        kim=f"{c['ad_soyad']} — kazanımlar",
    )


@router.get("/odevler")
def odev_listesi(
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_odevler")
    if c is None:
        raise HTTPException(404)
    return render(
        request,
        "veli/odevler.html",
        cocuklar=cocuklar,
        cocuk=c,
        odevler=odevler.ogrenci_odevleri(conn, c),
        simdi=zaman.simdi_str(),
    )


@router.get("/program")
def ders_programi(
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_program")
    if c is None:
        raise HTTPException(404)
    return render(
        request,
        "program.html",
        cocuklar=cocuklar,
        cocuk=c,
        program=ortak.haftalik_program(c["sinif"]),
        sinif=c["sinif"],
    )
