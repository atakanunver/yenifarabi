"""Kulüp yoklaması (2026-10-22): içe aktarma ayrıştırıcısı, yapılandırma
filtresi, kayıt alımı (kulup_yoklama, bildirim yok), tahta istemcisi temizliği,
admin SSH senkronu ve /kulup-yoklama sayfası."""

import asyncio
import hashlib
import json
import sys
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import admin
import db
import kulup_yoklama
import kulupler
import tahta_api
import yoklayici
from fastapi.requests import Request

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kulup_ice_aktar as ice  # noqa: E402

import tahta_istemci as ti  # noqa: E402

TARIH = "2026-10-06"
TOKEN = "token-10a"

BEYAZAY = {
    "kod": "KULUP-BEYAZAY", "ad": "Beyazay Kulübü", "danisman": "X", "sinif": "10-A",
    "uyeler": [{"no": 206, "ad_soyad": "Deniz Deneme", "sinif": "9-A"},
               {"no": 7, "ad_soyad": "Can Kaya", "sinif": "10-A"}],
}


def _p(metin):
    return f"<w:p><w:r><w:t>{metin}</w:t></w:r></w:p>"


def _tr(*h):
    return "<w:tr>" + "".join(f"<w:tc>{_p(x)}</w:tc>" for x in h) + "</w:tr>"


def sahte_docx(yol, ad="SİBERAY KULÜBÜ", sinif="DERS İŞLENECEK SINIF 11-B ", satirlar=()):
    xml = (
        '<w:document xmlns:w="x"><w:body>'
        + _p(ad) + _p("DANIŞMAN ÖĞRETMEN: ALİ VELİ") + _p(sinif) + _p("açıklama KULÜP LİSTESİ")
        + "<w:tbl>" + _tr("SIRA", "SINIF", "NO", "AD-SOYAD")
        + "".join(_tr(*s) for s in satirlar) + "</w:tbl></w:body></w:document>"
    )
    with zipfile.ZipFile(yol, "w") as z:
        z.writestr("word/document.xml", xml)


class TestIceAktar(unittest.TestCase):
    def test_docx_ayristir(self):
        with TemporaryDirectory() as d:
            yol = Path(d) / "k.docx"
            sahte_docx(yol, satirlar=[("1", "9/A", "206", "DENİZ DENEME"), ("2", "10/b", "7", "CAN &amp; KAYA")])
            r = ice.docx_ayristir(yol)
        self.assertEqual((r["ad"], r["danisman"], r["sinif"]), ("Siberay Kulübü", "ALİ VELİ", "11-B"))
        self.assertEqual([(s["sinif"], s["no"]) for s in r["satirlar"]], [("9-A", 206), ("10-B", 7)])
        self.assertEqual(r["satirlar"][1]["ad_soyad"], "CAN & KAYA")

    def test_baslik_ve_kod(self):
        self.assertEqual(ice._baslik_yap("TABİAT VE YAŞANABİLİR ÇEVRE KULÜBÜ"),
                         "Tabiat ve Yaşanabilir Çevre Kulübü")
        self.assertEqual(ice.kod_uret("Tabiat ve Yaşanabilir Çevre Kulübü"), "KULUP-TABIAT")
        self.assertEqual(ice.kod_uret("Siberay Kulübü"), "KULUP-SIBERAY")
        self.assertEqual(ice.kod_uret("Yeşilay Kulübü"), "KULUP-YESILAY")

    def test_eslestir(self):
        pano = {("9-A", 206): ("Deniz Deneme", 1), ("9-A", 5): ("Eski Öğrenci", 0),
                ("10-A", 7): ("Can Kaya", 1), ("9-B", 9): ("Zeynep Ay", 1)}
        adlar = {206: [("9-A", "Deniz Deneme")], 7: [("10-A", "Can Kaya")], 9: [("9-B", "Zeynep Ay")]}
        satirlar = [
            {"sira": 1, "sinif": "9-A", "no": 206, "ad_soyad": "DENİZ DENEME"},   # eşleşir
            {"sira": 2, "sinif": "9-A", "no": 5, "ad_soyad": "ESKİ ÖĞRENCİ"},      # pasif
            {"sira": 3, "sinif": "10-A", "no": 7, "ad_soyad": "CAN KAYAN"},        # ad uyuşmaz
            {"sira": 4, "sinif": "9-A", "no": 9, "ad_soyad": "ZEYNEP AY"},         # başka sınıf, ad aynı
            {"sira": 5, "sinif": "9-A", "no": 99, "ad_soyad": "YOK KİŞİ"},         # bulunamaz
        ]
        uyeler, say = ice.eslestir(satirlar, pano, adlar)
        self.assertEqual([(u["no"], u["ad_soyad"], u["sinif"]) for u in uyeler],
                         [(206, "Deniz Deneme", "9-A"), (7, "Can Kaya", "10-A"), (9, "Zeynep Ay", "9-B")])
        self.assertEqual({k: v for k, v in say.items() if k != "notlar"},
                         dict(eslesen=3, bulunamayan=1, pasif=1, ad_uyusmazligi=1, sinif_farki=1))


