"""EBYS botu (Müdür PC) → okul: Telegram tek tuşuyla rol duyurusu ekleme (yalnız LAN, servis anahtarlı)."""

import hmac
import sqlite3
from datetime import timedelta

import duyurular
import push
import zaman
from ayarlar import AYAR
from deps import db_conn
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

router = APIRouter()

YAZAR = "atakan"  # duyurular bu yönetici adına yayınlanır


@router.post("/api/duyuru-ekle")
async def duyuru_ekle(request: Request, arka: BackgroundTasks, conn: sqlite3.Connection = Depends(db_conn)):
    """Gövde (JSON): hedef ogrenci|veli|ogretmen, baslik, metin, gecerlilik_gun (1-90, varsayılan 14).
    Tünelden (cf-*/x-forwarded-*) gelirse ya da X-Duyuru-Anahtar yanlış/tanımsızsa 404."""
    basliklar = {b.lower() for b in request.headers.keys()}
    if any(b.startswith("cf-") or b.startswith("x-forwarded-") for b in basliklar):
        raise HTTPException(404)
    verilen = request.headers.get("x-duyuru-anahtar", "")
    if not AYAR.duyuru_anahtar or not hmac.compare_digest(verilen, AYAR.duyuru_anahtar):
        raise HTTPException(404)
    try:
        g = await request.json()
        hedef = g["hedef"]
        baslik = str(g["baslik"]).strip()
        metin = str(g["metin"]).strip()
        gun = int(g.get("gecerlilik_gun", 14))
    except (ValueError, KeyError, TypeError, AttributeError):
        return JSONResponse({"tamam": False, "mesaj": "Geçersiz gövde."}, status_code=400)
    if hedef not in duyurular.ROLLER or hedef == "yonetici" or not baslik or not metin:
        return JSONResponse({"tamam": False, "mesaj": "Hedef/başlık/metin geçersiz."}, status_code=400)
    yazar = conn.execute(
        "SELECT id FROM kullanici WHERE kullanici_adi = ? AND rol = 'yonetici' AND aktif = 1", (YAZAR,)
    ).fetchone()
    if yazar is None:
        return JSONResponse({"tamam": False, "mesaj": "Yazar hesap yok."}, status_code=500)
    bitis = (zaman.simdi() + timedelta(days=min(max(gun, 1), 90))).strftime(zaman.BICIM)
    did = duyurular.duyuru_ekle(conn, yazar["id"], baslik[:120], metin[:4000], "rol", hedef, bitis)
    arka.add_task(push.duyuru_bildir, "rol", hedef, yazar["id"])
    return JSONResponse({"tamam": True, "id": did})
