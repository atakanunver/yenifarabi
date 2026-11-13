"""okul_sql: DYK tabloları ve diğer SQLite veri tabanları (ek kaynaklar)."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import okul_sql

DYK = {
    "siniflar": {"11": {"derslik": "10-A", "dersler": [
        {"kod": "DYK-11-KIMYA", "ad": "Kimya", "ogretmen": "Ali Veli", "uyeler": [{"no": 5, "ad_soyad": "Deneme Bir"}]}]}},
    "program": {"11": [{"gun": "cuma", "bas": "16:00", "bit": "17:30", "kod": "DYK-11-KIMYA", "ders_no": 1}]},
}


class TestDyk(unittest.TestCase):
    def test_tablolar_ve_izin(self):
        t = okul_sql.dyk_tablolari(DYK)
        self.assertEqual(t["dyk_ogrenci"][1], [("DYK-11-KIMYA", "11", "10-A", "Kimya", "Ali Veli", 5, "Deneme Bir")])
        self.assertEqual(t["dyk_program"][1], [("11", "10-A", 5, "cuma", "16:00", "17:30", "DYK-11-KIMYA", "Kimya", "Ali Veli", 1)])
        sonuc = okul_sql.calistir("SELECT p.gun_adi, o.ad_soyad FROM dyk_program p JOIN dyk_ogrenci o USING (kod)", t)
        self.assertEqual(sonuc["satirlar"], [["cuma", "Deneme Bir"]])

    def test_bos_veri(self):
        for veri in ({}, None):
            self.assertEqual(okul_sql.dyk_tablolari(veri)["dyk_ogrenci"][1], [])


class TestEkSqlite(unittest.TestCase):
    def setUp(self):
        self.gecici = tempfile.TemporaryDirectory()
        kok = Path(self.gecici.name)
        (kok / "okul" / "veri").mkdir(parents=True)
        c = sqlite3.connect(kok / "okul" / "veri" / "okul.db")
        c.execute("CREATE TABLE kullanici (id INTEGER, ad_soyad TEXT, sifre_hash TEXT)")
        c.execute("INSERT INTO kullanici VALUES (1, 'Deneme Kisi', 'gizli-ozet')")
        c.execute("CREATE TABLE oturum (token_hash TEXT)")
        c.execute("INSERT INTO oturum VALUES ('x')")
        c.commit()
        c.close()
        self.kok = kok

    def tearDown(self):
        self.gecici.cleanup()

    def test_sifre_sutunu_okunmaz(self):
        t = okul_sql.ek_sqlite_tablolari("SELECT * FROM portal_kullanici", kok=self.kok)
        self.assertEqual(t["portal_kullanici"], (["id", "ad_soyad"], [(1, "Deneme Kisi")]))

    def test_yalniz_sorguda_gecen_tablo_okunur(self):
        self.assertEqual(okul_sql.ek_sqlite_tablolari("SELECT 1", kok=self.kok), {})

    def test_oturum_tablosu_listede_yok(self):
        self.assertNotIn("portal_oturum", okul_sql.IZINLI_TABLOLAR)
        self.assertNotIn("portal_push_abonelik", okul_sql.IZINLI_TABLOLAR)
        self.assertNotIn("sms_ayarlar", okul_sql.IZINLI_TABLOLAR)
        self.assertNotIn("sms_oturumlar", okul_sql.IZINLI_TABLOLAR)
        self.assertNotIn("panel_oturumlar", okul_sql.IZINLI_TABLOLAR)

    def test_kaynak_yoksa_sql_hatasi(self):
        with self.assertRaises(okul_sql.SqlHatasi):
            okul_sql.ek_sqlite_tablolari("SELECT * FROM kelebek_dagitim", kok=self.kok)

    def test_izinli_tablo_sorgulanir_digeri_reddedilir(self):
        t = okul_sql.ek_sqlite_tablolari("SELECT * FROM portal_kullanici", kok=self.kok)
        self.assertEqual(okul_sql.calistir("SELECT ad_soyad FROM portal_kullanici", t)["satirlar"], [["Deneme Kisi"]])
        with self.assertRaises(okul_sql.SqlHatasi):
            okul_sql.calistir("SELECT * FROM oturum", t)

    def test_pg_kaynak_yoksa_bagli_degilse_sql_hatasi(self):
        with patch.dict("sys.modules", {"psycopg": None}), self.assertRaises(okul_sql.SqlHatasi):
            okul_sql.pg_ek_tablolari("dbname=x", "SELECT * FROM sh_soru")
        self.assertEqual(okul_sql.pg_ek_tablolari("dbname=x", "SELECT 1"), {})


if __name__ == "__main__":
    unittest.main()
