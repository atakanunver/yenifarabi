"""Makine-makine JSON API (/api/ajan/*) — Open WebUI aracı için.

Yalnızca aynı makineden (127.0.0.1/::1) VE `X-Farabi-Ajan-Key` başlığıyla
erişilir; oturum çerezi KABUL EDİLMEZ. Yanıtlar yalnızca izin verilen
alanları içerir: IP/MAC/kullanıcı adı/SSH ayrıntısı/ham hata metni asla
dönmez (LLM görmemeli). Anahtar dosyası: config/ajan.json (gitignore'lu,
scripts/ajan_anahtari_olustur.py üretir; her istekte okunur).
"""

import asyncio
import hmac
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

import sistem_durumu
import ssh_istemci
import tahta_kaydi
import tahta_yeniden_baslat
import uzaktan_yonetim
import zil

AJAN_ANAHTAR_YOLU = Path(__file__).resolve().parent / "config" / "ajan.json"
_YEREL = {"127.0.0.1", "::1"}
_URL_MAKS = 2000

router = APIRouter(prefix="/api/ajan")


def _ajan_dogrula(request: Request) -> None:
    if not request.client or request.client.host not in _YEREL:
        raise HTTPException(403, "Yalnızca yerel erişim.")
    try:
        anahtar = json.loads(AJAN_ANAHTAR_YOLU.read_text(encoding="utf-8"))["anahtar"]
        if not isinstance(anahtar, str) or not anahtar:
            raise ValueError("anahtar boş")
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Ajan anahtarı yapılandırılmamış.")
    gelen = request.headers.get("X-Farabi-Ajan-Key")
    if not gelen or not hmac.compare_digest(gelen.encode("utf-8"), anahtar.encode("utf-8")):
        raise HTTPException(401, "Geçersiz anahtar.")


def _kaynak(request: Request) -> str:
    return request.headers.get("X-Farabi-Kaynak", "")[:120] or "ajan"


async def _govde(request: Request) -> dict:
    try:
        veri = await request.json()
    except Exception:  # noqa: BLE001 — bozuk JSON her türlü istisna verebilir
        raise HTTPException(400, "Geçersiz JSON.")
    if not isinstance(veri, dict):
        raise HTTPException(400, "JSON nesnesi bekleniyor.")
    return veri


def _hedefleri_coz(veri: dict) -> list[dict]:
    """İstenen tahta adlarını kayıt defterine karşı çözer. Boş liste ya da
    bilinmeyen ad → 400 (hiçbir şey çalıştırılmadan)."""
    istenen = veri.get("tahtalar")
    if not isinstance(istenen, list) or not istenen or not all(isinstance(a, str) for a in istenen):
        raise HTTPException(400, "tahtalar boş olmayan bir ad listesi olmalı.")
    kayit = tahta_kaydi.tahtalari_yukle()
    gecerli = [t["ad"] for t in kayit]
    bilinmeyen = [a for a in dict.fromkeys(istenen) if a not in gecerli]
    if bilinmeyen:
        raise HTTPException(400, {"bilinmeyen": bilinmeyen, "gecerli": gecerli})
    secili = set(istenen)
    return [t for t in kayit if t["ad"] in secili]


_ULASILAMADI_IPUCLARI = (
    "connection", "timed out", "no route", "refused", "could not resolve",
    "host is down", "unreachable", "ssh:", "kex_exchange", "closed by",
)


def _sebep(sonuc: dict) -> str:
    """Eylem fonksiyonlarının serbest metin `detay`'ını sabit sebep koduna
    çevirir (ham metin dışarı çıkmaz)."""
    if sonuc.get("basarili"):
        return "tamam"
    detay = (sonuc.get("detay") or "").lower()
    if "zaman_asimi" in detay:
        return "zaman_asimi"
    if "masaüstü oturumu" in detay:
        return "oturum_yok"
    if "permission denied" in detay or "izin" in detay:
        return "izin_yok"
    if any(i in detay for i in _ULASILAMADI_IPUCLARI):
        return "ulasilamadi"
    return "hata"


async def _paralel_calistir(hedefler: list[dict], islem) -> list[dict]:
    """Tahtalarda paralel çalıştırır; bir tahtadaki beklenmeyen istisna o
    tahtayı `hata` yapar, diğerlerini ve denetim kaydını engellemez
    (istisna metni dışarı çıkmaz)."""
    sonuclar = await asyncio.gather(*(islem(t) for t in hedefler), return_exceptions=True)
    return [
        {"tahta": t["ad"], "basarili": False, "sebep": "hata"} if isinstance(r, BaseException) else r
        for t, r in zip(hedefler, sonuclar)
    ]


def _ozet(sonuc: dict) -> dict:
    ozet = {"tahta": sonuc["tahta"], "basarili": bool(sonuc["basarili"]), "sebep": sonuc.get("sebep") or _sebep(sonuc)}
    if "uyari" in sonuc:
        ozet["uyari"] = sonuc["uyari"]
    return ozet


