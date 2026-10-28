"""okul_sql.py + /api/okul/sql testleri (unittest; PostgreSQL/yoklama DB'si sahte tablolarla)."""

import asyncio
import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

import okul_bilgisi as ob
import okul_sql as os_

TABLOLAR = {
    "ogrenci": (["okul_no", "ad_soyad", "telefon"], [(101, "Ayşe Yılmaz", "555"), (102, "Mehmet Demir", "556")]),
    "veli": (["id", "ad_soyad", "telefon"], [(1, "Selma Yılmaz", "557")]),
    "veli_ogrenci": (["veli_id", "okul_no", "yakinlik"], [(1, 101, "Anne")]),
    "yoklama_onbellek": (["tarih", "sinif", "ders_no", "durum", "yok_isimleri"],
                         [("2026-10-23", "9-A", 1, "alindi", '["Ayşe Yılmaz"]')]),
}


def cal(sorgu, **kw):
    return os_.calistir(sorgu, TABLOLAR, **kw)


class TestCalistir(unittest.TestCase):
    def test_join_ve_telefon(self):
        r = cal("SELECT o.ad_soyad, v.ad_soyad AS veli, v.telefon FROM ogrenci o "
                "JOIN veli_ogrenci vo ON vo.okul_no=o.okul_no JOIN veli v ON v.id=vo.veli_id")
        self.assertEqual(r["kolonlar"], ["ad_soyad", "veli", "telefon"])
        self.assertEqual(r["satirlar"], [["Ayşe Yılmaz", "Selma Yılmaz", "557"]])

    def test_json_each_yoklama(self):
        r = cal("SELECT j.value FROM yoklama_onbellek y, json_each(y.yok_isimleri) j")
        self.assertEqual(r["satirlar"], [["Ayşe Yılmaz"]])

    def test_ara_turkce_harf_ve_buyuk_kucuk_duyarsiz(self):
        T = {"personel": (["id", "ad_soyad"], [(1, "KARAKOÇ AYŞE MERVE"), (2, "ÇİÇEK AYŞE"), (3, "IŞIK ALİ")])}
        for aranan, beklenen in (("ayşe", 2), ("AYSE", 2), ("cicek", 1), ("ışık", 1), ("isik", 1), ("yok", 0)):
            r = os_.calistir(f"SELECT count(*) FROM personel WHERE ara(ad_soyad, '{aranan}')", T)
            self.assertEqual(r["satirlar"][0][0], beklenen, aranan)

    def test_like_turkce_duyarsiz(self):
        T = {"personel": (["id", "ad_soyad"], [(1, "KARAKOÇ AYŞE MERVE"), (2, "ÇİÇEK AYŞE"), (3, "IŞIK ALİ"), (4, "A_B 50%")])}
        for kalip, beklenen in (("%Ayşe%", 2), ("%ayse%", 2), ("ayşe%", 0), ("%çiçek%", 1), ("%IŞIK%", 1), ("%isik%", 1),
                                ("_ŞIK ALİ", 1), ("%yok%", 0)):
            r = os_.calistir(f"SELECT count(*) FROM personel WHERE ad_soyad LIKE '{kalip}'", T)
            self.assertEqual(r["satirlar"][0][0], beklenen, kalip)
        r = os_.calistir("SELECT count(*) FROM personel WHERE ad_soyad LIKE '%\\%' ESCAPE '\\'", T)
        self.assertEqual(r["satirlar"][0][0], 1)  # kaçışlı % = gerçek %

    def test_noktalı_virgul_ve_bosluk_tolere_edilir(self):
        self.assertEqual(len(cal("  SELECT * FROM ogrenci ;  ")["satirlar"]), 2)

    def test_yazma_ve_ddl_reddedilir(self):
        for q in ("DELETE FROM ogrenci", "UPDATE ogrenci SET ad_soyad='x'", "DROP TABLE ogrenci",
                  "INSERT INTO veli VALUES (9,'x','y')", "CREATE TABLE x (a)",
                  "ATTACH DATABASE '/tmp/x.db' AS x", "PRAGMA table_info(ogrenci)"):
            with self.assertRaises(os_.SqlHatasi, msg=q):
                cal(q)

    def test_izinsiz_tablo_ve_sqlite_master(self):
        for q in ("SELECT * FROM sqlite_master", "SELECT * FROM oturum", "SELECT * FROM kullanici"):
            with self.assertRaises(os_.SqlHatasi, msg=q):
                cal(q)

    def test_birden_cok_ifade_reddedilir(self):
        with self.assertRaises(os_.SqlHatasi):
            cal("SELECT 1; DELETE FROM ogrenci")

    def test_load_extension_yasak(self):
        with self.assertRaises(os_.SqlHatasi):
            cal("SELECT load_extension('x')")

    def test_satir_siniri(self):
        r = cal("WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM s LIMIT 1000) SELECT n FROM s", azami_satir=5)
        self.assertEqual(len(r["satirlar"]), 5)
        self.assertTrue(r["kesildi"])

    def test_zaman_asimi(self):
        with self.assertRaises(os_.SqlHatasi) as e:
            cal("WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM s) SELECT count(*) FROM s", sure_sn=0.2)
        self.assertIn("bitmedi", str(e.exception))

    def test_sql_hatasi_modele_okunur_metin(self):
        with self.assertRaises(os_.SqlHatasi) as e:
            cal("SELECT yok_kolon FROM ogrenci")
        self.assertIn("yok_kolon", str(e.exception))

    def test_bos_sorgu(self):
        with self.assertRaises(os_.SqlHatasi):
            cal("   ")


