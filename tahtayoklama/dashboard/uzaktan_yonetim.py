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
import shlex
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

import auth
import db
import ssh_istemci
import tahta_kaydi
import uzaktan_baslat
import zil

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
            raise HTTPException(401, "Oturum geçersiz.")
    finally:
        conn.close()


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


# --------------------------------------------------------------------
# Route'lar
# --------------------------------------------------------------------

@router.get("/uzaktan", response_class=HTMLResponse)
async def uzaktan_sayfa(request: Request):
    _dogrula(request)
    tahtalar = await tum_durumlar()
    return templates.TemplateResponse(request, "uzaktan_yonetim.html", {"tahtalar": tahtalar, "sonuclar": None})


async def _eylem_calistir_ve_render(request: Request, eylem) -> HTMLResponse:
    _dogrula(request)
    form = await request.form()
    secilenler = set(form.getlist("tahta"))
    hedefler = [t for t in tahta_kaydi.tahtalari_yukle() if t["ad"] in secilenler]
    if hedefler:
        sonuclar = list(await asyncio.gather(*(eylem(t, form) for t in hedefler)))
    else:
        sonuclar = [{"tahta": None, "basarili": False, "detay": "Hiçbir tahta seçilmedi."}]
    durumlar = await tum_durumlar()
    return templates.TemplateResponse(request, "uzaktan_yonetim.html", {"tahtalar": durumlar, "sonuclar": sonuclar})


@router.post("/uzaktan/yoklama-ac", response_class=HTMLResponse)
async def yoklama_ac_route(request: Request):
    return await _eylem_calistir_ve_render(request, _yoklama_ac_tek)


@router.post("/uzaktan/yoklama-kapat", response_class=HTMLResponse)
async def yoklama_kapat_route(request: Request):
    return await _eylem_calistir_ve_render(request, _yoklama_kapat_tek)


@router.post("/uzaktan/web-ac", response_class=HTMLResponse)
async def web_ac_route(request: Request):
    return await _eylem_calistir_ve_render(request, _web_ac_tek)


@router.post("/uzaktan/chrome-kapat", response_class=HTMLResponse)
async def chrome_kapat_route(request: Request):
    return await _eylem_calistir_ve_render(request, _chrome_kapat_tek)


@router.post("/uzaktan/ekran-karart", response_class=HTMLResponse)
async def ekran_karart_route(request: Request):
    return await _eylem_calistir_ve_render(request, _ekran_karart_tek)


@router.post("/uzaktan/ekran-kaldir", response_class=HTMLResponse)
async def ekran_kaldir_route(request: Request):
    return await _eylem_calistir_ve_render(request, _ekran_kaldir_tek)


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
    durumlar = await tum_durumlar()
    return templates.TemplateResponse(request, "uzaktan_yonetim.html", {"tahtalar": durumlar, "sonuclar": sonuclar})
