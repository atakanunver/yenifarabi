"""admin.py::_rapor_grafikleri — rapor sayfasındaki günlük devamsızlık ve sınıf
bazında yoklama oranı grafiklerinin verisi (2026-10-23). Saf fonksiyon, DB yok."""

import unittest

import admin


def _satir(tarih, sinif, ders_no, durum, yok=(), izinli=()):
    return {"tarih": tarih, "sinif": sinif, "ders_no": ders_no, "durum": durum,
            "yok_isimleri": list(yok), "izinli_isimleri": list(izinli)}


class TestRaporGrafikleri(unittest.TestCase):
    def test_bos(self):
        self.assertEqual(admin._rapor_grafikleri([]), {"gunluk": [], "siniflar": [], "gunluk_maks": 0})

    def test_gunluk_tekil_ogrenci(self):
        # Aynı öğrenci aynı gün iki derste yok → 1 öğrenci; farklı sınıfta aynı ad ayrı sayılır.
        satirlar = [
            _satir("2026-10-20", "9-A", 1, "alindi", yok=["Ali"]),
            _satir("2026-10-20", "9-A", 2, "alindi", yok=["Ali"], izinli=["Ayşe"]),
            _satir("2026-10-20", "9-B", 1, "alindi", yok=["Ali"]),
            _satir("2026-10-21", "9-A", 1, "alindi"),
        ]
        g = admin._rapor_grafikleri(satirlar)
        self.assertEqual(g["gunluk"], [
            {"tarih": "2026-10-20", "yok": 2, "izinli": 1},
            {"tarih": "2026-10-21", "yok": 0, "izinli": 0},
        ])
        self.assertEqual(g["gunluk_maks"], 3)

    def test_sinif_orani(self):
        # henuz_baslamadi / tahta_atanmamis paydaya girmez; ulaşılamaz girer.
        satirlar = [
            _satir("2026-10-20", "9-A", 1, "alindi"),
            _satir("2026-10-20", "9-A", 2, "alinmadi"),
            _satir("2026-10-20", "9-A", 3, "tahta_ulasilamaz"),
            _satir("2026-10-20", "9-A", 4, "alindi"),
            _satir("2026-10-20", "9-A", 5, "henuz_baslamadi"),
            _satir("2026-10-20", "fenlab", 1, "tahta_atanmamis"),
        ]
        g = admin._rapor_grafikleri(satirlar)
        self.assertEqual(g["siniflar"], [{"sinif": "9-A", "alindi": 2, "toplam": 4, "oran": 50}])


if __name__ == "__main__":
    unittest.main()
