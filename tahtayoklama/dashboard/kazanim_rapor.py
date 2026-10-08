"""Kazanım raporu sayfası (`/kazanim-rapor`) — kazanimtest analiz JSON'unu gösterir.

Veri kaynağı YALNIZCA `RAPOR_DIZINI/<sinif>.json` dosyalarıdır (kazanimtest
`calistir analiz` üretir, bu modül salt-okunur okur). kazanimtest'e import ya da
DB bağı YOKTUR. Rapor isimsizdir (yalnızca okul_no); ad eşleşmesi panonun kendi
roster'ından (`ogrenciler`) yapılır. Dosya yok/bozuk → sayfa 500 vermez,
açıklayıcı empty-state gösterir.
"""

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

import auth
import db
import zil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

RAPOR_DIZINI = Path("/mnt/farabi-data/farabi/kazanim_testleri/rapor")
PYTHON_SERVER = Path("/home/ata/farabi/server/venv/bin/python")
KAZANIMTEST_KOK = Path("/home/ata/farabi")
DERSLER = ("kimya", "matematik", "biyoloji", "fizik", "edebiyat", "tarih", "cografya", "din")
_TARIH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _ders_tarih_dogrula(ders, tarih) -> tuple[str | None, str | None]:
    """ders/tarih alt sürece argüman olarak gider — yalnız beyaz liste ve YYYY-AA-GG."""
    ders = str(ders).strip().lower() if ders else None
    tarih = str(tarih).strip() if tarih else None
    if ders and ders not in DERSLER:
        raise HTTPException(400, "Geçersiz ders.")
    if tarih and not _TARIH_RE.match(tarih):
        raise HTTPException(400, "Geçersiz tarih (YYYY-AA-GG).")
    return ders, tarih

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

_SINIF_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_DURUM_ETIKETI = {
    "eksik": ("Eksik", "pill-yok"),
    "orta": ("Orta", "pill-alinmadi"),
    "guclu": ("Güçlü", "pill-tam"),
    "az_veri": ("Az veri", "pill-ulasilamaz"),
}


