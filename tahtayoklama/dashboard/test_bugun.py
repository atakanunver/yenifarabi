import json
import sqlite3
import unittest

import bugun


def _baglanti(satirlar):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        "CREATE TABLE yoklama_onbellek (tarih TEXT, sinif TEXT, ders_no INTEGER, durum TEXT, yok_isimleri TEXT)"
    )
    c.executemany("INSERT INTO yoklama_onbellek VALUES (?,?,?,?,?)", satirlar)
    return c


class TestYoklamaOzeti(unittest.TestCase):
    def test_sinif_bazli_sayim_ve_tekil_yok(self):
        t = "2026-10-26"
        c = _baglanti([
            (t, "9-A", 1, "alindi", json.dumps(["A", "B"])),
            (t, "9-A", 2, "alindi", json.dumps(["B", "C"])),  # B tekrar: tekil sayılır
            (t, "9-A", 3, "alinmadi", "[]"),
            (t, "10-A", 1, "tahta_ulasilamaz", "[]"),
            (t, "10-A", 2, "ders_yok_o_gun", "[]"),  # sayıma girmez
            ("2026-10-25", "9-B", 1, "alindi", json.dumps(["Z"])),  # başka gün
        ])
        o = bugun.yoklama_ozeti(c, t)
        self.assertEqual([s["ad"] for s in o["siniflar"]], ["9-A", "10-A"])
        self.assertEqual(o["siniflar"][0], {"ad": "9-A", "alindi": 2, "alinmadi": 1, "ulasilamaz": 0, "yok": 3})
        self.assertEqual((o["toplam_yok"], o["alinmayan_ders"], o["ulasilamayan_ders"]), (3, 1, 1))

    def test_kayit_yoksa_bos(self):
        o = bugun.yoklama_ozeti(_baglanti([]), "2026-10-26")
        self.assertEqual((o["siniflar"], o["toplam_yok"]), ([], 0))


if __name__ == "__main__":
    unittest.main()
