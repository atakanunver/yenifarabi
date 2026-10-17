"""Dijital Okul — FastAPI uygulaması (port 9090, farabi-okul.service)."""

import logging
from contextlib import asynccontextmanager

import acil as acil_modul
import analitik
import auth
import db
import sohbet as sohbet_modul
from ayarlar import KOK
from deps import GirisGerekli, SifreDegistirmeli, https_mi, render
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from rotalar import (
    acil,
    anket,
    arena,
    avatar,
    belge_sinav,
    deneme,
    etkinlik,
    gelisim,
    giris,
    kisisel,
    kutu,
    ogrenci,
    oduller,
    ogretmen,
    ogretmen_liderlik,
    oyun,
    pano,
    push,
    sohbet,
    sudoku,
    veli,
    yonetici,
)


@asynccontextmanager
async def omur(_app):
    db.sema_kur()
    sohbet_modul.baslangic_temizligi()
    acil_modul.baslangic_temizligi()
    yield
    analitik.bosalt()


app = FastAPI(
    title="Dijital Okul", docs_url=None, redoc_url=None, openapi_url=None, lifespan=omur
)
app.mount("/static", StaticFiles(directory=str(KOK / "static")), name="static")
for r in (giris, pano, belge_sinav, ogrenci, arena, avatar, anket, gelisim, etkinlik, kisisel, oduller, oyun, veli, deneme, ogretmen_liderlik, ogretmen, yonetici, push, sohbet, kutu, acil, sudoku):
    app.include_router(r.router)


@app.middleware("http")
async def basliklar(request: Request, call_next):
    yanit = await call_next(request)
    analitik.sayfa_goruntulendi(request, yanit.status_code)
    yanit.headers["X-Robots-Tag"] = "noindex, nofollow"
    yanit.headers["X-Content-Type-Options"] = "nosniff"
    yanit.headers["X-Frame-Options"] = "DENY"
    yanit.headers["Referrer-Policy"] = "same-origin"
    if not request.url.path.startswith("/static") and "cache-control" not in yanit.headers:
        yanit.headers["Cache-Control"] = "no-store"  # kişisel veri içeren sayfalar hiçbir yerde saklanmasın
    token = getattr(request.state, "token", None)
    if token and "set-cookie" not in yanit.headers:
        auth.cerez_yaz(yanit, token, https_mi(request))  # kayan 1 yıllık oturum
    return yanit


@app.exception_handler(GirisGerekli)
async def _giris(request: Request, _e):
    return RedirectResponse("/giris", status_code=303)


@app.exception_handler(SifreDegistirmeli)
async def _sifre(request: Request, _e):
    return RedirectResponse("/sifre", status_code=303)


log = logging.getLogger("uvicorn.error")
BAKIM_MESAJI = "Ş.M.U.A.L Bakım Yapılıyor ..."
BAKIM_SAYFASI = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Ş.M.U.A.L Bakım Yapılıyor</title>
<style>
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;text-align:center;padding:1.5rem;
background:#0a1030;color:#eaf1ff;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:26rem}h1{font-size:1.6rem;margin:.6rem 0}p{color:#a9b8e0;line-height:1.5}
.simge{font-size:3rem}a{display:inline-block;margin-top:1rem;padding:.8rem 1.4rem;border-radius:12px;background:#22d3ee;
color:#0a1030;font-weight:700;text-decoration:none}
</style></head><body><main>
<div class="simge" aria-hidden="true">🛠️</div>
<h1>Ş.M.U.A.L Bakım Yapılıyor ...</h1>
<p>Sistem kısa bir süre için bakımda. Birkaç dakika içinde otomatik olarak yenilenecek.</p>
<a href="/">Şimdi yenile</a>
</main></body></html>"""


@app.exception_handler(Exception)
async def _beklenmeyen(request: Request, e: Exception):
    """Beklenmeyen sunucu hatası: kullanıcı ham 'Internal Server Error' yerine bakım mesajı görür (hata yine günlüğe düşer)."""
    log.error("Beklenmeyen hata: %s %s", request.method, request.url.path, exc_info=e)
    basliklar = {"Cache-Control": "no-store", "Retry-After": "30"}
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mesaj": BAKIM_MESAJI}, status_code=503, headers=basliklar)
    return HTMLResponse(BAKIM_SAYFASI, status_code=503, headers=basliklar)


@app.exception_handler(HTTPException)
async def _hata(request: Request, e: HTTPException):
    if e.status_code == 404:
        mesaj = "Aradığın sayfa yok ya da bu sayfayı görme yetkin yok."
    else:
        mesaj = e.detail or "Bir şeyler ters gitti."
    return render(
        request, "hata.html", status_code=e.status_code, kod=e.status_code, mesaj=mesaj
    )


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    return FileResponse(
        KOK / "static" / "sw.js",
        media_type="text/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/manifest.webmanifest", include_in_schema=False)
async def manifest():
    return FileResponse(
        KOK / "static" / "manifest.webmanifest", media_type="application/manifest+json"
    )
