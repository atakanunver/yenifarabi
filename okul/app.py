"""Dijital Okul — FastAPI uygulaması (port 9090, farabi-okul.service)."""

from contextlib import asynccontextmanager

import auth
import db
from ayarlar import KOK
from deps import GirisGerekli, SifreDegistirmeli, https_mi, render
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from rotalar import belge_sinav, giris, ogrenci, ogretmen, veli, yonetici


@asynccontextmanager
async def omur(_app):
    db.sema_kur()
    yield


app = FastAPI(
    title="Dijital Okul", docs_url=None, redoc_url=None, openapi_url=None, lifespan=omur
)
app.mount("/static", StaticFiles(directory=str(KOK / "static")), name="static")
for r in (giris, belge_sinav, ogrenci, veli, ogretmen, yonetici):
    app.include_router(r.router)


@app.middleware("http")
async def basliklar(request: Request, call_next):
    yanit = await call_next(request)
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
