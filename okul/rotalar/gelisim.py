"""Akademik gelişim ekranları: yönetici (okul), öğretmen (sınıf, öğrenci), öğrenci (kendisi).

Yetkisiz erişim 404. Öğretmen/yönetici görüntülemeleri KVKK erişim kaydına yazılır. Raporlar
yalnızca gerçek kayıtlardan hesaplanır (gelisim.py); kaynak erişilemezse ekran bunu açıkça söyler.
"""

import sqlite3

import gelisim
import yetki
from deps import db_conn, istemci_ip, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from kaynaklar import KaynakHatasi, form_toplu

router = APIRouter()
YONETICI = rol("yonetici")
OGRETMEN = rol("ogretmen", "yonetici")
OGRENCI = rol("ogrenci")


def _form(okul_nolar: list[int]) -> tuple[dict, bool]:
    """(okul_no -> form sonuçları, kaynak erişildi mi). Erişilemezse boş + False: veri uydurulmaz."""
    try:
        return form_toplu.sonuclar(okul_nolar), True
    except KaynakHatasi:
        return {}, False


def _nolar(conn: sqlite3.Connection, sinif: str | None = None) -> list[int]:
    sql, arg = "SELECT okul_no FROM ogrenci", ()
    if sinif:
        sql, arg = sql + " WHERE sinif = ?", (sinif,)
    return [r[0] for r in conn.execute(sql, arg)]


@router.get("/yonetici/gelisim")
def okul_gelisim(request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)):
    form, erisildi = _form(_nolar(conn))
    return render(request, "yonetici/gelisim.html", r=gelisim.okul_raporu(conn, form, erisildi))


@router.get("/ogretmen/gelisim/{sinif}")
def sinif_gelisim(
    sinif: str, request: Request, ders: str = "", k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    if not yetki.sinif_yetkili(conn, k, sinif):
        raise HTTPException(404)
    yetki.erisim_kaydet(conn, k, f"sinif_gelisim:{sinif}", None, istemci_ip(request))
    form, erisildi = _form(_nolar(conn, sinif))
    rapor = gelisim.sinif_raporu(conn, sinif, form, erisildi, ders or None)
    tum_dersler = sorted({d["ders"] for d in gelisim.sinif_raporu(conn, sinif, form, erisildi)["dersler"]})
    return render(request, "ogretmen/gelisim_sinif.html", r=rapor, ders=ders, tum_dersler=tum_dersler)


@router.get("/ogretmen/ogrenci/{ogrenci_id}/gelisim")
def ogrenci_gelisim(
    ogrenci_id: int, request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)
):
    o = yetki.ogrenci_getir(conn, k, ogrenci_id)
    yetki.erisim_kaydet(conn, k, "ogrenci_gelisim", o["id"], istemci_ip(request))
    form, erisildi = _form([o["okul_no"]])
    return render(
        request, "ogretmen/gelisim_ogrenci.html", r=gelisim.ogrenci_raporu(conn, o, form, erisildi)
    )


@router.get("/ogrenci/gelisim")
def benim_gelisimim(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    form, erisildi = _form([o["okul_no"]])
    return render(request, "ogrenci/gelisim.html", r=gelisim.ogrenci_raporu(conn, o, form, erisildi))
