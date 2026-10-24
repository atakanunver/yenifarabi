import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

import aylik_ozet


def _yoklama_db(satirlar):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE yoklama_onbellek (tarih TEXT, sinif TEXT, ders_no INTEGER, durum TEXT, yok_isimleri TEXT)")
    c.executemany("INSERT INTO yoklama_onbellek VALUES (?,?,?,?,?)", satirlar)
    return c


class TestAyCoz(unittest.TestCase):
    def test_gecerli_gecersiz_ve_gelecek_ay(self):
        bugun = date(2026, 10, 24)
        self.assertEqual(aylik_ozet.ay_coz("2026-09", bugun), (date(2026, 9, 1), date(2026, 9, 30), "2026-09"))
        self.assertEqual(aylik_ozet.ay_coz("2028-02", date(2030, 1, 5))[1], date(2028, 2, 29))
        for kotu in (None, "", "2026-13", "x", "2026-9"):
            self.assertEqual(aylik_ozet.ay_coz(kotu, bugun)[2], "2026-10")
        self.assertEqual(aylik_ozet.ay_coz("2027-01", bugun)[2], "2026-10")  # gelecek ay -> bu ay

    def test_ay_kaydir_yil_sinirinda(self):
        self.assertEqual(aylik_ozet._ay_kaydir("2026-01", -1), "2025-12")
        self.assertEqual(aylik_ozet._ay_kaydir("2026-12", 1), "2027-01")


class TestYoklamaOzeti(unittest.TestCase):
    def test_oran_tekil_ogrenci_ve_ay_siniri(self):
        c = _yoklama_db([
            ("2026-09-10", "9-A", 1, "alindi", json.dumps(["A", "B"])),
            ("2026-09-11", "9-A", 1, "alindi", json.dumps(["B"])),     # B tekil sayılır
            ("2026-09-11", "9-A", 2, "alinmadi", "[]"),
            ("2026-09-12", "10-A", 1, "tahta_ulasilamaz", "[]"),
            ("2026-09-12", "10-A", 2, "ders_yok_o_gun", "[]"),         # sayıma girmez
            ("2026-10-01", "9-A", 1, "alindi", json.dumps(["Z"])),     # başka ay
        ])
        o = aylik_ozet.yoklama_ozeti(c, date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual([s["ad"] for s in o["siniflar"]], ["9-A", "10-A"])
        a = o["siniflar"][0]
        self.assertEqual((a["ders"], a["alindi"], a["oran"], a["yok_ogrenci"], a["yok_ders"]), (3, 2, 67, 2, 3))
        self.assertEqual((o["gun"], o["oran"], o["yok_ogrenci"]), (2, 50, 2))

    def test_kayit_yok(self):
        o = aylik_ozet.yoklama_ozeti(_yoklama_db([]), date(2026, 9, 1), date(2026, 9, 30))
        self.assertEqual((o["siniflar"], o["oran"], o["gun"]), ([], 0, 0))


class TestEtkinlikOzeti(unittest.TestCase):
    def test_aktif_ve_kayitli_rol_bazli(self):
        with tempfile.TemporaryDirectory() as d:
            yol = Path(d) / "okul.db"
            c = sqlite3.connect(yol)
            c.executescript(
                "CREATE TABLE kullanici (id INTEGER, rol TEXT, aktif INTEGER);"
                "CREATE TABLE olay (kullanici_id INTEGER, rol TEXT, tur TEXT, gun TEXT);"
                "INSERT INTO kullanici VALUES (1,'ogrenci',1),(2,'ogrenci',1),(3,'ogretmen',1),(4,'ogrenci',0);"
                "INSERT INTO olay VALUES (1,'ogrenci','aktif','2026-09-02'),(1,'ogrenci','aktif','2026-09-03'),"
                "(3,'ogretmen','aktif','2026-09-04'),(2,'ogrenci','aktif','2026-10-01');"
            )
            c.commit()
            c.close()
            o = aylik_ozet.etkinlik_ozeti(date(2026, 9, 1), date(2026, 9, 30), yol)
            yok = aylik_ozet.etkinlik_ozeti(date(2026, 9, 1), date(2026, 9, 30), Path(d) / "yok.db")
        self.assertEqual(o["roller"], [
            {"ad": "Öğrenci", "aktif": 1, "kayitli": 2, "oran": 50},
            {"ad": "Öğretmen", "aktif": 1, "kayitli": 1, "oran": 100},
        ])
        self.assertIsNone(yok)


if __name__ == "__main__":
    unittest.main()
