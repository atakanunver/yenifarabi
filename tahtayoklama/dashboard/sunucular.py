"""Sunucular sekmesi — farabi / debian / bilgehan durumu + proxy anahtarı.

Her makinede aynı betik var: `/usr/local/sbin/okul-sunucu {durum|proxy-ac|
proxy-kapat}` (kaynak: `server/okul-sunucu/`). Farabi yerelde `sudo -n` ile,
diğerleri `~/.ssh/sunucu_izleme` anahtarıyla SSH üzerinden çağrılır; o anahtar
hedefte `command="/usr/local/sbin/okul-sunucu-ssh"` ile yalnızca bu üç alt
komuta kısıtlı. ssh_istemci.py'deki gibi paramiko yok, düz `ssh` alt süreci.

Toplama İSTEK ÜZERİNE ve 60 sn önbellekli (sistem_durumu.py'nin sürekli arka
plan döngüsü burada bilerek YOK): sekme açık değilken hedef makinelerin
auth/journal loguna dakikada bir SSH girişi yazılmasın. Tek kilit, kaç sekme
açık olursa olsun 60 sn'de en fazla bir tur.

TTS (EMA Lightning, debian:5002; 2026-10-08 öncesi Chatterbox) kartı `/saglik/detay`'dan HTTP ile okunur.
Proxy URL'si (parolalı) hiçbir yanıta girmez — betik onu zaten basmaz,
ek olarak hata metinlerinden de maskelenir.
"""

import asyncio
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import menu
import auth
import db
import uzaktan_yonetim
import zil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci  # taban.html (2026-10-08)
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk  # taban.html kullanıyor

BETIK = "/usr/local/sbin/okul-sunucu"
SSH_ANAHTARI = Path.home() / ".ssh" / "sunucu_izleme"
CHATTERBOX_URL = "http://192.168.23.251:5002/saglik/detay"  # debian EMA Lightning TTS (aynı alanlar)
ONBELLEK_SN = 60
DURUM_ZAMAN_ASIMI_SN = 25
PROXY_ZAMAN_ASIMI_SN = 240  # Ollama restart'ı (model ön-yükleme dahil) sürebilir
ALT_KOMUTLAR = ("durum", "proxy-ac", "proxy-kapat")
_ISTANBUL = ZoneInfo("Europe/Istanbul")

# Sıra = sayfadaki sıra.
MAKINELER = {
    "farabi": {
        "ad": "Farabi",
        "rol": "RAG + LLM sunucusu",
        "yerel": True,
        "proxy_dugmesi": True,
    },
    "bilgehan": {
        "ad": "Bilgehan",
        "rol": "RAG Embed & Rerank + Chatterbox TTS",
        "host": "bilgehan.local",
        "proxy_dugmesi": True,
    },
    "debian": {
        "ad": "Debian",
        "rol": "OMV NAS + EMA Lightning TTS",
        "host": "192.168.23.251",
        "proxy_dugmesi": False,
    },
}

_PAROLALI_URL = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@")

_onbellek: dict | None = None
_onbellek_zamani = 0.0
_kilit = asyncio.Lock()


def _maskele(metin: str) -> str:
    return _PAROLALI_URL.sub(r"\1***@", metin)


def durum_ayristir(cikti: str, kod: int, hata: str) -> dict:
    """okul-sunucu çıktısının son JSON satırını okur."""
    for satir in reversed((cikti or "").strip().splitlines()):
        try:
            veri = json.loads(satir)
        except ValueError:
            continue
        if isinstance(veri, dict):
            if "hata" in veri and "makine" not in veri:
                return {
                    "ulasilabilir": False,
                    "hata": _maskele(str(veri["hata"]))[:300],
                }
            return {**veri, "ulasilabilir": True}
    metin = (hata or "").strip() or f"çıkış kodu {kod}"
    return {"ulasilabilir": False, "hata": _maskele(metin)[-300:]}


def komut_argumanlari(makine: str, alt: str) -> list[str]:
    if alt not in ALT_KOMUTLAR:
        raise ValueError(f"izin verilmeyen alt komut: {alt}")
    tanim = MAKINELER[makine]
    if tanim.get("yerel"):
        return ["sudo", "-n", BETIK, alt]
    return [
        "ssh",
        "-i",
        str(SSH_ANAHTARI),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=3",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        f"ata@{tanim['host']}",
        alt,
    ]


