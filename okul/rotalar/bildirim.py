"""Soru bildirimi: öğrenci "bu soruda sorun var" der; yönetici listeyi görür; soruhavuzu gece turunda okur."""

import hmac
import sqlite3

import analitik
import soru_bildirim
from ayarlar import AYAR
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from kaynaklar import KaynakHatasi, soru as havuz

router = APIRouter()


def _geri_yol(yol: str) -> str:
    """Açık yönlendirmeyi önle: yalnızca /ogrenci/ altındaki yerel yollar."""
    if yol.startswith("/ogrenci/") and "//" not in yol and "\\" not in yol and "\n" not in yol:
        return yol
    return "/ogrenci"


@router.post("/ogrenci/soru-bildir")
def bildir(
    soru_id: int = Form(...),
    tur: str = Form(...),
    geri: str = Form("/ogrenci"),
    request: Request = None,
    k=Depends(rol("ogrenci", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        yeni = soru_bildirim.bildir(conn, k["id"], soru_id, tur)
    except soru_bildirim.BildirimHatasi as e:
        raise HTTPException(400, str(e)) from e
    if yeni:
        analitik.istekten(request, "soru_bildir", str(soru_id))
    return RedirectResponse(_geri_yol(geri), status_code=303)


@router.get("/yonetici/soru-bildirimleri")
def liste(request: Request, k=Depends(rol("yonetici")), conn: sqlite3.Connection = Depends(db_conn)):
    satirlar = soru_bildirim.ozet(conn)
    try:
        sorular = havuz.getir([s["soru_id"] for s in satirlar])
        hata = False
    except KaynakHatasi:
        sorular, hata = {}, True
    gizli = set(soru_bildirim.gizli_idler(conn))
    return render(
        request,
        "yonetici/soru_bildirimleri.html",
        satirlar=satirlar,
        sorular=sorular,
        gizli=gizli,
        turler=soru_bildirim.TURLER,
        esik=soru_bildirim.ESIK,
        hata=hata,
    )


@router.get("/api/soru-bildirim")
def api(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    """soruhavuzu gece turu için: soru başına {soru_id, kisi, turler}. Tünelden (cf-*/x-forwarded-*) gelirse 404;
    anahtar (X-Soru-Anahtar) yoksa/yanlışsa 404. Kişi bilgisi dönmez, yalnızca sayılar."""
    basliklar = {b.lower() for b in request.headers.keys()}
    if any(b.startswith("cf-") or b.startswith("x-forwarded-") for b in basliklar):
        raise HTTPException(404)
    verilen = request.headers.get("x-soru-anahtar", "")
    if not AYAR.soru_anahtar or not hmac.compare_digest(verilen, AYAR.soru_anahtar):
        raise HTTPException(404)
    return JSONResponse({"esik": soru_bildirim.ESIK, "sorular": soru_bildirim.ozet(conn)})
