"""dyk_admin.py: /admin/dyk liste, düzenleme ve kaydetme uçları (uydurma veri).
Geçici SQLite ve geçici dyk.json; gerçek config/dyk.json'a ASLA dokunulmaz."""
import asyncio
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlencode

import db
import dyk
import dyk_admin
from fastapi import HTTPException
from starlette.requests import Request

ORNEK = {
    "siniflar": {
        "11": {"derslik": "10-A", "ad": "11. Sınıf DYK", "dersler": [
            {"kod": "DYK-11-COGRAFYA", "ad": "Coğrafya", "ogretmen": "Hoca A",
             "uyeler": [{"no": 5, "ad_soyad": "Deniz Deneme"}, {"no": 7, "ad_soyad": "Ayşe Örnek"}]}]},
        "12": {"derslik": "12-B", "ad": "12. Sınıf DYK", "dersler": [
            {"kod": "DYK-12-TARIH", "ad": "Tarih", "ogretmen": "Hoca B",
             "uyeler": [{"no": 9, "ad_soyad": "Can Sahte"}]}]},
    },
    "program": {
        "11": [{"gun": "pazartesi", "bas": "16:00", "bit": "17:30", "kod": "DYK-11-COGRAFYA", "ders_no": 1}],
        "12": [{"gun": "cuma", "bas": "16:00", "bit": "17:30", "kod": "DYK-12-TARIH", "ders_no": 1}],
    },
}


def _istek(yol, yontem="GET", govde=None, sorgu=b""):
    gonderildi = False

    async def al():
        nonlocal gonderildi
        if govde is None or gonderildi:
            return {"type": "http.disconnect"}
        gonderildi = True
        return {"type": "http.request", "body": urlencode(govde).encode(), "more_body": False}
    basliklar = [(b"content-type", b"application/x-www-form-urlencoded")] if govde is not None else []
    return Request({"type": "http", "method": yontem, "path": yol, "headers": basliklar,
                    "query_string": sorgu, "server": ("farabi.local", 80),
                    "scheme": "http", "root_path": ""}, al)


class Temel(unittest.TestCase):
    oturum = True

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        eski = db.DB_YOLU
        db.DB_YOLU = tmp / "test.db"
        self.addCleanup(setattr, db, "DB_YOLU", eski)
        db.semayi_kur()
        self.yol = tmp / "dyk.json"
        self.yol.write_text(json.dumps(ORNEK, ensure_ascii=False), encoding="utf-8")
        for yama in (patch.object(dyk_admin.auth, "dogrula", lambda r, c: self.oturum),
                     patch.object(dyk, "DYK_DOSYASI", self.yol)):
            yama.start()
            self.addCleanup(yama.stop)

    def kaydet(self, kod, govde):
        return asyncio.run(dyk_admin.dyk_uyelerini_kaydet(_istek(f"/admin/dyk/{kod}", "POST", govde), kod))

    def dosya(self):
        return self.yol.read_text(encoding="utf-8")


class TestSayfalar(Temel):
    def test_liste_iki_grup_sayilar_ve_program(self):
        r = asyncio.run(dyk_admin.dyk_listesi(_istek("/admin/dyk")))
        self.assertEqual(r.status_code, 200)
        h = r.body.decode()
        for parca in ("11. Sınıf DYK", "10-A tahtası", "12. Sınıf DYK", "12-B tahtası", "Coğrafya",
                      "Hoca A", "2 öğrenci", "1 öğrenci", "Pazartesi", "16:00–17:30", "Cuma",
                      'href="/admin/dyk/DYK-11-COGRAFYA"', 'href="/admin/dyk/DYK-12-TARIH"'):
            self.assertIn(parca, h)

    def test_duzenleme_sayfasi_alanlar_ve_bildirim(self):
        r = asyncio.run(dyk_admin.dyk_uyeleri(_istek("/admin/dyk/DYK-11-COGRAFYA"), "DYK-11-COGRAFYA"))
        h = r.body.decode()
        self.assertEqual(r.status_code, 200)
        self.assertIn('action="/admin/dyk/DYK-11-COGRAFYA"', h)
        self.assertRegex(h, r'<input[^>]*name="ogretmen"[^>]*value="Hoca A"')
        self.assertRegex(h, r'<input[^>]*name="no"[^>]*value="5"')
        self.assertRegex(h, r'<input[^>]*name="ad_soyad"[^>]*value="Deniz Deneme"')
        self.assertIn('id="satir-ekle"', h)
        self.assertNotIn("Kaydedildi.", h)
        r = asyncio.run(dyk_admin.dyk_uyeleri(
            _istek("/admin/dyk/DYK-11-COGRAFYA", sorgu=b"kaydedildi=1"), "DYK-11-COGRAFYA"))
        self.assertIn("Kaydedildi.", r.body.decode())

    def test_bilinmeyen_kod_404(self):
        with self.assertRaises(HTTPException) as c:
            asyncio.run(dyk_admin.dyk_uyeleri(_istek("/admin/dyk/DYK-YOK"), "DYK-YOK"))
        self.assertEqual(c.exception.status_code, 404)


