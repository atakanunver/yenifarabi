"""Faz 6 — uzaktan yönetim: yoklama aç/kapat, web sayfası aç, ekranı
karart, duvar kağıdı değiştir. Windows'taki tahta_panel.py'nin (tkinter)
bir alt kümesinin web karşılığı — bkz. docs/superpowers/specs/
2026-09-15-tahta-uzaktan-yonetim-design.md.

Tahta hedefleri HER ZAMAN server/tahtalar.json'dan (tahta_kaydi.py)
çözülür — istemciden yalnızca "ad" kabul edilir, IP/komut asla. Hiçbir
işlem sudo/root gerektirmez: SSH anahtarı zaten `ogretmen` hesabına
doğrudan yetkili (uzaktan_baslat.py bunu kanıtlamış), yerel Windows
aracındaki etapadmin+sudo katmanına burada ihtiyaç yok.
"""

import asyncio
import base64
from datetime import datetime
import io
import shlex
import time
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from PIL import Image

import auth
import db
import ssh_istemci
import tahta_kaydi
import uzaktan_baslat
import zil

_ISTANBUL = ZoneInfo("Europe/Istanbul")

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")
templates.env.globals["gun_adi_buyuk"] = zil.gun_adi_buyuk

_GORSEL_UZANTILARI = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
_MAKS_DOSYA_BOYUTU = 15 * 1024 * 1024

_PYTHON_ADAYLARI = [
    "/home/ogretmen/tahtayoklama/venv/bin/python",
    "/usr/bin/python3",
]

_DURUM_KOMUTU = (
    "U=$(id -un); "
    "SID=$(loginctl list-sessions --no-legend 2>/dev/null | awk -v u=\"$U\" '$3==u{print $1; exit}'); "
    "if [ -z \"$SID\" ]; then OTURUM=giris_ekrani; else "
    "L=$(loginctl show-session \"$SID\" -p LockedHint --value 2>/dev/null); "
    "if [ \"$L\" = yes ]; then OTURUM=kilitli; else OTURUM=acik; fi; fi; "
    "Y=0; pgrep -f '[t]ahtayoklama/yoklama.py' >/dev/null 2>&1 && Y=1; "
    "C=0; pgrep -f '[g]oogle-chrome' >/dev/null 2>&1 && C=1; "
    "K=0; pgrep -f '[e]ta-screen-cover' >/dev/null 2>&1 && K=1; "
    "echo \"$OTURUM $Y $C $K\""
)


def _dogrula(request: Request) -> None:
    conn = db.baglanti()
    try:
        if not auth.dogrula(request, conn):
            # Tarayıcı sayfa isteği → ana pano gibi /giris'e yönlendir;
            # API/otomasyon istekleri eski 401'i almaya devam eder.
            if "text/html" in request.headers.get("accept", ""):
                raise HTTPException(303, headers={"Location": "/giris"})
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()


def _denetim_yaz(request: Request, eylem: str, sonuclar: list[dict], kaynak: str | None = None) -> None:
    """Uzaktan eylemi uzaktan_denetim tablosuna yazar. Yalnızca eylem adı,
    tahta adları ve ok/hata durumu saklanır (URL, dosya adı/içeriği asla).
    Log hatası eylemi ASLA engellemez veya değiştirmez."""
    try:
        zaman = datetime.now(_ISTANBUL).isoformat(timespec="seconds")
        istemci_ip = request.client.host if request.client else None
        adlar = [r["tahta"] for r in sonuclar if r.get("tahta") is not None]
        tahtalar = ",".join(adlar)
        if adlar:
            sonuc = ",".join(
                f"{r['tahta']}:{r.get('denetim_kodu') or ('ok' if r.get('basarili') else 'hata')}"
                for r in sonuclar if r.get("tahta") is not None
            )
        else:
            sonuc = "secim_yok"
        conn = db.baglanti()
        try:
            conn.execute(
                "INSERT INTO uzaktan_denetim (zaman, istemci_ip, eylem, tahtalar, sonuc, kaynak) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (zaman, istemci_ip, eylem, tahtalar, sonuc, kaynak),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _url_normallestir(ham: str) -> str:
    ham = ham.strip()
    if not (ham.startswith("http://") or ham.startswith("https://")):
        ham = "https://" + ham
    return ham


# --------------------------------------------------------------------
# Durum tablosu
# --------------------------------------------------------------------

async def _tahta_durumu(t: dict) -> dict:
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], _DURUM_KOMUTU, zaman_asimi=6)
    varsayilan = {**t, "ulasilabilir": False, "oturum": "bilinmiyor", "yoklama": False, "chrome": False, "karartildi": False}
    if not sonuc.basarili:
        return varsayilan
    parcalar = sonuc.stdout.decode("utf-8", errors="replace").strip().split()
    if len(parcalar) < 4:
        return varsayilan
    oturum, y, c, k = parcalar[:4]
    return {**t, "ulasilabilir": True, "oturum": oturum, "yoklama": y == "1", "chrome": c == "1", "karartildi": k == "1"}


