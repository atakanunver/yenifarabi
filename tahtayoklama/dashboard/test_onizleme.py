"""Önizleme modu: DB yolu ortamdan, değiştiren istekler 403."""

import asyncio
import importlib
import os
import unittest
from pathlib import Path
from unittest import mock

from starlette.requests import Request
from starlette.responses import PlainTextResponse

import app
import db


def _istek(method, yol):
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http", "method": method, "path": yol, "headers": [],
        "query_string": b"", "client": ("127.0.0.1", 5000),
    }
    return Request(scope, receive)


class TestOnizleme(unittest.TestCase):
    def test_db_yolu_ortamdan(self):
        try:
            with mock.patch.dict(os.environ, {"FARABI_PANEL_DB": "/tmp/x.db"}):
                importlib.reload(db)
                self.assertEqual(db.DB_YOLU, Path("/tmp/x.db"))
            with mock.patch.dict(os.environ):
                os.environ.pop("FARABI_PANEL_DB", None)
                importlib.reload(db)
                self.assertEqual(
                    db.DB_YOLU, Path(db.__file__).resolve().parent / "veri" / "yoklama_pano.db")
        finally:
            importlib.reload(db)

    def _gec(self, method, yol):
        async def sonraki(_r):
            return PlainTextResponse("tamam")

        return asyncio.run(app.onizleme_koruma(_istek(method, yol), sonraki))

    def test_onizlemede_post_reddedilir(self):
        with mock.patch.object(app, "ONIZLEME", True):
            r = self._gec("POST", "/admin/okul-verisi/personel")
            self.assertEqual(r.status_code, 403)
            self.assertIn("Önizlemede değişiklik kapalı", r.body.decode())
            self.assertEqual(self._gec("POST", "/giris").status_code, 200)
            self.assertEqual(self._gec("POST", "/cikis").status_code, 200)
            self.assertEqual(self._gec("GET", "/").status_code, 200)

    def test_canlida_post_gecer(self):
        with mock.patch.object(app, "ONIZLEME", False):
            self.assertEqual(self._gec("POST", "/admin/okul-verisi/personel").status_code, 200)


if __name__ == "__main__":
    unittest.main()