class TestKaydet(Temel):
    def test_ekleme_silme_ve_ogretmen(self):
        # 5 silinir, 7 kalır, 11 eklenir; öğretmen değişir
        r = self.kaydet("DYK-11-COGRAFYA", [("ogretmen", " Hoca Z "), ("no", "7"), ("ad_soyad", "Ayşe Örnek"),
                                            ("no", "11"), ("ad_soyad", "Yeni Kişi"), ("no", ""), ("ad_soyad", "")])
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/admin/dyk/DYK-11-COGRAFYA?kaydedildi=1")
        d = dyk.bul("DYK-11-COGRAFYA")
        self.assertEqual(d["ogretmen"], "Hoca Z")
        self.assertEqual([u["no"] for u in d["uyeler"]], [7, 11])
        self.assertEqual(dyk.bul("DYK-12-TARIH")["ogretmen"], "Hoca B")  # diğer ders dokunulmaz
        self.assertEqual(json.loads(self.dosya())["program"], ORNEK["program"])

    def test_gecersiz_girdiler_400_dosya_degismez(self):
        once = self.dosya()
        vakalar = [
            [("ogretmen", "A"), ("no", "5"), ("ad_soyad", "")],                                # boş ad
            [("ogretmen", "A"), ("no", "5"), ("ad_soyad", "X"), ("no", "5"), ("ad_soyad", "Y")],  # yinelenen no
            [("ogretmen", "A"), ("no", "abc"), ("ad_soyad", "X")],                             # geçersiz no
            [("ogretmen", "A"), ("no", "0"), ("ad_soyad", "X")],                               # sıfır no
            [("ogretmen", "A" * 81), ("no", "5"), ("ad_soyad", "X")],                          # uzun öğretmen
        ]
        for govde in vakalar:
            with self.assertRaises(HTTPException) as c:
                self.kaydet("DYK-11-COGRAFYA", govde)
            self.assertEqual(c.exception.status_code, 400)
            self.assertEqual(self.dosya(), once)

    def test_bilinmeyen_kod_404(self):
        with self.assertRaises(HTTPException) as c:
            self.kaydet("DYK-YOK", [("ogretmen", "A"), ("no", "1"), ("ad_soyad", "X")])
        self.assertEqual(c.exception.status_code, 404)


class TestOturumsuz(Temel):
    oturum = False

    def test_hepsi_401_ve_dosya_degismez(self):
        once = self.dosya()
        for korutin in (dyk_admin.dyk_listesi(_istek("/admin/dyk")),
                        dyk_admin.dyk_uyeleri(_istek("/admin/dyk/DYK-11-COGRAFYA"), "DYK-11-COGRAFYA")):
            with self.assertRaises(HTTPException) as c:
                asyncio.run(korutin)
            self.assertEqual(c.exception.status_code, 401)
        with self.assertRaises(HTTPException) as c:
            self.kaydet("DYK-11-COGRAFYA", [("ogretmen", "Z"), ("no", "1"), ("ad_soyad", "X")])
        self.assertEqual(c.exception.status_code, 401)
        self.assertEqual(self.dosya(), once)


if __name__ == "__main__":
    unittest.main()