async def tum_durumlar() -> list[dict]:
    tahtalar = tahta_kaydi.tahtalari_yukle()
    if not tahtalar:
        return []
    return list(await asyncio.gather(*(_tahta_durumu(t) for t in tahtalar)))


_onbellek_durumlar: list[dict] | None = None
_onbellek_zamani = 0.0
_DURUM_ONBELLEK_SN = 45
_kilit = asyncio.Lock()


async def durumlar_al(yenile: bool = False) -> list[dict]:
    global _onbellek_durumlar, _onbellek_zamani
    async with _kilit:
        simdi = time.monotonic()
        if yenile or _onbellek_durumlar is None or (simdi - _onbellek_zamani > _DURUM_ONBELLEK_SN):
            _onbellek_durumlar = await tum_durumlar()
            _onbellek_zamani = simdi
        return _onbellek_durumlar


# --------------------------------------------------------------------
# Tek tahta üzerinde çalışan eylemler — hepsi (t, form) alır, ortak
# çalıştırıcı (_eylem_calistir_ve_render) tarafından paralel çağrılır.
# --------------------------------------------------------------------

async def _python_yolu_bul(ip: str, kullanici: str) -> str | None:
    for aday in _PYTHON_ADAYLARI:
        sonuc = await ssh_istemci.komut_calistir(ip, kullanici, f"test -x {shlex.quote(aday)}")
        if sonuc.basarili:
            return aday
    return None


async def _yoklama_ac_tek(t: dict, form) -> dict:
    py = await _python_yolu_bul(t["ip"], t["kullanici"])
    if py is None:
        return {"tahta": t["ad"], "basarili": False, "detay": "Python yorumlayıcısı bulunamadı (venv eksik)."}
    sonuc = await uzaktan_baslat.baslat(
        {"ip": t["ip"], "ssh_kullanici": t["kullanici"], "python_yolu": py, "ad": t["ad"]}
    )
    return {"tahta": t["ad"], "basarili": sonuc["basarili"], "detay": sonuc["detay"]}


async def _yoklama_kapat_tek(t: dict, form) -> dict:
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], "pkill -f '[t]ahtayoklama/yoklama.py'; true")
    return {"tahta": t["ad"], "basarili": sonuc.basarili, "detay": "Kapatıldı." if sonuc.basarili else f"SSH hatası: {sonuc.stderr.decode(errors='replace')[:200]}"}


async def _web_ac_tek(t: dict, form) -> dict:
    url = _url_normallestir(form.get("url", ""))
    if url in ("https://", "http://"):
        return {"tahta": t["ad"], "basarili": False, "detay": "URL boş."}
    ortam = await ssh_istemci.x_ortamini_kesfet(t["ip"], t["kullanici"])
    if ortam is None:
        return {"tahta": t["ad"], "basarili": False, "detay": "Aktif masaüstü oturumu bulunamadı (tahta kapalı olabilir)."}
    display, xauthority, _uid = ortam
    calisiyor = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], "pgrep -f '[g]oogle-chrome'")
    if not calisiyor.basarili:
        # Golden image'dan miras kalan eski Singleton kilidi — chrome
        # çalışmıyorsa güvenle temizlenebilir (bkz. yerel tahta_ssh.py).
        await ssh_istemci.komut_calistir(
            t["ip"], t["kullanici"], f"rm -f /home/{t['kullanici']}/.config/google-chrome/Singleton*"
        )
    komut = (
        f"setsid env DISPLAY={display} XAUTHORITY={xauthority} "
        f"google-chrome --new-window {shlex.quote(url)} "
        f"</dev/null >/tmp/yonetim_chrome.log 2>&1 &"
    )
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], komut)
    return {"tahta": t["ad"], "basarili": sonuc.basarili, "detay": f"Sayfa açıldı: {url}" if sonuc.basarili else sonuc.stderr.decode(errors="replace")[:200]}


