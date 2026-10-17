"""server/hafiza.py — Atos (Open WebUI) okul hafızasının sunucu ucu (2026-10-16).

Ortak okul hafızası (iki yönetici); öğretmen modelleri görmez (filtre/araç tarafı). Kayıt YALNIZCA
kullanıcı onayıyla: `kaydet` önce önizleme (taslak) döner, `onaylandi=true` ile yazar. Kişisel veri dahil
hiçbir içerik reddedilmez (kullanıcı kararı 2026-10-16: okul idaresi tüm bilgiye ihtiyaç duyar; veri yalnızca
yerelde, yalnızca yönetici hesabına açık).
Gömme bge-m3 (1024-d, normalize; webui.MOTOR.embed_model); gömme yoksa/başarısızsa tam-metin
aramasına düşülür. İçerik loga YAZILMAZ, yalnızca id+tür.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import db
import webui
from webui import webui_anahtari_dogrula

log = logging.getLogger("farabi.hafiza")
router = APIRouter(prefix="/api/webui/hafiza", dependencies=[Depends(webui_anahtari_dogrula)])

TABLO = "atos_hafiza"
AZAMI_KAYIT = 500
BENZER_ESIK = 0.92  # bu benzerlikte yeni kayıt açılmaz, mevcut güncellenir
UYARI_ESIK = 0.80  # önizlemede "benzer kayıt var" uyarısı
GETIR_ESIK = 0.45  # bge-m3 kosinüs benzerliği; altı enjekte edilmez
GETIR_AZAMI = 3
SABIT_KARAKTER = 500  # enjeksiyon bütçesi: sabit notlar
KAYIT_KARAKTER = 1000  # enjeksiyon bütçesi: ilgili kayıtlar
ISTANBUL = ZoneInfo("Europe/Istanbul")

def bugun() -> date:
    return datetime.now(ISTANBUL).date()


class KaydetIstek(BaseModel):
    baslik: str = Field(..., min_length=1, max_length=80)
    icerik: str = Field(..., min_length=1, max_length=600)
    tur: Literal["bilgi", "karar", "tercih", "belge"] = "bilgi"
    kaynak: str = Field("", max_length=120)
    son_gecerlilik: date | None = None
    sabit: bool = False
    onaylandi: bool = False
    yerine_gecen_id: int | None = None


class AraIstek(BaseModel):
    sorgu: str = Field("", max_length=500)
    limit: int = Field(5, ge=1, le=20)


class UnutIstek(BaseModel):
    id: int


class GetirIstek(BaseModel):
    soru: str = Field(..., min_length=1, max_length=2000)


def _vektor(metin: str):
    """bge-m3 vektörü; gömme yoksa/hata verirse None (tam-metin aramasına düşülür)."""
    motor = getattr(webui, "MOTOR", None)
    model = getattr(motor, "embed_model", None)
    if model is None:
        return None
    try:
        return model.encode(metin, normalize_embeddings=True)
    except Exception as e:  # noqa: BLE001 — gömme servisi kapalıysa hafıza yine çalışsın
        log.warning("hafiza gömme başarısız: %s", type(e).__name__)
        return None


_SATIR = "id, tur, baslik, icerik, kaynak, sabit, son_gecerlilik, olusturma"


def _kayit(s) -> dict:
    return {
        "id": s[0], "tur": s[1], "baslik": s[2], "icerik": s[3], "kaynak": s[4], "sabit": s[5],
        "son_gecerlilik": s[6].isoformat() if s[6] else None,
        "tarih": s[7].astimezone(ISTANBUL).date().isoformat(),
    }


def _benzerler(cur, vektor, esik: float, limit: int = 3) -> list[dict]:
    if vektor is None:
        return []
    cur.execute(
        f"SELECT {_SATIR}, 1 - (embedding <=> %s) AS skor FROM {TABLO} "
        "WHERE durum = 'aktif' AND embedding IS NOT NULL ORDER BY embedding <=> %s LIMIT %s",
        (vektor, vektor, limit),
    )
    return [{**_kayit(s), "skor": round(float(s[8]), 3)} for s in cur.fetchall() if float(s[8]) >= esik]


def _tam_metin(cur, sorgu: str, limit: int) -> list[dict]:
    cur.execute(
        f"SELECT {_SATIR} FROM {TABLO} WHERE durum = 'aktif' "
        "AND (son_gecerlilik IS NULL OR son_gecerlilik >= %s) "
        "AND to_tsvector('turkish', baslik || ' ' || icerik) @@ plainto_tsquery('turkish', %s) "
        "ORDER BY guncelleme DESC LIMIT %s",
        (bugun(), sorgu, limit),
    )
    return [{**_kayit(s), "skor": None} for s in cur.fetchall()]


def _ara(cur, sorgu: str, limit: int, esik: float) -> list[dict]:
    """Önce vektör (eşik üstü, süresi dolmamış); gömme yoksa ya da sonuç boşsa tam-metin."""
    v = _vektor(sorgu)
    if v is not None:
        cur.execute(
            f"SELECT {_SATIR}, 1 - (embedding <=> %s) AS skor FROM {TABLO} "
            "WHERE durum = 'aktif' AND embedding IS NOT NULL AND (son_gecerlilik IS NULL OR son_gecerlilik >= %s) "
            "ORDER BY embedding <=> %s LIMIT %s",
            (v, bugun(), v, limit),
        )
        sonuc = [{**_kayit(s), "skor": round(float(s[8]), 3)} for s in cur.fetchall() if float(s[8]) >= esik]
        if sonuc:
            return sonuc
    return _tam_metin(cur, sorgu, limit)


@router.post("/kaydet")
def kaydet(istek: KaydetIstek):
    vektor = _vektor(f"{istek.baslik}\n{istek.icerik}")
    with db.baglanti() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"SELECT count(*) FROM {TABLO} WHERE durum = 'aktif'")
                dolu = cur.fetchone()[0] >= AZAMI_KAYIT
                benzer = _benzerler(cur, vektor, UYARI_ESIK)
                if not istek.onaylandi:
                    return {"durum": "taslak", "onizleme": istek.model_dump(mode="json", exclude={"onaylandi"}),
                            "benzer": benzer}
                if benzer and benzer[0]["skor"] >= BENZER_ESIK:
                    hedef = benzer[0]["id"]
                    cur.execute(
                        f"UPDATE {TABLO} SET tur=%s, baslik=%s, icerik=%s, kaynak=%s, sabit=%s, son_gecerlilik=%s, "
                        "embedding=%s, guncelleme=now() WHERE id=%s",
                        (istek.tur, istek.baslik, istek.icerik, istek.kaynak, istek.sabit, istek.son_gecerlilik,
                         vektor, hedef),
                    )
                    conn.commit()
                    log.info("hafiza güncellendi id=%s tur=%s", hedef, istek.tur)
                    return {"durum": "guncellendi", "id": hedef}
                if dolu:
                    return {"durum": "dolu", "neden": f"Hafıza {AZAMI_KAYIT} kayıt sınırında; eski bir kaydı unutun."}
                cur.execute(
                    f"INSERT INTO {TABLO} (tur, baslik, icerik, kaynak, sabit, son_gecerlilik, yerine_gecen_id, embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (istek.tur, istek.baslik, istek.icerik, istek.kaynak, istek.sabit, istek.son_gecerlilik,
                     istek.yerine_gecen_id, vektor),
                )
                yeni = cur.fetchone()[0]
                if istek.yerine_gecen_id:
                    cur.execute(f"UPDATE {TABLO} SET durum='arsiv', guncelleme=now() WHERE id=%s", (istek.yerine_gecen_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    log.info("hafiza kaydedildi id=%s tur=%s", yeni, istek.tur)
    return {"durum": "kaydedildi", "id": yeni, "embedding": vektor is not None}


@router.post("/ara")
def ara(istek: AraIstek):
    with db.baglanti() as conn, conn.cursor() as cur:
        if istek.sorgu.strip():
            kayitlar = _ara(cur, istek.sorgu.strip(), istek.limit, GETIR_ESIK)
        else:  # sorgusuz = en yeni kayıtlar (listele)
            cur.execute(
                f"SELECT {_SATIR} FROM {TABLO} WHERE durum = 'aktif' AND (son_gecerlilik IS NULL OR son_gecerlilik >= %s) "
                "ORDER BY guncelleme DESC LIMIT %s",
                (bugun(), istek.limit),
            )
            kayitlar = [{**_kayit(s), "skor": None} for s in cur.fetchall()]
    return {"durum": "ok", "kayitlar": kayitlar}


@router.post("/unut")
def unut(istek: UnutIstek):
    with db.baglanti() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute(f"UPDATE {TABLO} SET durum='arsiv', guncelleme=now() WHERE id=%s AND durum='aktif' RETURNING id",
                            (istek.id,))
                bulundu = cur.fetchone() is not None
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    if bulundu:
        log.info("hafiza unutuldu id=%s", istek.id)
    return {"durum": "unutuldu" if bulundu else "bulunamadi", "id": istek.id}


@router.post("/getir")
def getir(istek: GetirIstek):
    """Filtre için: sabit çekirdek notlar + soruyla ilgili en çok 3 kayıt; karakter bütçesine göre kırpılmış."""
    try:
        with db.baglanti() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT {_SATIR} FROM {TABLO} WHERE durum='aktif' AND sabit "
                "AND (son_gecerlilik IS NULL OR son_gecerlilik >= %s) ORDER BY guncelleme DESC",
                (bugun(),),
            )
            sabit = [_kayit(s) for s in cur.fetchall()]
            ilgili = [k for k in _ara(cur, istek.soru, GETIR_AZAMI + len(sabit), GETIR_ESIK) if not k["sabit"]]
    except Exception as e:  # noqa: BLE001 — hafıza hatası sohbeti engellememeli
        log.warning("hafiza getir hatası: %s", type(e).__name__)
        return {"durum": "hata", "sabit": [], "kayitlar": []}
    return {"durum": "ok", "sabit": _kirp(sabit, SABIT_KARAKTER), "kayitlar": _kirp(ilgili[:GETIR_AZAMI], KAYIT_KARAKTER)}


def _kirp(kayitlar: list[dict], butce: int) -> list[dict]:
    sonuc, kullanilan = [], 0
    for k in kayitlar:
        uzunluk = len(k["baslik"]) + len(k["icerik"]) + 30
        if kullanilan + uzunluk > butce:
            break
        sonuc.append(k)
        kullanilan += uzunluk
    return sonuc
