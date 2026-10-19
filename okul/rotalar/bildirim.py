"""Soru bildirimi: öğrenci "bu soruda sorun var" der; yönetici listeyi görür; soruhavuzu gece turunda okur."""

import hmac
import sqlite3

import analitik
import dosyalar
import sinifpdf
import soru_bildirim
from ayarlar import AYAR
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from kaynaklar import KaynakHatasi
from kaynaklar import soru as havuz

router = APIRouter()


def _geri_yol(yol: str, onek: str = "/ogrenci") -> str:
    """Açık yönlendirmeyi önle: yalnızca verilen önek altındaki yerel yollar."""
    if yol.startswith(onek + "/") and "//" not in yol and "\\" not in yol and "\n" not in yol:
        return yol
    return onek


def _json_mu(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "")


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


@router.post("/ogretmen/soru-bildir")
def ogretmen_bildir(
    soru_id: int = Form(...),
    tur: str = Form(...),
    kaynak: str = Form("odev"),
    geri: str = Form("/ogretmen"),
    request: Request = None,
    k=Depends(rol("ogretmen", "yonetici", post=True)),
    conn: sqlite3.Connection = Depends(db_conn),
):
    """Öğretmen/yönetici havuzdaki herhangi bir soruyu bildirir (ağırlık 2: tek bildirim soruyu gizler)."""
    try:
        yeni = soru_bildirim.bildir(conn, k["id"], soru_id, tur, rol=k["rol"], kaynak=kaynak[:20])
    except soru_bildirim.BildirimHatasi as e:
        if _json_mu(request):
            return JSONResponse({"tamam": False, "mesaj": str(e)}, status_code=400)
        raise HTTPException(400, str(e)) from e
    if yeni:
        analitik.istekten(request, "soru_bildir", str(soru_id))
    if _json_mu(request):
        return JSONResponse({"tamam": True, "yeni": yeni})
    return RedirectResponse(_geri_yol(geri, "/ogretmen"), status_code=303)


@router.post("/yonetici/soru-bildirimleri/{soru_id}/iptal")
def iptal(soru_id: int, k=Depends(rol("yonetici", post=True)), conn: sqlite3.Connection = Depends(db_conn)):
    """"Sorun yok": bu sorunun mevcut bildirimleri sayılmaz, soru okulda yeniden açılır."""
    soru_bildirim.iptal_et(conn, soru_id)
    return RedirectResponse("/yonetici/soru-bildirimleri", status_code=303)


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


def _servis_anahtari(request: Request) -> None:
    """soruhavuzu → okul uçları: tünelden (cf-*/x-forwarded-*) gelirse 404; anahtar (X-Soru-Anahtar) yoksa/yanlışsa 404."""
    basliklar = {b.lower() for b in request.headers.keys()}
    if any(b.startswith("cf-") or b.startswith("x-forwarded-") for b in basliklar):
        raise HTTPException(404)
    verilen = request.headers.get("x-soru-anahtar", "")
    if not AYAR.soru_anahtar or not hmac.compare_digest(verilen, AYAR.soru_anahtar):
        raise HTTPException(404)


@router.get("/api/soru-istek")
def api_istekler(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    """Soru havuzuna katkı için sırada bekleyen öğretmen PDF'leri (kişi/öğretmen bilgisi dönmez)."""
    _servis_anahtari(request)
    return JSONResponse({"istekler": [dict(r) for r in sinifpdf.bekleyen_istekler(conn)]})


@router.get("/api/soru-istek/{pdf_id}/pdf")
def api_pdf(pdf_id: int, request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    _servis_anahtari(request)
    p = sinifpdf.pdf_getir(conn, pdf_id)
    if p is None or not p["soru_uret"]:
        raise HTTPException(404)
    yol = dosyalar.yol("pdf", p["depo_adi"])
    if not yol.exists():
        raise HTTPException(404)
    return FileResponse(yol, media_type="application/pdf")


@router.post("/api/soru-istek/{pdf_id}/sonuc")
async def api_sonuc(pdf_id: int, request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    _servis_anahtari(request)
    govde = await request.json()
    try:
        ok = sinifpdf.soru_sonucu(
            conn, pdf_id, str(govde.get("durum", "")), int(govde.get("onayli", 0)), int(govde.get("red", 0)),
            str(govde.get("not", "")),
        )
    except (sinifpdf.PdfHatasi, ValueError, TypeError) as e:
        raise HTTPException(400, str(e)) from e
    if not ok:
        raise HTTPException(404)
    return JSONResponse({"tamam": True})


@router.post("/api/soru-bildirim")
async def api_tahta(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    """Tahta Sınıf Arenası: {soru_id, tur, sube}. Kimlik yok; şube düzeyinde, günde bir kez, ağırlık 1."""
    _servis_anahtari(request)
    try:
        govde = await request.json()
        yeni = soru_bildirim.bildir_tahta(conn, int(govde.get("soru_id", 0)), str(govde.get("tur", "")), str(govde.get("sube", "")))
    except (soru_bildirim.BildirimHatasi, ValueError, TypeError, AttributeError) as e:
        raise HTTPException(400, str(e)) from e
    return JSONResponse({"tamam": True, "yeni": yeni})


@router.get("/api/soru-bildirim")
def api(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    """soruhavuzu gece turu için: soru başına {soru_id, kisi, turler}. Kişi bilgisi dönmez, yalnızca sayılar."""
    _servis_anahtari(request)
    return JSONResponse({"esik": soru_bildirim.ESIK, "sorular": soru_bildirim.ozet(conn)})