async def _chrome_kapat_tek(t: dict, form) -> dict:
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], "pkill -f '[g]oogle-chrome'; true")
    return {"tahta": t["ad"], "basarili": sonuc.basarili, "detay": "Kapatıldı." if sonuc.basarili else f"SSH hatası: {sonuc.stderr.decode(errors='replace')[:200]}"}


_ETA_SCREEN_COVER_BASLIK = "tr.org.pardus.eta-screen-cover"


async def _ekran_karart_tek(t: dict, form) -> dict:
    ortam = await ssh_istemci.x_ortamini_kesfet(t["ip"], t["kullanici"])
    if ortam is None:
        return {"tahta": t["ad"], "basarili": False, "detay": "Aktif masaüstü oturumu bulunamadı (tahta kapalı olabilir)."}
    display, xauthority, _uid = ortam
    calisiyor = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], "pgrep -f '[e]ta-screen-cover'")
    if not calisiyor.basarili:
        await ssh_istemci.komut_calistir(
            t["ip"], t["kullanici"],
            f"setsid env DISPLAY={display} XAUTHORITY={xauthority} eta-screen-cover "
            f"</dev/null >/tmp/yonetim_karart.log 2>&1 &",
        )
        await asyncio.sleep(1.5)
    sonuc = await ssh_istemci.komut_calistir(
        t["ip"], t["kullanici"],
        f"env DISPLAY={display} XAUTHORITY={xauthority} "
        f"wmctrl -r {shlex.quote(_ETA_SCREEN_COVER_BASLIK)} -b add,maximized_vert,maximized_horz",
    )
    return {"tahta": t["ad"], "basarili": sonuc.basarili, "detay": "Karartıldı (tam ekran)." if sonuc.basarili else sonuc.stderr.decode(errors="replace")[:200]}


async def _ekran_kaldir_tek(t: dict, form) -> dict:
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], "pkill -f '[e]ta-screen-cover'; true")
    return {"tahta": t["ad"], "basarili": sonuc.basarili, "detay": "Karartma kaldırıldı." if sonuc.basarili else f"SSH hatası: {sonuc.stderr.decode(errors='replace')[:200]}"}


async def _duvar_kagidi_tek(t: dict, icerik: bytes, uzanti: str) -> dict:
    uzak_ad = f"duvar_{int(time.time())}{uzanti}"
    ev = f"/home/{t['kullanici']}"
    uzak_yol = f"{ev}/Resimler/{uzak_ad}"
    yaz_komutu = (
        f"mkdir -p {ev}/Resimler && cat > {shlex.quote(uzak_yol)}.tmp && "
        f"mv {shlex.quote(uzak_yol)}.tmp {shlex.quote(uzak_yol)}"
    )
    yazma = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], yaz_komutu, stdin_bytes=icerik, zaman_asimi=25)
    if not yazma.basarili:
        return {"tahta": t["ad"], "basarili": False, "detay": f"Dosya yazılamadı: {yazma.stderr.decode(errors='replace')[:200]}"}

    ortam = await ssh_istemci.x_ortamini_kesfet(t["ip"], t["kullanici"])
    if ortam is None:
        return {"tahta": t["ad"], "basarili": False, "detay": "Dosya gönderildi ama aktif oturum yok — duvar kağıdı ayarlanamadı."}
    display, xauthority, uid = ortam
    uri = f"file://{uzak_yol}"
    # Asıl görünür etki org.cinnamon.desktop.background'a bağlı (masaüstü
    # Cinnamon, bkz. ssh_istemci.x_ortamini_kesfet docstring'i) — bu yüzden
    # raporlanan başarı/hata SADECE bu iki çağrıya bakar ($CINNAMON_DURUM).
    # org.gnome.desktop.background çağrısı yedek/best-effort'tur, sonucu
    # göz ardı edilir — önceden üçü ";" ile zincirlenmişti, bu durumda
    # bash'in döndürdüğü çıkış kodu zincirdeki SON komutundu (gnome), yani
    # asıl önemli olan cinnamon çağrısı başarısız olsa bile son adım
    # (gnome) başarılıysa panel yanlışlıkla "değiştirildi" diyebiliyordu.
    ic_komut = (
        f"gsettings set org.cinnamon.desktop.background picture-uri {shlex.quote(uri)} && "
        f"gsettings set org.cinnamon.desktop.background picture-options zoom; "
        f"CINNAMON_DURUM=$?; "
        f"gsettings set org.gnome.desktop.background picture-uri {shlex.quote(uri)} >/dev/null 2>&1; "
        f"exit $CINNAMON_DURUM"
    )
    komut = (
        f"env DISPLAY={display} XAUTHORITY={xauthority} "
        f"DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus "
        f"bash -c {shlex.quote(ic_komut)}"
    )
    sonuc = await ssh_istemci.komut_calistir(t["ip"], t["kullanici"], komut)
    return {"tahta": t["ad"], "basarili": sonuc.basarili, "detay": "Duvar kağıdı değiştirildi." if sonuc.basarili else sonuc.stderr.decode(errors="replace")[:200]}


