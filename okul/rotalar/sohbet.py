"""Sohbet odası rotaları (yalnızca öğretmen ve yönetici; diğer roller 404). Yalnızca metin, 30 gün saklama."""

import sqlite3

import sohbet
from deps import db_conn, render, rol
from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

router = APIRouter(prefix="/sohbet")
UYE = rol(*sohbet.ROLLER)
UYE_POST = rol(*sohbet.ROLLER, post=True)


def _json_mu(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


@router.get("")
def oda(request: Request, k=Depends(UYE), conn: sqlite3.Connection = Depends(db_conn)):
    liste = sohbet.mesajlar(conn, k)
    sohbet.okundu(conn, k["id"], sohbet.en_son_id(conn))
    return render(
        request, "sohbet.html", mesajlar=liste, son_id=liste[-1]["id"] if liste else 0,
        saklama_gun=sohbet.SAKLAMA_GUN, azami=sohbet.AZAMI_METIN,
    )


@router.get("/mesajlar")
def yeni_mesajlar(sonra: int = 0, k=Depends(UYE), conn: sqlite3.Connection = Depends(db_conn)):
    liste = sohbet.mesajlar(conn, k, max(sonra, 0))
    sohbet.okundu(conn, k["id"], sohbet.en_son_id(conn))
    return JSONResponse({"mesajlar": liste}, headers={"Cache-Control": "no-store"})


@router.post("/gonder")
def gonder(
    request: Request,
    arka: BackgroundTasks,
    metin: str = Form(""),
    k=Depends(UYE_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        mesaj_id = sohbet.mesaj_ekle(conn, k["id"], metin)
    except sohbet.SohbetHatasi as e:
        if _json_mu(request):
            return JSONResponse({"hata": e.mesaj}, status_code=e.kod)
        raise HTTPException(e.kod, e.mesaj) from e
    arka.add_task(sohbet.bildir, k["id"])
    if _json_mu(request):
        return JSONResponse({"id": mesaj_id})
    return RedirectResponse("/sohbet", status_code=303)


@router.post("/{mesaj_id}/sil")
def sil(
    request: Request,
    mesaj_id: int,
    k=Depends(UYE_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not sohbet.sil(conn, k, mesaj_id):
        raise HTTPException(404)
    if _json_mu(request):
        return JSONResponse({"ok": True})
    return RedirectResponse("/sohbet", status_code=303)
