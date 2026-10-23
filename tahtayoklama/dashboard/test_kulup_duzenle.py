"""kulupler.py düzenleme yardımcıları (2026-10-23): panelden kulüp listesi güncelleme.
Gerçek config/kulupler.json'a ASLA dokunmaz (geçici dosya)."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import kulupler

ORNEK = [{"kod": "KULUP-BEYAZAY", "ad": "Beyazay Kulübü", "danisman": "A", "sinif": "10-A",
          "uyeler": [{"no": 206, "ad_soyad": "Deniz Deneme", "sinif": "9-A"}]}]


class KulupDosyasi(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.yol = Path(self._tmp.name) / "kulupler.json"
        self.yol.write_text(json.dumps(ORNEK, ensure_ascii=False), encoding="utf-8")
        yama = patch.object(kulupler, "KULUP_DOSYASI", self.yol)
        yama.start()
        self.addCleanup(yama.stop)


class TestUyeAyristir(unittest.TestCase):
    def test_bos_satir_atlanir_ve_alanlar_temizlenir(self):
        uyeler = kulupler.uyeleri_ayristir([" 12 ", ""], [" Ali Veli ", ""], ["9-A", ""])
        self.assertEqual(uyeler, [{"no": 12, "ad_soyad": "Ali Veli", "sinif": "9-A"}])

    def test_gecersiz_no_ve_tekrar_reddedilir(self):
        with self.assertRaises(ValueError):
            kulupler.uyeleri_ayristir(["abc"], ["Ali"], ["9-A"])
        with self.assertRaises(ValueError):
            kulupler.uyeleri_ayristir(["5", "5"], ["Ali", "Can"], ["9-A", "9-B"])


class TestGuncelleEkle(KulupDosyasi):
    def test_guncelle_kod_degismez(self):
        kulupler.guncelle("KULUP-BEYAZAY", "Beyazay", "B", "11-A",
                          [{"no": 1, "ad_soyad": "X", "sinif": "9-B"}])
        k = kulupler.bul("KULUP-BEYAZAY")
        self.assertEqual((k["ad"], k["danisman"], k["sinif"], len(k["uyeler"])), ("Beyazay", "B", "11-A", 1))
        self.assertEqual(oct(os.stat(self.yol).st_mode & 0o777), "0o600")  # öğrenci verisi

    def test_bilinmeyen_kod(self):
        with self.assertRaises(KeyError):
            kulupler.guncelle("KULUP-YOK", "x", "", "", [])

    def test_ekle_kod_uretir_cakismada_sonek(self):
        self.assertEqual(kulupler.ekle("Şehir Kültürü Kulübü", "9-A"), "KULUP-SEHIR")
        self.assertEqual(kulupler.ekle("Beyazay İkinci", "9-B"), "KULUP-BEYAZAY2")
        self.assertEqual(len(kulupler.yukle()), 3)

    def test_ekle_bos_ad_reddedilir(self):
        with self.assertRaises(ValueError):
            kulupler.ekle("   ", "9-A")


if __name__ == "__main__":
    unittest.main()
