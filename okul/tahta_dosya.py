"""Öğretmenden tahtaya dosya kuyruğu ve imza doğrulaması."""

import os
import re
import shutil
import sqlite3
import unicodedata
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path

import zaman
from ayarlar import AYAR

AZAMI = 95 * 1024 * 1024


class DosyaHatasi(ValueError):
    pass


def guvenli_ad(ad: str) -> str:
    ad = Path(ad.replace('\\', '/')).name
    ad = unicodedata.normalize('NFKD', ad.replace('ı', 'i').replace('İ', 'I'))
    ad = ''.join(c for c in ad if not unicodedata.combining(c))
    ad = re.sub(r'[^A-Za-z0-9._-]+', '_', ad).strip('._-')[:100]
    return ad or 'dosya'


def tur_bul(yol: Path) -> str:
    with yol.open('rb') as f:
        bas = f.read(4096)
    if bas.startswith(b'%PDF-'):
        return 'pdf'
    if bas.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    if bas.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if bas.startswith(b'RIFF') and bas[8:12] == b'WAVE':
        return 'wav'
    if bas.startswith(b'OggS'):
        return 'ogg'
    if bas.startswith(b'ID3') or (len(bas) > 2 and bas[0] == 0xff and bas[1] & 0xe0 == 0xe0):
        return 'mp3'
    if bas.startswith(b'\x1a\x45\xdf\xa3'):
        if b'webm' in bas[:128]:
            return 'webm'
        if b'matroska' in bas[:128]:
            return 'mkv'
    if bas[4:8] == b'ftyp':
        marka = bas[8:12]
        if marka in (b'M4A ', b'M4B '):
            return 'm4a'
        if marka == b'qt  ':
            return 'mov'
        if marka in (b'isom', b'iso2', b'mp41', b'mp42', b'avc1', b'dash'):
            return 'mp4'
    if bas.startswith(b'PK\x03\x04'):
        try:
            with zipfile.ZipFile(yol) as z:
                adlar = set(z.namelist())
                if 'mimetype' in adlar:
                    if z.getinfo('mimetype').file_size > 150:
                        return ''
                    mime = z.read('mimetype')[:150].decode('ascii', 'ignore')
                    for ek, tur in (('text', 'odt'), ('presentation', 'odp'), ('spreadsheet', 'ods')):
                        if mime == 'application/vnd.oasis.opendocument.' + ek:
                            return tur
                if '[Content_Types].xml' in adlar:
                    if z.getinfo('[Content_Types].xml').file_size > 1024 * 1024:
                        return ''
                    xml = z.read('[Content_Types].xml')
                    for parca, tur in ((b'wordprocessingml.document.main+xml', 'docx'),
                                       (b'presentationml.presentation.main+xml', 'pptx'),
                                       (b'spreadsheetml.sheet.main+xml', 'xlsx')):
                        if parca in xml:
                            return tur
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError):
            pass
    return ''


def kaydet(conn: sqlite3.Connection, k, yol: Path, ad: str, tahtalar: list[str], izinli: set[str]) -> list[int]:
    if not tahtalar or len(set(tahtalar)) != len(tahtalar) or not set(tahtalar) <= izinli:
        raise DosyaHatasi('Geçersiz tahta seçimi.')
    boyut = yol.stat().st_size
    if not 0 < boyut <= AZAMI:
        raise DosyaHatasi('Dosya 95 MB sınırını aşıyor veya boş.')
    tur = tur_bul(yol)
    if not tur:
        raise DosyaHatasi('Desteklenmeyen dosya türü.')
    yedek_ad = guvenli_ad(ad)
    temiz_ad = yedek_ad
    # Yanıltıcı uzantıyla açılmaması için gerçek imzanın uzantısını kullan.
    if not temiz_ad.lower().endswith('.' + tur):
        temiz_ad = guvenli_ad(Path(temiz_ad).stem) + '.' + tur
    kok = AYAR.tahta_dosya_yedek
    kok.mkdir(parents=True, exist_ok=True)
    govde = f"{guvenli_ad(k['ad_soyad'])}_{zaman.simdi():%Y-%m-%d_%H%M}_{yedek_ad}"
    hedef = kok / govde
    sira = 2
    while hedef.exists():
        hedef = kok / f'{Path(govde).stem}_{sira}{Path(govde).suffix}'
        sira += 1
    gecici = kok / f'.{uuid.uuid4().hex}.tmp'
    try:
        shutil.copyfile(yol, gecici)
        os.replace(gecici, hedef)
        satirlar = []
        for tahta in tahtalar:
            cur = conn.execute(
                'INSERT INTO tahta_dosya (ogretmen_id, tahta, dosya_adi, tur, boyut, yedek_yol, durum, zaman) '
                'VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (k['id'], tahta, temiz_ad, tur, boyut, str(hedef), 'sirada', zaman.simdi_str()),
            )
            satirlar.append(cur.lastrowid)
        conn.commit()
        return satirlar
    except Exception:
        gecici.unlink(missing_ok=True)
        conn.rollback()
        raise


def sure_doldur(conn: sqlite3.Connection) -> None:
    esik = (zaman.simdi() - timedelta(hours=24)).strftime(zaman.BICIM)
    conn.execute("UPDATE tahta_dosya SET durum='suresi_doldu' WHERE durum IN ('sirada','hata') AND zaman <= ?", (esik,))
    conn.commit()


def bekleyenler(conn: sqlite3.Connection) -> list[dict]:
    sure_doldur(conn)
    return [dict(r) for r in conn.execute(
        "SELECT t.id, t.tahta, t.dosya_adi, t.boyut, t.zaman, k.ad_soyad AS ogretmen "
        "FROM tahta_dosya t JOIN kullanici k ON k.id=t.ogretmen_id WHERE t.durum IN ('sirada','hata') ORDER BY t.id LIMIT 100"
    )]


def sonuc(conn: sqlite3.Connection, id_: int, durum: str, hata: str = '') -> bool:
    if durum not in ('gonderildi', 'hata', 'sirada'):
        raise DosyaHatasi('Geçersiz durum.')
    sure_doldur(conn)
    cur = conn.execute(
        "UPDATE tahta_dosya SET durum=?, deneme=deneme+1, son_hata=?, gonderim_zamani=? "
        "WHERE id=? AND durum IN ('sirada','hata')",
        (durum, hata[:200], zaman.simdi_str() if durum == 'gonderildi' else None, id_),
    )
    conn.commit()
    return cur.rowcount > 0
