"""veli_mesajlari: sahte HTTP yanıtlarıyla liste, ulaşılamıyor, anahtar yok, yetkisiz."""
import asyncio
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.requests import Request

import veli_mesajlari as vm

MSJ = [
    {"id": 1, "kisi_ad": "Test Veli", "kisi_tur": "veli", "sinif": "9-A", "telefon": "0555***1234",
     "metin": "Merhaba <b>x</b>", "zaman": "2026-10-14 09:00", "cikis_talebi": 0, "okundu": 0},
    {"id": 2, "kisi_ad": None, "kisi_tur": None, "sinif": None, "telefon": "0555***9876",
     "metin": "Çocuğumu alacağım", "zaman": "2026-10-14 08:00", "cikis_talebi": 1, "okundu": 1},
]


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _yanit(obj):
    return _Yanit(json.dumps(obj).encode())


def _istek(yol="/veli-mesajlari", cookie=True):
    basliklar = [(b"cookie", b"oturum=x")] if cookie else []
    return Request({"type": "http", "method": "GET", "path": yol, "headers": basliklar,
                    "query_string": b"", "scheme": "http", "server": ("t", 80), "root_path": ""})


class AnahtarDosyasi(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        self.yol = Path(self.gecici.name) / "sms_panel.json"
        self.p = patch.object(vm, "AYAR_YOLU", self.yol)
        self.p.start()
        vm.onbellegi_sifirla()

    def tearDown(self):
        self.p.stop()
        self.gecici.cleanup()
        vm.onbellegi_sifirla()

    def anahtar_yaz(self):
        self.yol.write_text(json.dumps({"anahtar": "sahte-anahtar"}))


class TestIstemci(AnahtarDosyasi):
    def test_anahtar_yoksa_none_ve_ag_cagrisi_yok(self):
        with patch("urllib.request.urlopen") as u:
            self.assertIsNone(vm.mesajlari_getir())
            self.assertIsNone(vm.sayac_getir())
            u.assert_not_called()

    def test_liste_basarili_ve_baslik(self):
        self.anahtar_yaz()
        with patch("urllib.request.urlopen", return_value=_yanit({"mesajlar": MSJ})) as u:
            self.assertEqual(len(vm.mesajlari_getir(True)), 2)
        istek = u.call_args[0][0]
        self.assertEqual(istek.get_header("X-sms-panel-key"), "sahte-anahtar")
        self.assertIn("okunmamis=1", istek.full_url)
        self.assertLessEqual(u.call_args[1]["timeout"], 3)

    def test_ulasilamiyor_none(self):
        self.anahtar_yaz()
        for hata in (urllib.error.URLError("x"), TimeoutError(), ConnectionRefusedError()):
            with patch("urllib.request.urlopen", side_effect=hata):
                self.assertIsNone(vm.mesajlari_getir())

    def test_bozuk_govde_none(self):
        self.anahtar_yaz()
        with patch("urllib.request.urlopen", return_value=_Yanit(b"<html>")):
            self.assertIsNone(vm.mesajlari_getir())
        with patch("urllib.request.urlopen", return_value=_yanit({"baska": 1})):
            self.assertIsNone(vm.mesajlari_getir())

    def test_sayac_onbellek_30sn(self):
        self.anahtar_yaz()
        with patch("urllib.request.urlopen", return_value=_yanit({"okunmamis": 3, "cikis_talebi_okunmamis": 1})) as u:
            self.assertEqual(vm.sayac_getir(100.0)["okunmamis"], 3)
            vm.sayac_getir(120.0)
            self.assertEqual(u.call_count, 1)
            vm.sayac_getir(131.0)
            self.assertEqual(u.call_count, 2)

    def test_sayac_hata_none_ve_onbellekli(self):
        self.anahtar_yaz()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")) as u:
            self.assertIsNone(vm.sayac_getir(10.0))
            self.assertIsNone(vm.sayac_getir(11.0))
            self.assertEqual(u.call_count, 1)

    def test_okundu_ve_sil_yontemleri(self):
        self.anahtar_yaz()
        with patch("urllib.request.urlopen", side_effect=lambda *a, **k: _yanit({"ok": True})) as u:
            self.assertTrue(vm.okundu_isaretle(5))
            self.assertEqual((u.call_args[0][0].get_method(), u.call_args[0][0].full_url.rsplit("/", 2)[-2:]),
                             ("POST", ["5", "okundu"]))
            self.assertTrue(vm.mesaj_sil(5))
            self.assertEqual(u.call_args[0][0].get_method(), "DELETE")
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            self.assertFalse(vm.mesaj_sil(5))


class TestGoruntu(unittest.TestCase):
    def test_cikis_talebi_ustte_ve_bilinmeyen_numara(self):
        s = vm.goruntule(MSJ)
        self.assertEqual([x["id"] for x in s], [2, 1])
        self.assertTrue(s[0]["cikis"])
        self.assertEqual(s[0]["ad"], "Bilinmeyen numara …9876")
        self.assertEqual(s[1]["ad"], "Test Veli")
        self.assertEqual(s[1]["alt"], "Veli · 9-A")


class TestRota(AnahtarDosyasi):
    def _sayfa(self, oturum_var, **kw):
        with patch("auth.dogrula", return_value=oturum_var):
            return asyncio.run(vm.sayfa(_istek(), **kw))

    def test_yetkisiz_sayfa_girise_yonlendirir(self):
        yanit = self._sayfa(False)
        self.assertEqual((yanit.status_code, yanit.headers["location"]), (303, "/giris"))

    def test_yetkisiz_api_reddedilir(self):
        with patch("auth.dogrula", return_value=False), patch("urllib.request.urlopen") as u:
            for cagri in (vm.api_sayac(_istek()), vm.api_okundu(_istek(), 1), vm.api_sil(_istek(), 1)):
                with self.assertRaises(HTTPException) as h:
                    asyncio.run(cagri)
                self.assertEqual(h.exception.status_code, 401)
            u.assert_not_called()

    def test_liste_sayfasi_ve_kacis(self):
        self.anahtar_yaz()
        with patch("urllib.request.urlopen", return_value=_yanit({"mesajlar": MSJ})):
            html = self._sayfa(True).body.decode()
        self.assertIn("ÇIKIŞ TALEBİ", html)
        self.assertIn("Bilinmeyen numara …9876", html)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)  # metin kaçışlı
        self.assertLess(html.index("Çocuğumu"), html.index("Merhaba"))
        self.assertNotIn("Mesaj servisine ulaşılamıyor", html)

    def test_servis_ulasilamiyor_sayfasi_cokmez(self):
        self.anahtar_yaz()
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
            yanit = self._sayfa(True)
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("Mesaj servisine ulaşılamıyor", yanit.body.decode())

    def test_anahtar_yok_sayfasi_cokmez(self):
        yanit = self._sayfa(True)
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("Mesaj servisine ulaşılamıyor", yanit.body.decode())

    def test_sayac_api_hata_null(self):
        with patch("auth.dogrula", return_value=True):
            yanit = asyncio.run(vm.api_sayac(_istek()))
        self.assertEqual(json.loads(yanit.body), {"okunmamis": None, "cikis_talebi_okunmamis": None})

    def test_okundu_api_servis_yoksa_502(self):
        with patch("auth.dogrula", return_value=True), self.assertRaises(HTTPException) as h:
            asyncio.run(vm.api_okundu(_istek(), 1))
        self.assertEqual(h.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
