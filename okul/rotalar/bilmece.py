"""Günün Bilmecesi rotaları: öğrenci (çöz / dünkü cevap), yönetici (havuz). Diğer roller 404."""

import sqlite3

import bilmece
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter()
OGRENCI = rol("ogrenci")
OGRENCI_POST = rol("ogrenci", post=True)
YONETICI = rol("yonetici")
YONETICI_POST = rol("yonetici", post=True)


def _ogrenci(conn: sqlite3.Connection, k) -> sqlite3.Row:
    o = yetki.ogrenci_kaydi(conn, k["id"])
    if o is None:
        raise HTTPException(404)
    return o


def _sayfa(request: Request, conn, o, hata: str = "", durum: int = 200):
    return render(request, "ogrenci/bilmece.html", status_code=durum, bilmece=bilmece.kart(conn, o), hata=hata)


@router.get("/ogrenci/bilmece")
def sayfa(request: Request, k=Depends(OGRENCI), conn: sqlite3.Connection = Depends(db_conn)):
    return _sayfa(request, conn, _ogrenci(conn, k))


@router.post("/ogrenci/bilmece")
def cevapla(
    request: Request,
    secim: int = Form(-1),
    k=Depends(OGRENCI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    o = _ogrenci(conn, k)
    try:
        bilmece.cevapla(conn, k["id"], secim)
    except bilmece.BilmeceHatasi as e:
        if e.kod == 404:
            raise HTTPException(404) from None
        return _sayfa(request, conn, o, hata=e.mesaj, durum=e.kod)
    return RedirectResponse("/ogrenci/bilmece?kaydedildi=1", status_code=303)


def _yonetici_sayfa(request: Request, conn, hata: str = "", form: dict | None = None, durum: int = 200):
    return render(
        request, "yonetici/bilmeceler.html", status_code=durum, havuz=bilmece.havuz(conn), gecmis=bilmece.gecmis(conn),
        sorulmamis=bilmece.sorulmamis_sayisi(conn), hata=hata, form=form or {}, en_cok=bilmece.SECENEK_EN_COK,
    )


@router.get("/yonetici/bilmeceler")
def yonetici_liste(request: Request, k=Depends(YONETICI), conn: sqlite3.Connection = Depends(db_conn)):
    return _yonetici_sayfa(request, conn)


@router.post("/yonetici/bilmeceler")
def yonetici_ekle(
    request: Request,
    soru: str = Form(""),
    secenek: list[str] = Form([]),
    dogru: int = Form(-1),
    aciklama: str = Form(""),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    # Boş seçenek kutuları atlanır; doğru şıkkın sırası boşlar çıkarıldıktan sonraki sıraya çevrilir.
    dolu = [i for i, s in enumerate(secenek) if s.strip()]
    try:
        bilmece.ekle(conn, soru, [secenek[i] for i in dolu], dolu.index(dogru) if dogru in dolu else -1, aciklama, k["id"])
    except bilmece.BilmeceHatasi as e:
        return _yonetici_sayfa(request, conn, e.mesaj, {"soru": soru, "secenek": secenek, "dogru": dogru, "aciklama": aciklama}, e.kod)
    return RedirectResponse("/yonetici/bilmeceler?eklendi=1", status_code=303)


@router.post("/yonetici/bilmeceler/{bid}/aktif")
def yonetici_aktif(
    bid: int,
    aktif: int = Form(0),
    k=Depends(YONETICI_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not bilmece.aktif_ayarla(conn, bid, bool(aktif)):
        raise HTTPException(404)
    return RedirectResponse("/yonetici/bilmeceler", status_code=303)