class TestDosyaTablolari(unittest.TestCase):
    def test_ogretmen_programi_ve_kazanim(self):
        T = {
            **os_.ogretmen_programi_tablosu(
                {"9-A": {"pazartesi": {"1": ["KAYA AYŞE"], "2": ["KAYA AYŞE"]}, "cuma": {"3": ["DEMİR ALİ"]}}},
                {1: {"baslangic": "08:10", "bitis": "08:50"}}),
            **os_.kazanim_tablosu({"haftalar": {"1": "2026-09-14"},
                                   "kazanimlar": {"9": {"biyoloji": {"1": "Hücre zarı"}}}}),
        }
        r = os_.calistir("SELECT ogretmen, gun, ders_no, baslangic FROM ogretmen_programi WHERE ara(ogretmen,'ayse') ORDER BY ders_no", T)
        self.assertEqual(r["satirlar"], [["KAYA AYŞE", 1, 1, "08:10"], ["KAYA AYŞE", 1, 2, None]])  # personel_esle uygulanmadan: kolon sırası değişmez
        r = os_.calistir("SELECT metin, hafta_baslangic FROM kazanim WHERE seviye='9' AND ders='biyoloji'", T)
        self.assertEqual(r["satirlar"], [["Hücre zarı", "2026-09-14"]])

    def test_personel_esle_ad_sirasindan_bagimsiz(self):
        T = {
            "personel": (["id", "ad_soyad", "gorev"], [(7, "GÖZDE KAHRİMAN GÖKDOĞAN", "diger"), (8, "AYŞE ÇİÇEK", "ogretmen"),
                                                       (9, "ALİ VELİ", "ogretmen"), (10, "VELİ ALİ", "ogretmen")]),
            **os_.ogretmen_programi_tablosu(
                {"12-A": {"pazartesi": {"1": ["KAHRİMAN GÖKDOĞAN GÖZDE", "ÇİÇEK AYŞE", "YOK KİŞİ", "ALİ VELİ"]}}}, {}),
        }
        T["sinif"] = (["id", "ad"], [(1, "12-A")])
        T["ders_programi"] = (["sinif_id", "gun", "ders_no", "ders"], [(1, 1, 1, "Fizik")])
        r = os_.calistir("SELECT ogretmen, personel_id, ders FROM ogretmen_programi ORDER BY ogretmen", os_.personel_esle(T))
        self.assertEqual(r["satirlar"], [["ALİ VELİ", None, "Fizik"], ["KAHRİMAN GÖKDOĞAN GÖZDE", 7, "Fizik"],
                                         ["YOK KİŞİ", None, "Fizik"], ["ÇİÇEK AYŞE", 8, "Fizik"]])
        # personel yoksa tablo olduğu gibi kalır (dosya-only test ortamı)
        self.assertEqual(os_.personel_esle({"x": ([], [])}), {"x": ([], [])})

    def test_simdi_tablosu(self):
        T = os_.simdi_tablosu({"tarih": "2026-10-26", "saat": "09:10", "gun": "Pazartesi", "durum": "ders", "ders_no": 2}, 1)
        r = os_.calistir("SELECT gun, durum, ders_no, aciklama FROM simdi", T)
        self.assertEqual(r["satirlar"], [[1, "ders", 2, "2. ders saati"]])
        T = os_.simdi_tablosu({"tarih": "2026-10-25", "saat": "20:00", "gun": "Pazar", "durum": "okul_disi", "ders_no": None}, 7)
        self.assertEqual(os_.calistir("SELECT durum, ders_no FROM simdi", T)["satirlar"], [["okul_disi", None]])

    def test_eksik_dosya_bos_tablo(self):
        T = {**os_.ogretmen_programi_tablosu({}, {}), **os_.kazanim_tablosu({})}
        self.assertEqual(os_.calistir("SELECT count(*) FROM kazanim", T)["satirlar"], [[0]])