class KulupTemel(unittest.TestCase):
    def setUp(self):
        self._saat = patch("zil.simdi_istanbul", return_value=datetime(
            2026, 10, 6, 12, 0, tzinfo=ZoneInfo("Europe/Istanbul")))
        self._saat.start()
        self.addCleanup(self._saat.stop)
        self._tmp = TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._eski = (db.DB_YOLU, tahta_api.TOKEN_DOSYASI, kulupler.KULUP_DOSYASI)
        db.DB_YOLU = tmp / "test.db"
        db.semayi_kur()
        tahta_api.TOKEN_DOSYASI = tmp / "tokenlar.json"
        tahta_api.TOKEN_DOSYASI.write_text(json.dumps(
            {"10-A": hashlib.sha256(TOKEN.encode()).hexdigest()}))
        kulupler.KULUP_DOSYASI = tmp / "kulupler.json"
        kulupler.KULUP_DOSYASI.write_text(json.dumps([BEYAZAY], ensure_ascii=False), encoding="utf-8")
        conn = db.baglanti()
        conn.execute("INSERT INTO siniflar (id, ad) VALUES (1, '10-A'), (2, '9-A')")
        conn.execute("INSERT INTO ogrenciler (sinif_id, no, ad_soyad) VALUES (1, 7, 'Can Kaya'), (2, 206, 'Deniz Deneme')")
        conn.execute("INSERT INTO tahtalar (ad, ip, ssh_kullanici, sinif_id) VALUES ('10-A', '10.0.0.1', 'o', 1)")
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_YOLU, tahta_api.TOKEN_DOSYASI, kulupler.KULUP_DOSYASI = self._eski
        self._tmp.cleanup()

    def _kayit(self, **kw):
        k = {"sinif": "KULUP-BEYAZAY", "tarih": TARIH, "ders_no": 7,
             "kaydedilme_saati": "14:00:00", "durumlar": {"206": "yok", "7": "izinli"}}
        k.update(kw)
        return k

    def _say(self, tablo):
        conn = db.baglanti()
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0]
        finally:
            conn.close()


class TestYapilandirma(KulupTemel):
    def test_yalniz_kendi_sinifinin_tahtasina(self):
        y = tahta_api.yapilandirma_olustur("10-A")
        self.assertEqual(list(y["kulupler"]), ["KULUP-BEYAZAY"])
        r = json.loads(y["kulupler"]["KULUP-BEYAZAY"])
        self.assertEqual((r["sinif"], r["ad"]), ("KULUP-BEYAZAY", "Beyazay Kulübü"))
        self.assertEqual(r["ogrenciler"][0], {"no": 206, "ad_soyad": "Deniz Deneme (9-A)"})
        self.assertTrue(ti.roster_gecerli(y["kulupler"]["KULUP-BEYAZAY"], "KULUP-BEYAZAY"))

    def test_baska_sinif_ve_siniflandirilmamis_tahta_bos(self):
        conn = db.baglanti()
        conn.execute("INSERT INTO tahtalar (ad, ip, ssh_kullanici, sinif_id) VALUES ('9-A', '10.0.0.3', 'o', 2)")
        conn.execute("INSERT INTO tahtalar (ad, ip, ssh_kullanici) VALUES ('fenlab', '10.0.0.2', 'o')")
        conn.commit()
        conn.close()
        self.assertEqual(tahta_api.yapilandirma_olustur("9-A")["kulupler"], {})
        self.assertEqual(tahta_api.yapilandirma_olustur("fenlab")["kulupler"], {})

    def test_dosya_yoksa_bos(self):
        kulupler.KULUP_DOSYASI = Path(self._tmp.name) / "yok.json"
        self.assertEqual(tahta_api.yapilandirma_olustur("10-A")["kulupler"], {})


