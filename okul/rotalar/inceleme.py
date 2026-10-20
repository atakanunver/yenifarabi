"""Öğretmenin günlük 5 soru incelemesi (kendi dersinden havuz soruları): doğru / hatalı (+sebep) / pas."""

import sqlite3

import analitik
import inceleme
import soru_bildirim
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from kaynaklar import KaynakHatasi

router = APIRouter(prefix="/ogretmen/inceleme")

OGRETMEN = rol("ogretmen")


@router.get("")
def sayfa(request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)):
    if not inceleme.ciftler(conn, k["id"]):
        raise HTTPException(404)  # incelenecek dersi yok
    try:
        sorular, hata = inceleme.gunun_seti(conn, k), False
    except KaynakHatasi:
        sorular, hata = [], True
    return render(
        request, "ogretmen/inceleme.html", sorular=sorular, hata=hata, turler=soru_bildirim.TURLER,
        yapilan=sum(1 for s in sorular if s["sonuc"]), mesaj=request.query_params.get("m", ""),
    )


@router.post("/{sira}")
def isaretle(
    sira: int,
    request: Request,
    sonuc: str = Form(""),
    tur: str = Form(""),
    k=Depends(rol("ogretmen", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    """`tur` doluysa hatalı (sebep=tur); yoksa `sonuc` = dogru | pas."""
    try:
        inceleme.isle(conn, k, sira, "hatali" if tur else sonuc, tur)
    except inceleme.IncelemeHatasi as e:
        return RedirectResponse(f"/ogretmen/inceleme?m={e}", status_code=303)
    analitik.istekten(request, "ogretmen_inceleme", str(sira))
    return RedirectResponse(f"/ogretmen/inceleme#s{sira + 1}", status_code=303)
