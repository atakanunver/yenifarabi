"""Aylık yönetici özeti (`/aylik-ozet`, 2026-10-24): yoklama + kazanım testi + dijital okul etkinliği.

Yalnızca toplu sayılar; öğrenci adı/okul no hiçbir yerde gösterilmez (isimli döküm `/admin/rapor`).
Kaynaklar salt-okunur: panonun `yoklama_onbellek`'i, `kazanim_rapor` dosyaları ve dijital okulun
`olay` tablosu (okul.db, `mode=ro`). Bir kaynak yoksa/bozuksa o bölüm empty-state gösterir.
"""

import calendar
import json
import re
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import kazanim_rapor
import menu
import zil

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

OKUL_DB = Path("/home/ata/farabi/okul/veri/okul.db")
_AY_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
_ROL_ADI = {"ogrenci": "Öğrenci", "veli": "Veli", "ogretmen": "Öğretmen", "yonetici": "Yönetici"}


def ay_coz(ay: str | None, bugun: date) -> tuple[date, date, str]:
    """(ayın ilk günü, son günü, 'YYYY-AA'); geçersiz ya da gelecek ay -> içinde bulunulan ay."""
    m = _AY_RE.match(ay or "")
    yil, ayno = (int(m.group(1)), int(m.group(2))) if m else (bugun.year, bugun.month)
    yil, ayno = min((yil, ayno), (bugun.year, bugun.month))
    ilk = date(yil, ayno, 1)
    return ilk, date(yil, ayno, calendar.monthrange(yil, ayno)[1]), f"{yil:04d}-{ayno:02d}"


def ay_adi(ay: str) -> str:
    return f"{_AYLAR[int(ay[5:]) - 1]} {ay[:4]}"


def _sinif_sirasi(ad: str) -> tuple:
    m = re.match(r"^(\d+)-(.+)$", ad)
    return (int(m.group(1)), m.group(2)) if m else (999, ad)


def yoklama_ozeti(conn, ilk: date, son: date) -> dict:
    """Ay içi yoklama: alınma oranı ve en az bir derste yok olan TEKİL öğrenci sayısı (sınıf bazlı)."""
    sinif: dict[str, dict] = {}
    gunler: set[str] = set()
    for r in conn.execute(
        "SELECT tarih, sinif, durum, yok_isimleri FROM yoklama_onbellek "
        "WHERE tarih BETWEEN ? AND ? AND durum IN ('alindi', 'alinmadi', 'tahta_ulasilamaz')",
        (ilk.isoformat(), son.isoformat()),
    ):
        s = sinif.setdefault(r["sinif"], {"ad": r["sinif"], "ders": 0, "alindi": 0, "yok": set(), "yok_ders": 0})
        s["ders"] += 1
        if r["durum"] == "alindi":
            s["alindi"] += 1
            gunler.add(r["tarih"])
            try:
                isimler = json.loads(r["yok_isimleri"] or "[]")
            except ValueError:
                isimler = []
            s["yok"].update(isimler)
            s["yok_ders"] += len(isimler)
    siniflar = []
    for ad in sorted(sinif, key=_sinif_sirasi):
        s = sinif[ad]
        siniflar.append({
            "ad": ad,
            "ders": s["ders"],
            "alindi": s["alindi"],
            "oran": round(100 * s["alindi"] / s["ders"]) if s["ders"] else 0,
            "yok_ogrenci": len(s["yok"]),
            "yok_ders": s["yok_ders"],
        })
    ders = sum(s["ders"] for s in siniflar)
    alindi = sum(s["alindi"] for s in siniflar)
    return {
        "siniflar": siniflar,
        "gun": len(gunler),
        "oran": round(100 * alindi / ders) if ders else 0,
        "yok_ogrenci": sum(s["yok_ogrenci"] for s in siniflar),
        "yok_ders": sum(s["yok_ders"] for s in siniflar),
    }


def kazanim_ozeti(ilk: date, son: date) -> dict:
    """Ayın kazanım testleri (sınıf başına test sayısı, ortalama katılım ve doğru oranı)."""
    siniflar = []
    for ad in kazanim_rapor.sinif_adlari():
        rapor, _hata = kazanim_rapor._rapor_oku(ad)
        if rapor is None:
            continue
        testler = [
            t for t in kazanim_rapor._sozluk_listesi(rapor.get("testler"))
            if ilk.isoformat() <= kazanim_rapor._metin(t.get("tarih"))[:10] <= son.isoformat()
        ]
        if not testler:
            continue
        siniflar.append({
            "ad": ad,
            "test": len(testler),
            "katilim": round(sum(kazanim_rapor._tam(t.get("katilim")) for t in testler) / len(testler)),
            "oran": round(100 * sum(kazanim_rapor._sayi(t.get("ortalama_oran")) for t in testler) / len(testler)),
        })
    return {"siniflar": siniflar, "test": sum(s["test"] for s in siniflar)}


def etkinlik_ozeti(ilk: date, son: date, yol: Path = OKUL_DB) -> dict | None:
    """Dijital okulda ayda en az bir gün aktif olan kullanıcı sayısı (role göre) / kayıtlı; kaynak yoksa None."""
    if not yol.exists():
        return None
    try:
        with closing(sqlite3.connect(f"file:{yol}?mode=ro", uri=True, timeout=3)) as c:
            kayitli = dict(c.execute("SELECT rol, COUNT(*) FROM kullanici WHERE aktif = 1 GROUP BY rol"))
            aktif = dict(c.execute(
                "SELECT rol, COUNT(DISTINCT kullanici_id) FROM olay WHERE tur = 'aktif' AND gun BETWEEN ? AND ? GROUP BY rol",
                (ilk.isoformat(), son.isoformat()),
            ))
            veri_baslangici = c.execute("SELECT MIN(gun) FROM olay").fetchone()[0]
    except sqlite3.Error:
        return None
    roller = [
        {"ad": _ROL_ADI.get(rol, rol), "aktif": aktif.get(rol, 0), "kayitli": kayitli[rol],
         "oran": round(100 * aktif.get(rol, 0) / kayitli[rol])}
        for rol in _ROL_ADI if kayitli.get(rol)
    ]
    return {"roller": roller, "veri_baslangici": veri_baslangici}


def _ay_kaydir(ay: str, n: int) -> str:
    t = int(ay[:4]) * 12 + int(ay[5:]) - 1 + n
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


@router.get("/aylik-ozet", response_class=HTMLResponse)
async def aylik_ozet_sayfa(request: Request, ay: str | None = None):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
        bugun = zil.simdi_istanbul().date()
        ilk, son, ay = ay_coz(ay, bugun)
        yoklama = yoklama_ozeti(conn, ilk, son)
    finally:
        conn.close()
    bu_ay = f"{bugun.year:04d}-{bugun.month:02d}"
    return templates.TemplateResponse(
        request,
        "aylik_ozet.html",
        {
            "ay": ay,
            "ay_adi": ay_adi(ay),
            "onceki": _ay_kaydir(ay, -1),
            "sonraki": _ay_kaydir(ay, 1) if ay < bu_ay else None,
            "devam_ediyor": ay == bu_ay,
            "yoklama": yoklama,
            "kazanim": kazanim_ozeti(ilk, son),
            "etkinlik": etkinlik_ozeti(ilk, son),
        },
    )