# Makine API'si (ajan_api.py) için ad → eylem haritası. Duvar kağıdı YOK.
# Eylemler (t, form) alır; form yerine .get() destekleyen düz dict verilebilir
# (yalnızca web_ac "url" okur).
EYLEMLER = {
    "yoklama_ac": _yoklama_ac_tek,
    "yoklama_kapat": _yoklama_kapat_tek,
    "web_ac": _web_ac_tek,
    "chrome_kapat": _chrome_kapat_tek,
    "ekran_karart": _ekran_karart_tek,
    "ekran_kaldir": _ekran_kaldir_tek,
}


# --------------------------------------------------------------------
# Route'lar
# --------------------------------------------------------------------

@router.get("/uzaktan/api/durumlar")
async def api_uzaktan_durumlar(request: Request, yenile: int = 0):
    _dogrula(request)
    durumlar = await durumlar_al(yenile=bool(yenile))
    return JSONResponse({"tahtalar": durumlar, "onbellek": not bool(yenile)})


@router.get("/uzaktan", response_class=HTMLResponse)
async def uzaktan_sayfa(request: Request, yenile: int = 0):
    _dogrula(request)
    if _onbellek_durumlar is not None and not yenile:
        tahtalar = _onbellek_durumlar
        yukleniyor = False
    else:
        # Hızlı iskelet: sayfa beklemeden 1 ms'de render edilir; durumlar arka planda doldurulur
        ham = tahta_kaydi.tahtalari_yukle()
        tahtalar = [{**t, "ulasilabilir": None, "oturum": "yukleniyor", "yoklama": False, "chrome": False, "karartildi": False} for t in ham]
        yukleniyor = True
    return templates.TemplateResponse(request, "uzaktan_yonetim.html", {"tahtalar": tahtalar, "yukleniyor": yukleniyor, "sonuclar": None})


async def _eylem_calistir_ve_render(request: Request, eylem, eylem_adi: str) -> HTMLResponse:
    _dogrula(request)
    form = await request.form()
    secilenler = set(form.getlist("tahta"))
    hedefler = [t for t in tahta_kaydi.tahtalari_yukle() if t["ad"] in secilenler]
    if hedefler:
        sonuclar = list(await asyncio.gather(*(eylem(t, form) for t in hedefler)))
    else:
        sonuclar = [{"tahta": None, "basarili": False, "detay": "Hiçbir tahta seçilmedi."}]
    _denetim_yaz(request, eylem_adi, sonuclar)
    durumlar = await durumlar_al(yenile=True)
    return templates.TemplateResponse(request, "uzaktan_yonetim.html", {"tahtalar": durumlar, "yukleniyor": False, "sonuclar": sonuclar})


@router.post("/uzaktan/yoklama-ac", response_class=HTMLResponse)
async def yoklama_ac_route(request: Request):
    return await _eylem_calistir_ve_render(request, _yoklama_ac_tek, "yoklama_ac")


@router.post("/uzaktan/yoklama-kapat", response_class=HTMLResponse)
async def yoklama_kapat_route(request: Request):
    return await _eylem_calistir_ve_render(request, _yoklama_kapat_tek, "yoklama_kapat")


@router.post("/uzaktan/web-ac", response_class=HTMLResponse)
async def web_ac_route(request: Request):
    return await _eylem_calistir_ve_render(request, _web_ac_tek, "web_ac")


@router.post("/uzaktan/chrome-kapat", response_class=HTMLResponse)
async def chrome_kapat_route(request: Request):
    return await _eylem_calistir_ve_render(request, _chrome_kapat_tek, "chrome_kapat")


