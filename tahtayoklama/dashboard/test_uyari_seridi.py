"""pano.html uyarı şeridi + ders hücresindeki öğretmen (2026-10-14).
Doldurma istemci JS'indedir (Python testi yazılamaz); burada şablon sözleşmesi ve
ders_programi.ogretmen_adi sınanır. Gerçek ogretmenler.json (kişisel ad) teste girmez."""
import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import ders_programi

PANO = (Path(__file__).parent / "templates" / "pano.html").read_text(encoding="utf-8")


class TestUyariSeridi(unittest.TestCase):
    def test_serit_ve_baglantisi_sablonda(self):
        self.assertIn('id="uyari-seridi"', PANO)
        self.assertIn('href="/sistem-durumu"', PANO)
        self.assertIn("uyariSeriti(veri.satirlar", PANO)

    def test_acilista_sunucu_durumu_cekilmez(self):  # 2026-10-03 kararı
        self.assertNotIn("/api/sistem-durumu", PANO)

    def test_ogretmen_hucreye_yazilir(self):
        self.assertIn("satir.ogretmen", PANO)


class TestOgretmenAdi(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        dosya = Path(self._tmp.name) / "ogretmenler.json"
        dosya.write_text(json.dumps({"program": {"9-A": {"pazartesi": {"1": ["AA BB"], "2": ["AA BB", "CC DD"]}}}}))
        self._p = patch.object(ders_programi, "OGRETMEN_DOSYASI", dosya)
        self._p.start()
        ders_programi.yenile()

    def tearDown(self):
        self._p.stop()
        ders_programi.yenile()
        self._tmp.cleanup()

    def test_tek_ve_birden_cok_ogretmen(self):
        pzt = date(2026, 10, 12)
        self.assertEqual(ders_programi.ogretmen_adi("9-A", pzt, 1), "AA BB")
        self.assertEqual(ders_programi.ogretmen_adi("9-A", pzt, 2), "AA BB / CC DD")

    def test_olmayan_kayit_ve_hafta_sonu_none(self):
        self.assertIsNone(ders_programi.ogretmen_adi("9-A", date(2026, 10, 12), 5))
        self.assertIsNone(ders_programi.ogretmen_adi("9-Z", date(2026, 10, 12), 1))
        self.assertIsNone(ders_programi.ogretmen_adi("9-A", date(2026, 10, 17), 1))  # cumartesi

    def test_dosya_yoksa_none(self):
        with patch.object(ders_programi, "OGRETMEN_DOSYASI", Path(self._tmp.name) / "yok.json"):
            ders_programi.yenile()
            self.assertIsNone(ders_programi.ogretmen_adi("9-A", date(2026, 10, 12), 1))


if __name__ == "__main__":
    unittest.main()
