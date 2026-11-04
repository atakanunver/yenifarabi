"""Farabi Atlas portal içinde: /kure (SPA) ve /api/atlas istekleri öğretmen girişiyle :8099'a proxy'lenir.

Atlas ayrı servis ve ayrı DB'dir (tahtaatlasfarabi/); burada yalnızca giriş kapısı + aynı origin (smual.app dahil) sağlanır.
Atlas kendi CSRF'ini form alanıyla doğrular; gövde aynen iletilir. Çerez ve cf-*/x-forwarded-* başlıkları Atlas'a gitmez.
"""

import httpx
from ayarlar import AYAR
from deps import render, rol
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

router = APIRouter()
OGRETMEN = rol("ogretmen", "yonetici")
_GIDEN = ("content-type", "range", "if-none-match", "if-modified-since")
_DONEN = ("content-type", "content-range", "accept-ranges", "cache-control", "etag", "last-modified", "location")


def _ilet(yontem: str, url: str, icerik: bytes, basliklar: dict) -> httpx.Response:
    return httpx.request(yontem, url, content=icerik, headers=basliklar, timeout=15, follow_redirects=False, trust_env=False)


async def _proxy(request: Request) -> Response:
    url = AYAR.atlas_url + request.url.path + (f"?{request.url.query}" if request.url.query else "")
    basliklar = {a: request.headers[a] for a in _GIDEN if a in request.headers}
    icerik = await request.body()
    try:
        r = await run_in_threadpool(_ilet, request.method, url, icerik, basliklar)
    except httpx.HTTPError:
        return Response("Atlas servisine ulaşılamadı; biraz sonra yeniden deneyin.", status_code=502, media_type="text/plain; charset=utf-8")
    donen = {a: r.headers[a] for a in _DONEN if a in r.headers}
    if "location" in donen and donen["location"].startswith(AYAR.atlas_url):
        donen["location"] = donen["location"][len(AYAR.atlas_url):] or "/"
    # Middleware başlıksız yanıta no-store koyar; harita verisi (catalog.json 3,4 MB) her açılışta tünelden inmesin:
    # karma adlı assets kalıcı, diğerleri ETag ile yeniden doğrulanır (304).
    if "cache-control" not in donen and request.url.path.startswith("/kure/"):
        donen["cache-control"] = "public, max-age=31536000, immutable" if request.url.path.startswith("/kure/assets/") else "no-cache"
    return Response(r.content, status_code=r.status_code, headers=donen)


@router.get("/ogretmen/atlas")
def sayfa(request: Request, k=Depends(OGRETMEN)):
    return render(request, "ogretmen/atlas.html")


@router.get("/kure", include_in_schema=False)
def egik_cizgi(k=Depends(OGRETMEN)):
    return RedirectResponse("/kure/", status_code=307)


@router.api_route("/kure/{yol:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def kure(request: Request, yol: str, k=Depends(OGRETMEN)):
    return await _proxy(request)


@router.api_route("/api/atlas/{yol:path}", methods=["GET", "POST"], include_in_schema=False)
async def api(request: Request, yol: str, k=Depends(OGRETMEN)):
    return await _proxy(request)
