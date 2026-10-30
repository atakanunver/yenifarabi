import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException
from fastapi.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db  # noqa: E402
import duyuru  # noqa: E402
import tahta_api  # noqa: E402
import tahta_istemci as ti  # noqa: E402


class TestDuyuru(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        gecici = Path(self.tmp.name)
        self.yamalar = [
            mock.patch.object(db, "DB_YOLU", gecici / "t.db"),
            mock.patch.object(duyuru, "SES_DIZINI", gecici / "ses"),
        ]
        for y in self.yamalar:
            y.start()
        db.semayi_kur()
        self.conn = db.baglanti()
        self.conn.execute("INSERT INTO siniflar (id, ad, aktif) VALUES (1, '9-A', 1)")
        self.conn.execute(
            "INSERT INTO tahtalar (ad, ip, ssh_kullanici, sinif_id, aktif) "
            "VALUES ('9-A', '1.2.3.4', 'ogretmen', 1, 1), ('fenlab', '1.2.3.5', 'ogretmen', NULL, 1)"
        )
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        for y in self.yamalar:
            y.stop()
        self.tmp.cleanup()

    def test_mesaj_dogrulama(self):
        with self.assertRaises(duyuru.DuyuruHatasi):
            duyuru.mesaj_temizle("   ")
        with self.assertRaises(duyuru.DuyuruHatasi):
            duyuru.mesaj_temizle("x" * 301)
        self.assertEqual(duyuru.mesaj_temizle(" Selam\x00 "), "Selam")

    def test_hedef_suzme(self):
        duyuru.olustur(self.conn, ["9-A"], "yalniz 9-A", "bilgi", False, None)
        duyuru.olustur(self.conn, ["tum-okul"], "herkes", "bilgi", False, None)
        a = duyuru.tahta_icin(self.conn, "9-A", 0)["duyurular"]
        f = duyuru.tahta_icin(self.conn, "fenlab", 0)["duyurular"]
        self.assertEqual([d["mesaj"] for d in a], ["yalniz 9-A", "herkes"])
        self.assertEqual([d["mesaj"] for d in f], ["herkes"])

    def test_sinif_hedefi_tahtanin_sinifina_gider(self):
        duyuru.olustur(self.conn, ["9-A"], "sinif", "bilgi", False, None)
        self.conn.execute("UPDATE tahtalar SET ad = 'tahta-x' WHERE ad = '9-A'")
        self.conn.commit()
        self.assertEqual(len(duyuru.tahta_icin(self.conn, "tahta-x", 0)["duyurular"]), 1)

    def test_son_id_ve_iptal(self):
        i = duyuru.olustur(self.conn, ["tum-okul"], "a", "acil", False, None)[0]
        self.assertEqual(duyuru.tahta_icin(self.conn, "9-A", i)["duyurular"], [])
        self.assertEqual(duyuru.hepsini_iptal_et(self.conn), 1)
        yanit = duyuru.tahta_icin(self.conn, "9-A", 0)
        self.assertEqual(yanit["duyurular"], [])
        self.assertEqual(yanit["iptal"], [i])

    def test_sessiz_tip_ses_yazmaz_ve_ses_yedegi(self):
        i = duyuru.olustur(self.conn, ["9-A"], "x", "bilgi", True, b"RIFFxxxx")[0]
        self.assertIsNone(duyuru.ses_yolu(self.conn, "9-A", i))
        j = duyuru.olustur(self.conn, ["9-A"], "y", "idare", True, None)[0]
        self.assertIsNone(duyuru.ses_yolu(self.conn, "9-A", j))
        d = duyuru.tahta_icin(self.conn, "9-A", j - 1)["duyurular"][0]
        self.assertTrue(d["sesli_oku"])
        self.assertFalse(d["ses"])

    def test_ses_yalniz_hedefteki_tahtaya(self):
        i = duyuru.olustur(self.conn, ["9-A"], "x", "acil", True, b"RIFFxxxx")[0]
        self.assertIsNotNone(duyuru.ses_yolu(self.conn, "9-A", i))
        self.assertIsNone(duyuru.ses_yolu(self.conn, "fenlab", i))

    def test_tts_ulasilamazsa_none(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError):
            self.assertIsNone(duyuru.tts_uret("merhaba"))


class TestDuyuruUcu(unittest.TestCase):
    """httpx yok → TestClient yerine Request elle kurulur (bkz. test_tahta_api)."""

    def _istek(self):
        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        scope = {"type": "http", "method": "GET", "path": "/x", "headers": [],
                 "query_string": b"", "client": ("192.168.23.245", 5000)}
        return Request(scope, receive)

    def test_tahta_ucu_token_ister(self):
        with self.assertRaises(HTTPException) as e:
            asyncio.run(tahta_api.duyuru_al(self._istek()))
        self.assertEqual(e.exception.status_code, 401)
        with self.assertRaises(HTTPException) as e:
            asyncio.run(tahta_api.duyuru_ses(self._istek(), 1))
        self.assertEqual(e.exception.status_code, 401)


class TestIstemciDuyuru(unittest.TestCase):
    """tahta_istemci.duyuru_cek: kimlik ilerler, pencere açılamasa da döngü düşmez."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.yamalar = [
            mock.patch.object(ti, "DUYURU_DIR", Path(self.tmp.name) / "d"),
            mock.patch.object(ti, "DURUM_DOSYASI", Path(self.tmp.name) / "durum.json"),
        ]
        for y in self.yamalar:
            y.start()

    def tearDown(self):
        for y in self.yamalar:
            y.stop()
        self.tmp.cleanup()

    def test_kimlik_ilerler_ve_pencere_acilir(self):
        yanit = {"duyurular": [{"id": 5, "mesaj": "m", "tip": "bilgi", "sesli_oku": False,
                                "ses": False, "sure_sn": 10, "okuma_sayisi": 0}], "iptal": []}
        durum = {}
        with mock.patch.object(ti, "istek", return_value=(200, {}, json.dumps(yanit).encode())), \
                mock.patch.object(ti, "duyuru_ac") as ac:
            ti.duyuru_cek({"sunucu": "x", "token": "t"}, durum)
        self.assertEqual(durum["duyuru_son_id"], 5)
        ac.assert_called_once()

    def test_acma_hatasi_dongu_dusurmez(self):
        yanit = {"duyurular": [{"id": 6}], "iptal": []}
        durum = {}
        with mock.patch.object(ti, "istek", return_value=(200, {}, json.dumps(yanit).encode())), \
                mock.patch.object(ti, "duyuru_ac", side_effect=OSError("x")):
            ti.duyuru_cek({"sunucu": "x", "token": "t"}, durum)
        self.assertEqual(durum["duyuru_son_id"], 6)

    def test_sunucu_yoksa_sessiz(self):
        with mock.patch.object(ti, "istek", return_value=(0, {}, b"")):
            ti.duyuru_cek({"sunucu": "x", "token": "t"}, {})


if __name__ == "__main__":
    unittest.main()
