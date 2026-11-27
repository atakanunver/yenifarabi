"""Sabit sorgular için sentetik kaynaklar."""

import unittest

import okul_sorgu as sorgu
import okul_sql


class TestOkulSorgu(unittest.TestCase):
    def setUp(self):
        self.t = {
            "ogrenci_genis": (["okul_no", "ad_soyad", "sinif", "anne_ad_soyad", "anne_telefon",
                               "baba_ad_soyad", "baba_telefon"],
                              [(11, "Test IŞIK", "9-A", "Veli Bir", None, None, None),
                               (12, "Test IŞIK", "9-B", None, None, None, None)]),
            "ogretmen": (["ad_soyad", "brans", "gorev", "telefon"],
                         [("Test Danışman", "Fizik", "Öğretmen", None),
                          ("Test İki", "Türkçe", "Müdür", "000")]),
            **okul_sql.kulup_tablolari([
                {"kod": "K", "ad": "Çizim", "danisman": "Test Danışman", "sinif": "9-A",
                 "uyeler": [{"no": "11", "ad_soyad": "Test IŞIK", "sinif": "9-A"}]},
                {"kod": "B", "ad": "Boş", "danisman": "Test İki", "uyeler": []}]),
            **okul_sql.dyk_tablolari({"siniflar": {"D1": {"dersler": [
                {"kod": "F", "ad": "Fizik", "ogretmen": "Test Danışman",
                 "uyeler": [{"no": "11", "ad_soyad": "Test IŞIK"}]}]}}}),
        }

    def test_sinif(self):
        r = sorgu.get_sinif_listesi("9-A", tablolar=self.t)
        self.assertEqual(r, {"baslik": "9-A Sınıf Listesi", "kolonlar": ["Okul No", "Ad Soyad", "Sınıf"],
                             "satirlar": [[11, "Test IŞIK", "9-A"]], "satir_sayisi": 1})
        self.assertEqual(r, sorgu.get_sinif_listesi("9", "a", tablolar=self.t))
        self.assertEqual(sorgu.get_sinif_listesi("9", tablolar=self.t)["satir_sayisi"], 2)
        self.assertEqual(sorgu.get_sinif_listesi("19-A", tablolar=self.t)["satirlar"], [])

    def test_basliklar(self):
        ornekler = [
            (sorgu.get_sinif_listesi, ("9",), "9. Sınıflar Listesi"),
            (sorgu.get_dyk_listesi, ("fizik",), "Fizik DYK Listesi"),
            (sorgu.get_dyk_listesi, (None, "danisman"), "Test Danışman DYK Listesi"),
            (sorgu.get_dyk_listesi, (), "DYK Listesi"),
            (sorgu.get_kulup_bilgisi, ("cizim",), "Çizim Üye Listesi"),
            (sorgu.get_kulup_bilgisi, (), "Kulüp Üye Listesi"),
            (sorgu.get_kulup_bilgisi, ("yok",), "Kulüp Üye Listesi"),
            (sorgu.get_ogretmen_listesi, ("turkce",), "Türkçe Öğretmen Listesi"),
            (sorgu.get_ogretmen_listesi, (), "Öğretmen Listesi"),
            (sorgu.get_ogrenci_ozet, (11,), "Öğrenci Özeti"),
        ]
        for islev, parametreler, baslik in ornekler:
            with self.subTest(islev=islev.__name__, parametreler=parametreler):
                self.assertEqual(islev(*parametreler, tablolar=self.t)["baslik"], baslik)

    def test_uzun_liste_kesilmez(self):
        kolonlar, _ = self.t["ogretmen"]
        self.t["ogretmen"] = (kolonlar, [(f"Test {i}", "Fizik", "Öğretmen", None) for i in range(205)])
        self.assertEqual(sorgu.get_ogretmen_listesi(tablolar=self.t)["satir_sayisi"], 205)

    def test_dyk(self):
        self.assertEqual(sorgu.get_dyk_listesi("fizik", "danisman", tablolar=self.t)["satirlar"],
                         [["Fizik", "Test Danışman", "D1", "11", "Test IŞIK"]])
        self.assertEqual(sorgu.get_dyk_listesi("Fizik", "İki", tablolar=self.t)["satirlar"], [])

    def test_kulup(self):
        self.assertEqual(sorgu.get_kulup_bilgisi("cizim", "danisman", tablolar=self.t)["satirlar"],
                         [["Çizim", "Test Danışman", "11", "Test IŞIK", "9-A", "üye"]])
        self.assertEqual(sorgu.get_kulup_bilgisi("bos", tablolar=self.t)["satirlar"],
                         [["Boş", "Test İki", None, None, None, None]])

    def test_ogretmen(self):
        r = sorgu.get_ogretmen_listesi("turkce", tablolar=self.t)
        self.assertEqual(r["kolonlar"], ["Ad Soyad", "Branş", "Görev", "Telefon"])
        self.assertEqual(r["satirlar"], [["Test İki", "Türkçe", "Müdür", "000"]])
        self.assertEqual(sorgu.get_ogretmen_listesi("' OR 1=1 --", tablolar=self.t)["satirlar"], [])

    def test_ozet(self):
        tek = sorgu.get_ogrenci_ozet(11, tablolar=self.t)["satirlar"]
        self.assertEqual(tek, [[11, "Test IŞIK", "9-A", "Veli Bir", None, None, None, "Fizik", "Çizim"]])
        for yazim in ("ışık", "IŞIK", "isik"):
            with self.subTest(yazim=yazim):
                r = sorgu.get_ogrenci_ozet(yazim, tablolar=self.t)
                self.assertEqual(r["satirlar"], tek + [[12, "Test IŞIK", "9-B", None, None, None, None, None, None]])
