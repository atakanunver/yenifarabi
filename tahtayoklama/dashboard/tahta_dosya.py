"""Okul dosya kuyruğunu tahtalara taşıyan dashboard görevi."""

import asyncio
import hmac
import ipaddress
import json
import logging
import shlex
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

import ssh_istemci
import tahta_kaydi
import uzaktan_yonetim
from fastapi import APIRouter, HTTPException, Request

log = logging.getLogger(__name__)
router = APIRouter()
CONFIG = Path(__file__).resolve().parent / 'config' / 'tahta_dosya.json'
OKUL_URL = 'http://127.0.0.1:9090/api/tahta-dosya'


def anahtar() -> str:
    try:
        return str(json.loads(CONFIG.read_text(encoding='utf-8')).get('anahtar') or '')
    except (OSError, ValueError, AttributeError):
        return ''


def _yerel(request: Request) -> None:
    if any(k.startswith(('cf-', 'x-forwarded-')) or k == 'x-real-ip' for k in request.headers):
        raise HTTPException(404)
    try:
        ip = ipaddress.ip_address(request.client.host)
    except (ValueError, AttributeError):
        raise HTTPException(404) from None
    if not ip.is_private or not anahtar():
        raise HTTPException(404)
    if not hmac.compare_digest(request.headers.get('x-tahta-dosya-key', ''), anahtar()):
        raise HTTPException(404)


@router.get('/api/tahta-dosya/tahtalar')
def tahtalar(request: Request):
    _yerel(request)
    return {'tahtalar': [{'ad': t['ad'], 'sinif': t['ad'] if '-' in t['ad'] and t['ad'][0].isdigit() else ''}
                         for t in tahta_kaydi.tahtalari_yukle()]}


def _istek(yol: str, govde: dict | None = None):
    key = anahtar()
    if not key:
        return None
    veri = json.dumps(govde).encode('utf-8') if govde is not None else None
    req = urllib.request.Request(OKUL_URL + yol, data=veri,
        headers={'X-Tahta-Dosya-Key': key, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20) as yanit:
        if yol.endswith('/dosya'):
            with tempfile.NamedTemporaryFile(prefix='tahta-dosya-', delete=False) as f:
                shutil.copyfileobj(yanit, f)
                return Path(f.name)
        return json.load(yanit)


async def _gonder(is_: dict, tahta: dict) -> tuple[str, str]:
    ip, kullanici = tahta['ip'], tahta['kullanici']
    # Masaüstü yolunu tahtadaki kullanıcı belirler.
    cmd = 'p=$(xdg-user-dir DESKTOP 2>/dev/null); if [ -z "$p" ] || [ ! -d "$p" ]; then '
    cmd += 'if [ -d "$HOME/Masaüstü" ]; then p="$HOME/Masaüstü"; else p="$HOME/Desktop"; fi; fi; '
    cmd += 'mkdir -p "$p/Gelen Dosyalar" && printf "%s" "$p/Gelen Dosyalar"'
    sonuc = await ssh_istemci.komut_calistir(ip, kullanici, cmd, zaman_asimi=12)
    if not sonuc.basarili:
        return 'sirada', 'Tahtaya erişilemedi.'
    dizin = sonuc.stdout.decode('utf-8', 'replace').strip()
    if not dizin.startswith('/'):
        return 'hata', 'Masaüstü yolu bulunamadı.'
    isaret = f"{dizin}/.farabi-{is_['id']}.done"
    once = await ssh_istemci.komut_calistir(ip, kullanici,
        f'test -f {shlex.quote(isaret)}', zaman_asimi=10)
    if once.basarili:
        return 'gonderildi', ''
    gecici = f".farabi-tahta-dosya-{is_['id']}.part"
    son = f"{dizin}/{is_['dosya_adi']}"
    alternatif = f"{dizin}/{Path(is_['dosya_adi']).stem}_{is_['id']}{Path(is_['dosya_adi']).suffix}"
    yerel = None
    try:
        yerel = await asyncio.to_thread(_istek, f"/{is_['id']}/dosya")
        if yerel.stat().st_size != is_['boyut']:
            return 'hata', 'İndirilen dosya boyutu uyuşmuyor.'
        saniye = max(30, is_['boyut'] // (1024 * 1024) * 3)
        kopya = await ssh_istemci.scp_gonder(ip, kullanici, yerel, gecici, zaman_asimi=saniye)
        if not kopya.basarili:
            return 'sirada', 'Tahtaya kopyalanamadı.'
        tasima = await ssh_istemci.komut_calistir(ip, kullanici,
            f'if [ -e {shlex.quote(son)} ]; then hedef={shlex.quote(alternatif)}; '
            f'else hedef={shlex.quote(son)}; fi; '
            f'mv -f {shlex.quote(gecici)} "$hedef" && touch {shlex.quote(isaret)}', zaman_asimi=15)
        if not tasima.basarili:
            return 'hata', 'Dosya masaüstüne taşınamadı.'
        try:
            ortam = await ssh_istemci.x_ortamini_kesfet(ip, kullanici)
            if ortam:
                display, xauth, uid = ortam
                metin = f"{is_['ogretmen']}: {is_['dosya_adi']}"
                ortam_komut = f'DISPLAY={shlex.quote(display)} DBUS_SESSION_BUS_ADDRESS={shlex.quote("unix:path=/run/user/" + uid + "/bus")} '
                if xauth:
                    ortam_komut += f'XAUTHORITY={shlex.quote(xauth)} '
                await ssh_istemci.komut_calistir(ip, kullanici,
                    ortam_komut + 'notify-send ' + shlex.quote('Farabi') + ' ' + shlex.quote(metin), zaman_asimi=5)
        except Exception:  # noqa: BLE001 — bildirim dosya teslimini engellemez
            log.warning('Tahta dosyası bildirimi atlandı: %s', is_['id'])
        return 'gonderildi', ''
    finally:
        if yerel is not None:
            yerel.unlink(missing_ok=True)


async def bir_tur() -> None:
    veri = await asyncio.to_thread(_istek, '/bekleyen')
    if not veri:
        return
    tahtalar = {t['ad']: t for t in tahta_kaydi.tahtalari_yukle()}
    for is_ in veri.get('dosyalar', []):
        try:
            tahta = tahtalar.get(is_['tahta'])
            durum, hata = await _gonder(is_, tahta) if tahta else ('hata', 'Tahta kaydı bulunamadı.')
            await asyncio.to_thread(_istek, f"/{is_['id']}/sonuc", {'durum': durum, 'hata': hata})
            uzaktan_yonetim._denetim_yaz(
                Request({'type': 'http', 'headers': [], 'client': ('127.0.0.1', 0)}),
                'tahta-dosya', [{'tahta': is_['tahta'], 'basarili': durum == 'gonderildi'}],
                kaynak='okul',
            )
        except Exception as e:  # noqa: BLE001 — tek dosya diğerlerini engellemez
            log.warning('Tahta dosyası %s gönderilemedi: %s', is_.get('id'), type(e).__name__)
            try:
                await asyncio.to_thread(_istek, f"/{is_['id']}/sonuc",
                                        {'durum': 'sirada', 'hata': 'Aktarım başarısız.'})
            except Exception:  # noqa: BLE001 — okul kapalıysa sonraki tur dener
                log.warning('Tahta dosyası %s sonucu bildirilemedi', is_.get('id'))


async def dongu() -> None:
    while True:
        try:
            await bir_tur()
        except Exception as e:  # noqa: BLE001 — dashboard çalışmaya devam eder
            log.warning('Tahta dosyası kuyruğu okunamadı: %s', type(e).__name__)
        await asyncio.sleep(60)
