"""Web Push abonelik rotaları (bildirim izni verilen cihazlar). Oturum zorunlu; tüm roller."""

import sqlite3

import push
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()
HERKES = rol()
HERKES_POST = rol(post=True)

ANAHTAR_AZAMI = 200  # p256dh/auth base64 uzunluk üst sınırı


def _alan(form, ad: str, azami: int) -> str:
    v = str(form.get(ad, "")).strip()
    if not v or len(v) > azami:
        raise HTTPException(400, "Geçersiz bildirim aboneliği.")
    return v


@router.get("/bildirimler")
def sayfa(request: Request, _k: sqlite3.Row = Depends(HERKES)):
    if not push.etkin_mi():
        raise HTTPException(404)
    return render(request, "bildirim.html")


@router.get("/push/anahtar")
def anahtar(_k: sqlite3.Row = Depends(HERKES)):
    """Genel VAPID anahtarı (istemci aboneliği için). Bildirim kapalıysa 404."""
    if not push.etkin_mi():
        raise HTTPException(404)
    return JSONResponse({"acik": push.AYAR.vapid_acik}, headers={"Cache-Control": "no-store"})


@router.post("/push/abone", status_code=204)
async def abone(
    request: Request,
    k: sqlite3.Row = Depends(HERKES_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not push.etkin_mi():
        raise HTTPException(404)
    form = await request.form()
    uc = _alan(form, "uc_nokta", push.UC_NOKTA_AZAMI)
    if not push.uc_nokta_gecerli(uc):
        raise HTTPException(400, "Geçersiz bildirim aboneliği.")
    p256dh = _alan(form, "p256dh", ANAHTAR_AZAMI)
    auth = _alan(form, "auth", ANAHTAR_AZAMI)
    if not push.abone_ol(conn, k["id"], uc, p256dh, auth):
        raise HTTPException(400, "Çok fazla cihazda bildirim açık; birini kapatıp tekrar deneyin.")


@router.post("/push/iptal", status_code=204)
async def iptal(
    request: Request,
    k: sqlite3.Row = Depends(HERKES_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    form = await request.form()
    push.abonelik_sil(conn, k["id"], _alan(form, "uc_nokta", push.UC_NOKTA_AZAMI))


@router.post("/push/deneme", status_code=204)
def deneme(
    k: sqlite3.Row = Depends(HERKES_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    """Kullanıcının kendi cihazlarına sabit bir deneme bildirimi yollar."""
    if not push.etkin_mi():
        raise HTTPException(404)
    push.gonder(conn, [k["id"]], "deneme")