@router.get("/tahtalar")
async def tahtalar(request: Request, canli: int = 0):
    _ajan_dogrula(request)
    if not canli:
        return JSONResponse({"tahtalar": [{"ad": t["ad"]} for t in tahta_kaydi.tahtalari_yukle()]})
    alanlar = ("ad", "ulasilabilir", "oturum", "yoklama", "chrome", "karartildi")
    durumlar = await uzaktan_yonetim.tum_durumlar()
    return JSONResponse({"tahtalar": [{a: d[a] for a in alanlar} for d in durumlar]})


@router.get("/sistem")
async def sistem(request: Request):
    _ajan_dogrula(request)
    ham = await sistem_durumu.durum_topla()
    gpular = []
    for g in ham.get("gpu", []):
        toplam = g.get("bellek_toplam_mb")
        gpular.append({
            "sicaklik_c": g.get("sicaklik_c"),
            "kullanim_yuzde": g.get("kullanim_yuzde"),
            "bellek_yuzde": round(100 * g["bellek_kullanim_mb"] / toplam) if toplam else None,
        })
    servisler = []
    for s in ham.get("servisler", []):
        satir = {"ad": s.get("etiket"), "durum": s.get("durum")}
        http = s.get("http")
        if http and http.get("ms") is not None:
            satir["ms"] = http["ms"]
        servisler.append(satir)
    return JSONResponse({
        "cpu_yuzde": ham.get("cpu_kullanim_yuzde"),
        "cpu_sicaklik_c": (ham.get("cpu") or {}).get("sicaklik_c"),
        "gpu": gpular,
        "bellek_yuzde": (ham.get("bellek") or {}).get("yuzde"),
        "disk_yuzde": (ham.get("disk") or {}).get("yuzde"),
        "servisler": servisler,
    })


@router.get("/yoklama")
async def yoklama(request: Request, tarih: str | None = None, sinif: str | None = None):
    _ajan_dogrula(request)
    from datetime import date

    import app  # geç içe aktarma: app.py bu modülü içe aktarıyor (döngü)
    import db

    hedef = tarih or zil.simdi_istanbul().date().isoformat()
    try:
        ssh_istemci.tarih_dogrula(hedef)
        hedef_tarih = date.fromisoformat(hedef)
    except ValueError:
        raise HTTPException(400, "Geçersiz tarih, YYYY-MM-DD bekleniyor.")
    if sinif is not None:
        try:
            ssh_istemci.ad_dogrula(sinif)
        except ValueError:
            raise HTTPException(400, "Geçersiz sınıf adı.")
    conn = db.baglanti()
    try:
        satirlar = app._durum_satirlari(conn, hedef_tarih)
    finally:
        conn.close()
    if sinif is not None:
        satirlar = [s for s in satirlar if s["sinif"] == sinif]
    return JSONResponse({"tarih": hedef, "satirlar": satirlar})


@router.post("/eylem")
async def eylem(request: Request):
    _ajan_dogrula(request)
    veri = await _govde(request)
    ad = veri.get("eylem")
    if not isinstance(ad, str) or ad not in uzaktan_yonetim.EYLEMLER:
        raise HTTPException(400, {"gecerli_eylemler": sorted(uzaktan_yonetim.EYLEMLER)})
    hedefler = _hedefleri_coz(veri)
    url = veri.get("url", "")
    if not isinstance(url, str) or len(url) > _URL_MAKS:
        raise HTTPException(400, "Geçersiz url.")
    fonksiyon = uzaktan_yonetim.EYLEMLER[ad]
    ham = await _paralel_calistir(hedefler, lambda t: fonksiyon(t, {"url": url}))
    uzaktan_yonetim._denetim_yaz(request, f"ajan:{ad}", ham, kaynak=_kaynak(request))
    return JSONResponse({"sonuclar": [_ozet(r) for r in ham]})


@router.post("/yeniden-baslat")
async def yeniden_baslat(request: Request):
    _ajan_dogrula(request)
    veri = await _govde(request)
    hedefler = _hedefleri_coz(veri)
    if tahta_yeniden_baslat.ders_saatinde_mi():
        uzaktan_yonetim._denetim_yaz(
            request, "ajan:yeniden_baslat",
            [{"tahta": t["ad"], "basarili": False, "denetim_kodu": "ders_saati"} for t in hedefler],
            kaynak=_kaynak(request),
        )
        return JSONResponse(
            {"durum": "ders_saati", "mesaj": "Ders saatinde tahtalar yeniden başlatılamaz."},
            status_code=409,
        )
    ham = await _paralel_calistir(hedefler, tahta_yeniden_baslat.yeniden_baslat_tek)
    uzaktan_yonetim._denetim_yaz(request, "ajan:yeniden_baslat", ham, kaynak=_kaynak(request))
    return JSONResponse({"sonuclar": [_ozet(r) for r in ham]})