def _sayi(v, varsayilan=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return varsayilan


def _tam(v) -> int:
    return int(_sayi(v))


def _metin(v) -> str:
    return "" if v is None else str(v)


def _liste(v) -> list:
    return v if isinstance(v, list) else []


def _sozluk_listesi(v) -> list[dict]:
    return [x for x in _liste(v) if isinstance(x, dict)]


def yuzde(oran) -> int:
    return round(max(0.0, min(1.0, _sayi(oran))) * 100)


def ders_adi(ders) -> str:
    """'kimya' → 'Kimya'; Türkçe i/ı büyütme ('islam' → 'İslam')."""
    s = _metin(ders).strip()
    if not s:
        return "—"
    ilk = {"i": "İ", "ı": "I"}.get(s[0], s[0].upper())
    return ilk + s[1:]


templates.env.filters["yuzde"] = yuzde
templates.env.filters["ders_adi"] = ders_adi


def sinif_adlari() -> list[str]:
    """Dizindeki rapor dosyalarından sınıf adları. Yol enjeksiyonunu önlemek
    için seçim yalnızca bu listeden yapılır (kullanıcı girdisi dosya yoluna
    girmez)."""
    try:
        adlar = [
            p.stem for p in RAPOR_DIZINI.glob("*.json")
            if p.is_file() and _SINIF_RE.match(p.stem)
        ]
    except OSError:
        return []

    def anahtar(ad: str):
        m = re.match(r"^(\d+)-(.+)$", ad)
        return (0, int(m.group(1)), m.group(2)) if m else (1, 0, ad)

    return sorted(adlar, key=anahtar)


def _rapor_oku(sinif: str) -> tuple[dict | None, str | None]:
    """(rapor, hata_mesajı). `sinif` sinif_adlari() listesinden gelmeli."""
    try:
        with open(RAPOR_DIZINI / f"{sinif}.json", encoding="utf-8") as f:
            veri = json.load(f)
    except (OSError, ValueError):
        return None, "Rapor dosyası okunamadı ya da bozuk. Bir sonraki gece analizinde yeniden üretilir."
    if not isinstance(veri, dict):
        return None, "Rapor dosyasının biçimi tanınmadı."
    return veri, None


def _roster(conn, sinif: str) -> dict[str, str] | None:
    """Aktif öğrenciler {no: ad}. Sınıf panoda kayıtlı değilse None."""
    satir = conn.execute("SELECT id FROM siniflar WHERE ad = ?", (sinif,)).fetchone()
    if satir is None:
        return None
    return {
        str(r["no"]): r["ad_soyad"]
        for r in conn.execute(
            "SELECT no, ad_soyad FROM ogrenciler WHERE sinif_id = ? AND aktif = 1 ORDER BY no",
            (satir["id"],),
        )
    }


def _uretim_etiketi(v) -> str:
    try:
        return datetime.fromisoformat(_metin(v)).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return _metin(v) or "—"


def _oran_sinifi(oran: float, esikler: dict) -> str:
    if oran < _sayi(esikler.get("zorlanilan_esik"), 0.5):
        return "kr-cubuk-kotu"
    if oran < _sayi(esikler.get("guclu_esik"), 0.8):
        return "kr-cubuk-orta"
    return "kr-cubuk-iyi"


def gorunum_olustur(rapor: dict, roster: dict[str, str] | None) -> dict:
    """Ham rapor + roster → şablonun kullanacağı sade yapı. Eksik/bozuk
    alanlara dayanıklıdır (varsayılan değerlerle)."""
    esikler = rapor.get("esikler") if isinstance(rapor.get("esikler"), dict) else {}

    kazanimlar = []
    for k in _sozluk_listesi(rapor.get("kazanimlar")):
        oran = _sayi(k.get("dogru_orani"))
        kazanimlar.append({
            "ders": _metin(k.get("ders")),
            "satir": _metin(k.get("kazanim_satiri")),
            "soru": _tam(k.get("soru_sayisi")),
            "cevap": _tam(k.get("cevap_sayisi")),
            "oran": oran,
            "zorlanilan": bool(k.get("zorlanilan")),
            "cubuk": _oran_sinifi(oran, esikler),
        })
    kazanimlar.sort(key=lambda k: (not k["zorlanilan"], k["oran"]))

    testler = []
    for t in _sozluk_listesi(rapor.get("testler")):
        sorular = []
        for s in _sozluk_listesi(t.get("sorular")):
            oran = _sayi(s.get("dogru_orani"))
            yanlis = s.get("en_cok_secilen_yanlis")
            yanlis = yanlis if isinstance(yanlis, dict) and yanlis.get("sik_harfi") else None
            sorular.append({
                "sira": _tam(s.get("sira")),
                "soru": _metin(s.get("soru")),
                "oran": oran,
                "cevap": _tam(s.get("cevap_sayisi")),
                "yanlis_sik": _metin(yanlis["sik_harfi"]) if yanlis else None,
                "yanlis_oran": yuzde(yanlis.get("oran")) if yanlis else 0,
                "cubuk": _oran_sinifi(oran, esikler),
            })
        url = _metin(t.get("form_url"))
        testler.append({
            "id": _tam(t.get("id")),
            "ders": _metin(t.get("ders")),
            "hafta": t.get("hafta"),
            "tarih": _metin(t.get("tarih")),
            "katilim": _tam(t.get("katilim")),
            "oran": _sayi(t.get("ortalama_oran")),
            "form_url": url if url.startswith(("https://", "http://")) else "",
            "kazanim": _metin(t.get("kazanim")),
            "sms_gonderildi": bool(t.get("sms_gonderildi")),
            "sorular": sorular,
            "cubuk": _oran_sinifi(_sayi(t.get("ortalama_oran")), esikler),
        })
    testler.sort(key=lambda t: t["tarih"], reverse=True)

    ogrenciler = []
    rapordaki_nolar: set[str] = set()
    for o in _sozluk_listesi(rapor.get("ogrenciler")):
        no = _metin(o.get("okul_no")).strip()
        rapordaki_nolar.add(no)
        oran = _sayi(o.get("oran"))
        detay = []
        for k in _sozluk_listesi(o.get("kazanimlar")):
            etiket, sinif = _DURUM_ETIKETI.get(_metin(k.get("durum")), ("—", "pill-ulasilamaz"))
            detay.append({
                "ders": _metin(k.get("ders")),
                "satir": _metin(k.get("kazanim_satiri")),
                "dogru": _tam(k.get("dogru")),
                "soru": _tam(k.get("soru")),
                "etiket": etiket,
                "rozet": sinif,
                "sayfalar": [_metin(p) for p in _liste(k.get("sayfalar"))],
            })
        ogrenciler.append({
            "no": no,
            "ad": roster.get(no) if roster is not None else None,
            "testler": _tam(o.get("test_sayisi")),
            "dogru": _tam(o.get("dogru")),
            "toplam": _tam(o.get("toplam")),
            "oran": oran,
            "eksik": _tam(o.get("eksik_sayisi")),
            "guclu": _tam(o.get("guclu_sayisi")),
            "cubuk": _oran_sinifi(oran, esikler),
            "kazanimlar": detay,
        })
    ogrenciler.sort(key=lambda o: (-o["eksik"], o["oran"], _tam(o["no"]) if o["no"].isdigit() else 10**9))

    eslesen = [o for o in ogrenciler if o["ad"]]
    eslesmeyen = [o for o in ogrenciler if not o["ad"]]
    katilmadi = []
    if roster is not None:
        katilmadi = [
            {"no": no, "ad": ad} for no, ad in roster.items() if no not in rapordaki_nolar
        ]
        katilmadi.sort(key=lambda r: _tam(r["no"]))

    toplam_dogru = sum(o["dogru"] for o in ogrenciler)
    toplam_soru = sum(o["toplam"] for o in ogrenciler)
    if toplam_soru:
        ortalama = toplam_dogru / toplam_soru
    elif testler:
        ortalama = sum(t["oran"] for t in testler) / len(testler)
    else:
        ortalama = None

    return {
        "ozet": {
            "test": len(testler),
            "katilan": len(ogrenciler),
            "roster": len(roster) if roster is not None else None,
            "ortalama": ortalama,
            "zorlanilan": sum(1 for k in kazanimlar if k["zorlanilan"]),
            "uretim": _uretim_etiketi(rapor.get("uretim")),
        },
        "kazanimlar": kazanimlar,
        "testler": testler,
        "ogrenciler": eslesen,
        "eslesmeyen": eslesmeyen,
        "katilmadi": katilmadi,
        "roster_yok": roster is None,
        "bos": not (kazanimlar or testler or ogrenciler),
    }


def _tum_sinif_adlari(conn) -> list[str]:
    try:
        adlar = [r["ad"] for r in conn.execute("SELECT ad FROM siniflar WHERE aktif = 1 ORDER BY ad").fetchall()]
        if adlar:
            return adlar
    except Exception:
        pass
    return ["9-A", "9-B", "10-A", "11-A", "11-B", "12-A", "12-B"]


async def _komut_calistir(*args: str, zaman_asimi: int = 120) -> tuple[int, str, str]:
    if not PYTHON_SERVER.exists():
        return -1, "", f"Python yolu bulunamadı: {PYTHON_SERVER}"
    proc = await asyncio.create_subprocess_exec(
        str(PYTHON_SERVER),
        *args,
        cwd=str(KAZANIMTEST_KOK),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=zaman_asimi)
        return (
            proc.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except OSError:
            pass
        return -1, "", "İşlem zaman aşımına uğradı."


@router.get("/kazanim-rapor", response_class=HTMLResponse)
async def kazanim_rapor_sayfa(request: Request, sinif: str | None = None):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            return RedirectResponse("/giris", status_code=303)
        adlar = sinif_adlari()
        tum_siniflar = _tum_sinif_adlari(conn)
        secili = None
        hata = None
        gorunum = None
        if not adlar:
            hata = "Henüz kazanım raporu üretilmemiş. Rapor, kazanım testi yapılan sınıflar için her gece oluşturulur."
        elif sinif is None:
            secili = adlar[0]
        elif sinif in adlar:
            secili = sinif
        else:
            hata = "İstenen sınıf için rapor bulunamadı. Yukarıdaki listeden bir sınıf seçin."
        if secili is not None:
            rapor, hata = _rapor_oku(secili)
            if rapor is not None:
                gorunum = gorunum_olustur(rapor, _roster(conn, secili))
    finally:
        conn.close()
    return templates.TemplateResponse(request, "kazanim_rapor.html", {
        "adlar": adlar,
        "secili": secili,
        "hata": hata,
        "g": gorunum,
        "tum_siniflar": tum_siniflar,
        "tum_dersler": list(DERSLER),
    })


@router.post("/api/kazanim-rapor/sonuc-guncelle")
async def sonuc_guncelle(request: Request):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()

    rc1, out1, err1 = await _komut_calistir("-m", "kazanimtest.calistir", "sonuc", zaman_asimi=60)
    rc2, out2, err2 = await _komut_calistir("-m", "kazanimtest.calistir", "analiz", zaman_asimi=30)
    if rc2 != 0:
        return JSONResponse({"ok": False, "hata": f"Rapor güncellenemedi: {err2 or out2}"}, status_code=500)
    return JSONResponse({"ok": True, "mesaj": "Google Form yanıtları çekildi ve rapor başarıyla güncellendi."})


@router.post("/api/kazanim-rapor/sms-gonder")
async def sms_gonder(request: Request):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()

    try:
        veri = await request.json()
    except Exception:
        veri = {}
    sinif = veri.get("sinif") or request.query_params.get("sinif")
    test_mi = bool(veri.get("test_mi", False))
    tarih = veri.get("tarih")
    ders = veri.get("ders")
    if not sinif or not _SINIF_RE.match(sinif):
        raise HTTPException(400, "Geçersiz sınıf adı.")
    ders, tarih = _ders_tarih_dogrula(ders, tarih)

    param = ["-m", "kazanimtest.calistir", "uret", "--sinif", sinif]
    if ders:
        param.extend(["--ders", ders])
    if tarih:
        param.extend(["--tarih", str(tarih)])
    if test_mi:
        param.append("--sms-test")
    else:
        param.append("--sms")

    rc, out, err = await _komut_calistir(*param, zaman_asimi=90)
    await _komut_calistir("-m", "kazanimtest.calistir", "analiz", zaman_asimi=30)
    if rc != 0:
        return JSONResponse({"ok": False, "hata": f"SMS gönderilemedi: {err or out}"}, status_code=500)
    hedef_metin = "yetkili test telefonuna" if test_mi else f"{sinif} sınıfı öğrencilerine"
    return JSONResponse({"ok": True, "mesaj": f"Kazanım test SMS'i {hedef_metin} iletildi."})


@router.post("/api/kazanim-rapor/test-uret")
async def test_uret(request: Request):
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()

    try:
        veri = await request.json()
    except Exception:
        veri = {}
    sinif = veri.get("sinif") or request.query_params.get("sinif")
    ders = veri.get("ders") or request.query_params.get("ders")
    tarih = veri.get("tarih") or request.query_params.get("tarih")
    sms_gonder_hemen = bool(veri.get("sms", False))
    if not sinif or not _SINIF_RE.match(sinif):
        raise HTTPException(400, "Geçersiz sınıf adı.")
    if not ders:
        raise HTTPException(400, "Ders seçilmelidir.")
    ders, tarih = _ders_tarih_dogrula(ders, tarih)

    param = ["-m", "kazanimtest.calistir", "uret", "--sinif", sinif, "--ders", ders]
    if tarih:
        param.extend(["--tarih", str(tarih)])
    if sms_gonder_hemen:
        param.append("--sms")

    rc, out, err = await _komut_calistir(*param, zaman_asimi=180)
    await _komut_calistir("-m", "kazanimtest.calistir", "analiz", zaman_asimi=30)
    if rc != 0:
        return JSONResponse({"ok": False, "hata": f"Test hazırlanamadı: {err or out}"}, status_code=500)
    return JSONResponse({"ok": True, "mesaj": f"{sinif} {ders_adi(ders)} kazanım testi başarıyla hazırlandı."})
