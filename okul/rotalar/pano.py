"""Kiosk LCD panosu için LAN'a açık, salt-okunur veri ucu (/api/pano).

Yalnızca okul geneli (hedef=okul) süresi dolmamış duyurular ve (tahtalarla aynı kaynaktan) kısaltmalı ders programı + zil çizelgesi döner.
Cloudflare Tunnel (smual.app) üzerinden gelen istekte 404 verir: tünel istekleri
127.0.0.1'den gelir ama `cf-*` / `x-forwarded-*` başlıkları taşır.
"""

import importlib.util
import ipaddress
import json
from datetime import date, timedelta

import belirli_gunler
import db
import oduller
import sinavlar
import zaman
from ayarlar import AYAR
from fastapi import APIRouter, HTTPException, Request
from kaynaklar import dogum

router = APIRouter()

# Tahtalarla AYNI kaynak: tahtayoklama/data (Farabi :80 /yapilandirma da bunu dağıtır).
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


def _dogum_ogesi() -> dict | None:
    """Bugün (pazartesi: hafta sonu dahil) doğum günü olanlar için kutlama; kimse yoksa None."""
    kisiler = dogum.bugunun_dogumlari(zaman.simdi().date())
    if not kisiler:
        return None
    adlar = ", ".join(f"{k['ad']} ({k['sinif']})" if k["sinif"] else k["ad"] for k in kisiler)
    return {"baslik": "DOĞUM GÜNÜ", "metin": f"{adlar} — doğum gününüz kutlu olsun!"}


def _deneme_ogeleri(denemeler) -> list[dict]:
    """Zamanı yaklaşan / haftası süren denemeler (ör. MEBİ YKS) için pano öğeleri."""
    return [
        {
            "baslik": d["baslik"],
            "metin": f"{sinavlar.deneme_durumu(d)}"
            + (f" — {d['aciklama']}" if d["aciklama"] else ""),
        }
        for d in denemeler
    ]


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
        try:
            denemeler = sinavlar.yaklasan_denemeler(conn)
        except Exception:  # noqa: BLE001 — sınav kaynağı pano ucunu düşürmesin
            denemeler = []
        try:
            odul_ogeleri = oduller.kiosk_ogeleri(conn)  # yalnızca cuma/pazartesi dolu
        except Exception:  # noqa: BLE001 — ödül hesabı pano ucunu düşürmesin
            odul_ogeleri = []
    finally:
        conn.close()
    try:
        program = _kisa_program()
        zil = json.loads(AYAR.zil_yolu.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — pano ucu uygulamayı düşürmesin
        program, zil = {"siniflar": {}}, None
    duyuru = [{"baslik": r["baslik"], "metin": r["metin"]} for r in satirlar]
    duyuru[0:0] = odul_ogeleri
    try:
        dogum_ogesi = _dogum_ogesi()
    except Exception:  # noqa: BLE001 — kutlama kaynağı pano ucunu düşürmesin
        dogum_ogesi = None
    if dogum_ogesi:
        duyuru.insert(0, dogum_ogesi)
    duyuru[0:0] = _deneme_ogeleri(denemeler)
    try:
        gunler = belirli_gunler.bugun()
    except Exception:  # noqa: BLE001 — belirli gün kaynağı pano ucunu düşürmesin
        gunler = []
    return {
        "duyurular": duyuru,
        "program": program,
        "zil": zil,
        "belirli_gunler": gunler,
        # Tahta teneffüs hatırlatması (tahtayoklama/dashboard/deneme_hatirlatma.py) okur.
        "yaklasan_denemeler": [
            {
                "baslik": d["baslik"],
                "tarih": d["tarih"],
                "bitis": d["bitis"],
                "duzeyler": d["duzeyler"],
                "aciklama": d["aciklama"],
                "durum": sinavlar.deneme_durumu(d),
            }
            for d in denemeler
        ],
    }


@router.get("/api/odul/hafta", include_in_schema=False)
async def odul_hafta(request: Request, hb: str | None = None, gecici: int = 0):
    """Haftalık ödül birincilerinin TAM adı (LAN; /api/pano ile aynı koruma). hb yoksa geçen hafta."""
    if not _lan_mi(request):
        raise HTTPException(404)
    if hb is None:
        hb = oduller.onceki_hafta(oduller.hafta_basi())
    else:
        try:
            date.fromisoformat(hb)
        except ValueError:
            raise HTTPException(400, "hb YYYY-MM-DD olmalı") from None
    kat: dict[str, list[dict]] = {"maraton": [], "etkinlik": []}
    conn = db.baglanti()
    try:
        tam = {
            r["kullanici_id"]: r["ad_soyad"]
            for r in conn.execute("SELECT kullanici_id, ad_soyad FROM ogrenci WHERE kullanici_id IS NOT NULL")
        }
        if gecici:
            s = oduller.siralama(conn, hb)
            for x in s["etkinlik"]:
                kat["etkinlik"].append({"ad_soyad": tam.get(x["kid"], x["ad"]), "sinif": x["sinif"],
                                        "deger": x["etkinlik"], "ayrinti": f"{x['etkinlik']} etkinlik, {x['gun']} gün"})
            for x in s["maraton"]:
                kat["maraton"].append({"ad_soyad": tam.get(x["kid"], x["ad"]), "sinif": x["sinif"], "deger": x["toplam"],
                                       "ayrinti": f"Soru Maratonu: en iyi {x['adet']} turda {x['toplam']} puan"})
            kesin = False
        else:
            satirlar = [r for r in oduller.kayitli(conn, hb) if r["kategori"] in kat]
            for r in satirlar:
                kat[r["kategori"]].append({"ad_soyad": r["ad_soyad"], "sinif": r["sinif"],
                                           "deger": r["deger"], "ayrinti": r["ayrinti"]})
            kesin = bool(satirlar)
    finally:
        conn.close()
    return {"hafta": hb, "kesin": kesin, "kategoriler": kat}
