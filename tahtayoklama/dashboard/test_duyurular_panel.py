import asyncio
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock

from fastapi.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db
import duyuru
import duyurular_panel as dp
import zil

ZIL = {
    "dersler": [{"no": 1, "baslangic": "08:10", "bitis": "08:50"}],
    "ogle_arasi": {"baslangic": "12:10", "bitis": "13:30"},
    "ders_gunleri": [1, 2, 3, 4, 5],
}


def _istek(path="/duyurular"):
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": path, "headers": [], "query_string": b"",
             "client": ("127.0.0.1", 1), "server": ("farabi.local", 80), "scheme": "http"}
    return Request(scope, receive)


class TestDuyurularPanel(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gecici = Path(self.tmp.name)
        self.yamalar = [
            mock.patch.object(db, "DB_YOLU", self.gecici / "t.db"),
            mock.patch.object(duyuru, "SES_DIZINI", self.gecici / "ses"),
            mock.patch.object(zil, "_zil_yukle", lambda: ZIL),
        ]
        for y in self.yamalar:
            y.start()
        db.semayi_kur()
        self.conn = db.baglanti()

    def tearDown(self):
        self.conn.close()
        for y in self.yamalar:
            y.stop()
        self.tmp.cleanup()

    def test_tahta_gecmisi_cok_hedef_tek_satir(self):
        duyuru.olustur(self.conn, ["11-A", "11-B"], "Merhaba", "bilgi", False, None)
        duyuru.olustur(self.conn, [duyuru.TUM_OKUL], "Toplantı", "idare", False, None)
        duyuru.hepsini_iptal_et(self.conn)
        g = dp.tahta_gecmisi(self.conn)
        self.assertEqual(len(g), 2)
        merhaba = next(x for x in g if x["mesaj"] == "Merhaba")
        self.assertEqual(merhaba["hedefler"].split(", "), ["11-A", "11-B"])
        self.assertEqual(merhaba["durum"], "kapatildi")

    def test_smual_duyurular_gruplar_ve_yoksa_none(self):
        yol = self.gecici / "okul.db"
        with sqlite3.connect(yol) as c:
            c.executescript(
                "CREATE TABLE kullanici (id INTEGER PRIMARY KEY, ad_soyad TEXT);"
                "CREATE TABLE duyuru (id INTEGER PRIMARY KEY, yazar_id INT, baslik TEXT, hedef_tur TEXT,"
                " hedef TEXT, yayin TEXT, bitis TEXT);"
                "INSERT INTO kullanici VALUES (1, 'Atakan');"
                "INSERT INTO duyuru VALUES (1,1,'Takvim','sinif','11-A','2026-11-01 09:00:00','2099-01-01 00:00:00'),"
                " (2,1,'Takvim','sinif','12-A','2026-11-01 09:00:00','2099-01-01 00:00:00'),"
                " (3,1,'Eski','okul',NULL,'2026-01-01 09:00:00','2026-01-02 00:00:00'),"
                " (4,1,'Veli notu','rol','veli','2026-10-01 09:00:00',NULL);"
            )
        d = dp.smual_duyurular(yol)
        self.assertEqual([x["baslik"] for x in d], ["Takvim", "Veli notu"])
        self.assertEqual(d[0]["hedefler"], ["11-A", "12-A"])
        self.assertEqual(d[1]["hedefler"], ["Veliler"])
        self.assertIsNone(dp.smual_duyurular(self.gecici / "yok.db"))

    def test_sonraki_gonderim(self):
        cuma_aksam = datetime(2026, 11, 6, 13, 0, tzinfo=zil.ISTANBUL)
        self.assertEqual(dp.sonraki_gonderim(cuma_aksam), datetime(2026, 11, 9, 8, 50, tzinfo=zil.ISTANBUL))
        sabah = datetime(2026, 11, 9, 8, 52, tzinfo=zil.ISTANBUL)  # yuva içindeyken o yuva
        self.assertEqual(dp.sonraki_gonderim(sabah).hour, 8)

    def test_sayfa_okul_kapaliyken_de_acilir(self):
        with mock.patch("auth.dogrula", return_value=True), \
             mock.patch.object(dp, "pano_cek", return_value=None), \
             mock.patch.object(dp, "smual_duyurular", return_value=None):
            yanit = asyncio.run(dp.duyurular_sayfa(_istek()))
        html = yanit.body.decode()
        self.assertEqual(yanit.status_code, 200)
        self.assertIn("Okul portalına ulaşılamadı", html)
        self.assertIn('action="/duyurular/tahta"', html)

    def test_sayfa_icerik(self):
        pano = {"duyurular": [{"baslik": "MEBİ 3. YKS Denemesi", "metin": "9–15 Kasım · 3 gün kaldı"}],
                "yaklasan_denemeler": [{"baslik": "MEBİ 3. YKS Denemesi", "duzeyler": "11,12",
                                        "durum": "9–15 Kasım · 3 gün kaldı"}]}
        self.conn.execute("INSERT INTO siniflar (ad, aktif) VALUES ('11-A', 1), ('9-A', 1)")
        self.conn.commit()
        with mock.patch("auth.dogrula", return_value=True), \
             mock.patch.object(dp, "pano_cek", return_value=pano), \
             mock.patch.object(dp, "smual_duyurular", return_value=[]):
            html = asyncio.run(dp.duyurular_sayfa(_istek())).body.decode()
        self.assertIn("<td>11-A</td>", html)
        self.assertNotIn("9-A</td>", html)
        self.assertIn("Yayında duyuru yok", html)

    def _gizli(self, icerik='{"duyuru_anahtar": "anahtar-x"}'):
        yol = self.gecici / "gizli.json"
        yol.write_text(icerik, encoding="utf-8")
        return mock.patch.object(dp, "OKUL_GIZLI", yol)

    def test_smual_gonder_anahtarla_rol_duyurusu_yollar(self):
        yakalanan = {}

        def sahte_urlopen(istek, timeout):
            yakalanan["istek"] = istek
            return io.BytesIO(b'{"tamam": true, "id": 7}')

        metin = "Yarın veli toplantısı saat 14:00'te konferans salonunda yapılacaktır, katılımınız önemlidir."
        with self._gizli(), mock.patch("urllib.request.urlopen", sahte_urlopen):
            s = dp.smual_gonder("veli", metin)
        self.assertTrue(s["basarili"])
        self.assertEqual(s["tahta"], "smual.app · Veliler")
        istek = yakalanan["istek"]
        self.assertEqual(istek.get_header("X-duyuru-anahtar"), "anahtar-x")
        govde = json.loads(istek.data)
        self.assertEqual((govde["hedef"], govde["metin"]), ("veli", metin))
        self.assertEqual(len(govde["baslik"]), 60)

    def test_smual_gonder_hata_ve_anahtarsiz(self):
        hata = urllib.error.HTTPError(dp.OKUL_DUYURU_URL, 404, "yok", {}, None)
        with self._gizli(), mock.patch("urllib.request.urlopen", side_effect=hata):
            self.assertFalse(dp.smual_gonder("ogrenci", "x")["basarili"])
        with self._gizli("{}"), mock.patch("urllib.request.urlopen") as u:
            self.assertFalse(dp.smual_gonder("ogrenci", "x")["basarili"])
            u.assert_not_called()

    def _form_istegi(self, govde: bytes):
        async def receive():
            return {"type": "http.request", "body": govde, "more_body": False}

        scope = {"type": "http", "method": "POST", "path": "/duyurular/tahta", "query_string": b"",
                 "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
                 "client": ("127.0.0.1", 1), "server": ("farabi.local", 80), "scheme": "http"}
        return Request(scope, receive)

    def test_yalniz_smual_secilince_tahtaya_yazilmaz(self):
        istek = self._form_istegi("mesaj=Okul+gezisi&tip=bilgi&smual_hedef=veli&smual_hedef=ogrenci".encode())
        with mock.patch("auth.dogrula", return_value=True),              mock.patch.object(dp.uzaktan_yonetim, "_denetim_yaz"),              mock.patch.object(dp, "_sayfa", side_effect=lambda r, s=None: s),              mock.patch.object(dp, "smual_gonder", side_effect=lambda h, m: {"tahta": h, "basarili": True, "detay": m}) as g:
            sonuclar = asyncio.run(dp.tahta_duyuru_gonder(istek))
        self.assertEqual([c.args for c in g.call_args_list], [("ogrenci", "Okul gezisi"), ("veli", "Okul gezisi")])
        self.assertEqual(len(sonuclar), 2)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM duyuru").fetchone()[0], 0)

    def test_hicbir_hedef_yoksa_uyari(self):
        istek = self._form_istegi(b"mesaj=x&tip=bilgi")
        with mock.patch("auth.dogrula", return_value=True),              mock.patch.object(dp.uzaktan_yonetim, "_denetim_yaz"),              mock.patch.object(dp, "_sayfa", side_effect=lambda r, s=None: s),              mock.patch.object(dp, "smual_gonder") as g:
            sonuclar = asyncio.run(dp.tahta_duyuru_gonder(istek))
        g.assert_not_called()
        self.assertFalse(sonuclar[0]["basarili"])


if __name__ == "__main__":
    unittest.main()
