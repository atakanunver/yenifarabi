"""kameralar.py — Okul güvenlik kameraları canlı izleme (WebRTC/mediamtx) ve harekete duyarlı kayıt arşivi.
Kaynak akışlar ~/farabi/kameralar/ altında (mediamtx + ffmpeg), hareket algılama ve temizlik
~/farabi/kameralar/hareket/hareket.py tarafından yürütülür.
Üç sayfa:
  - /kameralar (DVR, ana canlı izleme)
  - /kameralar-ip (bağımsız IP kameralar, yedek canlı izleme)
  - /kameralar-kayit (harekete duyarlı geçmiş kayıtları tarih/saat seçerek izleme — 2026-10-27)
"""

import re
import subprocess
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import guvenlik
import menu

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci

KAYIT_KOK = Path("/mnt/farabi-data/kamera-kayit")
ONBELLEK_KOK = Path("/tmp/kamera-h264-onbellek")
DOSYA_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})-(\d{2})-\d+\.mp4$")

# Klasör adı -> (Görünen ad, doğrudan H264 mü)
KAMERA_KAYITLARI: dict[str, tuple[str, bool]] = {
    "giris_ip_ham": ("Giriş", False),
    "onbahce_ip_ham": ("Ön Bahçe", False),
    "altkoridor_ip_ham": ("Alt Koridor", False),
    "ustkoridor_ip_ham": ("Üst Koridor", False),
    "ogretmenler_ip_ham": ("Öğretmenler Koridoru", False),
    "arkataraf_ham": ("Yan Bahçe / Arka Taraf", False),
    "disbina_kaliteli_ham": ("Dış Bina Girişi", True),
    "rsvideo_250": ("Basket Sahası / Dış 1", True),
}


def _yetkili_mi(request: Request) -> bool:
    if guvenlik.yetkili(request):
        return True
    conn = db.baglanti()
    try:
        return bool(auth.dogrula(request, conn))
    finally:
        conn.close()


async def _goster(request: Request, sablon: str):
    if not _yetkili_mi(request):
        return RedirectResponse("/giris", status_code=303)
    return templates.TemplateResponse(request, sablon, {})


@router.get("/kameralar", response_class=HTMLResponse)
async def kameralar_sayfa(request: Request):
    return await _goster(request, "kameralar.html")


@router.get("/kameralar-ip", response_class=HTMLResponse)
async def kameralar_ip_sayfa(request: Request):
    return await _goster(request, "kameralar_ip.html")


@router.get("/kameralar-kayit", response_class=HTMLResponse)
async def kameralar_kayit_sayfa(request: Request):
    return await _goster(request, "kameralar_kayit.html")


@router.get("/api/kameralar/kayitlar")
async def api_kamera_kayitlari(request: Request, kamera: str = "", tarih: str = ""):
    if not _yetkili_mi(request):
        raise HTTPException(status_code=401, detail="Yetkisiz erişim")

    kameralar_listesi = [
        {"id": k, "ad": ad} for k, (ad, _) in KAMERA_KAYITLARI.items()
    ]
    secili_kamera = kamera if kamera in KAMERA_KAYITLARI else next(iter(KAMERA_KAYITLARI))
    klasor = KAYIT_KOK / secili_kamera

    gunler_set: set[str] = set()
    dosyalar: list[Path] = []
    if klasor.is_dir():
        for p in klasor.iterdir():
            m = DOSYA_RE.match(p.name)
            if m:
                gunler_set.add(m.group(1))
                dosyalar.append(p)

    gunler = sorted(gunler_set, reverse=True)
    secili_tarih = tarih if tarih in gunler_set else (gunler[0] if gunler else "")

    kayitlar = []
    if secili_tarih:
        for p in sorted(dosyalar, key=lambda x: x.name, reverse=True):
            m = DOSYA_RE.match(p.name)
            if m and m.group(1) == secili_tarih:
                try:
                    boyut_mb = round(p.stat().st_size / (1024 * 1024), 2)
                except OSError:
                    continue
                if boyut_mb < 0.03:
                    continue
                kayitlar.append(
                    {
                        "dosya": p.name,
                        "saat": f"{m.group(2)}:{m.group(3)}:{m.group(4)}",
                        "saat_grup": m.group(2),
                        "boyut_mb": boyut_mb,
                    }
                )

    return JSONResponse(
        {
            "kameralar": kameralar_listesi,
            "secili_kamera": secili_kamera,
            "gunler": gunler,
            "secili_tarih": secili_tarih,
            "kayitlar": kayitlar,
        }
    )


@router.get("/api/kameralar/video/{kamera}/{dosya}")
async def api_kamera_video(request: Request, kamera: str, dosya: str):
    if not _yetkili_mi(request):
        raise HTTPException(status_code=401, detail="Yetkisiz erişim")
    if kamera not in KAMERA_KAYITLARI or not DOSYA_RE.match(dosya):
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı")

    kaynak = KAYIT_KOK / kamera / dosya
    if not kaynak.is_file():
        raise HTTPException(status_code=404, detail="Kayıt dosyası yok")

    # Tarayıcı uyumluluğu için (HEVC -> H264 ve fMP4 -> faststart MP4) hızlı önbellek
    ONBELLEK_KOK.mkdir(parents=True, exist_ok=True)
    hedef = ONBELLEK_KOK / f"{kamera}__{dosya}"
    if not hedef.is_file() or hedef.stat().st_size == 0:
        # Önbellekte en fazla 60 dosya tut
        mevcut = sorted(ONBELLEK_KOK.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        for eski in mevcut[:-60]:
            eski.unlink(missing_ok=True)

        _, dogrudan_h264 = KAMERA_KAYITLARI[kamera]
        gecici = hedef.with_suffix(".tmp.mp4")
        komut = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(kaynak),
            *(
                ["-c:v", "copy"]
                if dogrudan_h264
                else ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p"]
            ),
            "-an",
            "-movflags",
            "+faststart",
            str(gecici),
        ]
        r = subprocess.run(komut, timeout=25, check=False)
        if r.returncode != 0 or not gecici.is_file() or gecici.stat().st_size == 0:
            gecici.unlink(missing_ok=True)
            return FileResponse(kaynak, media_type="video/mp4", filename=dosya)
        gecici.replace(hedef)

    return FileResponse(hedef, media_type="video/mp4", filename=dosya)
