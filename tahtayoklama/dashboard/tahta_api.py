"""Tahta istemcisi API'si (/api/v1/tahta/*) — tahtalardaki
`tahta_istemci.py`'nin (bkz. tahtayoklama/tahta_istemci.py) konuştuğu uçlar.

SSH ile çekme modelinin yerine (2026-10-06) "tahta iter / tahta çeker":
- POST /kayit         — yoklama kaydı (yoklama.py'nin yazdığı JSON'un aynısı)
- POST /nabiz         — 60 sn'de bir; taze nabızlı tahta SSH ile taranmaz
- GET  /yapilandirma  — roster (atanmış sınıf) + zil.json + ders_programi.json
                        + kazanimlar.json (2026-10-06), ETag/If-None-Match ile

Kimlik: `Authorization: Bearer <token>` — tahta başına ayrı token. Sunucuda
yalnızca SHA-256 özeti durur: config/tahta_tokenlari.json ({"9-A": "<hex>"},
gitignore'lu, scripts/tahta_istemci_kur.py yazar, her istekte okunur).
/api/ajan'dan (yalnızca localhost, Open WebUI) tamamen ayrı — bu uçlar LAN'a
açık, bu yüzden her girdi sıkı doğrulanır ve hiçbir uç komut çalıştırmaz.
"""

import hashlib
import hmac
import json
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

import db
import yoklayici
import zil

TOKEN_DOSYASI = Path(__file__).resolve().parent / "config" / "tahta_tokenlari.json"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ZIL_DOSYASI = DATA_DIR / "zil.json"
DERS_PROGRAMI_DOSYASI = DATA_DIR / "ders_programi.json"
KAZANIM_DOSYASI = DATA_DIR / "kazanimlar.json"

GOVDE_MAKS = 64 * 1024
_TARIH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SAAT_RE = re.compile(r"^\d{2}:\d{2}:\d{2}$")
_SINIF_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_GECERLI_DURUMLAR = {"var", "yok", "izinli"}

router = APIRouter(prefix="/api/v1/tahta")


def _tahta_dogrula(request: Request) -> str:
    """Token'ı doğrular, tahta adını döner. Tahta DB'de aktif olmalı."""
    baslik = request.headers.get("Authorization", "")
    if not baslik.startswith("Bearer ") or len(baslik) > 300:
        raise HTTPException(401, "Token yok.")
    ozet = hashlib.sha256(baslik[7:].strip().encode("utf-8")).hexdigest()
    try:
        tokenlar = json.loads(TOKEN_DOSYASI.read_text(encoding="utf-8"))
        if not isinstance(tokenlar, dict):
            raise ValueError
    except (OSError, ValueError):
        raise HTTPException(503, "Tahta tokenları yapılandırılmamış.")
    bulunan = None
    for ad, beklenen in tokenlar.items():
        if isinstance(beklenen, str) and hmac.compare_digest(ozet, beklenen):
            bulunan = ad
    if bulunan is None:
        raise HTTPException(401, "Geçersiz token.")
    conn = db.baglanti()
    try:
        satir = conn.execute(
            "SELECT 1 FROM tahtalar WHERE ad = ? AND aktif = 1", (bulunan,)
        ).fetchone()
    finally:
        conn.close()
    if satir is None:
        raise HTTPException(403, "Tahta aktif değil.")
    return bulunan


async def _govde(request: Request) -> dict:
    ham = await request.body()
    if len(ham) > GOVDE_MAKS:
        raise HTTPException(413, "Gövde çok büyük.")
    try:
        veri = json.loads(ham)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "Geçersiz JSON.")
    if not isinstance(veri, dict):
        raise HTTPException(400, "JSON nesnesi bekleniyor.")
    return veri


def kayit_dogrula(veri: dict) -> dict:
    """yoklama.py `_kaydet` şeması: sinif, tarih, ders_no, kaydedilme_saati,
    durumlar{no: var|yok|izinli}. Geçersizse 422 (istemci yeniden denemez)."""
    sinif = veri.get("sinif")
    tarih = veri.get("tarih")
    ders_no = veri.get("ders_no")
    saat = veri.get("kaydedilme_saati")
    durumlar = veri.get("durumlar")
    if not isinstance(sinif, str) or not _SINIF_RE.match(sinif):
        raise HTTPException(422, "Geçersiz sınıf.")
    if not isinstance(tarih, str) or not _TARIH_RE.match(tarih):
        raise HTTPException(422, "Geçersiz tarih.")
    try:
        date.fromisoformat(tarih)
    except ValueError:
        raise HTTPException(422, "Geçersiz tarih.")
    # Saati ileri kaymış tahtadan gelecek tarihli kayıt (bkz. yoklayici.
    # itilen_kaydi_yaz'daki saat notu) — kalıcı ret, istemci yeniden denemez.
    if tarih > zil.simdi_istanbul().date().isoformat():
        raise HTTPException(422, "Gelecek tarihli kayıt.")
    gecerli_dersler = {d["no"] for d in zil.ders_saatleri()}
    if type(ders_no) is not int or ders_no not in gecerli_dersler:
        raise HTTPException(422, "Geçersiz ders no.")
    if saat is not None and (not isinstance(saat, str) or not _SAAT_RE.match(saat)):
        raise HTTPException(422, "Geçersiz kaydedilme saati.")
    if not isinstance(durumlar, dict) or len(durumlar) > 300:
        raise HTTPException(422, "Geçersiz durumlar.")
    for no, durum in durumlar.items():
        if not no.isdigit() or len(no) > 6 or durum not in _GECERLI_DURUMLAR:
            raise HTTPException(422, "Geçersiz durumlar.")
    return {
        "sinif": sinif, "tarih": tarih, "ders_no": ders_no,
        "kaydedilme_saati": saat, "durumlar": durumlar,
    }


