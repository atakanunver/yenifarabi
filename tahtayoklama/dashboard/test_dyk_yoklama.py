"""DYK kursu yoklaması (2026-11-13): kayıt alımı (dyk_yoklama, bildirim yok),
yapılandırma anahtarları ve /dyk-yoklama sayfası. Veri sahte (uydurma isimler)."""

import asyncio
import hashlib
import json
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zoneinfo import ZoneInfo

import db
import dyk
import dyk_yoklama
import kulupler
import tahta_api
import yoklayici
from fastapi.requests import Request

TARIH = "2026-11-12"
KOD = "DYK-11-COGRAFYA"

SAHTE = {
    "siniflar": {"11": {"derslik": "10-A", "ad": "11. Sınıf DYK", "dersler": [
        {"kod": KOD, "ad": "Coğrafya", "ogretmen": "Ayşe Örnek",
         "uyeler": [{"no": 206, "ad_soyad": "Deniz Deneme"}, {"no": 7, "ad_soyad": "Can Kaya"}]}]}},
    "program": {"11": [{"gun": "pazartesi", "bas": "16:00", "bit": "17:30", "kod": KOD, "ders_no": 1}]},
}


class DykTemel(unittest.TestCase):
    def setUp(self):
        self._saat = patch("zil.simdi_istanbul", return_value=datetime(
            2026, 11, 12, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")))
        self._saat.start()
        self.addCleanup(self._saat.stop)
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self._eski = (db.DB_YOLU, tahta_api.TOKEN_DOSYASI, dyk.DYK_DOSYASI, kulupler.KULUP_DOSYASI)
        self.addCleanup(self._geri)
        db.DB_YOLU = tmp / "test.db"
        db.semayi_kur()
        tahta_api.TOKEN_DOSYASI = tmp / "tokenlar.json"
        tahta_api.TOKEN_DOSYASI.write_text(json.dumps({"10-A": hashlib.sha256(b"t").hexdigest()}))
        kulupler.KULUP_DOSYASI = tmp / "kulupler_yok.json"
        dyk.DYK_DOSYASI = tmp / "dyk.json"
        dyk.DYK_DOSYASI.write_text(json.dumps(SAHTE, ensure_ascii=False), encoding="utf-8")
        conn = db.baglanti()
        conn.execute("INSERT INTO siniflar (id, ad) VALUES (1, '10-A'), (2, '9-A')")
        conn.execute("INSERT INTO ogrenciler (sinif_id, no, ad_soyad) VALUES (1, 7, 'Can Kaya'), (2, 206, 'Deniz Deneme')")
        conn.execute("INSERT INTO tahtalar (ad, ip, ssh_kullanici, sinif_id) VALUES ('10-A', '10.0.0.1', 'o', 1)")
        conn.commit()
        conn.close()

    def _geri(self):
        db.DB_YOLU, tahta_api.TOKEN_DOSYASI, dyk.DYK_DOSYASI, kulupler.KULUP_DOSYASI = self._eski

    def _kayit(self, **kw):
        k = {"sinif": KOD, "tarih": TARIH, "ders_no": 7,
             "kaydedilme_saati": "14:00:00", "durumlar": {"206": "yok", "7": "izinli"}}
        k.update(kw)
        return k

    def _say(self, tablo):
        conn = db.baglanti()
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0]
        finally:
            conn.close()


class TestKayit(DykTemel):
    def test_kod_dogrulamadan_gecer(self):
        self.assertEqual(tahta_api.kayit_dogrula(self._kayit())["sinif"], KOD)

    def test_dyk_kaydi_ayri_tabloya_bildirim_yok(self):
        conn = db.baglanti()
        try:
            self.assertEqual(yoklayici.itilen_kaydi_yaz(conn, self._kayit(), "10-A"), (True, []))
            s = conn.execute("SELECT * FROM dyk_yoklama").fetchone()
        finally:
            conn.close()
        self.assertEqual((s["sinif"], s["durum"], s["kaynak_tahta"]), (KOD, "alindi", "10-A"))
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Deniz Deneme"])
        self.assertEqual(json.loads(s["izinli_isimleri"]), ["Can Kaya"])
        self.assertEqual(json.loads(s["yok_nolari"]), [206])
        self.assertEqual((self._say("yoklama_onbellek"), self._say("kulup_yoklama")), (0, 0))

    def test_bugunku_kayitta_da_bildirim_yok(self):
        conn = db.baglanti()
        try:
            sonuc = yoklayici.itilen_kaydi_yaz(conn, self._kayit(tarih="2026-11-12"), "10-A")
        finally:
            conn.close()
        self.assertEqual(sonuc, (True, []))
        self.assertEqual(self._say("dyk_yoklama"), 1)

    def test_bilinmeyen_kod_reddedilir(self):
        conn = db.baglanti()
        try:
            self.assertEqual(
                yoklayici.itilen_kaydi_yaz(conn, self._kayit(sinif="DYK-11-YOK"), "10-A"), (False, []))
        finally:
            conn.close()
        self.assertEqual(self._say("dyk_yoklama"), 0)

    def test_gecmis_gunun_kaydi_ezilmez(self):
        conn = db.baglanti()
        try:
            yoklayici.itilen_kaydi_yaz(conn, self._kayit(tarih="2026-11-11"), "10-A")
            sonuc = yoklayici.itilen_kaydi_yaz(
                conn, self._kayit(tarih="2026-11-11", kaydedilme_saati="15:00:00", durumlar={}), "10-A")
            s = conn.execute("SELECT * FROM dyk_yoklama").fetchone()
        finally:
            conn.close()
        self.assertEqual(sonuc, (True, []))
        self.assertEqual(s["kaydedilme_saati"], "14:00:00")
        self.assertEqual(json.loads(s["yok_nolari"]), [206])

    def test_ayni_gun_daha_eski_saat_ezmez(self):
        conn = db.baglanti()
        try:
            yoklayici.itilen_kaydi_yaz(conn, self._kayit(kaydedilme_saati="14:10:00"), "10-A")
            yoklayici.itilen_kaydi_yaz(conn, self._kayit(kaydedilme_saati="14:05:00", durumlar={"7": "yok"}), "10-A")
            s = conn.execute("SELECT * FROM dyk_yoklama").fetchone()
        finally:
            conn.close()
        self.assertEqual(s["kaydedilme_saati"], "14:10:00")

    def test_sinif_kaydi_degismedi(self):
        conn = db.baglanti()
        try:
            sonuc = yoklayici.itilen_kaydi_yaz(conn, self._kayit(sinif="10-A", durumlar={"7": "yok"}), "10-A")
        finally:
            conn.close()
        self.assertEqual(sonuc, (True, [7]))
        self.assertEqual((self._say("yoklama_onbellek"), self._say("dyk_yoklama")), (1, 0))

    def test_tablo_beyaz_liste(self):
        conn = db.baglanti()
        try:
            with self.assertRaises(ValueError):
                yoklayici.onbellege_yaz(conn, TARIH, KOD, 1, "alindi", [], [], None, None, tablo="oturumlar")
        finally:
            conn.close()


class TestYapilandirma(DykTemel):
    def test_derslik_eslesen_tahtada_dolu(self):
        y = tahta_api.yapilandirma_olustur("10-A")
        self.assertEqual(list(y["dyk"]), [KOD])
        r = json.loads(y["dyk"][KOD])
        self.assertEqual((r["sinif"], r["ad"]), (KOD, "11. sınıf Coğrafya"))
        self.assertEqual(json.loads(y["dyk_program"])["oturumlar"][0]["kod"], KOD)
        self.assertEqual(list(y["kulupler"]), [])  # mevcut anahtar etkilenmez

    def test_eslesmeyen_ve_sinifsiz_tahta_bos(self):
        conn = db.baglanti()
        conn.execute("INSERT INTO tahtalar (ad, ip, ssh_kullanici, sinif_id) VALUES ('9-A', '10.0.0.3', 'o', 2)")
        conn.execute("INSERT INTO tahtalar (ad, ip, ssh_kullanici) VALUES ('fenlab', '10.0.0.2', 'o')")
        conn.commit()
        conn.close()
        for tahta in ("9-A", "fenlab"):
            y = tahta_api.yapilandirma_olustur(tahta)
            self.assertEqual(y["dyk"], {})
            self.assertIsNone(y["dyk_program"])

    def test_dosya_yoksa_bos(self):
        dyk.DYK_DOSYASI = Path(self._tmp.name) / "yok.json"
        y = tahta_api.yapilandirma_olustur("10-A")
        self.assertEqual(y["dyk"], {})
        self.assertIsNone(y["dyk_program"])


class TestSayfa(DykTemel):
    def _sayfa(self, giris=True, **sorgu):
        scope = {"type": "http", "method": "GET", "path": "/dyk-yoklama", "headers": [],
                 "query_string": b"", "client": ("127.0.0.1", 1)}
        with patch("auth.dogrula", return_value=giris):
            return asyncio.run(dyk_yoklama.dyk_yoklama_sayfa(Request(scope), **sorgu))

    def test_oturumsuz_yonlendirir(self):
        r = self._sayfa(giris=False)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/giris"))

    def test_bos_gun(self):
        self.assertIn("Bu tarihte DYK yoklaması yok", self._sayfa(tarih="2026-11-01").body.decode())

    def test_dolu_gun(self):
        conn = db.baglanti()
        yoklayici.itilen_kaydi_yaz(conn, self._kayit(), "10-A")
        conn.close()
        html = self._sayfa(tarih=TARIH).body.decode()
        self.assertIn("11. sınıf Coğrafya", html)
        self.assertIn("Ayşe Örnek", html)
        self.assertIn("Deniz Deneme", html)
        self.assertNotIn(KOD, html)

    def test_gecersiz_tarih_bugune_duser(self):
        conn = db.baglanti()
        yoklayici.itilen_kaydi_yaz(conn, self._kayit(), "10-A")
        conn.close()
        self.assertIn("11. sınıf Coğrafya", self._sayfa(tarih="bozuk").body.decode())


if __name__ == "__main__":
    unittest.main()