@router.post("/uzaktan/ekran-karart", response_class=HTMLResponse)
async def ekran_karart_route(request: Request):
    return await _eylem_calistir_ve_render(request, _ekran_karart_tek, "ekran_karart")


@router.post("/uzaktan/ekran-kaldir", response_class=HTMLResponse)
async def ekran_kaldir_route(request: Request):
    return await _eylem_calistir_ve_render(request, _ekran_kaldir_tek, "ekran_kaldir")


@router.post("/uzaktan/duvar-kagidi", response_class=HTMLResponse)
async def duvar_kagidi_route(request: Request):
    _dogrula(request)
    form = await request.form()
    secilenler = set(form.getlist("tahta"))
    dosya = form.get("dosya")
    if dosya is None or not getattr(dosya, "filename", ""):
        raise HTTPException(400, "Dosya seçilmedi.")

    icerik = await dosya.read()
    if not icerik:
        raise HTTPException(400, "Dosya boş.")
    if len(icerik) > _MAKS_DOSYA_BOYUTU:
        raise HTTPException(400, "Dosya çok büyük (maks 15MB).")
    uzanti = Path(dosya.filename).suffix.lower()
    if uzanti not in _GORSEL_UZANTILARI:
        uzanti = ".jpg"

    hedefler = [t for t in tahta_kaydi.tahtalari_yukle() if t["ad"] in secilenler]
    if hedefler:
        sonuclar = list(await asyncio.gather(*(_duvar_kagidi_tek(t, icerik, uzanti) for t in hedefler)))
    else:
        sonuclar = [{"tahta": None, "basarili": False, "detay": "Hiçbir tahta seçilmedi."}]
    _denetim_yaz(request, "duvar_kagidi", sonuclar)
    durumlar = await tum_durumlar()
    return templates.TemplateResponse(request, "uzaktan_yonetim.html", {"tahtalar": durumlar, "sonuclar": sonuclar})


# --------------------------------------------------------------------
# Ekran Görüntüsü (Screenshot) ve Önizleme
# --------------------------------------------------------------------

def _gorsel_optimize_et(baytlar: bytes, maks_genislik: int = 1280, kalite: int = 75) -> tuple[bytes, str, int | None, int | None]:
    """Gelen ekran görüntüsünü Pillow ile optimize eder (maksimum genişliğe ölçekler ve JPEG yapar)."""
    try:
        with Image.open(io.BytesIO(baytlar)) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            w, h = img.size
            if w > maks_genislik:
                yeni_h = int(h * (maks_genislik / w))
                img = img.resize((maks_genislik, yeni_h), Image.Resampling.LANCZOS)
                w, h = img.size
            cikti = io.BytesIO()
            img.save(cikti, format="JPEG", quality=kalite, optimize=True)
            return cikti.getvalue(), "image/jpeg", w, h
    except Exception:
        mime = "image/png" if baytlar.startswith(b"\x89PNG") else "image/jpeg"
        return baytlar, mime, None, None


async def _ekran_goruntusu_al(t: dict) -> tuple[bool, bytes, str, int | None, int | None]:
    """Tahtadan X11 masaüstü ekran görüntüsü alır.
    Önce DISPLAY=:0 ile import/gnome-screenshot komutunu dener;
    olmazsa derin X ortamı keşfi ile dener."""
    user = t["kullanici"]
    ip = t["ip"]

    # 1. Hızlı yol (standart Pardus X11 ortamı - ~0.5sn)
    komut = (
        "export DISPLAY=:0; "
        f"if [ -f /home/{user}/.Xauthority ]; then export XAUTHORITY=/home/{user}/.Xauthority; fi; "
        "if command -v import >/dev/null 2>&1; then "
        "  import -window root -resize 1280x -quality 70 jpg:- 2>/dev/null; "
        "elif command -v gnome-screenshot >/dev/null 2>&1; then "
        "  gnome-screenshot --file=/tmp/tahta_ss.png >/dev/null 2>&1 && cat /tmp/tahta_ss.png && rm -f /tmp/tahta_ss.png; "
        "fi"
    )
    sonuc = await ssh_istemci.komut_calistir(ip, user, komut, zaman_asimi=8)
    if sonuc.basarili and len(sonuc.stdout) > 1000:
        opt_bayt, mime, w, h = _gorsel_optimize_et(sonuc.stdout)
        return True, opt_bayt, "", w, h

    # 2. X ortamını derin keşfetme ile yedek deneme
    ortam = await ssh_istemci.x_ortamini_kesfet(ip, user)
    if ortam is None:
        return False, b"", "Tahtaya ulaşılamıyor veya aktif masaüstü oturumu (X11) bulunamadı.", None, None

    display, xauth, _uid = ortam
    yedek_komut = (
        f"env DISPLAY={display} XAUTHORITY={xauth} bash -c '"
        "if command -v import >/dev/null 2>&1; then "
        "  import -window root -resize 1280x -quality 70 jpg:- 2>/dev/null; "
        "elif command -v gnome-screenshot >/dev/null 2>&1; then "
        "  gnome-screenshot --file=/tmp/tahta_ss.png >/dev/null 2>&1 && cat /tmp/tahta_ss.png && rm -f /tmp/tahta_ss.png; "
        "fi'"
    )
    sonuc2 = await ssh_istemci.komut_calistir(ip, user, yedek_komut, zaman_asimi=10)
    if sonuc2.basarili and len(sonuc2.stdout) > 1000:
        opt_bayt, mime, w, h = _gorsel_optimize_et(sonuc2.stdout)
        return True, opt_bayt, "", w, h

    hata = sonuc.stderr.decode("utf-8", errors="replace").strip() or "Ekran görüntüsü alınamadı (tahta kilitli veya kapalı olabilir)."
    return False, b"", hata, None, None


