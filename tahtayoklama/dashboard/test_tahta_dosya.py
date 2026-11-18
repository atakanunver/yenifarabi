"""Tahta dosyası aktarımı; ağ ve SSH taklit edilir."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ssh_istemci
import tahta_dosya as td


def _sonuc(basarili=True, stdout=b''):
    return ssh_istemci.SSHSonuc(basarili, stdout, b'')


IS = {'id': 7, 'tahta': '9-A', 'dosya_adi': 'sinav.pdf', 'boyut': 8,
      'ogretmen': 'Öğretmen'}
TAHTA = {'ad': '9-A', 'ip': '192.0.2.10', 'kullanici': 'ogretmen'}


class TestTahtaDosya(unittest.TestCase):
    def test_liste_yalniz_ad_sinif(self):
        from fastapi.requests import Request
        req = Request({'type': 'http', 'headers': [(b'x-tahta-dosya-key', b'test')],
                       'client': ('127.0.0.1', 1)})
        with patch.object(td, 'anahtar', return_value='test'), \
             patch.object(td.tahta_kaydi, 'tahtalari_yukle', return_value=[TAHTA]):
            self.assertEqual(td.tahtalar(req), {'tahtalar': [{'ad': '9-A', 'sinif': '9-A'}]})
        cf = Request({'type': 'http', 'headers': [(b'x-tahta-dosya-key', b'test'), (b'cf-ray', b'x')],
                      'client': ('127.0.0.1', 1)})
        with patch.object(td, 'anahtar', return_value='test'), self.assertRaises(Exception) as hata:
            td.tahtalar(cf)
        self.assertEqual(hata.exception.status_code, 404)

    def test_aktarma_ve_bildirim(self):
        async def calistir():
            with tempfile.TemporaryDirectory() as dizin:
                kaynak = Path(dizin) / 'f'; kaynak.write_bytes(b'%PDF-1.4')
                is_ = {**IS, 'boyut': kaynak.stat().st_size}
                komut = AsyncMock(side_effect=[_sonuc(stdout='/home/ogretmen/Masaüstü/Gelen Dosyalar'.encode()),
                                               _sonuc(False), _sonuc(), _sonuc()])
                with patch.object(td.ssh_istemci, 'komut_calistir', komut), \
                     patch.object(td.ssh_istemci, 'scp_gonder', new_callable=AsyncMock, return_value=_sonuc()) as scp, \
                     patch.object(td.ssh_istemci, 'x_ortamini_kesfet', new_callable=AsyncMock,
                                  return_value=(':0', '', '1000')), \
                     patch.object(td, '_istek', return_value=kaynak):
                    self.assertEqual(await td._gonder(is_, TAHTA), ('gonderildi', ''))
                self.assertTrue(scp.called)
                self.assertIn('notify-send', komut.call_args.args[2])
                self.assertFalse(kaynak.exists())
        asyncio.run(calistir())

    def test_kapali_tahta_sirada_kalir(self):
        async def calistir():
            with patch.object(td.ssh_istemci, 'komut_calistir', new_callable=AsyncMock,
                              return_value=_sonuc(False)):
                self.assertEqual(await td._gonder(IS, TAHTA), ('sirada', 'Tahtaya erişilemedi.'))
        asyncio.run(calistir())

    def test_bir_hata_digerini_durdurmaz(self):
        async def calistir():
            sonuc = []
            def istek(yol, govde=None):
                if yol == '/bekleyen':
                    return {'dosyalar': [IS, {**IS, 'id': 8}]}
                sonuc.append((yol, govde))
            with patch.object(td, '_istek', side_effect=istek), \
                 patch.object(td.tahta_kaydi, 'tahtalari_yukle', return_value=[TAHTA]), \
                 patch.object(td.uzaktan_yonetim, '_denetim_yaz'), \
                 patch.object(td, '_gonder', new_callable=AsyncMock,
                              side_effect=[OSError('kapali'), ('gonderildi', '')]):
                await td.bir_tur()
            self.assertEqual(len(sonuc), 2)
            self.assertEqual(sonuc[0][1]['durum'], 'sirada')
            self.assertEqual(sonuc[1][1]['durum'], 'gonderildi')
        asyncio.run(calistir())
