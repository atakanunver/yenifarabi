"""guvenlik.py — Kapıdaki güvenlik personeli ekranı (2026-10-18).

/guvenlik: kamera ızgarası + birkaç büyük düğme. Güvenlikçi buradan
  - 4 acil alarmdan birini (Kilit-kapı / Tahliye / Yangın / Deprem) tek onayla,
    GERÇEK ya da TATBİKAT olarak başlatır (acil._baslat — /acil ile aynı kanallar),
  - aktif alarmı "yanlış alarm" olarak iptal eder (acil._yanlis_alarm),
  - sessizce yönetime haber verir: sabit 4 neden, Telegram + 2 yöneticiye SMS
    (siren/anons/tahta ekranı YOK).
Yetki: dashboard'un ortak yönetici şifresinden AYRI bir güvenlik şifresi
(config/guvenlik.json, gitignore). Güvenlik çerezi yalnız bu modülün yollarında
geçerlidir; /acil, /admin vb. onu tanımaz (onlar auth.dogrula'nın "oturum"
çerezine bakar). Yönetici oturumu /guvenlik'i de açabilir.
"""

import asyncio
import hashlib
import hmac
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import acil
import auth
import db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

DIZIN = Path(__file__).resolve().parent
CONFIG = DIZIN / "config" / "guvenlik.json"
HAREKET_DURUM = Path.home() / "farabi" / "kameralar" / "hareket" / "durum.json"
MEDIAMTX_API = "http://127.0.0.1:9997/v3/paths/list"
COOKIE_ADI = "guvenlik_oturum"
OTURUM_SN = (
    60 * 60
)  # görevli kalkınca başkası kullanamasın: girişten 1 saat sonra şifre tekrar sorulur
ALARMLAR = ("kilit", "tahliye", "yangin", "deprem")
NEDENLER = {
    "supheli": "Şüpheli kişi / araç",
    "kavga": "Kavga / kargaşa",
    "saglik": "Sağlık sorunu / ambulans",
    "yonetici": "Yönetici kapıya çağrılıyor",
}
HABER_ARALIK_SN = 30  # aynı neden art arda basılırsa SMS tekrar gitmesin
_son_haber: dict[str, float] = {}


def _ayar() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def _imza(anahtar: str, zaman: str) -> str:
    return hmac.new(
        bytes.fromhex(anahtar), f"guvenlik:{zaman}".encode(), hashlib.sha256
    ).hexdigest()


def cerez_uret(a: dict, simdi: float | None = None) -> str:
    zaman = str(int(simdi if simdi is not None else time.time()))
    return f"{zaman}.{_imza(a['anahtar'], zaman)}"


def cerez_gecerli(a: dict, deger: str | None, simdi: float | None = None) -> bool:
    try:
        zaman, imza = (deger or "").split(".", 1)
        yas = (simdi if simdi is not None else time.time()) - int(zaman)
    except ValueError:
        return False
    return 0 <= yas <= OTURUM_SN and hmac.compare_digest(
        imza, _imza(a["anahtar"], zaman)
    )


def yetkili(request: Request) -> bool:
    deger = request.cookies.get(COOKIE_ADI)
    if deger:
        try:
            if cerez_gecerli(_ayar(), deger):
                return True
        except (OSError, ValueError, KeyError):
            pass
    conn = db.baglanti()
    try:
        return auth.dogrula(request, conn)
    finally:
        conn.close()


def _dogrula(request: Request) -> None:
    if not yetkili(request):
        raise HTTPException(401, "Oturum geçersiz.")


def _kaynak(request: Request) -> str:
    return f"guvenlik:{request.client.host}" if request.client else "guvenlik"


def _simdi() -> datetime:
    return datetime.now(acil.ISTANBUL)


@router.get("/guvenlik/giris", response_class=HTMLResponse)
async def giris_formu(request: Request):
    return templates.TemplateResponse(request, "guvenlik_giris.html", {"hata": None})


@router.post("/guvenlik/giris")
async def giris_gonder(request: Request, sifre: str = Form(...)):
    a = _ayar()
    if not auth.sifre_dogrula(sifre, a["sifre_hash"]):
        await asyncio.sleep(1)  # LAN'dan deneme-yanılmayı yavaşlatır
        return templates.TemplateResponse(
            request, "guvenlik_giris.html", {"hata": "Şifre yanlış."}, status_code=401
        )
    yanit = RedirectResponse("/guvenlik", status_code=303)
    yanit.set_cookie(
        COOKIE_ADI, cerez_uret(a), httponly=True, samesite="lax", max_age=OTURUM_SN
    )
    return yanit


@router.post("/guvenlik/cikis")
async def cikis():
    """KİLİTLE düğmesi: görevli yerinden kalkarken ekranı hemen kilitler."""
    yanit = RedirectResponse("/guvenlik/giris", status_code=303)
    yanit.delete_cookie(COOKIE_ADI)
    return yanit


