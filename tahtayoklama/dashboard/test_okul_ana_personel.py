"""okul_ana_veri personel doğrulamaları (DB'siz)."""
import sqlite3
import unittest
from unittest.mock import patch

import okul_ana_veri as veri


class TestPersonelAlanlari(unittest.TestCase):
    @patch.object(veri, "denetim")
    def test_adres(self, _denetim):
        class Baglanti(sqlite3.Connection):
            def execute(self, sql, params=()):
                return super().execute(sql.replace("%s", "?"), params)

        c = sqlite3.connect(":memory:", factory=Baglanti)
        self.addCleanup(c.close)
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE personel(id INTEGER PRIMARY KEY, ad_soyad, telefon, gorev, "
                  "dogum_tarihi, brans, tc_kimlik, eposta, adres, aktif)")
        def adres():
            return c.execute("SELECT adres FROM personel").fetchone()["adres"]

        args = ("Test Personeli", "", "diger", "", "", "", "")
        veri.personel_kaydet(c, None, *args, adres="  Örnek   Sokak  ")
        self.assertEqual(adres(), "Örnek Sokak")
        veri.personel_kaydet(c, 1, *args, adres="Yeni Cadde")
        veri.personel_kaydet(c, 1, *args)
        self.assertEqual(adres(), "Yeni Cadde")
        veri.personel_kaydet(c, 1, *args, adres="  ")
        self.assertIsNone(adres())
        with self.assertRaises(ValueError):
            veri.personel_kaydet(c, 1, *args, adres="a" * 501)

    def test_tc(self):
        self.assertIsNone(veri._tc(""))
        self.assertEqual(veri._tc(" 12345678901 "), "12345678901")
        for kotu in ("1234567890", "123456789012", "1234567890a"):
            with self.assertRaises(ValueError):
                veri._tc(kotu)

    def test_eposta(self):
        self.assertIsNone(veri._eposta(" "))
        self.assertEqual(veri._eposta(" Ali@Okul.com "), "ali@okul.com")
        for kotu in ("ali", "ali@okul", "a b@okul.com"):
            with self.assertRaises(ValueError):
                veri._eposta(kotu)


if __name__ == "__main__":
    unittest.main()
