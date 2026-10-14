"""Kiosk LCD panosu için LAN'a açık, salt-okunur veri ucu (/api/pano).

Yalnızca okul geneli (hedef=okul) süresi dolmamış duyurular ve (tahtalarla aynı kaynaktan) kısaltmalı ders programı + zil çizelgesi döner.
Cloudflare Tunnel (smual.app) üzerinden gelen istekte 404 verir: tünel istekleri
127.0.0.1'den gelir ama `cf-*` / `x-forwarded-*` başlıkları taşır.
"""

import importlib.util
import ipaddress
import json
from datetime import date, timedelta

import db
import maraton
import zaman
from ayarlar import AYAR
from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

# Tahtalarla AYNI kaynak: tahtayoklama/data (Farabi :8010 /yapilandirma da bunu dağıtır).
TAHTA_DATA = AYAR.zil_yolu.parent
KISA_MODUL = AYAR.zil_yolu.parent.parent / "dashboard" / "ders_programi.py"


_modul = None


def _tahta_modul():
    """Tahta panosunun ders_programi modülü (ders + öğretmen kısa adı tek kaynak)."""
    global _modul
    if _modul is None:
        spec = importlib.util.spec_from_file_location("tahta_ders_programi", KISA_MODUL)
        _modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_modul)
    _modul.yenile()  # dosya değişince önbellek temizlensin
    return _modul


def _kisa_program() -> dict:
    """{sınıf: {gün: [{"d": "KİM", "o": "EMİNE"} x8]}} — tahtadaki etiketle aynı."""
    m = _tahta_modul()
    pzt = date(2026, 1, 5)  # herhangi bir pazartesi; gün adı için
    gunler = ["pazartesi", "sali", "carsamba", "persembe", "cuma"]
    sonuc = {}
    for sinif in m._yukle():
        sonuc[sinif] = {
            g: [
                {
                    "d": m.ders_kisa_adi(sinif, pzt + timedelta(days=i), n) or "",
                    "o": m.ogretmen_kisa_adi(sinif, pzt + timedelta(days=i), n) or "",
                }
                for n in range(1, 9)
            ]
            for i, g in enumerate(gunler)
        }
    return {"siniflar": sonuc}


def _lan_mi(request: Request) -> bool:
    h = request.headers
    if any(k.startswith(("cf-", "x-forwarded-")) or k == "x-real-ip" for k in h):
        return False
    try:
        ip = ipaddress.ip_address(request.client.host)
    except (ValueError, AttributeError):
        return False
    return ip.is_private


def _maraton_birincisi(conn) -> dict | None:
    """Bu haftanın Soru Maratonu birincisi (uygulamadaki liderlikle aynı sıralama)."""
    lider = maraton.liderlik(conn)
    if not lider:
        return None
    b = lider[0]
    r = conn.execute(
        "SELECT COALESCE(SUM(m.dogru), 0) AS dogru, COUNT(*) AS adet FROM maraton m"
        f" WHERE m.kullanici_id = ? AND m.bitis >= ? AND {maraton._TAMAM}",
        (b["kullanici_id"], maraton.hafta_basi()),
    ).fetchone()
    return {
        "baslik": "SORU MARATONU BİRİNCİSİ",
        "metin": f"{b['ad']} ({b['sinif']}) — bu hafta {r['adet']} maratonda "
        f"{r['dogru']} doğru, en iyi {b["adet"]} maratonu {b["toplam"]} puan. Tebrikler!",
    }


@router.get("/api/pano", include_in_schema=False)
async def pano(request: Request):
    if not _lan_mi(request):
        raise HTTPException(404)
    simdi = zaman.simdi_str()
    conn = db.baglanti()
    try:
        satirlar = conn.execute(
            "SELECT baslik, metin FROM duyuru WHERE hedef_tur = 'okul'"
            " AND yayin <= ? AND (bitis IS NULL OR bitis >= ?)"
            " ORDER BY yayin DESC, id DESC LIMIT 20",
            (simdi, simdi),
        ).fetchall()
        birinci = _maraton_birincisi(conn)
    finally:
        conn.close()
    try:
        program = _kisa_program()
        zil = json.loads(AYAR.zil_yolu.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — pano ucu uygulamayı düşürmesin
        program, zil = {"siniflar": {}}, None
    duyuru = [{"baslik": r["baslik"], "metin": r["metin"]} for r in satirlar]
    if birinci:
        duyuru.insert(0, birinci)
    return {
        "duyurular": duyuru,
        "program": program,
        "zil": zil,
    }