@router.get("/guvenlik", response_class=HTMLResponse)
async def guvenlik_sayfa(request: Request):
    if not yetkili(request):
        return RedirectResponse("/guvenlik/giris", status_code=303)
    try:
        telefonlar = _ayar().get("telefonlar") or []
    except OSError:
        telefonlar = []
    return templates.TemplateResponse(
        request,
        "guvenlik.html",
        {
            "alarmlar": {k: acil.TURLER[k] for k in ALARMLAR},
            "nedenler": NEDENLER,
            "telefonlar": telefonlar or [{"ad": "Acil", "no": "112"}],
        },
    )


def _kamera_durumu() -> dict | None:
    """mediamtx API (yalnız 127.0.0.1) → {yol: hazır mı}. API kapalıysa None
    (ekran o zaman kaynak değiştirmez)."""
    try:
        acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with acici.open(MEDIAMTX_API, timeout=2) as y:
            return {
                p["name"]: bool(p.get("ready")) for p in json.loads(y.read())["items"]
            }
    except Exception:
        return None


def _hareket_durumu() -> dict:
    """hareket.py'nin yazdığı {yol: son hareket unix zamanı}."""
    try:
        return json.loads(HAREKET_DURUM.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@router.get("/api/guvenlik/durum")
async def durum(request: Request):
    _dogrula(request)
    aktif = acil.aktif_alarm(acil.son_olaylar())
    return JSONResponse(
        {
            "aktif": {
                "tur": aktif["tur"],
                "baslik": acil.TURLER.get(aktif["tur"], {}).get("baslik", aktif["tur"]),
                "tatbikat": bool(aktif.get("tatbikat")),
                "zaman": aktif.get("zaman"),
            }
            if aktif
            else None,
            "kameralar": await asyncio.to_thread(_kamera_durumu),
            "hareket": _hareket_durumu(),
            "simdi": time.time(),
        }
    )


def _ozet(kayit: dict) -> dict:
    tahtalar = kayit.get("tahtalar") or []
    return {
        "kanallar": [
            {"kanal": k.get("kanal"), "basarili": bool(k.get("basarili"))}
            for k in kayit.get("kanallar") or []
        ],
        "tahta_toplam": len(tahtalar),
        "tahta_basarili": sum(1 for t in tahtalar if t.get("basarili")),
    }


@router.post("/api/guvenlik/alarm")
async def alarm(request: Request):
    _dogrula(request)
    govde = await request.json()
    tur, tatbikat = govde.get("tur"), govde.get("tatbikat")
    if tur not in ALARMLAR or not isinstance(tatbikat, bool):
        raise HTTPException(400, "Geçersiz alarm.")
    kayit = await acil._baslat(acil._ayarlar(), tur, tatbikat, kaynak=_kaynak(request))
    return JSONResponse(_ozet(kayit))


@router.post("/api/guvenlik/iptal")
async def iptal(request: Request):
    _dogrula(request)
    if acil.aktif_alarm(acil.son_olaylar()) is None:
        raise HTTPException(409, "Aktif alarm yok.")
    kayit = await acil._yanlis_alarm(acil._ayarlar(), _kaynak(request))
    return JSONResponse(_ozet(kayit))


def haber_metni(neden: str, saat: str) -> str:
    return f"GÜVENLİK: {NEDENLER[neden]} — kapı, saat {saat}."


def _haber_sms(a: dict, metin: str) -> dict:
    """/api/arac/acil = yönetim (2 kişi) — tatbikat SMS'iyle aynı alıcılar, önek yok."""
    r = acil._post(
        f"{a['sms_url']}/api/arac/acil",
        {"metin": metin},
        {"X-Sms-Arac-Key": a["sms_anahtar"], "Content-Type": "application/json"},
    )
    if not r.get("alicilar"):
        raise RuntimeError("SMS alıcı listesi boş (yönetim).")
    return {"kanal": "SMS", "basarili": True, "detay": ", ".join(r["alicilar"])}


@router.post("/api/guvenlik/haber")
async def haber(request: Request):
    _dogrula(request)
    neden = (await request.json()).get("neden")
    if neden not in NEDENLER:
        raise HTTPException(400, "Geçersiz neden.")
    simdi = time.time()
    if simdi - _son_haber.get(neden, 0) < HABER_ARALIK_SN:
        raise HTTPException(429, "Az önce bildirildi.")
    _son_haber[neden] = simdi
    a = acil._ayarlar()
    metin = haber_metni(neden, _simdi().strftime("%H:%M"))
    kanallar = await asyncio.gather(
        acil._guvenli("SMS", _haber_sms, a, metin),
        acil._guvenli("Telegram", acil._telegram_bildir, a, "🛡 " + metin),
    )
    acil._olay_yaz(
        {
            "zaman": _simdi().isoformat(timespec="seconds"),
            "tur": "guvenlik_uyari",
            "neden": neden,
            "istemci_ip": _kaynak(request),
            "kanallar": list(kanallar),
        }
    )
    return JSONResponse(
        {
            "kanallar": [
                {"kanal": k["kanal"], "basarili": k["basarili"]} for k in kanallar
            ]
        }
    )
