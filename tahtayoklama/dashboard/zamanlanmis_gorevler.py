"""zamanlanmis_gorevler.py — /zamanlanmis-gorevler: farabi.local systemd zamanlayıcılarının tek sayfada
görünümü + katmanlı korumalı yönetimi (2026-10-17).

Sınıflar: "sistem" (apt, logrotate… yalnız görünür) / "farabi" (YONETILEN: aç-kapat-çalıştır-saat, SİLİNEMEZ)
/ "panel" (farabi-gorev-<id>: hepsi + sil). Ayrıcalık YALNIZCA
`sudo -n /usr/local/sbin/farabi-zamanlayici <eylem> ...` (kabuk yok, argüman listesi); sunucu tarafı
izin denetimi betikten ÖNCE burada yapılır, istemci kuralına güvenilmez. Okuma sudo gerektirmez.
Tahta tarafı SALT-OKUNUR (ssh ile list-timers/crontab okur, hiçbir şey değiştirmez).
YONETILEN scripts/farabi-zamanlayici'daki liste ile birebir aynı (test_farabi_zamanlayici)."""

import asyncio
import re
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

import menu
import servis_yonetimi
import ssh_istemci
import tahta_kaydi
import tahta_yeniden_baslat
import uzaktan_yonetim
import zil

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["menu_agaci"] = menu.menu_agaci  # taban.html
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk  # taban.html kullanır

BETIK = "/usr/local/sbin/farabi-zamanlayici"
# kazanim-test* zamanlayıcıları 2026-10-14'te silindi (listeden 2026-10-23'te çıktı).
YONETILEN = ("soru-havuzu-uret", "farabi-idari-yukle", "farabi-tahta-karart-haftaici", "farabi-tahta-karart-haftasonu")
GOREV_ONEKI = "farabi-gorev-"
ID_DESENI = re.compile(r"^[a-z0-9][a-z0-9-]{0,29}$")
EYLEM_ETIKETLERI = {"ekran_karart": "Ekranı karart", "ekran_kaldir": "Karartmayı kaldır",
                    "yoklama_kapat": "Yoklamayı kapat", "chrome_kapat": "Chrome'u kapat"}
ORTAK_EYLEMLER = ("ac", "kapat", "calistir", "takvim", "takvim-sifirla")
IZINLI_EYLEMLER = {"farabi": ORTAK_EYLEMLER, "panel": (*ORTAK_EYLEMLER, "sil")}
DERS_SAATINDE_YASAK = {("soru-havuzu-uret", "calistir")}
GUNLER = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SISTEM_TIMER_SINIRI = 60
TAHTA_ONBELLEK_SN = 60
ANALIZ_ONBELLEK_SN = 60
TAHTA_KOMUT = ("systemctl list-timers --all --no-pager | grep -E 'ekran-kapat|tahta-gece-reboot'; "
               "crontab -l 2>/dev/null | grep -v '^#'")

_analiz_onbellek: dict[str, tuple[float, dict]] = {}
_tahta_onbellek: dict = {"t": -1e9, "v": None}


def sinif(birim: str) -> str:
    """Birimin yönetim sınıfı; tanınmayan her şey 'sistem' (eylem yok)."""
    if birim in YONETILEN:
        return "farabi"
    if birim.startswith(GOREV_ONEKI) and ID_DESENI.match(birim[len(GOREV_ONEKI):]):
        return "panel"
    return "sistem"


def eylem_dogrula(birim: str, eylem: str) -> str:
    s = sinif(birim)
    if eylem not in IZINLI_EYLEMLER.get(s, ()):
        raise ValueError(f"izin yok: {eylem} {birim}")
    return s


def ders_saatinde_yasak_mi(birim: str, eylem: str, simdi=None) -> bool:
    return (birim, eylem) in DERS_SAATINDE_YASAK and tahta_yeniden_baslat.ders_saatinde_mi(simdi)


def onay_gerekli_mi(birim: str, eylem: str, simdi=None) -> str | None:
    """Karartma ve panel görevlerini derste elle çalıştırmak canlı dersi etkiler."""
    if eylem == "calistir" and (birim.startswith(("farabi-tahta-karart", GOREV_ONEKI))) \
            and tahta_yeniden_baslat.ders_saatinde_mi(simdi):
        return "Şu an ders saati. Bu görev tahtalarda anında çalışır."
    return None


