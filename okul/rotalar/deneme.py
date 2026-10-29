"""Denemeler: öğrenci kendi sonuçlarını, veli yalnızca çocuğununkini görür (yayında olanlar)."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

import denemeler
import dosyalar
import yetki
from deps import db_conn, istemci_ip, render, rol
from rotalar import veli as veli_rota
from rotalar.ogrenci import _kendisi
from rotalar.ogretmen_liderlik import benim_siniflarim

router = APIRouter()
OGRENCI = rol("ogrenci")
VELI = rol("veli")
OGRETMEN = rol("ogretmen", "yonetici")
YONETICI = rol("yonetici")


def _pdf_yanit(conn: sqlite3.Connection, deneme_id: int, okul_no: int, yayinda_sart: bool = True):
    """Öğrencinin deneme PDF'i; yetki çağıran tarafta. Dosya/kayıt/yayın yoksa 404."""
    if yayinda_sart and not conn.execute(
        "SELECT 1 FROM deneme WHERE id = ? AND yayinda = 1", (deneme_id,)
    ).fetchone():
        raise HTTPException(404)
    depo = denemeler.pdf_dosyasi(conn, deneme_id, okul_no)
    if depo is None:
        raise HTTPException(404)
    yol = dosyalar.yol("deneme", depo)
    if not yol.exists():
        raise HTTPException(404)
    return FileResponse(
        yol, media_type="application/pdf", headers={"Cache-Control": "private, no-store"}
    )


@router.get("/ogrenci/deneme")
def ogrenci_liste(
    request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    o = _kendisi(conn, k)
    return render(
        request,
        "ogrenci/deneme.html",
        denemeler=denemeler.ogrenci_denemeleri(conn, o["okul_no"]),
        pdf_taban="/ogrenci/deneme",
        pdf_ek="",
    )


@router.get("/ogrenci/deneme/{deneme_id}/pdf")
def ogrenci_pdf(
    deneme_id: int, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)
):
    return _pdf_yanit(conn, deneme_id, _kendisi(conn, k)["okul_no"])


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
    return render(request, "ogrenci/deneme.html", denemeler=[d], pdf_taban="/ogrenci/deneme", pdf_ek="")


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
        pdf_taban="/veli/deneme",
        pdf_ek=f"?ogr={c['id']}",
    )


@router.get("/veli/deneme/{deneme_id}/pdf")
def veli_pdf(
    deneme_id: int,
    request: Request,
    ogr: int | None = None,
    k=Depends(VELI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _cocuklar, c = veli_rota._cocuk(request, conn, k, ogr, "veli_deneme_pdf")
    if c is None:
        raise HTTPException(404)
    return _pdf_yanit(conn, deneme_id, c["okul_no"])


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
    return render(
        request, "veli/deneme.html", cocuklar=cocuklar, cocuk=c, denemeler=[d],
        pdf_taban="/veli/deneme", pdf_ek=f"?ogr={c['id']}",
    )


# --- öğretmen (kendi şubeleri) + yönetici (tüm okul) ---
# Yönetici yayında olmayan denemeyi de görür (yayın öncesi kontrol); öğretmen yalnız yayındakileri.
# Sıralama YOK: öğrenciler ada göre, şubeler şube adına göre listelenir.


def _yetkili_sinif(conn: sqlite3.Connection, k: sqlite3.Row, sinif: str) -> None:
    if sinif not in benim_siniflarim(conn, k):
        raise HTTPException(404)


@router.get("/ogretmen/deneme")
def ogretmen_liste(
    request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    liste = denemeler.denemeler_listesi(
        conn, benim_siniflarim(conn, k), yalniz_yayinda=k["rol"] != "yonetici"
    )
    return render(request, "ogretmen/deneme_liste.html", liste=liste)


@router.get("/ogretmen/deneme/{deneme_id}/{sinif}")
def ogretmen_sinif(
    deneme_id: int,
    sinif: str,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _yetkili_sinif(conn, k, sinif)
    ozet = denemeler.sinif_ozeti(conn, deneme_id, sinif, yalniz_yayinda=k["rol"] != "yonetici")
    if ozet is None:
        raise HTTPException(404)
    yetki.erisim_kaydet(conn, k, f"deneme:{sinif}", None, istemci_ip(request))
    ad = conn.execute("SELECT ad FROM deneme WHERE id = ?", (deneme_id,)).fetchone()["ad"]
    return render(
        request,
        "ogretmen/deneme_sinif.html",
        deneme_id=deneme_id,
        deneme_ad=ad,
        o=ozet,
        yorum=denemeler.yorum_oku(conn, deneme_id, sinif),
        yonetici=k["rol"] == "yonetici",
    )


@router.get("/ogretmen/deneme/{deneme_id}/{sinif}/{okul_no}/pdf")
def ogretmen_ogrenci_pdf(
    deneme_id: int,
    sinif: str,
    okul_no: int,
    request: Request,
    k=Depends(OGRETMEN),
    conn: sqlite3.Connection = Depends(db_conn),
):
    _yetkili_sinif(conn, k, sinif)
    o = conn.execute(
        "SELECT id FROM ogrenci WHERE okul_no = ? AND sinif = ?", (okul_no, sinif)
    ).fetchone()
    if o is None:
        raise HTTPException(404)
    yanit = _pdf_yanit(conn, deneme_id, okul_no, yayinda_sart=k["rol"] != "yonetici")
    yetki.erisim_kaydet(conn, k, "deneme_pdf", o["id"], istemci_ip(request))
    return yanit


@router.get("/yonetici/deneme/{deneme_id}")
def yonetici_okul(
    deneme_id: int,
    request: Request,
    k=Depends(YONETICI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    ozet = denemeler.okul_ozeti(conn, deneme_id, yalniz_yayinda=False)
    if ozet is None:
        raise HTTPException(404)
    d = conn.execute("SELECT ad, yayinda FROM deneme WHERE id = ?", (deneme_id,)).fetchone()
    return render(
        request,
        "yonetici/deneme.html",
        deneme_id=deneme_id,
        deneme_ad=d["ad"],
        yayinda=bool(d["yayinda"]),
        o=ozet,
        yorum=denemeler.yorum_oku(conn, deneme_id, ""),
    )
