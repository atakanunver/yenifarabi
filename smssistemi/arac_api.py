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
    gonderim_id TEXT,
    tur TEXT NOT NULL DEFAULT 'veli',        -- veli|ogrenci (alıcı türü)
    test_telefon TEXT                        -- doluysa sınıf yerine yalnızca bu numara
);
CREATE TABLE IF NOT EXISTS kisisel_taslaklari (
    id TEXT PRIMARY KEY,
    ogeler TEXT NOT NULL,           -- JSON: [{okul_no, metin_sablon}]
    alici_sayisi INTEGER NOT NULL,
    olusturma TEXT NOT NULL,        -- TR yerel saat
    durum TEXT NOT NULL DEFAULT 'taslak',    -- taslak|gonderildi
    gonderim_id TEXT,
    test_telefon TEXT
);
"""


def sema_kur() -> None:
    conn = db.baglanti()
    try:
        conn.executescript(SEMA)
        mevcut = [r["name"] for r in conn.execute("PRAGMA table_info(veli_taslaklari)").fetchall()]
        if "tur" not in mevcut:  # eski DB: tur kolonu sonradan eklendi
            conn.execute("ALTER TABLE veli_taslaklari ADD COLUMN tur TEXT NOT NULL DEFAULT 'veli'")
        if "test_telefon" not in mevcut:
            conn.execute("ALTER TABLE veli_taslaklari ADD COLUMN test_telefon TEXT")
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


def _alicilar(conn, sinif_ad: str, tur: str) -> list[tuple[str, str]]:
    sinif = next((s for s in db.siniflar_listele(conn) if s["ad"] == sinif_ad), None)
    if sinif is None:
        return []
    goruldu, alicilar = set(), []
    for ad, tel in db.kisiler_telefonlu(conn, sinif["id"], tur):
        tel = gonderim.normalize_phone(tel)
        if (
            gonderim.is_valid_phone(tel) and tel not in goruldu
        ):  # aynı telefon (kardeş velisi vb.) tek SMS alır
            goruldu.add(tel)
            alicilar.append((ad, tel))
    return alicilar


def _veli_alicilari(conn, sinif_ad: str) -> list[tuple[str, str]]:
    return _alicilar(conn, sinif_ad, "veli")


_TUR_ETIKET = {"veli": "veli", "ogrenci": "öğrenci"}


def _test_alicisi(tel: str) -> list[tuple[str, str]]:
    tel = gonderim.normalize_phone(tel)
    if not gonderim.is_valid_phone(tel):
        raise HTTPException(status_code=422, detail="Test telefonu geçersiz.")
    return [("test", tel)]


def _taslak_olustur(
    sinif_ham: str, metin_ham: str, tur: str, test_telefon: str | None = None
) -> dict:
    metin = _metin(metin_ham, VELI_AZAMI)
    sinif = _sinif_normalize(sinif_ham)
    test_tel = None
    if test_telefon:
        alicilar = _test_alicisi(test_telefon)
        test_tel = alicilar[0][1]
    conn = db.baglanti()
    try:
        if test_tel is None:
            alicilar = _alicilar(conn, sinif, tur)
        if not alicilar:
            raise HTTPException(
                status_code=404,
                detail=f"{sinif} için telefonu kayıtlı {_TUR_ETIKET[tur]} bulunamadı.",
            )
        tid = secrets.token_hex(4)
        conn.execute(
            "INSERT INTO veli_taslaklari "
            "(id, sinif, metin, alici_sayisi, olusturma, tur, test_telefon) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (tid, sinif, metin, len(alicilar), simdi().strftime(ZAMAN_BICIMI), tur, test_tel),
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
        "test": test_tel is not None,
    }


def _suresi_doldu(olusturma: str) -> bool:
    """Taslak ömrü (TR yerel saat, naive — simdi() ile aynı düzlemde)."""
    return simdi() - datetime.strptime(olusturma, ZAMAN_BICIMI) > TASLAK_OMRU


def _taslak_gonder(taslak_id: str, tur: str) -> dict:
    conn = db.baglanti()
    try:
        t = conn.execute(
            "SELECT * FROM veli_taslaklari WHERE id = ? AND tur = ?", (taslak_id, tur)
        ).fetchone()
        if t is None or t["durum"] != "taslak":
            raise HTTPException(
                status_code=404,
                detail="Gönderilmemiş böyle bir taslak yok; yeni taslak oluştur.",
            )
        if _suresi_doldu(t["olusturma"]):
            raise HTTPException(
                status_code=410, detail="Taslağın süresi doldu; yeni taslak oluştur."
            )
        if t["test_telefon"]:
            alicilar = [("test", t["test_telefon"])]
        else:
            alicilar = _alicilar(conn, t["sinif"], tur)
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


class VeliTaslakIstek(BaseModel):
    sinif: str
    metin: str


@router.post("/veli-taslak", dependencies=[Depends(anahtar_dogrula)])
def veli_taslak(istek: VeliTaslakIstek):
    return _taslak_olustur(istek.sinif, istek.metin, "veli")


class VeliGonderIstek(BaseModel):
    taslak_id: str


@router.post("/veli-gonder", dependencies=[Depends(anahtar_dogrula)])
def veli_gonder(istek: VeliGonderIstek):
    return _taslak_gonder(istek.taslak_id, "veli")


# --- Öğrenci SMS'i (aynı desen; alıcı = sınıfın öğrencileri) -----------


class OgrenciTaslakIstek(VeliTaslakIstek):
    test_telefon: str | None = None  # doluysa sınıf yerine yalnızca bu numaraya (deneme)


@router.post("/ogrenci-taslak", dependencies=[Depends(anahtar_dogrula)])
def ogrenci_taslak(istek: OgrenciTaslakIstek):
    return _taslak_olustur(
        istek.sinif, istek.metin, "ogrenci", getattr(istek, "test_telefon", None)
    )


@router.post("/ogrenci-gonder", dependencies=[Depends(anahtar_dogrula)])
def ogrenci_gonder(istek: VeliGonderIstek):
    return _taslak_gonder(istek.taslak_id, "ogrenci")


# --- Kişiye özel SMS (okul_no ile öğrenci + velileri; {ad} doldurulur) ---


def _kisisel_alicilar(
    conn, ogeler: list[dict], test_telefon: str | None = None
) -> tuple[list[tuple[int, str, str, str]], list[int], list[int]]:
    """(alıcılar, bulunamayan, alicisiz) döndürür. alıcı = (okul_no, ad, telefon, metin).
    Eşleşme YALNIZCA okul_no ile (sınıf kullanılmaz). Telefonlar öğe içinde tekil.
    test_telefon varsa yalnızca İLK bulunan öğe, yalnızca o numaraya."""
    test_alici = _test_alicisi(test_telefon)[0] if test_telefon else None
    liste, bulunamayan, alicisiz = [], [], []
    for oge in ogeler:
        no = int(oge["okul_no"])
        ogr = conn.execute(
            "SELECT id, ad_soyad, telefon FROM kisiler "
            "WHERE tur = 'ogrenci' AND okul_no = ? ORDER BY id LIMIT 1",
            (no,),
        ).fetchone()
        if ogr is None:
            bulunamayan.append(no)
            continue
        try:
            metin = _metin(str(oge["metin_sablon"]).replace("{ad}", ogr["ad_soyad"]), VELI_AZAMI)
        except HTTPException as e:
            raise HTTPException(
                status_code=422, detail=f"okul_no {no}: {e.detail}"
            ) from None
        if test_alici is not None:
            return [(no, test_alici[0], test_alici[1], metin)], bulunamayan, alicisiz
        adaylar = [(ogr["ad_soyad"], ogr["telefon"] or "")]
        adaylar += [(v["ad_soyad"], v["telefon"]) for v in db.veliler_ogrenci_ile(conn, ogr["id"])]
        goruldu, oge_alicilari = set(), []
        for ad, tel in adaylar:
            tel = gonderim.normalize_phone(tel)
            if gonderim.is_valid_phone(tel) and tel not in goruldu:
                goruldu.add(tel)
                oge_alicilari.append((no, ad, tel, metin))
        if not oge_alicilari:
            alicisiz.append(no)
        liste += oge_alicilari
    return liste, bulunamayan, alicisiz


class KisiselOge(BaseModel):
    okul_no: int
    metin_sablon: str


class KisiselTaslakIstek(BaseModel):
    ogeler: list[KisiselOge]
    test_telefon: str | None = None


@router.post("/kisisel-taslak", dependencies=[Depends(anahtar_dogrula)])
def kisisel_taslak(istek: KisiselTaslakIstek):
    ogeler = [o.model_dump() for o in istek.ogeler]
    test_tel = None
    if istek.test_telefon:
        test_tel = _test_alicisi(istek.test_telefon)[0][1]
    conn = db.baglanti()
    try:
        liste, bulunamayan, alicisiz = _kisisel_alicilar(conn, ogeler, test_tel)
        if not liste:
            raise HTTPException(
                status_code=404,
                detail=f"Alıcı bulunamadı (bulunamayan okul_no: {bulunamayan}, alıcısız: {alicisiz}).",
            )
        tid = secrets.token_hex(4)
        conn.execute(
            "INSERT INTO kisisel_taslaklari "
            "(id, ogeler, alici_sayisi, olusturma, test_telefon) VALUES (?, ?, ?, ?, ?)",
            (
                tid,
                json.dumps(ogeler, ensure_ascii=False),
                len(liste),
                simdi().strftime(ZAMAN_BICIMI),
                test_tel,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "taslak_id": tid,
        "oge_sayisi": len({a[0] for a in liste}),
        "alici_sayisi": len(liste),
        "bulunamayan": bulunamayan,
        "alicisiz": alicisiz,
        "ornek_metin": liste[0][3],
        "test": test_tel is not None,
        "gecerlilik_dk": int(TASLAK_OMRU.total_seconds() // 60),
    }


class KisiselGonderIstek(BaseModel):
    taslak_id: str


@router.post("/kisisel-gonder", dependencies=[Depends(anahtar_dogrula)])
def kisisel_gonder(istek: KisiselGonderIstek):
    conn = db.baglanti()
    try:
        t = conn.execute(
            "SELECT * FROM kisisel_taslaklari WHERE id = ?", (istek.taslak_id,)
        ).fetchone()
        if t is None or t["durum"] != "taslak":
            raise HTTPException(
                status_code=404,
                detail="Gönderilmemiş böyle bir taslak yok; yeni taslak oluştur.",
            )
        if _suresi_doldu(t["olusturma"]):
            raise HTTPException(
                status_code=410, detail="Taslağın süresi doldu; yeni taslak oluştur."
            )
        liste, _, _ = _kisisel_alicilar(conn, json.loads(t["ogeler"]), t["test_telefon"])
        if not liste:
            raise HTTPException(status_code=404, detail="Alıcı kalmadı.")
        gid = gonder([(ad, tel, metin) for _, ad, tel, metin in liste])
        conn.execute(
            "UPDATE kisisel_taslaklari SET durum = 'gonderildi', gonderim_id = ? WHERE id = ?",
            (gid, t["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "gonderim_id": gid,
        "oge_sayisi": len({a[0] for a in liste}),
        "alici_sayisi": len(liste),
    }


# --- Dijital okul (okul/, port 9090) veli giriş kodu — 2026-10-10 ---
# Tek telefona serbest metin. Anahtar sızsa bile toplu SMS aracı olamasın diye
# telefon başına dakikada 1 / saatte 5 sınırı vardır (bellekte; servis yeniden
# başlayınca sıfırlanır — kabul edilebilir, kod zaten 5 dk geçerli).
KOD_SMS_DAKIKA = timedelta(minutes=1)
KOD_SMS_SAAT_AZAMI = 5
_kod_sms_gecmis: dict[str, list[datetime]] = {}


class KodSmsIstek(BaseModel):
    telefon: str
    metin: str


@router.post("/kod-sms", dependencies=[Depends(anahtar_dogrula)])
def kod_sms(istek: KodSmsIstek):
    tel = gonderim.normalize_phone(istek.telefon)
    if not gonderim.is_valid_phone(tel):
        raise HTTPException(status_code=422, detail="Geçersiz telefon.")
    metin = istek.metin.strip()
    if not metin or len(metin) > 160:
        raise HTTPException(status_code=422, detail="Metin 1-160 karakter olmalı.")
    an = simdi()
    gecmis = [t for t in _kod_sms_gecmis.get(tel, []) if an - t < timedelta(hours=1)]
    if (gecmis and an - gecmis[-1] < KOD_SMS_DAKIKA) or len(gecmis) >= KOD_SMS_SAAT_AZAMI:
        raise HTTPException(status_code=429, detail="Bu numaraya çok sık kod gönderildi.")
    gecmis.append(an)
    _kod_sms_gecmis[tel] = gecmis
    return {"gonderim_id": gonder([("Dijital Okul", tel, metin)])}
