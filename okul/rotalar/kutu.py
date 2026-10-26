"""Dilek/istek/şikayet kutusu rotaları. Gönderen: öğrenci/öğretmen/veli; okuyan: yönetici. Diğer roller 404."""

import sqlite3

import kutu
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter()
UYE = rol(*kutu.ROLLER)
UYE_POST = rol(*kutu.ROLLER, post=True)
YONETICI = rol("yonetici")
YONETICI_POST = rol("yonetici", post=True)


def _sayfa(request: Request, k, conn, hata: str = "", tur: str = "dilek", metin: str = "", durum: int = 200):
    return render(
        request, "kutu.html", status_code=durum, kayitlar=kutu.benim(conn, k["id"]), turler=kutu.TURLER,
        azami=kutu.AZAMI_METIN, hata=hata, secili_tur=tur, metin=metin,
    )


@router.get("/kutu")
def form(request: Request, k=Depends(UYE), conn: sqlite3.Connection = Depends(db_conn)):
    return _sayfa(request, k, conn)


@router.post("/kutu/gonder")
def gonder(
    request: Request,
    tur: str = Form(""),
    metin: str = Form(""),
    k=Depends(UYE_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        kutu.ekle(conn, k["id"], tur, metin)
    except kutu.KutuHatasi as e:
        return _sayfa(request, k, conn, hata=e.mesaj, tur=tur if tur in kutu.TURLER else "dilek", metin=metin, durum=e.kod)
    return RedirectResponse("/kutu?gonderildi=1", status_code=303)


@router.get("/yonetici/kutu")
def yonetici_liste(
    request: Request,
    durum: str = "",
    tur: str = "",
    k=Depends(YONETICI),
    conn: sqlite3.Connection = Depends(db_conn),
):
    return render(
        request, "yonetici/kutu.html", kayitlar=kutu.liste(conn, durum, tur), turler=kutu.TURLER,
        durumlar=kutu.DURUMLAR, durum=durum, tur=tur, yeni=kutu.yeni_sayisi(conn),
    )


@router.post("/yonetici/kutu/{kayit_id}/durum")
def yonetici_durum(
    kayit_id: int,
    durum: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not kutu.durum_ayarla(conn, kayit_id, durum):
        raise HTTPException(404)
    return RedirectResponse("/yonetici/kutu", status_code=303)
