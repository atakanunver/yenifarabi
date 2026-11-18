"""Coğrafya oyunu öğrenci rotaları."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

import analitik
import arena
import cografya_oyun
import yetki
from deps import db_conn, render, rol

router = APIRouter(prefix="/ogrenci/cografya")
ogretmen_router = APIRouter(prefix="/ogretmen/cografya")
OGRENCI = rol("ogrenci")
OGRENCI_POST = rol("ogrenci", post=True)
Kullanici = Annotated[object, Depends(OGRENCI)]
PostKullanici = Annotated[object, Depends(OGRENCI_POST)]
Conn = Annotated[object, Depends(db_conn)]


def _ogrenci(conn, k):
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    return o


@router.get("")
def sayfa(request: Request, k: Kullanici, conn: Conn):
    o = _ogrenci(conn, k)
    return render(request, "ogrenci/cografya.html", ogrenci=o, xp_acik=arena.duzey_uygun(o["sinif"]))


@ogretmen_router.get("")
def ogretmen_sayfa(request: Request, k: Annotated[object, Depends(rol("ogretmen", "yonetici"))]):
    """Deneme modu: oyun tarayıcıda oynanır, sunucuya/DB'ye hiçbir şey yazılmaz (basla/bitir/liderlik çağrılmaz)."""
    ogrenci = {"ad_soyad": k["ad_soyad"], "sinif": "Öğretmen" if k["rol"] == "ogretmen" else "Yönetici"}
    return render(request, "ogrenci/cografya.html", ogrenci=ogrenci, xp_acik=False, deneme=True)


@router.post("/basla")
async def basla(request: Request, k: PostKullanici, conn: Conn):
    _ogrenci(conn, k)
    form = await request.form()
    try:
        oyun_id = cografya_oyun.baslat(conn, k["id"], str(form.get("mod", "")), str(form.get("yanit", "")),
                                        str(form.get("bolge", "")), int(str(form.get("soru_sayisi", ""))))
    except cografya_oyun.GunlukSinir as e:
        return JSONResponse({"mesaj": str(e)}, status_code=429)
    except ValueError as e:
        return JSONResponse({"mesaj": str(e)}, status_code=400)
    conn.commit()
    return {"oyun_id": oyun_id}


@router.post("/{oyun_id}/bitir")
async def bitir(oyun_id: int, request: Request, k: PostKullanici, conn: Conn):
    o = _ogrenci(conn, k)
    form = await request.form()
    try:
        try:
            dogru, yanlis = int(str(form.get("dogru", ""))), int(str(form.get("yanlis", "")))
        except ValueError:
            dogru, yanlis = None, None
        sonuc = cografya_oyun.bitir(conn, k["id"], oyun_id, dogru, yanlis, arena.duzey_uygun(o["sinif"]))
    except ValueError as e:
        conn.commit()
        return JSONResponse({"mesaj": str(e)}, status_code=400)
    if sonuc is None:
        raise HTTPException(404)
    conn.commit()
    analitik.istekten(request, "cografya_bitir", str(oyun_id))
    return sonuc


@router.get("/liderlik")
def liderlik(k: Kullanici, conn: Conn, mod: str = "", yanit: str = "", bolge: str = "",
             donem: str = "hafta", kapsam: str = "sinif"):
    o = _ogrenci(conn, k)
    try:
        return cografya_oyun.liderlik(conn, k["id"], mod, yanit, bolge, donem, kapsam, o["sinif"])
    except ValueError as e:
        return JSONResponse({"mesaj": str(e)}, status_code=400)
