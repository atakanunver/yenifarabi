"""Panel duvar kağıdı listesi ve dosya ucu (panel_duvar.py)."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

import menu
import panel_duvar


class TestPanelDuvar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dizin = Path(self.tmp.name)
        for ad in ("b.jpg", "a.PNG", "c.webp", "not.txt"):
            (self.dizin / ad).write_bytes(b"x")
        (self.dizin / "alt").mkdir()
        (self.dizin / "alt" / "d.jpg").write_bytes(b"x")
        yama = mock.patch.object(panel_duvar, "DIZIN", self.dizin)
        yama.start()
        self.addCleanup(yama.stop)
        panel_duvar._onbellek.clear()
        self.addCleanup(panel_duvar._onbellek.clear)
        self.addCleanup(self.tmp.cleanup)

    def test_liste_yalniz_resimler_sirali(self):
        liste = panel_duvar.liste()
        self.assertEqual([d["ad"] for d in liste], ["a.PNG", "b.jpg", "c.webp"])
        self.assertRegex(liste[0]["url"], r"^/panel-duvar/a\.PNG\?v=\d+$")

    def test_klasor_yoksa_bos(self):
        with mock.patch.object(panel_duvar, "DIZIN", self.dizin / "yok"):
            panel_duvar._onbellek.clear()
            self.assertEqual(panel_duvar.liste(), [])

    def test_dosya_ucu(self):
        yanit = asyncio.run(panel_duvar.panel_duvar("b.jpg"))
        self.assertEqual(Path(yanit.path), self.dizin / "b.jpg")
        self.assertIn("max-age", yanit.headers["cache-control"])

    def test_listede_olmayan_ad_404(self):
        for ad in ("not.txt", "../b.jpg", "alt/d.jpg", "d.jpg", "yok.jpg"):
            with self.assertRaises(HTTPException) as h:
                asyncio.run(panel_duvar.panel_duvar(ad))
            self.assertEqual(h.exception.status_code, 404, ad)

    def test_ozel_karakterli_ad_url_kodlanir(self):
        (self.dizin / "Gökyüzü #1'.jpg").write_bytes(b"x")
        d = next(d for d in panel_duvar.liste() if d["ad"].startswith("Gökyüzü"))
        self.assertIn("G%C3%B6ky%C3%BCz%C3%BC%20%231%27.jpg", d["url"])

    def test_sembolik_bag_sunulmaz(self):
        (self.dizin / "bag.jpg").symlink_to(self.dizin / "alt" / "d.jpg")
        with self.assertRaises(HTTPException):
            asyncio.run(panel_duvar.panel_duvar("bag.jpg"))

    def test_menu_agacinda(self):
        self.assertEqual([d["ad"] for d in menu.menu_agaci("/")["duvar_kagitlari"]], ["a.PNG", "b.jpg", "c.webp"])


if __name__ == "__main__":
    unittest.main()
