"""Öğretmenin kişisel not defteri (/ogretmen/not): yalnızca sahibi görür/değiştirir; başkasının notu = 404."""

import sqlite3

import notdefteri
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

router = APIRouter(prefix="/ogretmen/not")
OGRETMEN = rol("ogretmen")
OGRETMEN_POST = rol("ogretmen", post=True)
DONUSLER = {"ana": "/ogretmen", "liste": "/ogretmen/not"}


@router.get("")
def liste(request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)):
    return render(request, "ogretmen/not_liste.html", notlar=notdefteri.liste(conn, k["id"]))


@router.get("/yeni")
def yeni_form(request: Request, sinif: str = "", ders: str = "", k=Depends(OGRETMEN)):
    return render(request, "ogretmen/not_form.html", n=None, sinif=sinif[:20], ders=ders[:60])


@router.post("/yeni")
def yeni(
    request: Request,
    metin: str = Form(""),
    sinif: str = Form(""),
    ders: str = Form(""),
    yapilacak: str = Form(""),
    donus: str = Form("liste"),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        notdefteri.ekle(conn, k["id"], metin, sinif[:20] or None, ders[:60] or None, yapilacak == "1")
    except notdefteri.NotHatasi as e:
        return render(request, "ogretmen/not_form.html", 422, hata=str(e), n=None, sinif=sinif[:20], ders=ders[:60], metin=metin, yapilacak=yapilacak == "1")
    return RedirectResponse(DONUSLER.get(donus, "/ogretmen/not"), status_code=303)


@router.get("/{not_id}")
def duzenle_form(not_id: int, request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)):
    n = notdefteri.getir(conn, k["id"], not_id)
    if n is None:
        raise HTTPException(404)
    return render(request, "ogretmen/not_form.html", n=n, sinif=n["sinif"] or "", ders=n["ders"] or "")


@router.post("/{not_id}")
def duzenle(
    not_id: int,
    request: Request,
    metin: str = Form(""),
    yapilacak: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    n = notdefteri.getir(conn, k["id"], not_id)
    if n is None:
        raise HTTPException(404)
    try:
        notdefteri.guncelle(conn, k["id"], not_id, metin, yapilacak == "1")
    except notdefteri.NotHatasi as e:
        return render(request, "ogretmen/not_form.html", 422, hata=str(e), n=n, sinif=n["sinif"] or "", ders=n["ders"] or "", metin=metin, yapilacak=yapilacak == "1")
    return RedirectResponse("/ogretmen/not", status_code=303)


@router.post("/{not_id}/tamam")
def tamam(not_id: int, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)):
    if not notdefteri.tamam_degistir(conn, k["id"], not_id):
        raise HTTPException(404)
    return RedirectResponse("/ogretmen/not", status_code=303)


@router.post("/{not_id}/sil")
def sil(not_id: int, k=Depends(OGRETMEN_POST), conn: sqlite3.Connection = Depends(db_conn)):
    if not notdefteri.sil(conn, k["id"], not_id):
        raise HTTPException(404)
    return RedirectResponse("/ogretmen/not", status_code=303)