class TestKayit(KulupTemel):
    def test_kulup_kaydi_ayri_tabloya_bildirim_yok(self):
        conn = db.baglanti()
        try:
            sonuc = yoklayici.itilen_kaydi_yaz(conn, self._kayit(), "10-A")
            self.assertEqual(sonuc, (True, []))
            s = conn.execute("SELECT * FROM kulup_yoklama").fetchone()
        finally:
            conn.close()
        self.assertEqual((s["sinif"], s["durum"], s["kaynak_tahta"]), ("KULUP-BEYAZAY", "alindi", "10-A"))
        self.assertEqual(json.loads(s["yok_isimleri"]), ["Deniz Deneme"])
        self.assertEqual(json.loads(s["izinli_isimleri"]), ["Can Kaya"])
        self.assertEqual(json.loads(s["yok_nolari"]), [206])
        self.assertEqual(self._say("yoklama_onbellek"), 0)

    def test_ayni_upsert_kurallari(self):
        conn = db.baglanti()
        try:
            yoklayici.itilen_kaydi_yaz(conn, self._kayit(kaydedilme_saati="14:10:00"), "10-A")
            yoklayici.itilen_kaydi_yaz(conn, self._kayit(kaydedilme_saati="14:05:00", durumlar={"7": "yok"}), "10-A")
            s = conn.execute("SELECT * FROM kulup_yoklama").fetchone()
        finally:
            conn.close()
        self.assertEqual(s["kaydedilme_saati"], "14:10:00")
        self.assertEqual(json.loads(s["yok_nolari"]), [206])

    def test_gecmis_gunun_kaydi_ezilmez(self):
        conn = db.baglanti()
        try:
            yoklayici.itilen_kaydi_yaz(conn, self._kayit(tarih="2026-10-05"), "10-A")
            sonuc = yoklayici.itilen_kaydi_yaz(
                conn, self._kayit(tarih="2026-10-05", kaydedilme_saati="15:00:00", durumlar={}), "10-A")
            s = conn.execute("SELECT * FROM kulup_yoklama").fetchone()
        finally:
            conn.close()
        self.assertEqual(sonuc, (True, []))
        self.assertEqual(s["kaydedilme_saati"], "14:00:00")

    def test_bilinmeyen_kod_reddedilir(self):
        conn = db.baglanti()
        try:
            self.assertEqual(yoklayici.itilen_kaydi_yaz(conn, self._kayit(sinif="KULUP-YOK"), "10-A"), (False, []))
        finally:
            conn.close()
        self.assertEqual(self._say("kulup_yoklama"), 0)

    def test_sinif_kaydi_degismedi(self):
        conn = db.baglanti()
        try:
            ok, bildir = yoklayici.itilen_kaydi_yaz(conn, self._kayit(sinif="10-A", durumlar={"7": "yok"}), "10-A")
        finally:
            conn.close()
        self.assertEqual((ok, bildir), (True, [7]))
        self.assertEqual((self._say("yoklama_onbellek"), self._say("kulup_yoklama")), (1, 0))


