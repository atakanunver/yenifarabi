"""okul_ana_veri personel doğrulamaları (DB'siz)."""
import unittest

import okul_ana_veri as veri


class TestPersonelAlanlari(unittest.TestCase):
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
