import asyncio
import io
from unittest import mock

from fastapi import HTTPException
from PIL import Image

import gorsel
import gorsel_panel as panel
from test_gorsel import _istek, _Ortak, _png


class TestYerelPanel(_Ortak):
    def setUp(self):
        super().setUp()
        self.arka = gorsel.arsivle('serbest', _png())
        panel._is.update(durum='bosta', dosya=None)

    def istek(self, **form):
        req = _istek(accept='application/json')
        req.form = mock.AsyncMock(return_value=form)
        return req

    def dosyalar(self):
        return {str(p.relative_to(self.gecici)): p.read_bytes() for p in self.gecici.rglob('*') if p.is_file()}

    def test_auth_once(self):
        async def kos():
            for fonk in (panel.gorsel_onizle, panel.gorsel_kaydet):
                req = self.istek(dosya=self.arka.name, ogrenciler='')
                with self.assertRaises(HTTPException):
                    await fonk(req)
                req.form.assert_not_awaited()
        asyncio.run(kos())

    def test_onizle_kaydet_ve_sinirlar(self):
        async def kos():
            with mock.patch('uzaktan_yonetim._dogrula'), mock.patch('uzaktan_yonetim._denetim_yaz') as den, \
                 mock.patch.object(gorsel, 'ai_arka_plan') as ai, \
                 mock.patch.object(gorsel, 'prompt_zenginlestir') as zengin, \
                 mock.patch.object(gorsel, 'uretim_hakki_al') as kota, \
                 mock.patch.object(panel, '_kazananlar', new_callable=mock.AsyncMock) as kazanan, \
                 mock.patch('urllib.request.urlopen') as url:
                once = self.dosyalar()
                for metin in ('', 'GizliSentinel;9-A', '\n'.join(['Örnek;9-A'] * 24), 'Başka;10-B'):
                    r = await panel.gorsel_onizle(self.istek(dosya=self.arka.name, ogrenciler=metin))
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(r.headers['cache-control'], 'no-store')
                    self.assertEqual(Image.open(io.BytesIO(r.body)).size, (1920, 1080))
                    self.assertEqual(self.dosyalar(), once)
                for dosya, metin in ((self.arka.name, 'x'), (self.arka.name, 'x' * 8001),
                                     (self.arka.name, '\n'.join(['x;9-A'] * 25)),
                                     (self.arka.name, 'x' * 200 + ';9-A'), ('../x.png', ''), ('', ''),
                                     ('2026-01-01_0000_serbest.png', '')):
                    for fonk in (panel.gorsel_onizle, panel.gorsel_kaydet):
                        r = await fonk(self.istek(dosya=dosya, ogrenciler=metin))
                        self.assertEqual(r.status_code, 400)
                        self.assertNotIn(b'GizliSentinel', r.body)
                self.assertEqual(self.dosyalar(), once)
                r = await panel.gorsel_kaydet(self.istek(dosya=self.arka.name, ogrenciler='GizliSentinel;9-A'))
                self.assertTrue(r['ok'])
                self.assertEqual(r['mesaj'], 'Görsel arşive kaydedildi.')
                self.assertIsNotNone(gorsel.arsiv_yolu(r['dosya']))
                sonra = self.dosyalar()
                self.assertEqual(len(set(sonra) - set(once)), 1)
                self.assertTrue(all(sonra[k] == v for k, v in once.items()))
                self.assertNotIn('GizliSentinel', str(den.call_args_list))
                for m in (ai, zengin, kota, kazanan, url):
                    m.assert_not_called()
        asyncio.run(kos())

    def test_cizim_hatasi_gizli(self):
        async def kos():
            with mock.patch('uzaktan_yonetim._dogrula'), \
                 mock.patch.object(gorsel, 'liste_karti', side_effect=RuntimeError('GizliSentinel /gizli')):
                r = await panel.gorsel_onizle(self.istek(dosya=self.arka.name, ogrenciler='GizliSentinel;9-A'))
                self.assertEqual(r.status_code, 500)
                self.assertNotIn(b'GizliSentinel', r.body)
                self.assertNotIn(b'/gizli', r.body)
        asyncio.run(kos())

    def test_manuel_uret_ve_durum(self):
        async def kos():
            gorsel.durum_guncelle(aday_arka_plan='aday', onayli_arka_plan='onay', onay_zamani='zaman')
            once = gorsel.durum_oku()
            with mock.patch('uzaktan_yonetim._dogrula'), mock.patch('uzaktan_yonetim._denetim_yaz') as den, \
                 mock.patch.object(gorsel, 'ai_arka_plan', return_value=_png()) as ai:
                panel._is.update(durum='bosta', dosya='eski')
                r = await panel.gorsel_uret(self.istek(tur='manuel', prompt='orman'))
                self.assertTrue(r['ok'])
                self.assertIsNone(panel._is['dosya'])
                await asyncio.gather(*panel._gorevler)
                ai.assert_called_once_with('orman', haftalik=False)
                self.assertIn('manuel-arka-plan', panel._is['dosya'])
                self.assertIsNotNone(gorsel.arsiv_yolu(panel._is['dosya']))
                for k in ('aday_arka_plan', 'onayli_arka_plan', 'onay_zamani'):
                    self.assertEqual(gorsel.durum_oku()[k], once[k])
                self.assertNotIn('GizliSentinel', str((ai.call_args_list, den.call_args_list)))
                panel._is.update(durum='calisiyor', baslangic=__import__('time').monotonic())
                self.assertEqual((await panel.gorsel_uret(self.istek(tur='manuel', prompt='x'))).status_code, 409)
                panel._is.update(durum='bosta', dosya='eski')
                ai.side_effect = RuntimeError('secret')
                await panel.gorsel_uret(self.istek(tur='manuel', prompt='x'))
                await asyncio.gather(*panel._gorevler)
                self.assertEqual(panel._is['durum'], 'hata')
                self.assertIsNone(panel._is['dosya'])
                self.assertNotIn('secret', panel._is['mesaj'])
        asyncio.run(kos())

    def test_haftalik_onizleme_yazmaz(self):
        async def kos():
            once = self.dosyalar()
            with mock.patch('uzaktan_yonetim._dogrula'), \
                 mock.patch.object(gorsel, 'kullanilacak_arka_plan', return_value=self.arka), \
                 mock.patch.object(panel, '_kazananlar', new_callable=mock.AsyncMock, return_value={
                     'maraton': [{'ad_soyad': 'Örnek', 'sinif': '9-A'}]}) as kazanan:
                r = await panel.gorsel_onizleme(self.istek())
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.headers['cache-control'], 'no-store')
                self.assertEqual(Image.open(io.BytesIO(r.body)).size, (1920, 1080))
                kazanan.assert_awaited_once()
                self.assertEqual(self.dosyalar(), once)
        asyncio.run(kos())
