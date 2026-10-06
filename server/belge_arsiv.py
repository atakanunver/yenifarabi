"""server/belge_arsiv.py — Atos (Open WebUI) "Belge Kalıcı Kayıt" aracının sunucu ucu (2026-10-05).

Araç (openwebui/farabi_belge_araci.py) sohbete eklenen dosyayı base64 olarak gönderir;
burada mudur/ klasörüne yazılır ve YALNIZCA o dosya için idari_yukle.py çalıştırılır
(gömme bge-m3, bilgehan). Aynı içerik klasörde başka bir adla zaten varsa ikinci kopya
yazılmaz. İdari kayıtlar yalnızca İdare'nin "hepsi"/"idari" kapsamından aranır (webui.py).
Gece taraması (farabi-idari-yukle.timer) klasöre elle atılan dosyaları da yükler.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import idari_yukle
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from webui import webui_anahtari_dogrula

log = logging.getLogger("farabi.belge_arsiv")
router = APIRouter()

KLASOR = idari_yukle.KLASOR
AZAMI_BAYT = 40 * 1024 * 1024
YUKLE_ZAMAN_ASIMI_SN = 600
SONUC_RE = re.compile(r"^yüklendi: (?P<ad>.+) — (?P<parca>\d+) parça$", re.MULTILINE)


class BelgeIstek(BaseModel):
    ad: str = Field(..., min_length=1, max_length=200)
    icerik_b64: str = Field(..., min_length=1)


def guvenli_ad(ad: str) -> str | None:
    """Yol bileşenlerini atar; gizli dosya ve desteklenmeyen uzantı → None."""
    ad = Path(ad.replace("\\", "/")).name.strip()
    if (
        not ad
        or ad.startswith(".")
        or Path(ad).suffix.lower() not in idari_yukle.UZANTILAR
    ):
        return None
    return ad


def ayni_icerikli(veri: bytes, klasor: Path) -> Path | None:
    h = hashlib.sha256(veri).hexdigest()
    for yol in idari_yukle.belgeleri_listele(klasor):
        if (
            yol.stat().st_size == len(veri)
            and hashlib.sha256(yol.read_bytes()).hexdigest() == h
        ):
            return yol
    return None


def rag_yukle(yol: Path) -> tuple[str, int | None, str]:
    """(rag durumu, parça sayısı, belge adı). Ayrı süreç: tokenizer/OCR API'yi şişirmesin."""
    betik = Path(idari_yukle.__file__).resolve()
    r = subprocess.run(
        [sys.executable, str(betik), "--dosya", str(yol)],
        capture_output=True,
        text=True,
        timeout=YUKLE_ZAMAN_ASIMI_SN,
        cwd=str(betik.parent),
        check=False,
    )
    m = SONUC_RE.search(r.stdout)
    if m:
        return "yuklendi", int(m["parca"]), m["ad"]
    if "atlandı" in r.stdout:
        return "zaten_yuklu", None, idari_yukle.belge_adi(yol)
    log.warning(
        "idari_yukle başarısız (kod %s): %s",
        r.returncode,
        (r.stderr or r.stdout)[-500:],
    )
    return "hata", None, idari_yukle.belge_adi(yol)


@router.post("/api/webui/belge-kaydet", dependencies=[Depends(webui_anahtari_dogrula)])
def belge_kaydet(istek: BelgeIstek):
    ad = guvenli_ad(istek.ad)
    if ad is None:
        return {
            "durum": "desteklenmiyor",
            "ad": istek.ad,
            "mesaj": "Desteklenen türler: " + ", ".join(sorted(idari_yukle.UZANTILAR)),
        }
    try:
        veri = base64.b64decode(istek.icerik_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="icerik_b64 geçersiz") from None
    if not veri or len(veri) > AZAMI_BAYT:
        return {"durum": "hata", "ad": ad, "mesaj": "Dosya boş ya da 40 MB'tan büyük."}

    mevcut = ayni_icerikli(veri, KLASOR)
    if mevcut is not None:
        yol, arsiv = mevcut, "zaten_vardi"
    else:
        yol = KLASOR / ad
        arsiv = "guncellendi" if yol.exists() else "kaydedildi"
        gecici = yol.with_name(f".{ad}.yaziliyor")
        gecici.write_bytes(veri)
        os.replace(gecici, yol)
    try:
        rag, parca, belge = rag_yukle(yol)
    except subprocess.TimeoutExpired:
        rag, parca, belge = "hata", None, idari_yukle.belge_adi(yol)
    return {
        "durum": "ok" if rag != "hata" else "rag_hatasi",
        "ad": yol.name,
        "belge": belge,
        "arsiv": arsiv,
        "rag": rag,
        "parca": parca,
    }
