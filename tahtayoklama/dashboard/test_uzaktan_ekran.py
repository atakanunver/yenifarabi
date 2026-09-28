import asyncio
import io
import unittest
from unittest.mock import AsyncMock, patch
from PIL import Image
from fastapi import HTTPException
from fastapi.requests import Request

import uzaktan_yonetim
import ssh_istemci


class TestUzaktanEkran(unittest.TestCase):
    def test_gorsel_optimize_et_resizing(self):
        # 1920x1080 bir görsel oluştur
        img = Image.new("RGBA", (1920, 1080), color=(255, 0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        ham_bayt = buf.getvalue()

        opt_bayt, mime, w, h = uzaktan_yonetim._gorsel_optimize_et(ham_bayt, maks_genislik=1280, kalite=75)
        self.assertEqual(mime, "image/jpeg")
        self.assertEqual(w, 1280)
        self.assertEqual(h, 720)
        self.assertTrue(len(opt_bayt) > 0)
        self.assertTrue(opt_bayt.startswith(b"\xff\xd8\xff"))

    def test_gorsel_optimize_et_kucuk_gorsel(self):
        # Zaten küçük (800x600) bir görsel genişletilmemeli
        img = Image.new("RGB", (800, 600), color=(0, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        ham_bayt = buf.getvalue()

        opt_bayt, mime, w, h = uzaktan_yonetim._gorsel_optimize_et(ham_bayt, maks_genislik=1280)
        self.assertEqual(w, 800)
        self.assertEqual(h, 600)
        self.assertEqual(mime, "image/jpeg")

    def test_gorsel_optimize_et_bozuk_veri(self):
        bozuk = b"bu bir resim degil"
        opt, mime, w, h = uzaktan_yonetim._gorsel_optimize_et(bozuk)
        self.assertEqual(opt, bozuk)
        self.assertIsNone(w)
        self.assertIsNone(h)

    def test_ekran_goruntusu_al_hizli_basarili(self):
        img = Image.new("RGB", (1280, 720), color=(0, 0, 255))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        sahte_jpeg = buf.getvalue()

        tahta = {"ad": "9-A", "ip": "192.168.23.245", "kullanici": "ogretmen"}

        async def run_test():
            with patch("ssh_istemci.komut_calistir", new_callable=AsyncMock) as mock_ssh:
                mock_ssh.return_value = ssh_istemci.SSHSonuc(True, sahte_jpeg, b"")
                ok, data, err, w, h = await uzaktan_yonetim._ekran_goruntusu_al(tahta)
                self.assertTrue(ok)
                self.assertEqual(err, "")
                self.assertEqual(w, 1280)
                self.assertEqual(h, 720)
                self.assertTrue(len(data) > 0)

        asyncio.run(run_test())

    def test_ekran_goruntusu_al_ulasilamaz(self):
        tahta = {"ad": "11-B", "ip": "192.168.23.233", "kullanici": "ogretmen"}

        async def run_test():
            with patch("ssh_istemci.komut_calistir", new_callable=AsyncMock) as mock_ssh, \
                 patch("ssh_istemci.x_ortamini_kesfet", new_callable=AsyncMock) as mock_x:
                mock_ssh.return_value = ssh_istemci.SSHSonuc(False, b"", b"Connection refused")
                mock_x.return_value = None

                ok, data, err, w, h = await uzaktan_yonetim._ekran_goruntusu_al(tahta)
                self.assertFalse(ok)
                self.assertIn("ulaşılamıyor", err.lower())

        asyncio.run(run_test())

    def test_route_unauthenticated(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/admin/uzaktan/ekran-goruntusu/9-A",
            "headers": [],
        }
        req = Request(scope)

        async def run_test():
            with patch("uzaktan_yonetim._dogrula", side_effect=HTTPException(401, "Oturum geçersiz.")):
                with self.assertRaises(HTTPException) as ctx:
                    await uzaktan_yonetim.ekran_goruntusu_route(req, "9-A")
                self.assertEqual(ctx.exception.status_code, 401)

        asyncio.run(run_test())

    def test_route_gecersiz_tahta(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/admin/uzaktan/ekran-goruntusu/olmayan-tahta",
            "headers": [],
        }
        req = Request(scope)

        async def run_test():
            with patch("uzaktan_yonetim._dogrula"):
                with self.assertRaises(HTTPException) as ctx:
                    await uzaktan_yonetim.ekran_goruntusu_route(req, "olmayan-tahta")
                self.assertEqual(ctx.exception.status_code, 404)

        asyncio.run(run_test())

    def test_route_basarili_json_ve_raw(self):
        img = Image.new("RGB", (1280, 720), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        sahte_jpeg = buf.getvalue()

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/admin/uzaktan/ekran-goruntusu/9-A",
            "headers": [],
        }
        req = Request(scope)

        async def run_test():
            with patch("uzaktan_yonetim._dogrula"), \
                 patch("uzaktan_yonetim._ekran_goruntusu_al", new_callable=AsyncMock) as mock_al:
                mock_al.return_value = (True, sahte_jpeg, "", 1280, 720)

                # 1. JSON yanıtı testi
                res_json = await uzaktan_yonetim.ekran_goruntusu_route(req, "9-A", ham=0)
                self.assertEqual(res_json.status_code, 200)
                import json
                body = json.loads(res_json.body.decode())
                self.assertTrue(body["basarili"])
                self.assertEqual(body["tahta"], "9-A")
                self.assertTrue(body["gorsel"].startswith("data:image/jpeg;base64,"))
                self.assertEqual(body["genislik"], 1280)
                self.assertEqual(body["yukseklik"], 720)

                # 2. Raw JPEG yanıtı testi
                res_raw = await uzaktan_yonetim.ekran_goruntusu_route(req, "9-A", ham=1)
                self.assertEqual(res_raw.status_code, 200)
                self.assertEqual(res_raw.media_type, "image/jpeg")
                self.assertEqual(res_raw.body, sahte_jpeg)

        asyncio.run(run_test())

    def test_route_ham_hata_html(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/admin/uzaktan/ekran-goruntusu/9-A",
            "headers": [],
        }
        req = Request(scope)

        async def run_test():
            with patch("uzaktan_yonetim._dogrula"), \
                 patch("uzaktan_yonetim._ekran_goruntusu_al", new_callable=AsyncMock) as mock_al:
                mock_al.return_value = (False, b"", "Tahtaya ulaşılamıyor.", None, None)

                # ham=1 iken HTML hata sayfası dönmeli
                res = await uzaktan_yonetim.ekran_goruntusu_route(req, "9-A", ham=1)
                self.assertEqual(res.status_code, 502)
                self.assertIn("text/html", res.media_type)
                self.assertIn("Ekran Görüntüsü Alınamadı", res.body.decode())

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
