"""tahtayoklama dashboard → okul: öğretmen bir dersi 'yok' kaydettiğinde veliye anlık push (yalnız LAN, servis anahtarlı)."""

import hmac

import push
from ayarlar import AYAR
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import JSONResponse
from rotalar.pano import _lan_mi

router = APIRouter()


@router.post("/api/devamsizlik-bildir")
async def devamsizlik_bildir(request: Request, arka: BackgroundTasks):
    """Gövde (JSON): {"okul_no_listesi": [int, ...]} — o an 'yok' yazılan öğrencilerin okul numaraları.
    Tünelden (cf-*/x-forwarded-*) gelirse ya da X-Devamsizlik-Anahtar yanlış/tanımsızsa 404."""
    if not _lan_mi(request):
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