def slug(ad: str) -> str:
    tr = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    s = re.sub(r"[^a-z0-9]+", "-", ad.translate(tr).lower()).strip("-")[:30].strip("-")
    return s


def ifade_uret(gunler: list[str], saat: str) -> str:
    """Gün kutuları + HH:MM → OnCalendar ('Mon..Fri *-*-* 21:00:00 Europe/Istanbul')."""
    if not isinstance(saat, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", saat):
        raise ValueError("saat")
    secili = sorted({GUNLER.index(g) for g in gunler if g in GUNLER})
    if not secili:
        raise ValueError("gun")
    if len(secili) == 7:
        gun_metni = ""
    else:
        parcalar, i = [], 0
        while i < len(secili):
            j = i
            while j + 1 < len(secili) and secili[j + 1] == secili[j] + 1:
                j += 1
            if j - i >= 2:
                parcalar.append(f"{GUNLER[secili[i]]}..{GUNLER[secili[j]]}")
            else:
                parcalar.extend(GUNLER[k] for k in secili[i:j + 1])
            i = j + 1
        gun_metni = ",".join(parcalar) + " "
    return f"{gun_metni}*-*-* {saat}:00 Europe/Istanbul"


_IFADE_DESENI = re.compile(r"^(?:(?P<g>[A-Za-z,.]+) )?\*-\*-\* (?P<s>[01]\d|2[0-3]):(?P<d>[0-5]\d)(?::00)?"
                           r"(?: Europe/Istanbul)?$")


def ifade_coz(ifade: str) -> dict | None:
    """ifade_uret'in tersi (düzenleme formunu doldurmak için); basit değilse None."""
    m = _IFADE_DESENI.match(ifade or "")
    if not m:
        return None
    gunler: set[int] = set()
    if m["g"] is None:
        gunler = set(range(7))
    else:
        for parca in m["g"].split(","):
            ad, ayrac, son = parca.partition("..")
            if ad not in GUNLER or (ayrac and son not in GUNLER):
                return None
            bas = GUNLER.index(ad)
            gunler.update(range(bas, GUNLER.index(son) + 1) if ayrac else [bas])
    return {"gunler": [GUNLER[i] for i in sorted(gunler)], "saat": f"{m['s']}:{m['d']}"}


# ── okuma ────────────────────────────────────────────────────────────────────

async def _komut_kos(args: list[str]) -> tuple[int, str, str]:
    return await servis_yonetimi._komut_kos(args)


def _show_ayristir(ham: str) -> dict[str, dict]:
    return servis_yonetimi._show_ayristir(ham)


async def ifade_analiz(ifade: str) -> dict:
    """`systemd-analyze calendar` → {normal, sonraki}; 60 sn önbellekli, hata dayanıklı."""
    simdi = time.monotonic()
    hit = _analiz_onbellek.get(ifade)
    if hit and hit[0] + ANALIZ_ONBELLEK_SN > simdi:
        return hit[1]
    kod, cikti, _ = await _komut_kos(["systemd-analyze", "calendar", "--", ifade])
    sonuc = {"normal": None, "sonraki": None}
    if kod == 0:
        for satir in cikti.splitlines():
            ad, _, deger = satir.strip().partition(":")
            if ad == "Normalized form":
                sonuc["normal"] = deger.strip()
            elif ad == "Next elapse":
                sonuc["sonraki"] = deger.strip()
    _analiz_onbellek[ifade] = (simdi, sonuc)
    return sonuc


async def liste() -> list[dict]:
    _, ham, _ = await _komut_kos(["systemctl", "list-unit-files", "--type=timer", "--no-legend",
                                  "--no-pager", "--plain"])
    # Şablon birimleri (örn. chrony-dnssrv@.timer) `systemctl show`'u tümden kırar, hiç listeleme.
    adlar = [s.split()[0][:-6] for s in ham.splitlines()
             if s.split() and s.split()[0].endswith(".timer") and "@" not in s.split()[0]]
    adlar = sorted(set(adlar) | set(YONETILEN))
    sistem = [a for a in adlar if sinif(a) == "sistem"][:SISTEM_TIMER_SINIRI]
    secili = [a for a in adlar if sinif(a) != "sistem"] + sistem
    birimler = [f"{a}.timer" for a in secili] + [f"{a}.service" for a in secili if sinif(a) == "panel"]
    _, ham, _ = await _komut_kos([
        "systemctl", "show", *birimler, "-p", "Id", "-p", "ActiveState", "-p", "UnitFileState",
        "-p", "NextElapseUSecRealtime", "-p", "LastTriggerUSec", "-p", "TimersCalendar", "-p", "ExecStart"])
    oz = _show_ayristir(ham)
    sonuc = []
    for a in secili:
        z = oz.get(f"{a}.timer", {})
        s = sinif(a)
        m = re.search(r"OnCalendar=(.*?) ;", z.get("TimersCalendar", ""))
        ifade = m.group(1) if m else None
        kayit = {"birim": a, "sinif": s, "izinli": list(IZINLI_EYLEMLER.get(s, ())),
                 "etkin": z.get("UnitFileState") == "enabled", "durum": z.get("ActiveState", "bilinmiyor"),
                 "sonraki": z.get("NextElapseUSecRealtime") or None, "son_tetik": z.get("LastTriggerUSec") or None,
                 "ifade": ifade, "ifade_parcalari": ifade_coz(ifade) if ifade else None,
                 "normal": None, "eylem": None, "tahtalar": None}
        if s != "sistem" and ifade:
            kayit["normal"] = (await ifade_analiz(ifade))["normal"]
        if s == "panel":
            e = re.search(r"tahta_eylem_zamanli\.py\s+(\w+)\s+([^\s;]+)",
                          oz.get(f"{a}.service", {}).get("ExecStart", ""))
            if e:
                kayit["eylem"], kayit["tahtalar"] = e.group(1), e.group(2)
        sonuc.append(kayit)
    sonuc.sort(key=lambda k: k["birim"])
    return sonuc


async def _tek_tahta(t: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        try:
            r = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], TAHTA_KOMUT, zaman_asimi=15)
        except Exception:  # noqa: BLE001  tek tahta hatası listeyi düşürmez
            return {"tahta": t["ad"], "ulasilabilir": False, "timer": [], "cron": []}
    # grep eşleşmezse çıkış kodu 1 olabilir; yalnızca bağlantı hatası (basarili=False + çıktı yok) erişilemez sayılır
    metin = (r.stdout or b"").decode(errors="replace")
    if not r.basarili and not metin.strip() and r.cikis_kodu in (None, 255):
        return {"tahta": t["ad"], "ulasilabilir": False, "timer": [], "cron": []}
    satirlar = [s.strip() for s in metin.splitlines() if s.strip()]
    return {"tahta": t["ad"], "ulasilabilir": True,
            "timer": [s[:300] for s in satirlar if ".timer" in s],
            "cron": [s[:300] for s in satirlar if ".timer" not in s]}


