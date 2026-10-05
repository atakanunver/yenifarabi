"""okul_bilgisi.py testleri (/api/okul/*). Route fonksiyonları doğrudan
çağrılır (test_ajan_api.py deseni); saat, ders programı, zil ve sınıf
listeleri geçici dosyalardan."""

import asyncio
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import okul_bilgisi as ob
import zil
from fastapi import HTTPException
from fastapi.requests import Request

ANAHTAR = "okul-anahtari-xyz"
ZIL = {
    "dersler": [
        {"no": 1, "baslangic": "08:10", "bitis": "08:50"},
        {"no": 2, "baslangic": "09:00", "bitis": "09:40"},
    ],
    "ders_gunleri": [1, 2, 3, 4, 5],
}
PROGRAM = {
    "siniflar": {
        "11-A": {
            "pazartesi": {"1": "kimya", "2": "fizik"},
            "sali": {"1": "tarih", "2": "tarih"},
        }
    }
}
ROSTER = {
    "sinif": "11-A",
    "ogrenciler": [
        {"no": "101", "ad_soyad": "Ayşe Yılmaz", "cinsiyet": "K"},
        {"no": "102", "ad_soyad": "Mehmet Demir", "cinsiyet": "E"},
    ],
}
# 2026-10-05 Pazartesi
PAZARTESI_0820 = datetime(2026, 10, 5, 8, 20, tzinfo=zil.ISTANBUL)
PAZARTESI_0855 = datetime(2026, 10, 5, 8, 55, tzinfo=zil.ISTANBUL)
PAZAR = datetime(2026, 10, 4, 21, 0, tzinfo=zil.ISTANBUL)


def _istek(istemci=("127.0.0.1", 5555), basliklar=None):
    h = [(k.lower().encode(), v.encode()) for k, v in (basliklar or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/okul/x",
            "headers": h,
            "client": istemci,
        }
    )


def _b(**ek):
    return {"X-Farabi-Okul-Key": ANAHTAR, **ek}


class Taban(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "okul.json").write_text(
            json.dumps(
                {
                    "anahtar": ANAHTAR,
                    "ogrenci_izinli": ["idare@farabi.local", "ogretmen@farabi.local"],
                }
            ),
            encoding="utf-8",
        )
        (self.tmp / "zil.json").write_text(json.dumps(ZIL), encoding="utf-8")
        (self.tmp / "ders_programi.json").write_text(
            json.dumps(PROGRAM), encoding="utf-8"
        )
        (self.tmp / "roster").mkdir()
        (self.tmp / "roster" / "11-A.json").write_text(
            json.dumps(ROSTER), encoding="utf-8"
        )
        yamalar = [
            patch.object(ob, "OKUL_AYAR_YOLU", self.tmp / "okul.json"),
            patch.object(ob, "ROSTER_DIZINI", self.tmp / "roster"),
            patch.object(
                ob.ders_programi,
                "DERS_PROGRAMI_DOSYASI",
                self.tmp / "ders_programi.json",
            ),
            patch.object(zil, "ZIL_DOSYASI", self.tmp / "zil.json"),
        ]
        for y in yamalar:
            y.start()
            self.addCleanup(y.stop)
        ob.ders_programi.yenile()
        zil.yenile()
        self.addCleanup(ob.ders_programi.yenile)
        self.addCleanup(zil.yenile)

    def saat(self, an):
        y = patch.object(zil, "simdi_istanbul", lambda: an)
        y.start()
        self.addCleanup(y.stop)

    def cagir(self, fonk, *a, **k):
        r = asyncio.run(fonk(*a, **k))
        return json.loads(r.body)


class TestErisim(Taban):
    def test_uzak_istemci_403(self):
        with self.assertRaises(HTTPException) as c:
            asyncio.run(ob.simdi(_istek(istemci=("192.168.23.50", 1), basliklar=_b())))
        self.assertEqual(c.exception.status_code, 403)

    def test_anahtarsiz_401(self):
        with self.assertRaises(HTTPException) as c:
            asyncio.run(ob.simdi(_istek()))
        self.assertEqual(c.exception.status_code, 401)

    def test_ajan_anahtari_GECMEZ(self):
        with self.assertRaises(HTTPException) as c:
            asyncio.run(ob.simdi(_istek(basliklar={"X-Farabi-Ajan-Key": ANAHTAR})))
        self.assertEqual(c.exception.status_code, 401)

    def test_ayar_dosyasi_yoksa_503(self):
        (self.tmp / "okul.json").unlink()
        with self.assertRaises(HTTPException) as c:
            asyncio.run(ob.simdi(_istek(basliklar=_b())))
        self.assertEqual(c.exception.status_code, 503)


class TestSimdi(Taban):
    def test_ders_sirasinda(self):
        self.saat(PAZARTESI_0820)
        v = self.cagir(ob.simdi, _istek(basliklar=_b()))
        self.assertEqual(v["tarih"], "2026-10-05")
        self.assertEqual(v["gun"], "Pazartesi")
        self.assertEqual(v["saat"], "08:20")
        self.assertEqual(v["durum"], "ders")
        self.assertEqual(v["ders_no"], 1)
        self.assertIn("1. ders", v["metin"])
        self.assertIn("5 Ekim 2026 Pazartesi", v["metin"])

    def test_teneffus(self):
        self.saat(PAZARTESI_0855)
        v = self.cagir(ob.simdi, _istek(basliklar=_b()))
        self.assertEqual(v["durum"], "teneffus")
        self.assertIn("teneffüs", v["metin"])

    def test_hafta_sonu_okul_disi(self):
        self.saat(PAZAR)
        v = self.cagir(ob.simdi, _istek(basliklar=_b()))
        self.assertEqual(v["durum"], "okul_disi")
        self.assertIn("Pazar", v["metin"])


