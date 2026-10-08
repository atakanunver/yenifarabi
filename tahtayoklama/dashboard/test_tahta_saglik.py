"""tahta_saglik.py testleri (2026-10-08): temizleme, uyarı eşikleri, liste, budama."""

import json
import sqlite3
import unittest

import db
import tahta_saglik as ts


def _iyi(**kw):
    s = {"sicaklik_c": 50.0, "bellek_bos_mb": 2000, "takas_mb": 10, "yuk1": 0.5,
         "calisma_sn": 3600, "oom_sayisi": 0, "acilis_id": "abc",
         "dokunmatik_var": True, "dokunmatik_kopma": 0}
    s.update(kw)
    return s


def _seviyeler(saglik, yas=10):
    return [u["seviye"] for u in ts.uyarilar(saglik, yas)]


class TestTemizle(unittest.TestCase):
    def test_gecerli_aynen_gecer(self):
        self.assertEqual(ts.saglik_temizle(_iyi()), _iyi())

    def test_dict_degilse_bos(self):
        for x in (None, [], "x", 5):
            self.assertEqual(ts.saglik_temizle(x), {})

    def test_bilinmeyen_anahtar_dusurulur(self):
        s = ts.saglik_temizle({"sicaklik_c": 40, "komut": "rm -rf /", "x": 1})
        self.assertEqual(s, {"sicaklik_c": 40})

    def test_aralik_disi_ve_yanlis_tip_dusurulur(self):
        s = ts.saglik_temizle({
            "sicaklik_c": 999, "bellek_bos_mb": -1, "takas_mb": "5", "yuk1": float("nan"),
            "oom_sayisi": 2_000_000, "dokunmatik_var": 1, "dokunmatik_kopma": True,
            "acilis_id": "x" * 65, "calisma_sn": None,
        })
        self.assertEqual(s, {})

    def test_bool_sayi_sayilmaz(self):
        self.assertEqual(ts.saglik_temizle({"bellek_bos_mb": True}), {})

    def test_tamsayi_alanlar_ondalikli_gelirse_dusurulur_float_alan_kabul(self):
        s = ts.saglik_temizle({"yuk1": 3, "bellek_bos_mb": 1.5})
        self.assertEqual(s, {"yuk1": 3.0})

    def test_acilis_id_metin(self):
        self.assertEqual(ts.saglik_temizle({"acilis_id": "a-b"}), {"acilis_id": "a-b"})
        self.assertEqual(ts.saglik_temizle({"acilis_id": 5}), {})


class TestUyarilar(unittest.TestCase):
    def test_saglikli_uyari_yok(self):
        self.assertEqual(ts.uyarilar(_iyi(), 10), [])

    def test_sicaklik(self):
        self.assertEqual(_seviyeler(_iyi(sicaklik_c=74.9)), [])
        self.assertEqual(_seviyeler(_iyi(sicaklik_c=75)), ["uyari"])
        self.assertEqual(_seviyeler(_iyi(sicaklik_c=85)), ["hata"])

    def test_bellek(self):
        self.assertEqual(_seviyeler(_iyi(bellek_bos_mb=600)), [])
        self.assertEqual(_seviyeler(_iyi(bellek_bos_mb=599)), ["uyari"])
        self.assertEqual(_seviyeler(_iyi(bellek_bos_mb=299)), ["hata"])

    def test_takas(self):
        self.assertEqual(_seviyeler(_iyi(takas_mb=999)), [])
        self.assertEqual(_seviyeler(_iyi(takas_mb=1000)), ["uyari"])

    def test_oom(self):
        u = ts.uyarilar(_iyi(oom_sayisi=3), 10)
        self.assertEqual(u[0]["seviye"], "hata")
        self.assertEqual(u[0]["mesaj"], "Açılıştan beri 3 kez bellek doldu (program kapatıldı)")

    def test_dokunmatik(self):
        self.assertEqual(_seviyeler(_iyi(dokunmatik_kopma=2)), [])
        self.assertEqual(_seviyeler(_iyi(dokunmatik_kopma=3)), ["uyari"])
        u = ts.uyarilar(_iyi(dokunmatik_var=False), 10)
        self.assertEqual(u, [{"seviye": "uyari", "mesaj": "Dokunmatik aygıt görünmüyor"}])

    def test_none_degerler_uyari_uretmez(self):
        self.assertEqual(ts.uyarilar({"sicaklik_c": None, "oom_sayisi": None}, 5), [])

    def test_cevrimdisi_tek_hata(self):
        u = ts.uyarilar(_iyi(sicaklik_c=99, oom_sayisi=5), 600)
        self.assertEqual(len(u), 1)
        self.assertEqual(u[0]["seviye"], "hata")
        self.assertEqual(u[0]["mesaj"], "Çevrimdışı (son nabız 10 dk önce)")
        self.assertEqual(ts.uyarilar(_iyi(), 180), [])


