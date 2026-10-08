"""servis_yonetimi.py — /servisler: farabi.local servis ve zamanlayıcılarının durumu +
onaylı, denetim kayıtlı eylemler (2026-10-08, spec
docs/superpowers/specs/2026-10-08-dashboard-menu-servis-yonetimi-design.md).

Ayrıcalık YALNIZCA `sudo -n /usr/local/sbin/farabi-servis <eylem> <birim>` ile
(kabuk yok, argüman listesi). Log/durum okumak sudo gerektirmez (`ata` adm grubunda).
BIRIMLER scripts/farabi-servis'teki listelerle birebir aynı (test_farabi_servis)."""

import asyncio
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import menu
import auth
import db
import tahta_yeniden_baslat
import uzaktan_yonetim
import zil

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci  # taban.html (2026-10-08)
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk  # taban.html kullanır
KAPSAM_JSON = Path("/mnt/farabi-data/farabi/kazanim_testleri/rapor/kapsam.json")

BETIK = "/usr/local/sbin/farabi-servis"
KOMUT_ZAMAN_ASIMI_SN = 60

_S = ("yeniden-baslat", "durdur", "baslat", "hata-temizle")
_Z = ("zamanlayici-ac", "zamanlayici-kapat", "simdi-calistir", "hata-temizle")
BIRIMLER: dict[str, dict] = {
    "farabi-api": {"ad": "Farabi Brain", "tur": "servis", "eylemler": _S, "ders_uyarisi": True,
                   "aciklama": "Tahtalardaki kitap/YKS soruları ~10 sn yanıt vermez."},
    "farabi-smssistemi": {"ad": "SMS sistemi", "tur": "servis", "eylemler": _S, "ders_uyarisi": False,
                          "aciklama": "09:00/14:00 otomasyon penceresindeyse gönderim kesilebilir."},
    "farabi-yoklama-dashboard": {"ad": "Yoklama panosu (bu sayfa)", "tur": "servis",
                                 "eylemler": ("yeniden-baslat",), "ders_uyarisi": False,
                                 "aciklama": "Sayfa birkaç saniye bağlantıyı kaybeder, sonra kendiliğinden döner."},
    "ollama": {"ad": "Ollama (qwen3.8:27b)", "tur": "servis", "eylemler": ("yeniden-baslat", "hata-temizle"),
               "ders_uyarisi": True, "aciklama": "Model yeniden yüklenir (~1 dk); Atos ve soru üretimi bekler."},
    "open-webui": {"ad": "Atos", "tur": "servis", "eylemler": _S, "ders_uyarisi": True,
                   "aciklama": "Atos sohbetleri bağlantıyı kaybeder."},
    "sinif-arena": {"ad": "Sınıf arenası", "tur": "servis", "eylemler": _S, "ders_uyarisi": True,
                    "aciklama": "Süren yarışma oturumları sıfırlanabilir."},
    "kazanim-test": {"ad": "Kazanım testi (hafta içi 16:30)", "tur": "zamanlayici", "eylemler": _Z,
                     "ders_uyarisi": False, "aciklama": "Haftalık kazanım testi formunu üretir."},
    "kazanim-test-sonuc": {"ad": "Kazanım testi sonuçları (her gün 00:00)", "tur": "zamanlayici",
                           "eylemler": _Z, "ders_uyarisi": False, "aciklama": "Form cevaplarını çeker."},
    "kazanim-test-aylik": {"ad": "Aylık kazanım raporu (ayın 1'i)", "tur": "zamanlayici", "eylemler": _Z,
                           "ders_uyarisi": False, "aciklama": "Önceki ayın raporlarını üretir."},
    "soru-havuzu-uret": {"ad": "Soru havuzu üretimi (gece)", "tur": "zamanlayici", "eylemler": _Z,
                         "ders_uyarisi": False,
                         "aciklama": "Yerel Ollama ile soru üretir; ders saatinde kendiliğinden durur."},
    "farabi-idari-yukle": {"ad": "İdari belge yükleme (02:30)", "tur": "zamanlayici", "eylemler": _Z,
                           "ders_uyarisi": False, "aciklama": "mudur/ belgelerini RAG'a yükler."},
}
# Ders saatinde tamamen reddedilen eylemler (GPU'yu derste Ollama'nın diğer kullanıcılarına bırak).
DERS_SAATINDE_YASAK = {("soru-havuzu-uret", "simdi-calistir")}