class TestDersProgrami(Taban):
    def test_simdiki_ders(self):
        self.saat(PAZARTESI_0820)
        v = self.cagir(
            ob.ders_programi_ucu, _istek(basliklar=_b()), sinif="11-A", gun="simdi"
        )
        self.assertEqual(v["sinif"], "11-A")
        self.assertEqual(
            v["dersler"],
            [
                {
                    "no": 1,
                    "baslangic": "08:10",
                    "bitis": "08:50",
                    "ders": "kimya",
                    "simdi": True,
                }
            ],
        )

    def test_bugun(self):
        self.saat(PAZARTESI_0820)
        v = self.cagir(
            ob.ders_programi_ucu, _istek(basliklar=_b()), sinif="11a", gun="bugun"
        )
        self.assertEqual(v["sinif"], "11-A")
        self.assertEqual([d["ders"] for d in v["dersler"]], ["kimya", "fizik"])
        self.assertEqual([d["simdi"] for d in v["dersler"]], [True, False])

    def test_belirli_gun_turkce_karakterli(self):
        self.saat(PAZARTESI_0820)
        v = self.cagir(
            ob.ders_programi_ucu, _istek(basliklar=_b()), sinif="11-A", gun="Salı"
        )
        self.assertEqual(v["gun"], "Salı")
        self.assertEqual([d["ders"] for d in v["dersler"]], ["tarih", "tarih"])

    def test_hafta(self):
        self.saat(PAZARTESI_0820)
        v = self.cagir(
            ob.ders_programi_ucu, _istek(basliklar=_b()), sinif="11-A", gun="hafta"
        )
        self.assertEqual(sorted(v["hafta"]), ["Pazartesi", "Salı"])

    def test_hafta_sonu_bugun_bos(self):
        self.saat(PAZAR)
        v = self.cagir(
            ob.ders_programi_ucu, _istek(basliklar=_b()), sinif="11-A", gun="simdi"
        )
        self.assertEqual(v["dersler"], [])
        self.assertEqual(v["durum"], "okul_disi")

    def test_bilinmeyen_sinif_404_gecerlileri_listeler(self):
        with self.assertRaises(HTTPException) as c:
            asyncio.run(
                ob.ders_programi_ucu(_istek(basliklar=_b()), sinif="13-Z", gun="bugun")
            )
        self.assertEqual(c.exception.status_code, 404)
        self.assertIn("11-A", c.exception.detail["gecerli"])

    def test_gecersiz_gun_400(self):
        with self.assertRaises(HTTPException) as c:
            asyncio.run(
                ob.ders_programi_ucu(_istek(basliklar=_b()), sinif="11-A", gun="dün")
            )
        self.assertEqual(c.exception.status_code, 400)


class TestOgrenci(Taban):
    def ogr(self, eposta="idare@farabi.local", rol="user", **sorgu):
        return self.cagir(
            ob.ogrenci,
            _istek(basliklar=_b(**{"X-Farabi-Kullanici": eposta, "X-Farabi-Rol": rol})),
            **sorgu,
        )

    def test_idare_adla_bulur(self):
        v = self.ogr(ad="ayşe")
        self.assertEqual(
            v["ogrenciler"], [{"no": "101", "ad_soyad": "Ayşe Yılmaz", "sinif": "11-A"}]
        )

    def test_buyuk_kucuk_harf_turkce(self):
        self.assertEqual(len(self.ogr(ad="AYŞE YILMAZ")["ogrenciler"]), 1)
        self.assertEqual(
            len(self.ogr(ad="yilmaz")["ogrenciler"]), 1
        )  # ı/i farkı tolere edilir

    def test_numarayla_bulur(self):
        self.assertEqual(
            self.ogr(no="102")["ogrenciler"][0]["ad_soyad"], "Mehmet Demir"
        )

    def test_sinif_listesi(self):
        v = self.ogr(eposta="ogretmen@farabi.local", sinif="11-A")
        self.assertEqual(len(v["ogrenciler"]), 2)

    def test_cinsiyet_alani_donmez(self):
        self.assertNotIn("cinsiyet", self.ogr(sinif="11-A")["ogrenciler"][0])

    def test_admin_listede_olmasa_da_gecer(self):
        self.assertEqual(
            len(self.ogr(eposta="mudur@x", rol="admin", sinif="11-A")["ogrenciler"]), 2
        )

    def test_tahta_hesabi_403(self):
        with self.assertRaises(HTTPException) as c:
            self.ogr(eposta="tahta@farabi.local", sinif="11-A")
        self.assertEqual(c.exception.status_code, 403)

    def test_kullanici_basligi_yoksa_403(self):
        with self.assertRaises(HTTPException) as c:
            self.cagir(ob.ogrenci, _istek(basliklar=_b()), sinif="11-A")
        self.assertEqual(c.exception.status_code, 403)

    def test_bos_sorgu_400(self):
        with self.assertRaises(HTTPException) as c:
            self.ogr()
        self.assertEqual(c.exception.status_code, 400)

    def test_ogrenci_adi_loga_yazilmaz(self):
        with self.assertLogs("okul_bilgisi", level="INFO") as kayit:
            self.ogr(ad="ayşe")
        self.assertFalse(any("Ayşe" in s or "ayşe" in s for s in kayit.output))


if __name__ == "__main__":
    unittest.main()
