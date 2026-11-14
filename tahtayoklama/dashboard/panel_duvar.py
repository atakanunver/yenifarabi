"""panel_duvar.py — panel arka planı (uzamsal cam kabuğu, 2026-11-14).

Resimler depoda değil, sunucudaki bir klasörde durur (varsayılan /home/ata/wallpaper; depo PUBLIC).
Klasöre resim eklemek yeterli: Ayarlar › Temalar › Duvar kağıdı listesi buradan dolar. Seçim
tarayıcıda (localStorage) tutulur, sunucuya yazılmaz. Giriş sayfası da kullandığı için oturum istemez;
yalnız listedeki dosya adları sunulur (yol/klasör adı kabul edilmez).
"""

import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

DIZIN = Path(os.environ.get("FARABI_DUVAR_DIZINI", "/home/ata/wallpaper"))
UZANTILAR = {".jpg", ".jpeg", ".png", ".webp"}
_onbellek: dict = {}

router = APIRouter()


def liste() -> list[dict]:
    """[{ad, url}] ad sırasıyla; url ?v=<mtime> taşır (dosya değişince tarayıcı yenisini çeker). 10 sn önbellekli."""
    simdi = time.monotonic()
    if _onbellek.get("t", -1e9) + 10 < simdi:
        try:
            dosyalar = sorted(
                (f for f in DIZIN.iterdir() if f.is_file() and f.suffix.lower() in UZANTILAR),
                key=lambda f: f.name,
            )
            sonuc = [{"ad": f.name, "url": f"/panel-duvar/{f.name}?v={int(f.stat().st_mtime)}"} for f in dosyalar]
        except OSError:
            sonuc = []
        _onbellek.update(t=simdi, v=sonuc)
    return _onbellek["v"]


@router.get("/panel-duvar/{ad}")
async def panel_duvar(ad: str):
    if ad not in {d["ad"] for d in liste()}:
        raise HTTPException(status_code=404)
    return FileResponse(DIZIN / ad, headers={"Cache-Control": "public, max-age=604800"})