_MASKE = [
    (re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"), r"\1***@"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:token|key|anahtar|sifre|şifre|password|secret)[A-Z0-9_]*)(\s*[=:]\s*)\S+"),
     r"\1\2***"),
]


def eylem_dogrula(birim: str, eylem: str) -> None:
    tanim = BIRIMLER.get(birim)
    if tanim is None or eylem not in tanim["eylemler"]:
        raise ValueError(f"izin yok: {eylem} {birim}")


def onay_gerekli_mi(birim: str, eylem: str, simdi=None) -> str | None:
    tanim = BIRIMLER[birim]
    if tanim["ders_uyarisi"] and eylem in ("yeniden-baslat", "durdur") \
            and tahta_yeniden_baslat.ders_saatinde_mi(simdi):
        return f"Şu an ders saati. {tanim['aciklama']}"
    return None


def ders_saatinde_yasak_mi(birim: str, eylem: str, simdi=None) -> bool:
    return (birim, eylem) in DERS_SAATINDE_YASAK and tahta_yeniden_baslat.ders_saatinde_mi(simdi)


def maskele(satir: str) -> str:
    for desen, yerine in _MASKE:
        satir = desen.sub(yerine, satir)
    return satir


def son_hata(satirlar: list[str]) -> str | None:
    """Son Traceback'in son (istisna) satırı; Traceback yoksa son 'Failed with result' satırı."""
    son_tb = None
    for i, s in enumerate(satirlar):
        if "Traceback (most recent call last)" in s:
            son_tb = i
    if son_tb is not None:
        aday = None
        for s in satirlar[son_tb + 1:]:
            govde = (s.split("]: ", 1)[-1] if "]: " in s else s).strip()
            if re.match(r"^[A-Za-z_][\w.]*(Error|Exception|Exit|Interrupt)\b", govde):
                aday = govde
        if aday:
            return maskele(aday)
    for s in reversed(satirlar):
        if "Failed with result" in s:
            return maskele(s.split("]: ", 1)[-1].strip())
    return None


async def _komut_kos(args: list[str]) -> tuple[int, str, str]:
    surec = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        cikti, hata = await asyncio.wait_for(surec.communicate(), KOMUT_ZAMAN_ASIMI_SN)
    except TimeoutError:
        surec.kill()
        return 124, "", "zaman aşımı"
    return surec.returncode, cikti.decode(errors="replace"), hata.decode(errors="replace")


async def calistir(birim: str, eylem: str) -> dict:
    eylem_dogrula(birim, eylem)
    kod, cikti, hata = await _komut_kos(["sudo", "-n", BETIK, eylem, birim])
    return {"ok": kod == 0, "kod": kod, "mesaj": maskele((hata or cikti).strip())[:500]}


def _show_ayristir(ham: str) -> dict[str, dict]:
    sonuc = {}
    for blok in ham.split("\n\n"):
        oz = dict(s.partition("=")[::2] for s in blok.splitlines() if "=" in s)
        if oz.get("Id"):
            sonuc[oz["Id"]] = oz
    return sonuc


def _birim_adlari() -> list[str]:
    adlar = []
    for birim, t in BIRIMLER.items():
        adlar.append(f"{birim}.service")
        if t["tur"] == "zamanlayici":
            adlar.append(f"{birim}.timer")
    return adlar


async def durumlar() -> list[dict]:
    _, ham, _ = await _komut_kos([
        "systemctl", "show", *_birim_adlari(), "-p", "Id", "-p", "ActiveState", "-p", "SubState",
        "-p", "Result", "-p", "MemoryCurrent", "-p", "ActiveEnterTimestamp",
        "-p", "NextElapseUSecRealtime", "-p", "LastTriggerUSec", "-p", "UnitFileState"])
    oz = _show_ayristir(ham)
    liste = []
    for birim, t in BIRIMLER.items():
        s = oz.get(f"{birim}.service", {})
        z = oz.get(f"{birim}.timer", {})
        bellek = s.get("MemoryCurrent", "")
        liste.append({
            "birim": birim, "ad": t["ad"], "tur": t["tur"], "aciklama": t["aciklama"],
            "eylemler": list(t["eylemler"]), "ders_uyarisi": t["ders_uyarisi"],
            "aktif_durum": s.get("ActiveState", "bilinmiyor"), "alt_durum": s.get("SubState", ""),
            "sonuc": s.get("Result", ""),
            "bellek_mib": round(int(bellek) / 2**20) if bellek.isdigit() else None,
            "baslama": s.get("ActiveEnterTimestamp") or None,
            "zamanlayici_etkin": (z.get("UnitFileState") == "enabled") if z else None,
            "sonraki": z.get("NextElapseUSecRealtime") or None,
            "son_tetik": z.get("LastTriggerUSec") or None,
        })
    return liste