class _Istek:
    def __init__(self, rol="admin", govde=None, host="127.0.0.1", anahtar="k"):
        self.client = type("C", (), {"host": host})()
        self.headers = {"X-Farabi-Okul-Key": anahtar, "X-Farabi-Rol": rol, "X-Farabi-Kullanici": "a@x"}
        self._govde = govde

    async def json(self):
        if self._govde is None:
            raise ValueError("boş")
        return self._govde


AYAR = {"anahtar": "k", "sql_dsn": "postgresql://x"}


def uc(istek):
    with patch.object(ob, "_ayar", return_value=AYAR), \
         patch.object(os_, "pg_tablolari", return_value={k: v for k, v in TABLOLAR.items() if k != "yoklama_onbellek"}), \
         patch.object(os_, "yoklama_tablolari", return_value={"yoklama_onbellek": TABLOLAR["yoklama_onbellek"]}), \
         patch.object(os_, "sms_tablolari", return_value={}), \
         patch.object(os_, "tc_tablosu", return_value={}), \
         patch.object(ob, "_dosya_tablolari", return_value={}):
        return asyncio.run(ob.sql(istek))


class TestUc(unittest.TestCase):
    def test_admin_sorgu_basarili(self):
        r = uc(_Istek(govde={"sorgu": "SELECT count(*) FROM ogrenci"}))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(r.body)["satirlar"], [[2]])

    def test_admin_olmayan_403(self):
        with self.assertRaises(HTTPException) as e:
            uc(_Istek(rol="user", govde={"sorgu": "SELECT 1"}))
        self.assertEqual(e.exception.status_code, 403)

    def test_yanlis_anahtar_401(self):
        with self.assertRaises(HTTPException) as e:
            uc(_Istek(anahtar="yanlis", govde={"sorgu": "SELECT 1"}))
        self.assertEqual(e.exception.status_code, 401)

    def test_dsn_yoksa_503(self):
        with patch.object(ob, "_ayar", return_value={"anahtar": "k"}), self.assertRaises(HTTPException) as e:
            asyncio.run(ob.sql(_Istek(govde={"sorgu": "SELECT 1"})))
        self.assertEqual(e.exception.status_code, 503)

    def test_gecersiz_govde_400(self):
        with self.assertRaises(HTTPException) as e:
            uc(_Istek(govde={"x": 1}))
        self.assertEqual(e.exception.status_code, 400)

    def test_azami_satir_parametresi(self):
        q = "WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM s LIMIT 500) SELECT n FROM s"
        self.assertEqual(len(json.loads(uc(_Istek(govde={"sorgu": q})).body)["satirlar"]), 200)  # varsayılan sınır
        r = json.loads(uc(_Istek(govde={"sorgu": q, "azami_satir": 450})).body)
        self.assertEqual(len(r["satirlar"]), 450)
        self.assertTrue(r["kesildi"])
        r = json.loads(uc(_Istek(govde={"sorgu": q, "azami_satir": 99999})).body)  # 2000'e kırpılır → 500 satırın hepsi
        self.assertEqual(len(r["satirlar"]), 500)
        self.assertFalse(r["kesildi"])
        r = json.loads(uc(_Istek(govde={"sorgu": q, "azami_satir": "x"})).body)  # geçersiz → varsayılan
        self.assertEqual(len(r["satirlar"]), 200)

    def test_yasak_sorgu_400_hata_metni(self):
        r = uc(_Istek(govde={"sorgu": "DELETE FROM ogrenci"}))
        self.assertEqual(r.status_code, 400)
        self.assertIn("İzin yok", json.loads(r.body)["hata"])



