"""Veli sayfaları — yalnızca veli_ogrenci'deki çocuklar; her görüntüleme erisim_log'a."""

import sqlite3

import denemeler
import duyurular
import odevler
import onay
import sinavlar
import veli_bugun
import yetki
import zaman
from ayarlar import AYAR
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from rotalar import ortak

router = APIRouter(prefix="/veli")
VELI = rol("veli")
VELI_POST = rol("veli", post=True)


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
    dv = ortak.devamsizlik(c, 30)
    bugun = zaman.simdi().strftime("%Y-%m-%d")
    return render(
        request,
        "veli/ana.html",
        cocuklar=cocuklar,
        cocuk=c,
        devamsizlik=dv,
        bugun=bugun,
        simdi=veli_bugun.simdi(c),
        bugun_yok=veli_bugun.bugun_yok(dv, bugun),
        akis=veli_bugun.akis(c),
        veli_gorev=veli_bugun.gorevler(conn, k, c),
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
        deneme_sayisi=denemeler.deneme_sayisi(conn, c["okul_no"]),
    )


@router.get("/onaylar")
def onaylar(
    request: Request,
    ogr: int | None = None,
    hata: str = "",
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    cocuklar, c = _cocuk(request, conn, k, ogr, "veli_onaylar")
    if c is None:
        raise HTTPException(404)
    mesaj = {"sure": "Bu belgenin yanıt süresi dolmuş.", "yanit": "Yanıt kaydedilemedi, lütfen tekrar deneyin."}.get(hata, "")  # URL'den gelen metin yansıtılmaz
    return render(request, "veli/onaylar.html", cocuklar=cocuklar, cocuk=c, talepler=onay.cocuk_talepleri(conn, c), yanitlar=onay.YANITLAR, hata=mesaj)


@router.post("/onay/{talep_id}")
def onay_yanitla(
    talep_id: int,
    ogr: int = Form(...),
    yanit: str = Form(""),
    k=Depends(VELI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        onay.yanitla(conn, k, ogr, talep_id, yanit)
    except onay.OnayHatasi as e:
        if e.kod == 404:
            raise HTTPException(404) from None
        return RedirectResponse(f"/veli/onaylar?ogr={ogr}&hata={'sure' if e.kod == 410 else 'yanit'}", status_code=303)
    return RedirectResponse(f"/veli/onaylar?ogr={ogr}", status_code=303)


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