async def log_oku(birim: str, satir: int = 200, yalniz_uyari: bool = False) -> list[str]:
    if birim not in BIRIMLER:
        raise ValueError(f"izin yok: log {birim}")
    args = ["journalctl", "-u", f"{birim}.service", "-n", str(min(max(satir, 10), 1000)),
            "-o", "short-iso", "--no-pager"]
    if yalniz_uyari:
        args += ["-p", "warning"]
    _, cikti, _ = await _komut_kos(args)
    return [maskele(s) for s in cikti.splitlines()]


# ── HTTP uçları ──────────────────────────────────────────────────────────────

def _oturum(request: Request) -> bool:
    conn = db.baglanti()
    try:
        return auth.dogrula(request, conn)
    finally:
        conn.close()


def _oturum_kontrol(request: Request) -> None:
    if not _oturum(request):
        raise HTTPException(401, "Oturum geçersiz.")


def _origin_kontrol(request: Request) -> None:
    kaynak = request.headers.get("origin") or request.headers.get("referer") or ""
    if urlsplit(kaynak).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "Yalnızca panonun kendi sayfasından.")


def _kapsam_ozeti() -> dict | None:
    """benchmark/kazanim_kapsam çıktısından soru havuzu kartı için yeterli/zayıf/boş."""
    try:
        veri = json.loads(KAPSAM_JSON.read_text(encoding="utf-8"))
        toplam = {"yeterli": 0, "zayif": 0, "bos": 0, "plan_haftasi": 0}
        for v in veri["sonuc"].values():
            for k in toplam:
                toplam[k] += v.get(k, 0)
        return {**toplam, "uretim": veri.get("uretim")}
    except (OSError, ValueError, KeyError, AttributeError):
        return None


@router.get("/servisler", response_class=HTMLResponse)
async def servisler_sayfa(request: Request):
    if not _oturum(request):
        return RedirectResponse("/giris", status_code=303)
    return templates.TemplateResponse(request, "servisler.html", {})


@router.get("/api/servisler")
async def api_servisler(request: Request):
    _oturum_kontrol(request)
    return JSONResponse({"birimler": await durumlar(),
                         "ders_saati": tahta_yeniden_baslat.ders_saatinde_mi(),
                         "kapsam": _kapsam_ozeti()})


@router.get("/api/servisler/log/{birim}")
async def api_log(request: Request, birim: str, yalniz_uyari: int = 0):
    _oturum_kontrol(request)
    try:
        satirlar = await log_oku(birim, 200, bool(yalniz_uyari))
        tum = satirlar if not yalniz_uyari else await log_oku(birim, 400)
    except ValueError:
        raise HTTPException(400, "Bilinmeyen birim.")
    return JSONResponse({"satirlar": satirlar, "son_hata": son_hata(tum)})


@router.post("/api/servisler/eylem")
async def api_eylem(request: Request):
    _oturum_kontrol(request)
    _origin_kontrol(request)
    try:
        govde = await request.json()
    except ValueError:
        govde = {}
    if not isinstance(govde, dict):
        govde = {}
    birim, eylem = str(govde.get("birim", "")), str(govde.get("eylem", ""))
    try:
        eylem_dogrula(birim, eylem)
    except ValueError:
        raise HTTPException(400, "Bu birim için izin verilmeyen eylem.")
    if ders_saatinde_yasak_mi(birim, eylem):
        raise HTTPException(403, "Ders saatinde çalıştırılamaz.")
    uyari = onay_gerekli_mi(birim, eylem)
    if uyari and govde.get("onay") is not True:
        return JSONResponse({"onay_gerekli": uyari}, status_code=409)
    sonuc = await calistir(birim, eylem)
    uzaktan_yonetim._denetim_yaz(request, f"servis-{eylem}",
                                 [{"tahta": birim, "basarili": sonuc["ok"]}], kaynak="servisler")
    return JSONResponse({"ok": sonuc["ok"], "mesaj": sonuc["mesaj"]})
