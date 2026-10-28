"""osym_yukle ayrıştırıcı testleri (sahte ızgaralarla; DB ve xlrd gerekmez). Çalıştırma: osym/venv/bin/python -m unittest"""

import unittest

import osym_analiz as an
import osym_yukle as o

TC1, TC2 = "10000000146", "10000000078"  # sağlama basamakları geçerli örnek numaralar


def izgara_yerlestirme():
    return [
        [""] * 4,
        ["", "", "YKS (ÖSYS) YERLEŞTİRME SONUÇLARI\nKURŞUNLU ANADOLU LİSESİ 2024  YILI SON SINIF ÖĞRENCİLERİ"],
        ["", "Tc Kimlik No", "", "Ad Soyad", "Program Adı", "Puan Türü", "Puan", "Yerleştiği Tercih Sırası", "TÜBİTAK /\nEngelli Ek Puan Durumu"],
        ["", TC1 + ".0", "", "ELİF AYDIN", "Maliye", "EA", 314.98989, 11.0, "Genel"],
        ["", "Toplam", "", "", "", "", "", "", ""],
    ]


class TestBaslik(unittest.TestCase):
    def test_yil_ve_rapor(self):
        self.assertEqual(o.baslik_bilgisi(izgara_yerlestirme(), "x.xls"), (2024, "yerlestirme"))

    def test_ayt_dosya_adindan(self):
        g = [["YKS DOĞRU YANLIŞ SAYILARI\nKURŞUNLU 2026  YILI SON SINIF ÖĞRENCİLERİ"]]
        self.assertEqual(o.baslik_bilgisi(g, "AYT Testleri Bazında.xls"), (2026, "dogru_yanlis_ayt"))
        self.assertEqual(o.baslik_bilgisi(g, "YKS Testleri Bazında.xls"), (2026, "dogru_yanlis_tyt"))

    def test_baslik_yoksa_none(self):
        self.assertEqual(o.baslik_bilgisi([["başka"]], "a.xls"), (None, None))


class TestYerlestirme(unittest.TestCase):
    def test_satir_ve_alanlar(self):
        (k,) = o.yerlestirme_satirlari(izgara_yerlestirme())
        self.assertEqual((k["tc_kimlik"], k["ad_soyad"], k["program_adi"], k["puan_turu"], k["tercih_sirasi"], k["ek_puan_2"]),
                         (TC1, "ELİF AYDIN", "Maliye", "EA", 11, "Genel"))
        self.assertAlmostEqual(k["puan"], 314.98989)
        self.assertIsNone(k["obp"])  # sütun yok → NULL

    def test_tc_olmayan_satir_atlanir(self):
        self.assertEqual(len(o.yerlestirme_satirlari(izgara_yerlestirme())), 1)


class TestPuan(unittest.TestCase):
    def test_uzun_bicim_ve_bos_grup(self):
        g = [
            [""],
            ["", "", "", "", "", "", "TYT", "", "SAYISAL"],
            ["", "Tc Kimlik No", "", "Ad Soyad", "", "", "Puan", "Başarı Sırası", "Puan", "Başarı Sırası"],
            ["", TC1, "", "ELİF AYDIN", "", "", 244.17, 1754969.0, "", ""],
        ]
        # başlık satırı 2, grup satırı 1
        k = o.puan_satirlari(g)
        self.assertEqual([(x["puan_turu"], x["puan"], x["basari_sirasi"]) for x in k], [("TYT", 244.17, 1754969)])


class TestDogruYanlis(unittest.TestCase):
    def izgara(self, bolum):
        return [
            ["", "", "", "", "", "", bolum, "", "", ""],
            ["", "", "", "", "", "", "TÜRKÇE TESTİ", "", "", ""],
            ["", "Tc Kimlik No", "", "", "Ad Soyad", "", "D", "Y", "B", "HAM"],
            ["", TC1, "", "", "ELİF AYDIN", "", 30.0, 4.0, 6.0, 29.0],
        ]

    def test_bolum_etiketi(self):
        (k,) = o.dogru_yanlis_satirlari(self.izgara("TYT"), "AYT")
        self.assertEqual((k["sinav"], k["test"], k["dogru"], k["yanlis"], k["bos"], k["ham"]), ("TYT", "TÜRKÇE TESTİ", 30, 4, 6, 29))

    def test_gecersiz_bolum_varsayilana_duser(self):
        (k,) = o.dogru_yanlis_satirlari(self.izgara("MATEMATİK TESTİ"), "AYT")  # AYT dosyasında üst satır test grubudur
        self.assertEqual(k["sinav"], "AYT")


class TestDocx(unittest.TestCase):
    def test_genel_istatistik(self):
        tablo = [
            ["Öğretim Yılı", "2012-2013Son Sınıf Öğrenci Sayısı", "x", "x", "x", "Yerleşen"],
            ["", "", "", "", "", "Lisans", "Önlisans", "AÖF", "TOPLAM"],
            ["2013", "27", "27", "27", "19", "14", "", "3", "", "17"],
        ]
        (k,) = o.genel_istatistik([tablo])
        self.assertEqual((k["yil"], k["ogretim_yili"], k["son_sinif"], k["lisans"], k["onlisans_sinavsiz"], k["onlisans_sinavli"], k["toplam_yerlesen"]),
                         (2013, "2012-2013", 27, 14, None, 3, 17))


class TestYardimci(unittest.TestCase):
    def test_tc_sagla(self):
        self.assertTrue(an.tc_gecerli(TC1))
        self.assertTrue(an.tc_gecerli(TC2))
        self.assertFalse(an.tc_gecerli("10000000147"))
        self.assertFalse(an.tc_gecerli("00000000000"))
        self.assertFalse(an.tc_gecerli("123"))

    def test_sade(self):
        self.assertEqual(o.sade("  Fakülte/MYO  Adı "), "fakulte/myo adi")
        self.assertEqual(o.sade("İNGİLİZCE"), "ingilizce")


if __name__ == "__main__":
    unittest.main()
