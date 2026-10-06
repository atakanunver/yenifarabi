"""smssistemi/arac_api.py — Atos (Open WebUI) SMS aracının makine API'si (2026-10-05).

Kullanıcı kararları (2026-10-05):
- Hatırlatma ve acil SMS her zaman aynı iki okul yöneticisine gider (config/arac.json
  → "yonetim"); hatırlatma ONAYSIZ kurulur ("hatırlat" emri bir kez verilir).
- Saat belirtilmezse 10:00 (TR); hatırlatma notu en fazla 120 karakter.
- Veli SMS'i (ör. "9-A velilerine kermes var") iki adımlı: taslak (alıcı sayısı +
  önizleme) → kullanıcı onayı → gönder. Taslak 30 dk geçerli.
Kimlik: X-Sms-Arac-Key başlığı (config/arac.json "anahtar", gitignore'lu). Gönderim
mevcut modem göndericisiyle (sms_gonderici.toplu_gonder) yapılır, sonuçlar
`gonderimler` tablosuna yazılır — /kayitlar sayfasında görünür.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import re
import secrets
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import db
import gonderim
import otomasyon
import sms_gonderici
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

log = logging.getLogger("smssistemi.arac")
router = APIRouter(prefix="/api/arac")

AYAR_YOLU = Path(__file__).resolve().parent / "config" / "arac.json"
HATIRLATMA_AZAMI = 120
VELI_AZAMI = 300
VARSAYILAN_SAAT = "10:00"
GEC_KALMA_SINIRI = timedelta(
    hours=6
)  # servis kapalıyken kaçan hatırlatma bundan geç gönderilmez
TASLAK_OMRU = timedelta(minutes=30)
ZAMAN_BICIMI = "%Y-%m-%d %H:%M"

SEMA = """
CREATE TABLE IF NOT EXISTS hatirlatmalar (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metin TEXT NOT NULL,
    zaman TEXT NOT NULL,            -- TR yerel saat, 'YYYY-MM-DD HH:MM'
    durum TEXT NOT NULL DEFAULT 'bekliyor',  -- bekliyor|gonderildi|iptal|kacirildi|hata
    olusturma TEXT NOT NULL DEFAULT (datetime('now')),
    gonderim_id TEXT
);
CREATE TABLE IF NOT EXISTS veli_taslaklari (
    id TEXT PRIMARY KEY,
    sinif TEXT NOT NULL,
    metin TEXT NOT NULL,
    alici_sayisi INTEGER NOT NULL,
    olusturma TEXT NOT NULL,        -- TR yerel saat
    durum TEXT NOT NULL DEFAULT 'taslak',    -- taslak|gonderildi
    gonderim_id TEXT
);
"""


def sema_kur() -> None:
    conn = db.baglanti()
    try:
        conn.executescript(SEMA)
        conn.commit()
    finally:
        conn.close()


def ayar() -> dict:
    try:
        return json.loads(AYAR_YOLU.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def anahtar_dogrula(
    x_sms_arac_key: str | None = Header(default=None, alias="X-Sms-Arac-Key"),
) -> None:
    beklenen = ayar().get("anahtar")
    if (
        not beklenen
        or not x_sms_arac_key
        or not hmac.compare_digest(str(beklenen), x_sms_arac_key)
    ):
        raise HTTPException(
            status_code=401, detail="Geçersiz ya da eksik araç anahtarı"
        )


def yonetim_alicilari() -> list[tuple[str, str]]:
    alicilar = []
    for k in ayar().get("yonetim", []):
        tel = gonderim.normalize_phone(str(k.get("telefon", "")))
        if k.get("ad") and gonderim.is_valid_phone(tel):
            alicilar.append((k["ad"], tel))
    return alicilar


def simdi() -> datetime:
    return otomasyon.simdi_istanbul().replace(tzinfo=None, second=0, microsecond=0)


def gonder(kisiler: list[tuple[str, str, str]]) -> str:
    """Arka planda modemle gönderir; sonuçlar gonderimler tablosuna (/kayitlar)."""
    gonderim_id = uuid.uuid4().hex[:12]

    def calis() -> None:
        conn = db.baglanti()
        try:
            sms_gonderici.toplu_gonder(
                sms_gonderici.modem_ayarlarini_yukle(),
                kisiler,
                lambda i, t, m, d, h: db.gonderim_kaydet(
                    conn, gonderim_id, i, t, m, d, h
                ),
                threading.Event(),
                2.0,
            )
        except Exception:
            log.exception("araç gönderimi başarısız: %s", gonderim_id)
        finally:
            conn.close()

    threading.Thread(target=calis, daemon=True).start()
    return gonderim_id


def _metin(metin: str, azami: int) -> str:
    metin = " ".join((metin or "").split())
    if not metin:
        raise HTTPException(status_code=422, detail="Mesaj boş.")
    if len(metin) > azami:
        raise HTTPException(
            status_code=422,
            detail=f"Mesaj {len(metin)} karakter; en fazla {azami} olmalı, kısalt.",
        )
    return metin


def _yonetim_sarti() -> list[tuple[str, str]]:
    alicilar = yonetim_alicilari()
    if not alicilar:
        raise HTTPException(
            status_code=503,
            detail="Yönetim alıcıları tanımlı değil (config/arac.json).",
        )
    return alicilar


# --- Hatırlatma (onaysız, yönetime) ------------------------------------


class HatirlatmaIstek(BaseModel):
    metin: str
    tarih: str  # YYYY-MM-DD
    saat: str | None = None  # HH:MM; boşsa 10:00


@router.post("/hatirlatma", dependencies=[Depends(anahtar_dogrula)])
def hatirlatma_kur(istek: HatirlatmaIstek):
    metin = _metin(istek.metin, HATIRLATMA_AZAMI)
    saat = (istek.saat or "").strip() or VARSAYILAN_SAAT
    try:
        zaman = datetime.strptime(f"{istek.tarih.strip()} {saat}", ZAMAN_BICIMI)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Tarih YYYY-MM-DD, saat HH:MM olmalı."
        ) from None
    if zaman <= simdi():
        raise HTTPException(
            status_code=422, detail=f"{zaman:%d.%m.%Y %H:%M} geçmişte kalıyor."
        )
    alicilar = _yonetim_sarti()
    conn = db.baglanti()
    try:
        cur = conn.execute(
            "INSERT INTO hatirlatmalar (metin, zaman) VALUES (?, ?)",
            (metin, zaman.strftime(ZAMAN_BICIMI)),
        )
        conn.commit()
        hid = cur.lastrowid
    finally:
        conn.close()
    log.info("hatırlatma kuruldu #%s %s", hid, zaman.strftime(ZAMAN_BICIMI))
    return {
        "id": hid,
        "zaman": zaman.strftime(ZAMAN_BICIMI),
        "metin": metin,
        "alicilar": [a for a, _ in alicilar],
    }


@router.get("/hatirlatmalar", dependencies=[Depends(anahtar_dogrula)])
def hatirlatmalar():
    conn = db.baglanti()
    try:
        satirlar = conn.execute(
            "SELECT id, metin, zaman, durum FROM hatirlatmalar "
            "WHERE durum = 'bekliyor' ORDER BY zaman"
        ).fetchall()
    finally:
        conn.close()
    return {"hatirlatmalar": [dict(r) for r in satirlar]}


@router.post("/hatirlatma/{hid}/iptal", dependencies=[Depends(anahtar_dogrula)])
def hatirlatma_iptal(hid: int):
    conn = db.baglanti()
    try:
        cur = conn.execute(
            "UPDATE hatirlatmalar SET durum = 'iptal' WHERE id = ? AND durum = 'bekliyor'",
            (hid,),
        )
        conn.commit()
    finally:
        conn.close()
    if cur.rowcount == 0:
        raise HTTPException(
            status_code=404, detail="Bekleyen böyle bir hatırlatma yok."
        )
    return {"id": hid, "durum": "iptal"}


def vadesi_gelenleri_gonder(an: datetime | None = None) -> int:
    an = an or simdi()
    conn = db.baglanti()
    gonderilen = 0
    try:
        satirlar = conn.execute(
            "SELECT id, metin, zaman FROM hatirlatmalar WHERE durum = 'bekliyor' "
            "AND zaman <= ? ORDER BY zaman",
            (an.strftime(ZAMAN_BICIMI),),
        ).fetchall()
        for r in satirlar:
            if an - datetime.strptime(r["zaman"], ZAMAN_BICIMI) > GEC_KALMA_SINIRI:
                conn.execute(
                    "UPDATE hatirlatmalar SET durum = 'kacirildi' WHERE id = ?",
                    (r["id"],),
                )
                log.warning("hatırlatma #%s kaçırıldı (%s)", r["id"], r["zaman"])
                continue
            alicilar = yonetim_alicilari()
            if not alicilar:
                conn.execute(
                    "UPDATE hatirlatmalar SET durum = 'hata' WHERE id = ?", (r["id"],)
                )
                continue
            gid = gonder([(ad, tel, r["metin"]) for ad, tel in alicilar])
            conn.execute(
                "UPDATE hatirlatmalar SET durum = 'gonderildi', gonderim_id = ? WHERE id = ?",
                (gid, r["id"]),
            )
            log.info("hatırlatma #%s gönderiliyor (%s)", r["id"], gid)
            gonderilen += 1
        conn.commit()
    finally:
        conn.close()
    return gonderilen


async def hatirlatma_dongusu() -> None:
    log.info("Hatırlatma zamanlayıcısı başlatıldı.")
    while True:
        try:
            await asyncio.sleep(30)
            await asyncio.to_thread(vadesi_gelenleri_gonder)
        except asyncio.CancelledError:
            break
        except Exception:
            log.exception("hatırlatma döngüsü hatası")


# --- Acil SMS (anında, yönetime) ---------------------------------------


class AcilIstek(BaseModel):
    metin: str


@router.post("/acil", dependencies=[Depends(anahtar_dogrula)])
def acil(istek: AcilIstek):
    metin = _metin(istek.metin, VELI_AZAMI)
    alicilar = _yonetim_sarti()
    gid = gonder([(ad, tel, metin) for ad, tel in alicilar])
    return {"gonderim_id": gid, "alicilar": [a for a, _ in alicilar], "metin": metin}


# --- Veli SMS'i (taslak → onay → gönder) -------------------------------


def _sinif_normalize(ad: str) -> str:
    m = re.fullmatch(
        r"\s*(\d{1,2})\s*[-/.\s]?\s*([a-zA-ZçÇğĞıIİiöÖşŞüÜ])\s*(?:sınıfı|sinifi)?\s*",
        ad or "",
    )
    if not m:
        return (ad or "").strip()
    harf = m.group(2).replace("i", "İ").replace("ı", "I").upper()
    return f"{m.group(1)}-{harf}"


def _veli_alicilari(conn, sinif_ad: str) -> list[tuple[str, str]]:
    sinif = next((s for s in db.siniflar_listele(conn) if s["ad"] == sinif_ad), None)
    if sinif is None:
        return []
    goruldu, alicilar = set(), []
    for ad, tel in db.kisiler_telefonlu(conn, sinif["id"], "veli"):
        tel = gonderim.normalize_phone(tel)
        if (
            gonderim.is_valid_phone(tel) and tel not in goruldu
        ):  # kardeş velisi tek SMS alır
            goruldu.add(tel)
            alicilar.append((ad, tel))
    return alicilar


class VeliTaslakIstek(BaseModel):
    sinif: str
    metin: str


@router.post("/veli-taslak", dependencies=[Depends(anahtar_dogrula)])
def veli_taslak(istek: VeliTaslakIstek):
    metin = _metin(istek.metin, VELI_AZAMI)
    sinif = _sinif_normalize(istek.sinif)
    conn = db.baglanti()
    try:
        alicilar = _veli_alicilari(conn, sinif)
        if not alicilar:
            raise HTTPException(
                status_code=404,
                detail=f"{sinif} için telefonu kayıtlı veli bulunamadı.",
            )
        tid = secrets.token_hex(4)
        conn.execute(
            "INSERT INTO veli_taslaklari (id, sinif, metin, alici_sayisi, olusturma) "
            "VALUES (?, ?, ?, ?, ?)",
            (tid, sinif, metin, len(alicilar), simdi().strftime(ZAMAN_BICIMI)),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "taslak_id": tid,
        "sinif": sinif,
        "alici_sayisi": len(alicilar),
        "metin": metin,
        "gecerlilik_dk": int(TASLAK_OMRU.total_seconds() // 60),
    }


class VeliGonderIstek(BaseModel):
    taslak_id: str


@router.post("/veli-gonder", dependencies=[Depends(anahtar_dogrula)])
def veli_gonder(istek: VeliGonderIstek):
    conn = db.baglanti()
    try:
        t = conn.execute(
            "SELECT * FROM veli_taslaklari WHERE id = ?", (istek.taslak_id,)
        ).fetchone()
        if t is None or t["durum"] != "taslak":
            raise HTTPException(
                status_code=404,
                detail="Gönderilmemiş böyle bir taslak yok; yeni taslak oluştur.",
            )
        if simdi() - datetime.strptime(t["olusturma"], ZAMAN_BICIMI) > TASLAK_OMRU:
            raise HTTPException(
                status_code=410, detail="Taslağın süresi doldu; yeni taslak oluştur."
            )
        alicilar = _veli_alicilari(conn, t["sinif"])
        if not alicilar:
            raise HTTPException(status_code=404, detail="Alıcı kalmadı.")
        gid = gonder([(ad, tel, t["metin"]) for ad, tel in alicilar])
        conn.execute(
            "UPDATE veli_taslaklari SET durum = 'gonderildi', gonderim_id = ? WHERE id = ?",
            (gid, t["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"gonderim_id": gid, "sinif": t["sinif"], "alici_sayisi": len(alicilar)}
