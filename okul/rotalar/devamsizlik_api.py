"""tahtayoklama dashboard → okul: öğretmen bir dersi 'yok' kaydettiğinde veliye anlık push (yalnız LAN, servis anahtarlı)."""

import hmac
import sqlite3

import push
from ayarlar import AYAR
from deps import db_conn
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.post("/api/devamsizlik-bildir")
async def devamsizlik_bildir(request: Request, arka: BackgroundTasks, conn: sqlite3.Connection = Depends(db_conn)):
    """Gövde (JSON): {"okul_no_listesi": [int, ...]} — o an 'yok' yazılan öğrencilerin okul numaraları.
    Tünelden (cf-*/x-forwarded-*) gelirse ya da X-Devamsizlik-Anahtar yanlış/tanımsızsa 404."""
    basliklar = {b.lower() for b in request.headers.keys()}
    if any(b.startswith("cf-") or b.startswith("x-forwarded-") for b in basliklar):
        raise HTTPException(404)
    verilen = request.headers.get("x-devamsizlik-anahtar", "")
    if not AYAR.devamsizlik_anahtar or not hmac.compare_digest(verilen, AYAR.devamsizlik_anahtar):
        raise HTTPException(404)
    try:
        g = await request.json()
        okul_no_listesi = [int(x) for x in g["okul_no_listesi"]]
    except (ValueError, KeyError, TypeError, AttributeError):
        return JSONResponse({"tamam": False, "mesaj": "Geçersiz gövde."}, status_code=400)
    arka.add_task(push.devamsizlik_bildir, okul_no_listesi)
    return JSONResponse({"tamam": True})
