"""Duyurular paneli (/duyurular, 2026-11-01): tüm duyuru kanalları tek sayfada.

- Tahta duyurusu: gönder (duyuru.formdan_gonder, /admin/uzaktan'daki formla aynı yol),
  son 2 günün gönderimleri, hepsini kapat.
- Otomatik hatırlatmalar: okul sınav takviminden yaklaşan denemeler (deneme_hatirlatma.py)
  ve tahtaya bir sonraki gönderim zamanı.
- smual.app: yayındaki okul portalı duyuruları (okul.db, salt-okunur; aylik_ozet ile aynı istisna).
- Kiosk panosu: okul /api/pano'nun şu an döndürdüğü duyurular.
- Tek form: aynı metin tahtalara ve/veya smual.app'e (rol hedefli) gider; smual.app için
  EBYS botunun kullandığı okul /api/duyuru-ekle ucu (push bildirimini okul gönderir).
  Anahtar okul/config/gizli.json'dan salt-okunur okunur (kopyalanmaz). SMS bilerek yok.
Okul kaynakları kapalıysa ilgili bölüm empty-state gösterir; sayfa düşmez.
"""

import asyncio
import json
import sqlite3
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

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
SMUAL_HEDEFLER = ("ogrenci", "veli", "ogretmen")
OKUL_DUYURU_URL = "http://127.0.0.1:9090/api/duyuru-ekle"
OKUL_GIZLI = Path("/home/ata/farabi/okul/config/gizli.json")


def smual_gonder(hedef: str, metin: str) -> dict:
    """smual.app rol duyurusu (okul /api/duyuru-ekle). Dönen biçim formdan_gonder ile aynı."""
    ad = f"smual.app · {HEDEF_ADI[hedef]}"
    baslik = metin if len(metin) <= 60 else metin[:59] + "…"
    try:
        anahtar = json.loads(OKUL_GIZLI.read_text(encoding="utf-8"))["duyuru_anahtar"]
        istek = urllib.request.Request(
            OKUL_DUYURU_URL,
            data=json.dumps({"hedef": hedef, "baslik": baslik, "metin": metin}).encode(),
            headers={"Content-Type": "application/json", "X-Duyuru-Anahtar": anahtar},
            method="POST",
        )
        with urllib.request.urlopen(istek, timeout=10) as yanit:
            tamam = bool(json.load(yanit).get("tamam"))
    except urllib.error.HTTPError as e:
        return {"tahta": ad, "basarili": False, "detay": f"Portal reddetti (HTTP {e.code})."}
    except (OSError, KeyError, ValueError) as e:
        return {"tahta": ad, "basarili": False, "detay": f"Portala ulaşılamadı: {type(e).__name__}."}
    detay = "Portalda yayında; uygulamayı kuranlara bildirim gidiyor." if tamam else "Portal kaydetmedi."
    return {"tahta": ad, "basarili": tamam, "detay": detay}


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
    smual = [h for h in SMUAL_HEDEFLER if h in form.getlist("smual_hedef")]
    sonuclar = []
    # yalnız smual.app seçildiyse tahta adımı atlanır; hiçbiri seçilmediyse formdan_gonder uyarır
    if form.get("tum_okul") or form.getlist("tahta") or not smual:
        sonuclar += await duyuru.formdan_gonder(form, [t["ad"] for t in tahta_kaydi.tahtalari_yukle()])
    if smual:
        try:
            metin = duyuru.mesaj_temizle(form.get("mesaj"))
        except duyuru.DuyuruHatasi as hata:
            sonuclar.append({"tahta": "smual.app", "basarili": False, "detay": str(hata)})
        else:
            for h in smual:
                sonuclar.append(await asyncio.to_thread(smual_gonder, h, metin))
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
