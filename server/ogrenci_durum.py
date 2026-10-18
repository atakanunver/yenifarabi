"""server/ogrenci_durum.py — "Öğrenci Bilgi Formu Detay" tablosunu yapılandırılmış sorgu olarak sunar (2026-10-16).

Kaynak: mudur/ klasöründeki en yeni `bilgi fomu detay*.docx` (sütunlar: SINIF, OKUL NO, AD SOYAD, MADDİ YETERSİZLİK,
HASTALIK, ANA BABA AYRI / ÖLÜ). Aynı belge RAG'a da düz metin olarak girer; ama "anne babası ayrı öğrenciler"
gibi liste soruları parça aramasıyla güvenilir cevaplanamaz → tablo olarak okunur, dosya her yıl değiştiğinde
(`...20272028.docx`) otomatik en yenisi alınır. Veri kısıtı yok (kullanıcı kararı 2026-10-16); erişim webui anahtarı +
Atos aracı yalnızca yönetici. İçerik loga yazılmaz.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

import idari_yukle
from webui import webui_anahtari_dogrula

log = logging.getLogger("farabi.ogrenci_durum")
router = APIRouter(prefix="/api/webui/ogrenci-durum", dependencies=[Depends(webui_anahtari_dogrula)])

DESEN = "bilgi fomu detay*.docx"
BOS = {"", "-", "--", "—", "–", "yok", "YOK"}
_ONBELLEK: dict = {}  # (yol, mtime) -> satırlar


class DurumIstek(BaseModel):
    tur: Literal["ana_baba", "maddi", "hastalik", "hepsi"] = "ana_baba"
    sinif: str = Field("", max_length=20)


def _sinif_anahtari(s: str) -> str:
    return "".join(c for c in (s or "").lower() if c.isalnum())


def _sinif_adi(s: str) -> str:
    """'9/A' ya da '10-A' → '9-A' / '10-A'."""
    k = (s or "").strip().replace("/", "-").replace(" ", "")
    return k.upper() if k else k


def dosya_bul(klasor: Path | None = None) -> Path | None:
    yollar = sorted((klasor or idari_yukle.KLASOR).glob(DESEN), key=lambda p: p.stat().st_mtime)
    return yollar[-1] if yollar else None


def satirlari_oku(yol: Path) -> list[dict]:
    anahtar = (str(yol), yol.stat().st_mtime)
    if anahtar in _ONBELLEK:
        return _ONBELLEK[anahtar]
    import docx

    sonuc = []
    for tablo in docx.Document(str(yol)).tables:
        baslik = [c.text.strip().upper() for c in tablo.rows[0].cells]
        if not any("AD SOYAD" in b for b in baslik):
            continue

        def sutun(*anahtarlar):
            return next((i for i, b in enumerate(baslik) if any(a in b for a in anahtarlar)), None)

        ix = {"sinif": sutun("SINIF"), "no": sutun("OKUL NO"), "ad": sutun("AD SOYAD"),
              "maddi": sutun("MADDİ", "MADDI"), "hastalik": sutun("HASTALIK"), "ana_baba": sutun("AYRI", "ÖLÜ")}
        for satir in tablo.rows[1:]:
            h = [c.text.strip() for c in satir.cells]

            def al(k):
                i = ix[k]
                return h[i] if i is not None and i < len(h) else ""

            if not al("ad"):
                continue
            sonuc.append({"sinif": _sinif_adi(al("sinif")), "okul_no": al("no"), "ad_soyad": al("ad"),
                          "maddi": al("maddi"), "hastalik": al("hastalik"), "ana_baba": al("ana_baba")})
    _ONBELLEK.clear()
    _ONBELLEK[anahtar] = sonuc
    return sonuc


def dolu_mu(deger: str) -> bool:
    return (deger or "").strip() not in BOS


@router.post("/getir")
def getir(istek: DurumIstek):
    yol = dosya_bul()
    if yol is None:
        return {"durum": "yok", "mesaj": "Öğrenci Bilgi Formu Detay belgesi mudur/ klasöründe bulunamadı."}
    try:
        satirlar = satirlari_oku(yol)
    except Exception as e:  # noqa: BLE001 — bozuk dosya; ayrıntı yanıta sızmasın
        log.warning("ogrenci-durum okunamadı: %s", type(e).__name__)
        return {"durum": "hata", "mesaj": "Belge okunamadı."}
    if istek.sinif.strip():
        k = _sinif_anahtari(istek.sinif)
        satirlar = [s for s in satirlar if _sinif_anahtari(s["sinif"]) == k]
    secili = ["ana_baba", "maddi", "hastalik"] if istek.tur == "hepsi" else [istek.tur]
    eslesen = [s for s in satirlar if any(dolu_mu(s[t]) for t in secili)]
    log.info("ogrenci-durum sorgusu: tur=%s, %d/%d", istek.tur, len(eslesen), len(satirlar))
    return {"durum": "ok", "kaynak": yol.name, "toplam_kayit": len(satirlar), "ogrenciler": eslesen}
