"""FastAPI bağımlılıkları: DB, oturum, rol + CSRF kontrolü, şablon render."""

import hmac
import sqlite3
from datetime import datetime

import auth
import db
from ayarlar import KOK
from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
import zaman
from kaynaklar.program import GUN_ADLARI, GUNLER

ANA_SAYFA = {
    "ogrenci": "/ogrenci",
    "veli": "/veli",
    "ogretmen": "/ogretmen",
    "yonetici": "/yonetici",
}
ROL_ADLARI = {
    "ogrenci": "Öğrenci",
    "veli": "Veli",
    "ogretmen": "Öğretmen",
    "yonetici": "Yönetici",
}
SIFRESIZ_YOLLAR = ("/sifre", "/cikis")

TEMPLATES = Jinja2Templates(directory=str(KOK / "templates"))


def _tarih(s: str | None, saatli: bool = True) -> str:
    if not s:
        return ""
    for bicim in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, bicim)
            break
        except ValueError:
            continue
    else:
        return s
    if saatli and bicim != "%Y-%m-%d":
        return dt.strftime("%d.%m.%Y %H:%M")
    return dt.strftime("%d.%m.%Y")


TEMPLATES.env.filters["tarih"] = _tarih
TEMPLATES.env.filters["gun_adi"] = lambda g: GUN_ADLARI.get(g, g)
TEMPLATES.env.filters["baslik"] = lambda s: (s or "")[:1].upper() + (s or "")[1:]
TEMPLATES.env.globals["ROL_ADLARI"] = ROL_ADLARI


class GirisGerekli(Exception):
    pass


class SifreDegistirmeli(Exception):
    pass


def db_conn():
    c = db.baglanti()
    try:
        yield c
    finally:
        c.close()


def istemci_ip(request: Request) -> str:
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1"):  # cloudflared yerelden bağlanır
        return request.headers.get("cf-connecting-ip") or host
    return host


def https_mi(request: Request) -> bool:
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
    )


def mevcut_kullanici(
    request: Request, conn: sqlite3.Connection = Depends(db_conn)
) -> sqlite3.Row:
    token = request.cookies.get(auth.COOKIE_ADI)
    k = auth.oturum_kullanici(conn, token)
    if k is None:
        raise GirisGerekli
    request.state.kullanici = k
    request.state.token = token
    request.state.csrf = auth.csrf_token(token)
    if k["sifre_degismeli"] and request.url.path not in SIFRESIZ_YOLLAR:
        raise SifreDegistirmeli
    return k


def rol(*roller: str, post: bool = False):
    async def bagimlilik(
        request: Request, k: sqlite3.Row = Depends(mevcut_kullanici)
    ) -> sqlite3.Row:
        if roller and k["rol"] not in roller:
            raise HTTPException(404)
        if post:
            form = await request.form()
            if not hmac.compare_digest(str(form.get("csrf", "")), request.state.csrf):
                raise HTTPException(
                    400, "Sayfanın süresi dolmuş. Sayfayı yenileyip tekrar deneyin."
                )
        return k

    return bagimlilik


def render(request: Request, sablon: str, status_code: int = 200, **ctx):
    ctx.setdefault("k", getattr(request.state, "kullanici", None))
    ctx["csrf"] = getattr(request.state, "csrf", "")
    ctx.setdefault("bugun_gun", GUNLER[zaman.simdi().weekday()])
    return TEMPLATES.TemplateResponse(request, sablon, ctx, status_code=status_code)
