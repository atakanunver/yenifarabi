"""FastAPI bağımlılıkları: DB, oturum, rol + CSRF kontrolü, şablon render."""

import hmac
import json
import sqlite3
import time
from datetime import datetime

import anket
import auth
import avatar
import db
import duyurular
import push
import acil
import kutu
import sohbet
from ayarlar import AYAR, KOK
from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
import tema
import zaman
from kaynaklar import KaynakHatasi, zil
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
TEMPLATES.env.globals["TEMALAR"] = tema.TEMALAR
# Yeni modül bağlantıları: yalnızca bu kodu çalıştıran süreçte tanımlı (şablonlarda `MODULLER is defined`).
TEMPLATES.env.globals["push_etkin"] = push.etkin_mi  # VAPID ayarlıysa bildirim bağlantıları görünür
TEMPLATES.env.globals["MODULLER"] = True
TEMPLATES.env.globals["avatar_svg"] = avatar.svg
TEMPLATES.env.globals["OYUN_NAV"] = True  # öğrenci alt menüsü oyun odaklı (yalnızca bu kodu çalıştıran süreçte)


KANAL_ADLARI = {"web": "Okul web sitesi", "instagram": "Instagram", "youtube": "YouTube"}


def _kanallar(rol: str | None = None) -> list[dict]:
    """Okulun dijital kanalları (config/kanallar.json: {"web": "https://...", ...}). Yalnızca https adresleri ve bilinen
    kanal adları alınır (javascript: vb. geçemez); dosya yok/bozuksa boş liste döner, sayfa bozulmaz."""
    try:
        veri = json.loads(AYAR.kanallar_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        veri = {}
    if not isinstance(veri, dict):
        veri = {}
    sonuc = []
    for anahtar, ad in KANAL_ADLARI.items():
        url = veri.get(anahtar)
        if isinstance(url, str) and url.startswith("https://") and len(url) <= 300 and " " not in url:
            sonuc.append({"anahtar": anahtar, "ad": ad, "url": url})
    # WhatsApp grupları: davet bağlantısı anahtar gibidir → herkese açık sayfada (giriş dahil) GÖSTERİLMEZ; her grup yalnızca
    # kendi rolüne (ve yöneticiye) görünür: veli grubu veliye, öğrenci grubu öğrenciye.
    for ad, wa, roller in (
        ("Veli WhatsApp grubu", AYAR.whatsapp_veli, ("veli", "yonetici")),
        ("Öğrenci WhatsApp grubu", AYAR.whatsapp_ogrenci, ("ogrenci", "yonetici")),
    ):
        if rol in roller and wa.startswith("https://chat.whatsapp.com/") and len(wa) <= 300 and " " not in wa:
            sonuc.append({"anahtar": "whatsapp", "ad": ad, "url": wa})
    return sonuc


TEMPLATES.env.globals["kanallar"] = _kanallar


def _saat_verisi() -> dict:
    # epoch: telefonun saati yanlışsa saat.js sunucu saatine göre düzeltir
    return {**zil.widget_verisi(zaman.simdi()), "epoch": int(time.time() * 1000)}


def _zil_cizelgesi() -> list[tuple[int, str, str]] | None:
    try:
        return zil.dersler() or None
    except KaynakHatasi:
        return None


TEMPLATES.env.globals["saat_verisi"] = _saat_verisi
TEMPLATES.env.globals["zil_cizelgesi"] = _zil_cizelgesi
TEMPLATES.env.globals["ogle_arasi"] = zil.ogle_arasi


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


def _anket_bekleyen(k) -> int:
    """Yanıt bekleyen anket sayısı (öğrenci/veli/öğretmen). Hata sayfayı bozmaz: 0 döner."""
    if k is None or k["rol"] not in anket.ROLLER or k["sifre_degismeli"]:
        return 0
    try:
        c = db.baglanti()
        try:
            return anket.bekleyen_sayisi(c, k)
        finally:
            c.close()
    except Exception:  # noqa: BLE001 — bildirim isteğe bağlıdır, sayfa açılmalı
        return 0


def _sohbet_okunmamis(request: Request, k) -> int:
    """Öğretmen/yönetici ana sayfasındaki sohbet kartı için okunmamış mesaj sayısı. Hata sayfayı bozmaz: 0 döner."""
    if k is None or k["rol"] not in sohbet.ROLLER or request.url.path not in ("/ogretmen", "/yonetici"):
        return 0
    try:
        c = db.baglanti()
        try:
            return sohbet.okunmamis_sayisi(c, k["id"])
        finally:
            c.close()
    except Exception:  # noqa: BLE001 — sayaç isteğe bağlıdır
        return 0


def _kutu_yeni(request: Request, k) -> int:
    """Yönetici ana sayfasındaki kutu kartı için 'yeni' kayıt sayısı. Hata sayfayı bozmaz: 0 döner."""
    if k is None or k["rol"] != "yonetici" or request.url.path != "/yonetici":
        return 0
    try:
        c = db.baglanti()
        try:
            return kutu.yeni_sayisi(c)
        finally:
            c.close()
    except Exception:  # noqa: BLE001 — sayaç isteğe bağlıdır
        return 0


def _duyuru_okunmamis(request: Request, k) -> int:
    """Rol ana sayfasındaki duyuru bağlantısı için okunmamış sayısı. Hata sayfayı bozmaz: 0 döner."""
    if k is None or request.url.path not in ("/ogrenci", "/veli", "/ogretmen"):
        return 0
    try:
        c = db.baglanti()
        try:
            return duyurular.okunmamis_sayisi(c, k)
        finally:
            c.close()
    except Exception:  # noqa: BLE001 — sayaç isteğe bağlıdır
        return 0


def _acil_aktif(k):
    """Öğretmen/yönetici sayfalarındaki kırmızı şerit için aktif alarm (yoksa None). Hata sayfayı bozmaz: None döner."""
    if k is None or k["rol"] not in acil.ROLLER or k["sifre_degismeli"]:
        return None
    try:
        c = db.baglanti()
        try:
            return acil.aktif(c)
        finally:
            c.close()
    except Exception:  # noqa: BLE001 — şerit isteğe bağlıdır
        return None


def render(request: Request, sablon: str, status_code: int = 200, **ctx):
    ctx.setdefault("k", getattr(request.state, "kullanici", None))
    ctx.setdefault("anket_bekleyen", _anket_bekleyen(ctx["k"]))
    ctx.setdefault("sohbet_okunmamis", _sohbet_okunmamis(request, ctx["k"]))
    ctx.setdefault("duyuru_okunmamis", _duyuru_okunmamis(request, ctx["k"]))
    ctx.setdefault("acil_aktif", _acil_aktif(ctx["k"]))
    ctx.setdefault("kutu_yeni", _kutu_yeni(request, ctx["k"]))
    ctx["csrf"] = getattr(request.state, "csrf", "")
    ctx.setdefault("bugun_gun", GUNLER[zaman.simdi().weekday()])
    return TEMPLATES.TemplateResponse(request, sablon, ctx, status_code=status_code)