class TestListe(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SEMA)

    def tearDown(self):
        self.conn.close()

    def _nabiz(self, ad, saglik=None, yas_sn=10):
        self.conn.execute(
            "INSERT INTO tahta_nabiz (tahta_ad, son_gorulme, saglik) "
            "VALUES (?, datetime('now', ?), ?)",
            (ad, f"-{yas_sn} seconds", json.dumps(saglik) if saglik is not None else None))

    def _gecmis(self, ad, sicaklik, saat_once):
        self.conn.execute(
            "INSERT INTO tahta_saglik_gecmis (tahta_ad, zaman, sicaklik_c) "
            "VALUES (?, datetime('now', ?), ?)", (ad, f"-{saat_once} hours", sicaklik))

    def test_siralama_ve_durumlar(self):
        self._nabiz("b-iyi", _iyi())
        self._nabiz("a-eski")  # saglik yok
        self._nabiz("c-uyari", _iyi(takas_mb=2000))
        self._nabiz("d-hata", _iyi(oom_sayisi=1))
        self._nabiz("e-off", _iyi(), yas_sn=900)
        liste = ts.liste(self.conn)
        self.assertEqual([t["tahta_ad"] for t in liste],
                         ["a-eski", "b-iyi", "c-uyari", "d-hata", "e-off"])
        self.assertEqual([t["durum"] for t in liste],
                         ["veri_yok", "iyi", "uyari", "hata", "cevrimdisi"])
        self.assertEqual(liste[0]["saglik"], {})
        self.assertGreaterEqual(liste[1]["nabiz_yasi_sn"], 9)
        self.assertEqual(liste[1]["saglik"]["bellek_bos_mb"], 2000)
        self.assertEqual(liste[4]["uyarilar"][0]["seviye"], "hata")

    def test_veri_yok_cevrimdisiysa_cevrimdisi_degil_veri_yok(self):
        self._nabiz("x", None, yas_sn=900)
        self.assertEqual(ts.liste(self.conn)[0]["durum"], "veri_yok")

    def test_24s_max_son_24_saatten(self):
        self._nabiz("t", _iyi())
        self._gecmis("t", 60.0, 1)
        self._gecmis("t", 71.5, 5)
        self._gecmis("t", 90.0, 30)  # 24 saatten eski
        self._gecmis("diger", 99.0, 1)
        self.assertEqual(ts.liste(self.conn)[0]["sicaklik_24s_max"], 71.5)

    def test_24s_max_gecmis_yoksa_none(self):
        self._nabiz("t", _iyi())
        self.assertIsNone(ts.liste(self.conn)[0]["sicaklik_24s_max"])

    def test_bozuk_json_veri_yok_sayilir(self):
        self.conn.execute(
            "INSERT INTO tahta_nabiz (tahta_ad, son_gorulme, saglik) "
            "VALUES ('z', datetime('now'), '{bozuk')")
        t = ts.liste(self.conn)[0]
        self.assertEqual(t["saglik"], {})
        self.assertEqual(t["durum"], "veri_yok")

    def test_buda_14_gunden_eskiyi_siler(self):
        self.conn.execute(
            "INSERT INTO tahta_saglik_gecmis (tahta_ad, zaman) VALUES ('t', datetime('now', '-15 days'))")
        self.conn.execute(
            "INSERT INTO tahta_saglik_gecmis (tahta_ad, zaman) VALUES ('t', datetime('now', '-13 days'))")
        ts.gecmisi_buda(self.conn)
        n = self.conn.execute("SELECT COUNT(*) FROM tahta_saglik_gecmis").fetchone()[0]
        self.assertEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
