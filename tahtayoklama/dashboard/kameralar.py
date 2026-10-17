"""kameralar.py — Okul güvenlik kameraları canlı izleme (WebRTC/mediamtx).
Kaynak akışlar ~/farabi/kameralar/ altında (mediamtx + ffmpeg), elle start.sh/stop.sh ile
yönetilir — bu route sadece hazır mediamtx WebRTC akışlarını ızgara halinde gösterir.
İki sayfa: /kameralar (DVR, ana) ve /kameralar-ip (bağımsız IP kameralar, DVR arıza
yaparsa yedek — 2026-10-16 eklendi; aynı fiziksel kameralar, farklı kaynaktan).
2026-10-15/16 Müdür PC üzerinden SSH ile kuruldu."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import menu

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci


async def _goster(request: Request, sablon: str):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    return templates.TemplateResponse(request, sablon, {})


@router.get("/kameralar", response_class=HTMLResponse)
async def kameralar_sayfa(request: Request):
    return await _goster(request, "kameralar.html")


@router.get("/kameralar-ip", response_class=HTMLResponse)
async def kameralar_ip_sayfa(request: Request):
    return await _goster(request, "kameralar_ip.html")
