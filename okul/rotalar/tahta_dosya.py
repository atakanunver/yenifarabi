"""Tahtaya dosya gönderme sayfası ve dashboard LAN API'si."""

import hmac
import json
import sqlite3
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Annotated

import tahta_dosya
from ayarlar import AYAR
from deps import db_conn, render, rol
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.datastructures import UploadFile

from rotalar.pano import _lan_mi

router = APIRouter()
OGRETMEN = rol('ogretmen', 'yonetici')
OGRETMEN_POST = rol('ogretmen', 'yonetici', post=True)
Ogretmen = Annotated[sqlite3.Row, Depends(OGRETMEN)]
OgretmenPost = Annotated[sqlite3.Row, Depends(OGRETMEN_POST)]
Baglanti = Annotated[sqlite3.Connection, Depends(db_conn)]


def _anahtar(request: Request) -> None:
    if not _lan_mi(request) or not AYAR.tahta_dosya_anahtar:
        raise HTTPException(404)
    if not hmac.compare_digest(request.headers.get('x-tahta-dosya-key', ''), AYAR.tahta_dosya_anahtar):
        raise HTTPException(404)


def _tahtalar() -> list[dict]:
    if not AYAR.tahta_dosya_anahtar:
        return []
    istek = urllib.request.Request(
        AYAR.tahta_dosya_dashboard_url + '/api/tahta-dosya/tahtalar',
        headers={'X-Tahta-Dosya-Key': AYAR.tahta_dosya_anahtar},
    )
    try:
        with urllib.request.urlopen(istek, timeout=3) as yanit:
            return json.load(yanit)['tahtalar']
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return []


def _sayfa(request, conn, k, status=200, hata=''):
    tahta_dosya.sure_doldur(conn)
    return render(request, 'ogretmen/tahta_dosya.html', status,
                  tahtalar=_tahtalar(), hata=hata,
                  gonderimler=conn.execute(
                      'SELECT tahta, dosya_adi, durum, zaman, gonderim_zamani FROM tahta_dosya '
                      'WHERE ogretmen_id=? ORDER BY id DESC LIMIT 100', (k['id'],)
                  ).fetchall())


@router.get('/ogretmen/tahtaya-gonder')
def sayfa(request: Request, k: Ogretmen, conn: Baglanti):
    return _sayfa(request, conn, k)


@router.post('/ogretmen/tahtaya-gonder')
async def gonder(request: Request, k: OgretmenPost, conn: Baglanti):
    form = await request.form()
    secilen = [str(t) for t in form.getlist('tahta')]
    izinli = {t['ad'] for t in _tahtalar()}
    dosya = form.get('dosya')
    if not isinstance(dosya, UploadFile):
        return _sayfa(request, conn, k, 422, 'Dosya seçin.')
    yol = None
    try:
        gecici = AYAR.tahta_dosya_gecici / str(k['id'])
        gecici.mkdir(parents=True, exist_ok=True)
        yol = gecici / (uuid.uuid4().hex + '.tmp')
        with yol.open('wb') as out:
            while parca := await dosya.read(1024 * 1024):
                out.write(parca)
                if out.tell() > tahta_dosya.AZAMI:
                    raise tahta_dosya.DosyaHatasi('Dosya 95 MB sınırını aşıyor.')
        tahta_dosya.kaydet(conn, k, yol, dosya.filename or '', secilen, izinli)
    except (tahta_dosya.DosyaHatasi, ValueError, OSError) as e:
        return _sayfa(request, conn, k, 422, str(e))
    finally:
        if yol is not None:
            yol.unlink(missing_ok=True)
        if isinstance(dosya, UploadFile):
            await dosya.close()
    return RedirectResponse('/ogretmen/tahtaya-gonder', status_code=303)


@router.get('/api/tahta-dosya/bekleyen')
def api_bekleyen(request: Request, conn: Baglanti):
    _anahtar(request)
    return {'dosyalar': tahta_dosya.bekleyenler(conn)}


@router.get('/api/tahta-dosya/{dosya_id}/dosya')
def api_dosya(dosya_id: int, request: Request, conn: Baglanti):
    _anahtar(request)
    satir = conn.execute("SELECT yedek_yol FROM tahta_dosya WHERE id=? AND durum IN ('sirada','hata')", (dosya_id,)).fetchone()
    if satir is None:
        raise HTTPException(404)
    yol = Path(satir['yedek_yol'])
    if not yol.is_file() or not yol.resolve().is_relative_to(AYAR.tahta_dosya_yedek.resolve()):
        raise HTTPException(404)
    return FileResponse(yol, media_type='application/octet-stream')


@router.post('/api/tahta-dosya/{dosya_id}/sonuc')
async def api_sonuc(dosya_id: int, request: Request, conn: Baglanti):
    _anahtar(request)
    try:
        veri = await request.json()
        if not tahta_dosya.sonuc(conn, dosya_id, str(veri.get('durum', '')), str(veri.get('hata', ''))):
            raise HTTPException(404)
    except tahta_dosya.DosyaHatasi as e:
        raise HTTPException(400, str(e)) from e
    return {'tamam': True}