class TestSmsTc(unittest.TestCase):
    def test_sms_tablolari_okunur(self):
        import os
        import sqlite3
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            yol = os.path.join(d, "s.db")
            c = sqlite3.connect(yol)
            c.executescript("CREATE TABLE kisiler (id, ad_soyad, telefon); CREATE TABLE siniflar (id, ad);"
                            "CREATE TABLE gonderimler (id, telefon, durum); INSERT INTO kisiler VALUES (1,'Ayşe','5551112233');")
            c.commit(); c.close()
            t = os_.sms_tablolari(yol)
            self.assertEqual(set(t), set(os_.SMS_TABLOLARI))
            self.assertEqual(os_.calistir("SELECT telefon FROM kisiler", t)["satirlar"], [["5551112233"]])

    def test_sms_db_yoksa_sql_hatasi(self):
        with self.assertRaises(os_.SqlHatasi):
            os_.sms_tablolari("/yok/yok.db")

    def test_tc_tablosu_xlsx(self):
        import os
        import tempfile
        import zipfile
        ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        basliklar = ["OKUL NO", "ÖĞRENCİ AD-SOYAD", "ANNE AD-SOYAD", "BABA AD-SOYAD", "ÖĞRENCİ TC", "ANNE TC", "BABA TC"]
        ortak = f'<sst {ns}>' + "".join(f"<si><t>{b}</t></si>" for b in basliklar) + "</sst>"
        satir1 = "".join(f'<c r="{c}2" t="s"><v>{i}</v></c>' for i, c in enumerate("ABCDEFG"))
        veri = ('<c r="A3"><v>42</v></c><c r="B3" t="inlineStr"><is><t>AYŞE DEMİR</t></is></c>'
                '<c r="E3" t="inlineStr"><is><t>12345678901</t></is></c><c r="F3" t="inlineStr"><is><t>10987654321</t></is></c>')
        sayfa = f'<worksheet {ns}><sheetData><row r="1"/><row r="2">{satir1}</row><row r="3">{veri}</row></sheetData></worksheet>'
        with tempfile.TemporaryDirectory() as d:
            with zipfile.ZipFile(os.path.join(d, "9-A.xlsx"), "w") as z:
                z.writestr("xl/sharedStrings.xml", ortak)
                z.writestr("xl/worksheets/sheet1.xml", sayfa)
            t = os_.tc_tablosu(d)
            self.assertEqual(t["tc_kimlik"][1], [("9-A", "42", "AYŞE DEMİR", "12345678901", None, "10987654321", None, None)])
            self.assertEqual(os_.calistir("SELECT ogrenci_tc FROM tc_kimlik WHERE okul_no='42'", t)["satirlar"], [["12345678901"]])

    def test_ogrenci_genis_birlestirir(self):
        t = {
            "ogrenci": (["okul_no", "ad_soyad", "cinsiyet", "dogum_tarihi", "telefon", "aktif"], [(42, "AYŞE DEMİR", "K", None, None, 1)]),
            "sinif": (["id", "ad"], [(1, "9-A")]),
            "sinif_atama": (["okul_no", "sinif_id"], [(42, 1)]),
            "tc_kimlik": (["sinif", "okul_no", "ogrenci_tc", "anne_ad_soyad", "anne_tc", "baba_ad_soyad", "baba_tc"],
                          [("9-A", "42", "11111111111", "FATMA DEMİR", "22222222222", None, None)]),
            "kisiler": (["id", "ad_soyad", "tur", "okul_no", "dogum_tarihi", "telefon", "ogrenci_kisi_id", "veli_rol"],
                        [(1, "AYŞE DEMİR", "ogrenci", 42, "2010-05-01", "5550000001", None, None),
                         (2, "FATMA DEMİR", "veli", None, None, "5550000002", 1, "Anne"),
                         (3, "ALİ DEMİR", "veli", None, None, "5550000003", 1, "Baba")]),
        }
        k, r = os_.ogrenci_genis(t)["ogrenci_genis"]
        s = dict(zip(k, r[0], strict=True))
        self.assertEqual((s["sinif"], s["dogum_tarihi"], s["telefon"], s["ogrenci_tc"], s["anne_tc"], s["anne_telefon"], s["baba_telefon"], s["baba_ad_soyad"]),
                         ("9-A", "2010-05-01", "5550000001", "11111111111", "22222222222", "5550000002", "5550000003", "ALİ DEMİR"))

    def test_ogretmen_yonetici_dersi_varsa_dahil(self):
        t = {
            "personel": (["id", "ad_soyad", "telefon", "dogum_tarihi", "gorev", "aktif", "brans"],
                         [(1, "ARZU ORAL", None, None, "yonetici", True, "İngilizce"), (2, "VELİ HOCA", None, None, "ogretmen", True, "Fizik"),
                          (3, "ÇAY Cİ", None, None, "diger", True, None)]),
            "ogretmen_programi": (["ogretmen", "personel_id", "sinif", "ders", "gun", "ders_no", "baslangic", "bitis"],
                                  [("ORAL ARZU", 1, "9-A", "ingilizce", 1, 1, None, None), ("ORAL ARZU", 1, "9-A", "ingilizce", 1, 2, None, None)]),
        }
        _, r = os_.ogretmen_tablosu(t)["ogretmen"]
        self.assertEqual([(x[0], x[6]) for x in r], [(1, 2), (2, 0)])

    def test_tc_dizin_yoksa_bos(self):
        self.assertEqual(os_.tc_tablosu("/yok/yok")["tc_kimlik"][1], [])

if __name__ == "__main__":
    unittest.main()
