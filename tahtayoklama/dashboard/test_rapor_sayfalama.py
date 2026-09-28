"""admin.py::_sayfala + gzip yapılandırma testleri (2026-09-28, dashboard
yük azaltma planı). `_sayfala` saf bir fonksiyon — DB/HTTP gerektirmez.
Gzip testi yalnızca yapılandırma kontrolüdür: `TestClient` KULLANILMAZ
(dashboard venv'inde `httpx` yok, üretim venv'ine paket kurulmaz); gerçek
sıkıştırma deploy sonrası `curl` ile doğrulanır (plan.md)."""

import unittest

from starlette.middleware.gzip import GZipMiddleware

import admin
import app as app_modulu


class TestSayfala(unittest.TestCase):
    def test_bos_liste(self):
        self.assertEqual(admin._sayfala([], None, 100), ([], 1, 1))

    def test_250_satir_100_boyut_ucuncu_sayfa(self):
        satirlar = list(range(250))
        dilim, sayfa, toplam_sayfa = admin._sayfala(satirlar, "3", 100)
        self.assertEqual(toplam_sayfa, 3)
        self.assertEqual(sayfa, 3)
        self.assertEqual(len(dilim), 50)
        self.assertEqual(dilim, satirlar[200:250])

    def test_gecersiz_sayfa_degerleri_bire_duser(self):
        satirlar = list(range(250))
        for deger in ("0", "-5", "abc", None):
            _, sayfa, _ = admin._sayfala(satirlar, deger, 100)
            self.assertEqual(sayfa, 1, f"sayfa={deger!r} icin 1 beklendi")

    def test_araligin_disindaki_sayfa_son_sayfaya_kistirilir(self):
        satirlar = list(range(250))
        dilim, sayfa, toplam_sayfa = admin._sayfala(satirlar, "99", 100)
        self.assertEqual(toplam_sayfa, 3)
        self.assertEqual(sayfa, 3)
        self.assertEqual(dilim, satirlar[200:250])

    def test_tam_bolunen_satir_sayisi(self):
        satirlar = list(range(200))
        dilim, sayfa, toplam_sayfa = admin._sayfala(satirlar, "2", 100)
        self.assertEqual(toplam_sayfa, 2)
        self.assertEqual(sayfa, 2)
        self.assertEqual(dilim, satirlar[100:200])


class TestGzipYapilandirmasi(unittest.TestCase):
    def test_gzip_middleware_ekli(self):
        self.assertTrue(
            any(m.cls is GZipMiddleware for m in app_modulu.app.user_middleware),
            "GZipMiddleware app.user_middleware icinde bulunamadi",
        )


if __name__ == "__main__":
    unittest.main()