async def tahta_zamanlayicilari(taze: bool = False) -> dict:
    simdi = time.monotonic()
    if not taze and _tahta_onbellek["v"] is not None and _tahta_onbellek["t"] + TAHTA_ONBELLEK_SN > simdi:
        return _tahta_onbellek["v"]
    try:
        tahtalar = tahta_kaydi.tahtalari_yukle()
    except (OSError, ValueError):
        tahtalar = []
    sem = asyncio.Semaphore(8)
    sonuc = {"tahtalar": list(await asyncio.gather(*[_tek_tahta(t, sem) for t in tahtalar]))}
    _tahta_onbellek.update(t=simdi, v=sonuc)
    return sonuc


def tahta_adlari() -> list[str]:
    try:
        return [t["ad"] for t in tahta_kaydi.tahtalari_yukle()]
    except (OSError, ValueError):
        return []


# ── yazma ────────────────────────────────────────────────────────────────────

async def betik_calistir(*args: str) -> dict:
    kod, cikti, hata = await _komut_kos(["sudo", "-n", BETIK, *args])
    return {"ok": kod == 0, "kod": kod, "mesaj": servis_yonetimi.maskele((hata or cikti).strip())[:500]}


# ── HTTP uçları ──────────────────────────────────────────────────────────────

_oturum = servis_yonetimi._oturum
_oturum_kontrol = servis_yonetimi._oturum_kontrol


