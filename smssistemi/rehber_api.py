"""smssistemi/rehber_api.py — Atos "Okul Bilgisi" aracı için salt-okunur öğrenci/veli iletişim sorgusu (2026-10-16).

GET /api/arac/ogrenci-iletisim?ad=&sinif=&dogum_yili=  (X-Sms-Arac-Key ile; arac_api.anahtar_dogrula)
Öğrencinin okul no, sınıf, doğum tarihi, kendi telefonu ve bağlı velilerinin (anne/baba/...)
telefonlarını döner. Yazma yok. Telefon ve doğum tarihi KVKK kapsamındadır: araç tarafı yalnızca
Open WebUI yöneticisine (admin) açar; ad/telefon loga YAZILMAZ, yalnızca sonuç sayısı.
"Anne-baba ayrı mı" bilgisi kayıtlarda YOK; uydurulmaz (araç bunu kullanıcıya söyler).
"""

from __future__ import annotations

import logging
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

import db
from arac_api import anahtar_dogrula

log = logging.getLogger("smssistemi.rehber")
router = APIRouter(prefix="/api/arac")
AZAMI = 60
TUM_AZAMI = 500  # liste/PDF için `limit` ile istenebilecek en çok kayıt


def _sade(metin: str | None) -> str:
    """Türkçe küçük harf; ı/i ve aksan farkı yok sayılır (okul API'siyle aynı kural)."""
    m = str(metin or "").replace("I", "ı").replace("İ", "i").lower().replace("ı", "i")
    m = unicodedata.normalize("NFKD", m)
    return "".join(c for c in m if not unicodedata.combining(c))


def _sinif_anahtari(ad: str | None) -> str:
    return "".join(c for c in _sade(ad) if c.isalnum())


@router.get("/ogrenci-iletisim", dependencies=[Depends(anahtar_dogrula)])
def ogrenci_iletisim(ad: str = "", sinif: str = "", dogum_yili: str = "", limit: int = AZAMI):
    ad, sinif, dogum_yili = ad.strip(), sinif.strip(), dogum_yili.strip()
    if not (ad or sinif or dogum_yili):
        raise HTTPException(400, "ad, sinif ya da dogum_yili gerekli.")
    if dogum_yili and not re.fullmatch(r"\d{4}", dogum_yili):
        raise HTTPException(400, "dogum_yili 4 haneli yıl olmalı (örn. 2010).")
    conn = db.baglanti()
    try:
        satirlar = conn.execute(
            "SELECT k.id, k.ad_soyad, k.telefon, k.tur, k.veli_rol, k.dogum_tarihi, "
            "k.okul_no, k.ogrenci_kisi_id, s.ad AS sinif "
            "FROM kisiler k JOIN siniflar s ON s.id = k.sinif_id "
            "WHERE k.tur IN ('ogrenci', 'veli')"
        ).fetchall()
    finally:
        conn.close()
    veliler: dict[int, list[dict]] = {}
    for r in satirlar:
        if r["tur"] == "veli" and r["ogrenci_kisi_id"]:
            veliler.setdefault(r["ogrenci_kisi_id"], []).append(
                {"rol": r["veli_rol"] or "Veli", "ad_soyad": r["ad_soyad"], "telefon": r["telefon"] or ""}
            )
    parcalar = _sade(ad).split()
    sonuc = []
    for r in satirlar:
        if r["tur"] != "ogrenci":
            continue
        if parcalar and not all(p in _sade(r["ad_soyad"]) for p in parcalar):
            continue
        if sinif and _sinif_anahtari(r["sinif"]) != _sinif_anahtari(sinif):
            continue
        if dogum_yili and not (r["dogum_tarihi"] or "").startswith(dogum_yili):
            continue
        sonuc.append(
            {
                "ad_soyad": r["ad_soyad"],
                "okul_no": r["okul_no"],
                "sinif": r["sinif"],
                "dogum_tarihi": r["dogum_tarihi"] or "",
                "ogrenci_telefon": r["telefon"] or "",
                "veliler": sorted(veliler.get(r["id"], []), key=lambda v: v["rol"]),
            }
        )
    sonuc.sort(key=lambda o: (o["sinif"], o["okul_no"] or 0))
    log.info("rehber/ogrenci-iletisim sorgusu: %d sonuç", len(sonuc))
    return JSONResponse({"toplam": len(sonuc), "ogrenciler": sonuc[: max(1, min(limit, TUM_AZAMI))]})
