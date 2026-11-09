"""Öğretmen soru katkısı: cevap anahtarlı PDF yükleme + LLM şıklı soruların onayı; soruhavuzu servis uçları."""

import sqlite3

import analitik
import dosyalar
import soru_katki
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from kaynaklar import soru as havuz

from rotalar.belge_sinav import _oku
from rotalar.bildirim import _servis_anahtari

router = APIRouter()
OGRETMEN = rol("ogretmen", "yonetici")
OGRETMEN_POST = rol("ogretmen", "yonetici", post=True)
GOSTERIM = 30  # sayfada bir seferde gösterilen onay bekleyen soru


def _sayfa(request, conn, k, status=200, **ek):
    bekleyen = soru_katki.onay_bekleyenler(conn, k)
    return render(
        request,
        "ogretmen/soru_katki.html",
        status,
        secenekler=soru_katki.secenekler(conn, k),
        katkilar=soru_katki.katkilarim(conn, k),
        bekleyenler=bekleyen[:GOSTERIM],
        bekleyen_sayi=len(bekleyen),
        adlar=havuz.GORUNEN_AD,
        **ek,
    )


@router.get("/ogretmen/soru-katki")
def sayfa(request: Request, k=Depends(OGRETMEN), conn: sqlite3.Connection = Depends(db_conn)):
    return _sayfa(request, conn, k)


@router.post("/ogretmen/soru-katki")
async def yukle(
    request: Request,
    dosya: UploadFile,
    secim: str = Form(""),
    baslik: str = Form(""),
    cevap: str = Form(""),
    onay: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    if not onay:
        return _sayfa(request, conn, k, 422, hata="Telif ve kişisel veri onayını işaretleyin.")
    sinif, _, ders = secim.partition("|")
    try:
        kid = soru_katki.gonder(
            conn, k, int(sinif or 0), ders, baslik, dosya.filename or "", await _oku(dosya, dosyalar.PLAN_AZAMI), cevap
        )
    except PermissionError:
        raise HTTPException(404) from None
    except (dosyalar.DosyaHatasi, soru_katki.KatkiHatasi) as e:
        return _sayfa(request, conn, k, 422, hata=str(e))
    except ValueError:
        raise HTTPException(404) from None
    analitik.istekten(request, "ogretmen_soru_katki", str(kid))
    return RedirectResponse("/ogretmen/soru-katki?m=sirada#katkilar", status_code=303)


@router.post("/ogretmen/soru-katki/karar")
def karar(
    soru_id: int = Form(...),
    karar: str = Form(""),
    k=Depends(OGRETMEN_POST),
    conn: sqlite3.Connection = Depends(db_conn),
):
    try:
        soru_katki.karar_ver(conn, k, soru_id, karar)
    except PermissionError:
        raise HTTPException(404) from None
    except soru_katki.KatkiHatasi as e:
        raise HTTPException(400, str(e)) from e
    return RedirectResponse("/ogretmen/soru-katki#onay", status_code=303)


# --- soruhavuzu `katki` turu (yalnız LAN + X-Soru-Anahtar) ---


@router.get("/api/soru-katki")
def api_bekleyen(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    _servis_anahtari(request)
    return JSONResponse({"katkilar": soru_katki.bekleyenler(conn), "kararlar": soru_katki.uygulanacak_kararlar(conn)})


@router.get("/api/soru-katki/{katki_id}/pdf")
def api_pdf(katki_id: int, request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    _servis_anahtari(request)
    kt = soru_katki.getir(conn, katki_id)
    if kt is None:
        raise HTTPException(404)
    yol = dosyalar.yol("pdf", kt["depo_adi"])
    if not yol.exists():
        raise HTTPException(404)
    return FileResponse(yol, media_type="application/pdf")


@router.post("/api/soru-katki/{katki_id}/sonuc")
async def api_sonuc(katki_id: int, request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    _servis_anahtari(request)
    g = await request.json()
    try:
        ok = soru_katki.sonuc(conn, katki_id, str(g.get("durum", "")), int(g.get("eklenen", 0)), str(g.get("not", "")))
    except (soru_katki.KatkiHatasi, ValueError, TypeError) as e:
        raise HTTPException(400, str(e)) from e
    if not ok:
        raise HTTPException(404)
    return JSONResponse({"tamam": True})


@router.post("/api/soru-katki/kararlar")
async def api_kararlar(request: Request, conn: sqlite3.Connection = Depends(db_conn)):
    _servis_anahtari(request)
    g = await request.json()
    try:
        n = soru_katki.kararlar_uygulandi(conn, [int(i) for i in g.get("uygulandi", [])])
    except (ValueError, TypeError) as e:
        raise HTTPException(400, str(e)) from e
    return JSONResponse({"tamam": True, "guncellenen": n})
