import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.requests import Request
from starlette.datastructures import FormData

import db
import uzaktan_yonetim


def _istek(accept=None, istemci=("10.1.2.3", 5555)):
    headers = []
    if accept is not None:
        headers.append((b"accept", accept.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/admin/uzaktan/yoklama-ac",
        "headers": headers,
        "client": istemci,
    }
    return Request(scope)


class _GeciciDB(unittest.TestCase):
    """Üretim DB'sine (veri/yoklama_pano.db) ASLA dokunmaz."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        yama = patch.object(db, "DB_YOLU", Path(self._tmp.name) / "test.db")
        yama.start()
        self.addCleanup(yama.stop)
        db.semayi_kur()

    def _satirlar(self):
        conn = db.baglanti()
        try:
            return [dict(r) for r in conn.execute("SELECT * FROM uzaktan_denetim")]
        finally:
            conn.close()


class TestDogrulaYonlendirme(_GeciciDB):
    def test_html_isteginde_303_giris(self):
        req = _istek(accept="text/html,application/xhtml+xml,*/*;q=0.8")
        with patch("auth.dogrula", return_value=False):
            with self.assertRaises(HTTPException) as ctx:
                uzaktan_yonetim._dogrula(req)
        self.assertEqual(ctx.exception.status_code, 303)
        self.assertEqual(ctx.exception.headers["Location"], "/giris")

    def test_json_ve_accept_yoksa_401(self):
        for accept in ("application/json", None):
            with self.subTest(accept=accept):
                req = _istek(accept=accept)
                with patch("auth.dogrula", return_value=False):
                    with self.assertRaises(HTTPException) as ctx:
                        uzaktan_yonetim._dogrula(req)
                self.assertEqual(ctx.exception.status_code, 401)

    def test_gecerli_oturumda_hata_yok(self):
        with patch("auth.dogrula", return_value=True):
            uzaktan_yonetim._dogrula(_istek(accept="text/html"))


class TestDenetimKaydi(_GeciciDB):
    def _calistir(self, req):
        async def sahte_eylem(t, form):
            return {"tahta": t["ad"], "basarili": t["ad"] == "9-A", "detay": "x"}

        form = FormData([
            ("tahta", "9-A"),
            ("tahta", "9-B"),
            ("url", "http://gizli.example/?q=1"),
        ])
        req.form = AsyncMock(return_value=form)
        tahtalar = [
            {"ad": "9-A", "ip": "1.1.1.1", "kullanici": "ogretmen"},
            {"ad": "9-B", "ip": "1.1.1.2", "kullanici": "ogretmen"},
            {"ad": "10-A", "ip": "1.1.1.3", "kullanici": "ogretmen"},
        ]
        with patch("uzaktan_yonetim._dogrula"), \
             patch("tahta_kaydi.tahtalari_yukle", return_value=tahtalar), \
             patch("uzaktan_yonetim.tum_durumlar", new_callable=AsyncMock, return_value=[]), \
             patch.object(uzaktan_yonetim.templates, "TemplateResponse", return_value="YANIT") as tr:
            yanit = asyncio.run(
                uzaktan_yonetim._eylem_calistir_ve_render(req, sahte_eylem, "web_ac")
            )
        return yanit, tr

    def test_bir_satir_dogru_alanlarla(self):
        yanit, _ = self._calistir(_istek())
        self.assertEqual(yanit, "YANIT")
        satirlar = self._satirlar()
        self.assertEqual(len(satirlar), 1)
        s = satirlar[0]
        self.assertEqual(s["eylem"], "web_ac")
        self.assertIn("+03:00", s["zaman"])
        self.assertEqual(s["tahtalar"], "9-A,9-B")
        self.assertEqual(s["sonuc"], "9-A:ok,9-B:hata")
        self.assertEqual(s["istemci_ip"], "10.1.2.3")
        for deger in s.values():
            self.assertNotIn("gizli.example", str(deger))

    def test_secim_yok(self):
        async def sahte_eylem(t, form):
            raise AssertionError("çağrılmamalı")

        req = _istek()
        req.form = AsyncMock(return_value=FormData([("url", "http://gizli.example")]))
        with patch("uzaktan_yonetim._dogrula"), \
             patch("tahta_kaydi.tahtalari_yukle", return_value=[{"ad": "9-A"}]), \
             patch("uzaktan_yonetim.tum_durumlar", new_callable=AsyncMock, return_value=[]), \
             patch.object(uzaktan_yonetim.templates, "TemplateResponse", return_value="YANIT"):
            asyncio.run(uzaktan_yonetim._eylem_calistir_ve_render(req, sahte_eylem, "ekran_karart"))
        s = self._satirlar()[0]
        self.assertEqual(s["tahtalar"], "")
        self.assertEqual(s["sonuc"], "secim_yok")

    def test_istemci_yoksa_ip_bos(self):
        req = _istek(istemci=None)
        uzaktan_yonetim._denetim_yaz(req, "chrome_kapat", [{"tahta": "9-A", "basarili": True}])
        self.assertIsNone(self._satirlar()[0]["istemci_ip"])

    def test_db_hatasi_eylemi_bozmaz(self):
        with patch("db.baglanti", side_effect=RuntimeError("db yok")):
            # _dogrula yamalı olduğundan db.baglanti yalnızca _denetim_yaz'da çağrılır
            yanit, _ = self._calistir(_istek())
        self.assertEqual(yanit, "YANIT")


if __name__ == "__main__":
    unittest.main()