@router.post("/kayit")
async def kayit_al(request: Request):
    tahta = _tahta_dogrula(request)
    kayit = kayit_dogrula(await _govde(request))
    conn = db.baglanti()
    try:
        if not yoklayici.itilen_kaydi_yaz(conn, kayit, tahta):
            raise HTTPException(422, "Bilinmeyen ya da pasif sınıf.")
    finally:
        conn.close()
    return JSONResponse({"durum": "kaydedildi"})


@router.post("/nabiz")
async def nabiz_al(request: Request):
    tahta = _tahta_dogrula(request)
    veri = await _govde(request)
    surum = veri.get("istemci_surum")
    surum = surum[:40] if isinstance(surum, str) else None
    acik = veri.get("yoklama_acik")
    acik = int(acik) if isinstance(acik, bool) else None
    ip = request.client.host if request.client else None
    conn = db.baglanti()
    try:
        conn.execute(
            """
            INSERT INTO tahta_nabiz (tahta_ad, son_gorulme, ip, istemci_surum, yoklama_acik)
            VALUES (?, datetime('now'), ?, ?, ?)
            ON CONFLICT(tahta_ad) DO UPDATE SET
                son_gorulme = excluded.son_gorulme, ip = excluded.ip,
                istemci_surum = excluded.istemci_surum, yoklama_acik = excluded.yoklama_acik
            """,
            (tahta, ip, surum, acik),
        )
        conn.commit()
    finally:
        conn.close()
    return JSONResponse({"durum": "tamam"})


def _dosya_metni(yol: Path) -> str | None:
    try:
        return yol.read_text(encoding="utf-8")
    except OSError:
        return None


def _kazanim_metni(sinif_ad: str | None) -> str | None:
    """data/kazanimlar.json (scripts/kazanim_yukle.py üretir). Sınıfı atanmış
    tahtaya yalnızca kendi düzeyi gider (dosya ~yüzlerce KB); atanmamış
    tahtaya (fenlab — her sınıf girer) tamamı."""
    metin = _dosya_metni(KAZANIM_DOSYASI)
    if metin is None or sinif_ad is None:
        return metin
    try:
        veri = json.loads(metin)
        duzey = sinif_ad.split("-")[0]
        veri["kazanimlar"] = {duzey: veri.get("kazanimlar", {}).get(duzey, {})}
        return json.dumps(veri, ensure_ascii=False, indent=1)
    except (ValueError, AttributeError, TypeError):
        return None


def yapilandirma_olustur(tahta: str) -> dict:
    """Roster, admin.py'nin SSH senkronuyla BAYT BAYT aynı üretilir
    (`_roster_payload_olustur`) — iki yol aynı dosyayı yazsın. Sınıfı
    atanmamış tahtada (fenlab, tahta-23x) ya da öğrencisi olmayan sınıfta
    roster None döner: istemci o durumda yerel roster'lara DOKUNMAZ."""
    import admin  # döngüsel içe aktarmayı önlemek için geç

    conn = db.baglanti()
    try:
        satir = conn.execute(
            "SELECT t.sinif_id, s.ad AS sinif_ad FROM tahtalar t "
            "LEFT JOIN siniflar s ON s.id = t.sinif_id AND s.aktif = 1 "
            "WHERE t.ad = ? AND t.aktif = 1",
            (tahta,),
        ).fetchone()
        sinif_ad, roster = None, None
        if satir is not None and satir["sinif_ad"] is not None:
            _, payload = admin._roster_payload_olustur(conn, satir["sinif_id"])
            if json.loads(payload)["ogrenciler"]:
                sinif_ad, roster = satir["sinif_ad"], payload.decode("utf-8")
    finally:
        conn.close()
    return {
        "tahta": tahta,
        "sinif": sinif_ad,
        "roster": roster,
        "zil": _dosya_metni(ZIL_DOSYASI),
        "ders_programi": _dosya_metni(DERS_PROGRAMI_DOSYASI),
        "kazanimlar": _kazanim_metni(sinif_ad),
    }


@router.get("/yapilandirma")
async def yapilandirma(request: Request):
    tahta = _tahta_dogrula(request)
    govde = json.dumps(yapilandirma_olustur(tahta), ensure_ascii=False, sort_keys=True)
    etag = '"' + hashlib.sha256(govde.encode("utf-8")).hexdigest()[:32] + '"'
    if request.headers.get("If-None-Match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=govde.encode("utf-8"),
        media_type="application/json; charset=utf-8",
        headers={"ETag": etag, "Cache-Control": "no-cache"},
    )
