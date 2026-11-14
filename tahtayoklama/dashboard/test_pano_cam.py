"""/yeni: buzlu cam React ders ızgarası kabuğu (2026-11-14, plan
docs/superpowers/plans/2026-11-14-ders-izgarasi-cam-react.md). Şablon bağlamı window.PANO_VERI
olarak basar; React (arayuz/ → static/pano-cam.*) buna bağlanır. `/` değişmez."""
import asyncio
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import app
import auth
import db
import menu
from fastapi.requests import Request


def _istek(yol="/yeni"):
    return Request({"type": "http", "method": "GET", "path": yol, "headers": [], "query_string": b"",
                    "server": ("farabi.local", 80), "scheme": "http", "root_path": ""})


class TestPanoCam(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._eski_db_yolu = db.DB_YOLU
        db.DB_YOLU = Path(self._tmp.name) / "test.db"
        db.semayi_kur()
        conn = db.baglanti()
        conn.execute("INSERT INTO siniflar (id, ad) VALUES (1, '9-A'), (2, '10-A')")
        conn.execute("INSERT INTO tahtalar (id, ad, ip, sinif_id) VALUES (5, 'tahta-9a', '10.0.0.5', 1)")
        conn.execute(
            "INSERT INTO yoklama_onbellek (tarih, sinif, ders_no, durum, yok_isimleri, izinli_isimleri) "
            "VALUES ('2026-11-13', '9-A', 1, 'alindi', '[]', '[\"Ali Veli\"]')")
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_YOLU = self._eski_db_yolu
        self._tmp.cleanup()

    def _html(self):
        async def calistir():
            with patch.object(auth, "oturum_gecerli_mi", return_value=True):
                return await app.pano_cam(_istek(), tarih="2026-11-13")
        return asyncio.run(calistir()).body.decode()

    def _veri(self, html):
        satir = re.search(r"window\.PANO_VERI = (.*?);</script>", html, re.S).group(1)
        return json.loads(satir)

    def test_yeni_oturumsuz_giris_yonlendirir(self):
        yanit = asyncio.run(app.pano_cam(_istek(), tarih=None))
        self.assertEqual(yanit.status_code, 303)
        self.assertEqual(yanit.headers["location"], "/giris")

    def test_sablon_sprite_ve_veri(self):
        html = self._html()
        self.assertIn('id="ik-ev"', html)
        self.assertIn("window.PANO_VERI =", html)
        self.assertRegex(html, r'/static/pano-cam\.js\?v=\d+')
        self.assertRegex(html, r'/static/pano-cam\.css\?v=\d+')
        self.assertNotIn('class="ust-cubuk"', html)

    def test_veri_json_gecerli(self):
        veri = self._veri(self._html())
        self.assertEqual(veri["tarih"], "2026-11-13")
        self.assertEqual(len(veri["menu"]), len(menu.ALANLAR))
        self.assertTrue(all({"ad", "ikon", "href"} <= set(m) for m in veri["menu"]))
        self.assertEqual(veri["acil"]["href"], menu.ACIL["href"])
        self.assertEqual(veri["sinif_tahta"], {"1": 5})
        self.assertEqual([s["ad"] for s in veri["siniflar"]], ["9-A", "10-A"])
        self.assertEqual(veri["ilk_durum"]["satirlar"][0]["izinli_isimleri"], '["Ali Veli"]')

    def test_ana_sayfa_degismedi(self):
        async def calistir():
            with patch.object(auth, "oturum_gecerli_mi", return_value=True):
                return await app.ana_sayfa(_istek("/"), tarih="2026-11-13")
        self.assertEqual(asyncio.run(calistir()).template.name, "pano.html")


if __name__ == "__main__":
    unittest.main()