def _origin_kontrol(request: Request) -> None:
    kaynak = request.headers.get("origin") or request.headers.get("referer") or ""
    if urlsplit(kaynak).netloc != request.headers.get("host", ""):
        raise HTTPException(403, "Yalnızca panonun kendi sayfasından.")


@router.get("/zamanlanmis-gorevler", response_class=HTMLResponse)
async def sayfa(request: Request):
    if not _oturum(request):
        return RedirectResponse("/giris", status_code=303)
    return templates.TemplateResponse(request, "zamanlanmis_gorevler.html", {})


@router.get("/zamanlanmis-gorevler/api/liste")
async def api_liste(request: Request):
    _oturum_kontrol(request)
    return JSONResponse({"gorevler": await liste(), "ders_saati": tahta_yeniden_baslat.ders_saatinde_mi(),
                         "tahta_adlari": tahta_adlari(), "eylem_etiketleri": EYLEM_ETIKETLERI})


@router.get("/zamanlanmis-gorevler/api/tahtalar")
async def api_tahtalar(request: Request, taze: int = 0):
    _oturum_kontrol(request)
    return JSONResponse(await tahta_zamanlayicilari(bool(taze)))


def _ifade_govdeden(govde: dict) -> str:
    gelismis = str(govde.get("ifade") or "").strip()
    if gelismis:
        return gelismis
    try:
        return ifade_uret(list(govde.get("gunler") or []), str(govde.get("saat", "")))
    except ValueError:
        raise HTTPException(400, "Gün ve saat geçerli değil.")


@router.post("/zamanlanmis-gorevler/api/eylem")
async def api_eylem(request: Request):
    _oturum_kontrol(request)
    _origin_kontrol(request)
    try:
        govde = await request.json()
    except ValueError:
        govde = {}
    if not isinstance(govde, dict):
        govde = {}
    eylem, birim = str(govde.get("eylem", "")), str(govde.get("birim", ""))

    if eylem == "olustur":
        gorev_id = slug(str(govde.get("ad", "")))
        sablon = str(govde.get("sablon", ""))
        tahtalar = govde.get("tahtalar")
        if not ID_DESENI.match(gorev_id):
            raise HTTPException(400, "Görev adı geçersiz.")
        if sablon not in EYLEM_ETIKETLERI:
            raise HTTPException(400, "Bu eylem şablonu izinli değil.")
        if tahtalar == "hepsi":
            tahta_csv = "hepsi"
        else:
            bilinen = set(tahta_adlari())
            if not isinstance(tahtalar, list) or not tahtalar or not all(t in bilinen for t in tahtalar):
                raise HTTPException(400, "Tahta seçimi geçersiz.")
            tahta_csv = ",".join(tahtalar)
        ifade = _ifade_govdeden(govde)
        birim = GOREV_ONEKI + gorev_id
        sonuc = await betik_calistir("olustur", gorev_id, sablon, tahta_csv, ifade)
    else:
        try:
            eylem_dogrula(birim, eylem)
        except ValueError:
            raise HTTPException(403, "Bu birim için izin verilmeyen eylem.")
        if ders_saatinde_yasak_mi(birim, eylem):
            raise HTTPException(403, "Ders saatinde çalıştırılamaz.")
        uyari = onay_gerekli_mi(birim, eylem)
        if uyari and govde.get("onay") is not True:
            return JSONResponse({"onay_gerekli": uyari}, status_code=409)
        if eylem == "takvim":
            sonuc = await betik_calistir("takvim", birim, _ifade_govdeden(govde))
        elif eylem == "sil":
            sonuc = await betik_calistir("sil", birim[len(GOREV_ONEKI):])
        else:
            sonuc = await betik_calistir(eylem, birim)
    _analiz_onbellek.clear()
    uzaktan_yonetim._denetim_yaz(request, f"zamanlayici-{eylem}",
                                 [{"tahta": birim, "basarili": sonuc["ok"]}], kaynak="zamanlanmis-gorevler")
    return JSONResponse({"ok": sonuc["ok"], "mesaj": sonuc["mesaj"]})