async def _calistir(makine: str, alt: str) -> dict:
    tanim = MAKINELER[makine]
    if not tanim.get("yerel") and not SSH_ANAHTARI.exists():
        return {
            "ulasilabilir": False,
            "hata": "SSH izleme anahtarı kurulmamış (~/.ssh/sunucu_izleme).",
        }
    zaman_asimi = DURUM_ZAMAN_ASIMI_SN if alt == "durum" else PROXY_ZAMAN_ASIMI_SN
    try:
        surec = await asyncio.create_subprocess_exec(
            *komut_argumanlari(makine, alt),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        cikti, hata = await asyncio.wait_for(surec.communicate(), zaman_asimi)
    except asyncio.TimeoutError:
        surec.kill()
        return {"ulasilabilir": False, "hata": f"{zaman_asimi} sn içinde yanıt yok."}
    except OSError as e:
        return {"ulasilabilir": False, "hata": _maskele(str(e))}
    return durum_ayristir(
        cikti.decode("utf-8", "replace"),
        surec.returncode,
        hata.decode("utf-8", "replace"),
    )


def _chatterbox_oku() -> dict:
    acici = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    baslangic = time.perf_counter()
    try:
        with acici.open(CHATTERBOX_URL, timeout=4) as yanit:
            veri = json.loads(yanit.read(65536))
        veri["ulasilabilir"] = True
        veri["ms"] = round((time.perf_counter() - baslangic) * 1000)
        return veri
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return {"ulasilabilir": False, "hata": _maskele(str(e))[:200]}


async def _topla() -> dict:
    sonuclar = await asyncio.gather(*(_calistir(ad, "durum") for ad in MAKINELER))
    chatterbox = await asyncio.to_thread(_chatterbox_oku)
    makineler = []
    for (anahtar, tanim), durum in zip(MAKINELER.items(), sonuclar):
        makineler.append(
            {
                "anahtar": anahtar,
                "ad": tanim["ad"],
                "rol": tanim["rol"],
                "proxy_dugmesi": tanim["proxy_dugmesi"],
                **durum,
            }
        )
    return {
        "zaman": datetime.now(_ISTANBUL).isoformat(timespec="seconds"),
        "makineler": makineler,
        "chatterbox": chatterbox,
    }


async def durum_al(yenile: bool = False) -> dict:
    global _onbellek, _onbellek_zamani
    async with _kilit:
        if (
            yenile
            or _onbellek is None
            or time.monotonic() - _onbellek_zamani > ONBELLEK_SN
        ):
            _onbellek = await _topla()
            _onbellek_zamani = time.monotonic()
        return _onbellek


def _oturum_kontrol(request: Request) -> None:
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()


@router.get("/sunucular", response_class=HTMLResponse)
async def sunucular_sayfa(request: Request):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
    finally:
        conn.close()
    return templates.TemplateResponse(request, "sunucular.html", {})


@router.get("/api/sunucular")
async def api_sunucular(request: Request, yenile: int = 0):
    _oturum_kontrol(request)
    return JSONResponse(await durum_al(yenile=bool(yenile)))


@router.post("/api/sunucular/{ad}/proxy")
async def api_proxy(request: Request, ad: str):
    _oturum_kontrol(request)
    if ad not in MAKINELER:
        raise HTTPException(404, "Bilinmeyen makine.")
    if not MAKINELER[ad]["proxy_dugmesi"]:
        raise HTTPException(400, "Bu makinede proxy anahtarı yok.")
    try:
        govde = await request.json()
    except ValueError:
        govde = {}
    eylem = govde.get("eylem") if isinstance(govde, dict) else None
    if eylem not in ("ac", "kapat"):
        raise HTTPException(400, "eylem 'ac' ya da 'kapat' olmalı.")

    alt = "proxy-ac" if eylem == "ac" else "proxy-kapat"
    sonuc = await _calistir(ad, alt)
    basarili = bool(sonuc.get("ulasilabilir"))
    uzaktan_yonetim._denetim_yaz(
        request,
        f"sunucu-{alt}",
        [{"tahta": ad, "basarili": basarili}],
        kaynak="sunucular",
    )
    global _onbellek
    _onbellek = None  # bir sonraki okuma taze olsun
    return JSONResponse(
        {
            "basarili": basarili,
            "makine": ad,
            "mesajlar": sonuc.get("mesajlar", []),
            "hata": sonuc.get("hata"),
            "proxy": sonuc.get("proxy"),
        }
    )
