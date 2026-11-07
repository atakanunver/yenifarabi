"""Duyurular paneli (/duyurular, 2026-11-01): tüm duyuru kanalları tek sayfada.

- Tahta duyurusu: gönder (duyuru.formdan_gonder, /admin/uzaktan'daki formla aynı yol),
  son 2 günün gönderimleri, hepsini kapat.
- Otomatik hatırlatmalar: okul sınav takviminden yaklaşan denemeler (deneme_hatirlatma.py)
  ve tahtaya bir sonraki gönderim zamanı.
- smual.app: yayındaki okul portalı duyuruları (okul.db, salt-okunur; aylik_ozet ile aynı istisna).
- Kiosk panosu: okul /api/pano'nun şu an döndürdüğü duyurular.
Okul kaynakları kapalıysa ilgili bölüm empty-state gösterir; sayfa düşmez.
"""

import json
import sqlite3
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import aylik_ozet
import db
import deneme_hatirlatma
import duyuru
import menu
import tahta_kaydi
import uzaktan_yonetim
import zil

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

HEDEF_ADI = {"okul": "Tüm okul", "ogrenci": "Öğrenciler", "veli": "Veliler", "ogretmen": "Öğretmenler"}


def pano_cek() -> dict | None:
    try:
        with urllib.request.urlopen(deneme_hatirlatma.PANO_URL, timeout=5) as yanit:
            return json.loads(yanit.read())
    except (OSError, ValueError):
        return None


def smual_duyurular(yol=aylik_ozet.OKUL_DB) -> list[dict] | None:
    """Yayındaki okul portalı duyuruları; aynı anda birden çok sınıfa gidenler tek satır."""
    simdi = zil.simdi_istanbul().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with closing(sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=3)) as c:
            satirlar = c.execute(
                "SELECT d.baslik, d.hedef_tur, d.hedef, d.yayin, d.bitis, u.ad_soyad FROM duyuru d"
                " JOIN kullanici u ON u.id = d.yazar_id WHERE d.yayin <= ? AND (d.bitis IS NULL OR d.bitis >= ?)"
                " ORDER BY d.yayin DESC, d.id DESC LIMIT 100",
                (simdi, simdi),
            ).fetchall()
    except sqlite3.Error:
        return None
    gruplar: dict[tuple, dict] = {}
    for baslik, tur, hedef, yayin, bitis, yazar in satirlar:
        g = gruplar.setdefault((baslik, yayin[:16]), {
            "baslik": baslik, "yayin": yayin[:16], "bitis": (bitis or "")[:10], "yazar": yazar, "hedefler": [],
        })
        g["hedefler"].append(hedef if tur == "sinif" else HEDEF_ADI.get(hedef or tur, hedef or tur))
    for g in gruplar.values():
        g["hedefler"].sort()
    return list(gruplar.values())


def tahta_gecmisi(conn) -> list[dict]:
    """Son 2 günün tahta duyuruları; aynı dakikada aynı mesaj (çok hedef) tek satır. Saat TR."""
    satirlar = conn.execute(
        "SELECT mesaj, tip, datetime(MIN(olusturma), '+3 hours') AS zaman, GROUP_CONCAT(hedef, ', ') AS hedefler,"
        " MAX(iptal) AS iptal, MAX(bitis) > datetime('now') AS etkin FROM duyuru"
        " WHERE olusturma > datetime('now', '-2 days') GROUP BY mesaj, substr(olusturma, 1, 16)"
        " ORDER BY MIN(olusturma) DESC LIMIT 30"
    ).fetchall()
    return [
        {
            "mesaj": r["mesaj"], "tip": r["tip"], "zaman": r["zaman"][5:16], "hedefler": r["hedefler"],
            "durum": "kapatildi" if r["iptal"] else ("etkin" if r["etkin"] else "doldu"),
        }
        for r in satirlar
    ]


def sonraki_gonderim(simdi: datetime) -> datetime | None:
    """Tahta hatırlatmasının bir sonraki yuvası (bugün kalan ya da sonraki okul günü)."""
    for gun in range(8):
        tarih = simdi.date() + timedelta(days=gun)
        if not zil.okul_gunu_mu(tarih):
            continue
        for y in deneme_hatirlatma.yuvalar():
            an = datetime.combine(tarih, y, tzinfo=simdi.tzinfo)
            if an + timedelta(minutes=deneme_hatirlatma.YUVA_DK) > simdi:
                return an
    return None


async def _sayfa(request: Request, sonuclar: list[dict] | None = None) -> HTMLResponse:
    uzaktan_yonetim._dogrula(request)
    pano = pano_cek()
    denemeler = (pano or {}).get("yaklasan_denemeler") or []
    conn = db.baglanti()
    try:
        gecmis = tahta_gecmisi(conn)
        for d in denemeler:
            d["siniflar"] = deneme_hatirlatma._hedefler(conn, d.get("duzeyler") or "")
    finally:
        conn.close()
    simdi = zil.simdi_istanbul()
    sonraki = sonraki_gonderim(simdi)
    return templates.TemplateResponse(request, "duyurular.html", {
        "tahtalar": [t["ad"] for t in tahta_kaydi.tahtalari_yukle()],
        "sonuclar": sonuclar,
        "gecmis": gecmis,
        "pano": pano,
        "denemeler": denemeler,
        "sonraki": f"{zil.gun_adi(sonraki.date())} {sonraki:%d.%m %H:%M}" if sonraki else None,
        "smual": smual_duyurular(),
        "smual_url": menu.SMUAL_URL,
    })


@router.get("/duyurular", response_class=HTMLResponse)
async def duyurular_sayfa(request: Request):
    return await _sayfa(request)


@router.post("/duyurular/tahta", response_class=HTMLResponse)
async def tahta_duyuru_gonder(request: Request):
    uzaktan_yonetim._dogrula(request)
    form = await request.form()
    sonuclar = await duyuru.formdan_gonder(form, [t["ad"] for t in tahta_kaydi.tahtalari_yukle()])
    uzaktan_yonetim._denetim_yaz(request, "duyuru", sonuclar)
    return await _sayfa(request, sonuclar)


@router.post("/duyurular/tahta-kapat", response_class=HTMLResponse)
async def tahta_duyuru_kapat(request: Request):
    uzaktan_yonetim._dogrula(request)
    conn = db.baglanti()
    try:
        sayi = duyuru.hepsini_iptal_et(conn)
    finally:
        conn.close()
    sonuclar = [{"tahta": duyuru.TUM_OKUL, "basarili": True,
                 "detay": f"{sayi} etkin duyuru iptal edildi; açık pencereler kapanacak."}]
    uzaktan_yonetim._denetim_yaz(request, "duyuru", sonuclar)
    return await _sayfa(request, sonuclar)