class TestAdminVeSayfa(KulupTemel):
    def test_ssh_temizligi_kulup_dosyalarini_korur(self):
        with patch("admin.ssh_istemci.komut_calistir", new=AsyncMock()) as sahte:
            asyncio.run(admin._tahtaya_roster_gonder(
                {"ip": "1.1.1.1", "ssh_kullanici": "o", "ad": "10-A"}, "10-A", b"{}"))
        komut = sahte.call_args.args[2]
        self.assertIn("! -name '10-A.json' ! -name 'KULUP-*' -delete", komut)

    def _sayfa(self, giris=True, **sorgu):
        scope = {"type": "http", "method": "GET", "path": "/kulup-yoklama", "headers": [],
                 "query_string": b"", "client": ("127.0.0.1", 1)}
        with patch("auth.dogrula", return_value=giris):
            return asyncio.run(kulup_yoklama.kulup_yoklama_sayfa(Request(scope), **sorgu))

    def test_sayfa(self):
        self.assertEqual(self._sayfa(giris=False).status_code, 303)
        self.assertIn("yok", self._sayfa(tarih=TARIH).body.decode())
        conn = db.baglanti()
        yoklayici.itilen_kaydi_yaz(conn, self._kayit(), "10-A")
        conn.close()
        html = self._sayfa(tarih=TARIH).body.decode()
        self.assertIn("Beyazay Kulübü", html)
        self.assertIn("Deniz Deneme", html)
        self.assertIn("Bu tarihte kulüp yoklaması yok", self._sayfa(tarih="2026-10-01").body.decode())
        self.assertIn("Beyazay Kulübü", self._sayfa(tarih="bozuk").body.decode())  # bugüne düşer


class TestIstemciTemizligi(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self._eski = (ti.ROSTER_DIR, ti.YEDEK_DIR, ti.DATA_DIR)
        ti.ROSTER_DIR, ti.YEDEK_DIR, ti.DATA_DIR = tmp / "roster", tmp / "yedek", tmp
        ti.ROSTER_DIR.mkdir()
        self.addCleanup(lambda: setattr(ti, "ROSTER_DIR", self._eski[0]) or setattr(ti, "YEDEK_DIR", self._eski[1])
                        or setattr(ti, "DATA_DIR", self._eski[2]))
        self.addCleanup(self._tmp.cleanup)

    def _roster(self, kod, ad="X"):
        return json.dumps({"sinif": kod, "ad": ad, "ogrenciler": [{"no": 1, "ad_soyad": "A"}]})

    def _adlar(self):
        return sorted(p.name for p in ti.ROSTER_DIR.glob("*.json"))

    def test_kulup_yazilir_sinif_temizligi_dokunmaz_eskisi_yedeklenir(self):
        (ti.ROSTER_DIR / "9-A.json").write_text("{}")             # eski sınıf: silinmeli
        (ti.ROSTER_DIR / "KULUP-ESKI.json").write_text("{}")      # yapılandırmadan düştü: yedeğe
        (ti.ROSTER_DIR / "KULUP-KALAN.json").write_text("{}")     # geçersiz geldi: dokunulmaz
        ti.yapilandirmayi_uygula({
            "sinif": "10-A", "roster": self._roster("10-A"),
            "kulupler": {"KULUP-BEYAZAY": self._roster("KULUP-BEYAZAY", "Beyazay Kulübü"),
                         "KULUP-KALAN": "bozuk json", "ZZZ": self._roster("ZZZ")},
        })
        self.assertEqual(self._adlar(), ["10-A.json", "KULUP-BEYAZAY.json", "KULUP-KALAN.json"])
        yedekler = sorted(p.name.split("_", 1)[1] for p in ti.YEDEK_DIR.glob("*"))
        self.assertIn("KULUP-ESKI.json", yedekler)
        self.assertIn("9-A.json", yedekler)

    def test_kulupler_anahtari_yoksa_dokunulmaz(self):
        (ti.ROSTER_DIR / "KULUP-ESKI.json").write_text("{}")
        ti.yapilandirmayi_uygula({"sinif": "10-A", "roster": self._roster("10-A")})
        self.assertEqual(self._adlar(), ["10-A.json", "KULUP-ESKI.json"])

    def test_bos_kulupler_hepsini_yedege_alir_roster_none_sinifa_dokunmaz(self):
        (ti.ROSTER_DIR / "9-A.json").write_text("{}")
        (ti.ROSTER_DIR / "KULUP-ESKI.json").write_text("{}")
        ti.yapilandirmayi_uygula({"sinif": None, "roster": None, "kulupler": {}})
        self.assertEqual(self._adlar(), ["9-A.json"])

    def test_surum(self):
        self.assertEqual(ti.SURUM, "5")


if __name__ == "__main__":
    unittest.main()