@router.get("/uzaktan/ekran-goruntusu/{tahta_adi}")
async def ekran_goruntusu_route(request: Request, tahta_adi: str, ham: int = 0):
    _dogrula(request)
    tahtalar = tahta_kaydi.tahtalari_yukle()
    tahta = next((t for t in tahtalar if t["ad"] == tahta_adi), None)
    if not tahta:
        raise HTTPException(404, f"Tahta bulunamadı: {tahta_adi}")

    basarili, gorsel_bayt, hata, w, h = await _ekran_goruntusu_al(tahta)
    if not basarili:
        if ham:
            html_hata = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <title>{tahta_adi} — Ekran Görüntüsü Alınamadı</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #e2e8f0; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .kutu {{ background: #1e293b; padding: 2.2rem 2.5rem; border-radius: 14px; border: 1px solid #334155; text-align: center; max-width: 480px; box-shadow: 0 15px 35px rgba(0,0,0,0.35); }}
    h2 {{ margin: 0 0 0.8rem; color: #ef4444; font-size: 1.3rem; font-weight: 700; }}
    p {{ color: #94a3b8; font-size: 0.95rem; line-height: 1.5; margin: 0.5rem 0 1.8rem; }}
    .butonlar {{ display: flex; gap: 0.75rem; justify-content: center; }}
    .btn {{ display: inline-flex; align-items: center; justify-content: center; padding: 0.6rem 1.3rem; background: #2563eb; color: white; border-radius: 8px; font-weight: 600; font-size: 0.9rem; border: none; cursor: pointer; text-decoration: none; }}
    .btn-ikincil {{ background: #334155; color: #e2e8f0; }}
    .btn:hover {{ opacity: 0.9; }}
  </style>
</head>
<body>
  <div class="kutu">
    <h2>⚠️ {tahta_adi} Ekran Görüntüsü Alınamadı</h2>
    <p>{hata}</p>
    <div class="butonlar">
      <button class="btn" onclick="location.reload()">⟳ Tekrar Dene</button>
      <button class="btn btn-ikincil" onclick="window.close()">Pencereyi Kapat</button>
    </div>
  </div>
</body>
</html>"""
            return HTMLResponse(content=html_hata, status_code=502)

        return JSONResponse(
            {
                "basarili": False,
                "tahta": tahta_adi,
                "ip": tahta["ip"],
                "hata": hata,
            },
            status_code=502 if ("ulaşıl" in hata.lower() or "kapalı" in hata.lower()) else 500,
        )

    if ham:
        headers = {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        }
        return Response(content=gorsel_bayt, media_type="image/jpeg", headers=headers)

    gorsel_b64 = "data:image/jpeg;base64," + base64.b64encode(gorsel_bayt).decode("ascii")
    simdi = datetime.now(_ISTANBUL).strftime("%H:%M:%S")

    return JSONResponse({
        "basarili": True,
        "tahta": tahta_adi,
        "ip": tahta["ip"],
        "zaman": simdi,
        "gorsel": gorsel_b64,
        "genislik": w,
        "yukseklik": h,
        "boyut_kb": round(len(gorsel_bayt) / 1024, 1),
    })
