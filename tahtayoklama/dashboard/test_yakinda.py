"""yakinda.py: yer tutucu bölümler ve eski /kazanim-rapor yönlendirmesi."""
import asyncio
import unittest

from starlette.requests import Request

import kazanim_rapor
import menu
import yakinda


def _istek(yol, sorgu=b""):
    return Request({
        "type": "http", "method": "GET", "path": yol, "root_path": "", "scheme": "http",
        "server": ("farabi.local", 8010), "query_string": sorgu,
        "headers": [(b"host", b"farabi.local")], "client": ("127.0.0.1", 5555),
    })


class TestYakinda(unittest.TestCase):
    def test_menudeki_b_yollari_tanimli(self):
        yollar = {f"/b/{ad}" for ad in yakinda.BOLUMLER}
        for o in [s for a in menu.ALANLAR for s in a["sayfalar"]] + menu.AYARLAR:
            if o.get("href", "").startswith("/b/"):
                self.assertIn(o["href"], yollar, o["href"])

    def test_oturumsuz_giris_sayfasina(self):
        for ad in yakinda.BOLUMLER:
            fn = yakinda._sayfa_olustur(ad)
            r = asyncio.run(fn(_istek(f"/b/{ad}")))
            self.assertEqual(r.status_code, 303)
            self.assertEqual(r.headers["location"], "/giris")

    def test_eski_kazanim_adresi_yonlenir(self):
        r = asyncio.run(kazanim_rapor.kazanim_rapor_eski_yol(_istek("/kazanim-rapor", b"sinif=9-A")))
        self.assertEqual(r.status_code, 308)
        self.assertEqual(r.headers["location"], "/kazanim?sinif=9-A")


if __name__ == "__main__":
    unittest.main()
