"""app.py::panel_git — harici panellere şifresiz geçiş (TestClient yok: rota doğrudan çağrılır)."""

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException

import app as app_modulu
import menu


class _Baglanti:
    def close(self):
        pass


def _cagir(ad, oturum=True, kimlik=None):
    with tempfile.TemporaryDirectory() as d, \
            mock.patch.object(app_modulu.db, "baglanti", lambda: _Baglanti()), \
            mock.patch.object(app_modulu.auth, "dogrula", lambda r, c: oturum), \
            mock.patch.object(app_modulu, "__file__", str(Path(d) / "app.py")):
        if kimlik is not None:
            (Path(d) / "config").mkdir()
            (Path(d) / "config" / "panel_giris.json").write_text(json.dumps(kimlik), encoding="utf-8")
        return asyncio.run(app_modulu.panel_git(None, ad))


class TestPanelGit(unittest.TestCase):
    def test_kimlik_adrese_gomulur_ozel_karakter_kodlanir(self):
        r = _cagir("pano", kimlik={"kiosk": {"kullanici": "admin", "sifre": "a:b@c/d"}})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "http://admin:a%3Ab%40c%2Fd@kiosk.local:9100/pano")
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_oturum_yoksa_girise(self):
        r = _cagir("zil", oturum=False, kimlik={"zil": {"kullanici": "a", "sifre": "b"}})
        self.assertEqual(r.headers["location"], "/giris")

    def test_kimlik_dosyasi_yoksa_duz_adres(self):
        self.assertEqual(_cagir("zil").headers["location"], menu.ZIL_PANELI)

    def test_bilinmeyen_panel_404(self):
        with self.assertRaises(HTTPException) as h:
            _cagir("yok")
        self.assertEqual(h.exception.status_code, 404)

    def test_menu_dogrudan_adrese_degil_rotaya_gider(self):
        hrefler = {o["ad"]: o["href"] for o in menu.MENU if "href" in o}
        for ad, k in (("Zil paneli", "zil"), ("Bilgehan Paneli", "bilgehan"), ("Kiosk Paneli", "kiosk"), ("Pano Paneli", "pano")):
            self.assertEqual(hrefler[ad], f"/panel-git/{k}")


if __name__ == "__main__":
    unittest.main()
