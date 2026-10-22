"""Veli onay/izin istekleri: yönetici (tüm okul/sınıf) ve öğretmen (kendi sınıfı) oluşturur, sonuçları adlı görür."""

import sqlite3

import onay
import push
import yetki
from deps import db_conn, render, rol
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/ogretmen/onay")
YAZAR = rol("ogretmen", "yonetici")
YAZAR_POST = rol("ogretmen", "yonetici", post=True)


def _siniflar(conn: sqlite3.Connection, k) -> list[str]:
    s = yetki.kullanici_siniflari(conn, k)
    return s if s is not None else [r[0] for r in conn.execute("SELECT DISTINCT sinif FROM ogrenci ORDER BY sinif")]


def _sayfa(request: Request, k, conn, hata: str = "", durum: int = 200, **form):
    return render(request, "ogretmen/onay_liste.html", status_code=durum, talepler=onay.listele(conn, k), siniflar=_siniflar(conn, k), hata=hata, form=form)


@router.get("")
def liste(request: Request, k=Depends(YAZAR), conn: sqlite3.Connection = Depends(db_conn)):
    return _sayfa(request, k, conn)


@router.post("")
def olustur(
    request: Request,
    arka: BackgroundTasks,
    baslik: str = Form(""),
    aciklama: str = Form(""),
    hedef_tur: str = Form("sinif"),
    hedef: str = Form(""),
    son_tarih: str = Form(""),
    k=Depends(YAZAR_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        talep_id = onay.olustur(conn, k, baslik, aciklama, hedef_tur, hedef or None, son_tarih)
    except onay.OnayHatasi as e:
        if e.kod == 404:
            raise HTTPException(404) from None
        return _sayfa(request, k, conn, hata=e.mesaj, durum=e.kod, baslik=baslik, aciklama=aciklama, hedef_tur=hedef_tur, hedef=hedef, son_tarih=son_tarih)
    arka.add_task(push.onay_bildir, hedef_tur, hedef or None, k["id"])
    return RedirectResponse(f"/ogretmen/onay/{talep_id}", status_code=303)


@router.get("/{talep_id}")
def sonuc(talep_id: int, request: Request, k=Depends(YAZAR), conn: sqlite3.Connection = Depends(db_conn)):
    t = onay.getir(conn, k, talep_id)
    if t is None:
        raise HTTPException(404)
    return render(request, "ogretmen/onay_sonuc.html", t=t, s=onay.sonuc(conn, t))
