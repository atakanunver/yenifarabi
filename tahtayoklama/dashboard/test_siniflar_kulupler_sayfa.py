"""Sınıflar ve tahtalar + Kulüpler sayfaları: liste + ayrıntı paneli (2026-10-30).
Geçici SQLite ve geçici kulupler.json; SSH/Yükle ASLA çağrılmaz (yalnız GET render)."""

import asyncio
import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import urlencode

from starlette.requests import Request

import admin
import db
import kulupler

ESKI_SINIFLAR = (
    "yeni-form", "btn-ikincil", "admin-tablo", "tablo-sarici", "etiket", "rapor-aciklama",
    "pano-ozet", "pill", "kpi-", "sinif-etiket",
)
SABLONLAR = Path(__file__).resolve().parent / "templates"


def _istek(yol="/admin/siniflar"):
    async def al():
        return {"type": "http.disconnect"}
    return Request({"type": "http", "method": "GET", "path": yol, "headers": [],
                    "query_string": b"", "server": ("farabi.local", 80),
                    "scheme": "http", "root_path": ""}, al)


def _panel(html):
    bas = html.find('<aside class="ayrinti-panel"')
    return html[bas:html.index("</aside>", bas)] if bas != -1 else ""


class Temel(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        eski = db.DB_YOLU
        db.DB_YOLU = tmp / "test.db"
        self.addCleanup(setattr, db, "DB_YOLU", eski)
        db.semayi_kur()
        conn = db.baglanti()
        conn.execute("INSERT INTO siniflar (id, ad) VALUES (1, '9-A'), (2, '9-B')")
        conn.execute("INSERT INTO ogrenciler (sinif_id, no, ad_soyad) VALUES (1, 5, 'Ali Veli')")
        conn.execute("INSERT INTO tahtalar (id, ad, ip, mac, sinif_id) VALUES (7, 'tahta9a', '10.0.0.7', 'aa:bb', 1)")
        conn.execute("INSERT INTO tahtalar (id, ad, ip) VALUES (8, 'tahta9b', '10.0.0.8')")
        conn.commit()
        conn.close()
        self.kulup_yolu = tmp / "kulupler.json"
        self.kulup_yolu.write_text(json.dumps([
            {"kod": "KULUP-SATRANC", "ad": "Satranç Kulübü", "danisman": "Ayşe Hoca", "sinif": "9-A",
             "uyeler": [{"no": 12, "ad_soyad": "Deniz Deneme", "sinif": "9-A"}]},
            {"kod": "KULUP-TIYATRO", "ad": "Tiyatro", "danisman": "", "sinif": "", "uyeler": []},
        ], ensure_ascii=False), encoding="utf-8")
        for yama in (patch.object(admin.auth, "dogrula", lambda r, c: True),
                     patch.object(kulupler, "KULUP_DOSYASI", self.kulup_yolu)):
            yama.start()
            self.addCleanup(yama.stop)


class TestSiniflar(Temel):
    def _sayfa(self, **q):
        r = asyncio.run(admin.siniflar_listesi(_istek(), **q))
        self.assertEqual(r.status_code, 200)
        return r.body.decode()

    def test_panel_kapali(self):
        html = self._sayfa()
        self.assertEqual(_panel(html), "")
        self.assertIn('class="ayrinti-duzen panel-kapali"', html)
        self.assertIn('href="/admin/siniflar?duzenle=1"', html)

    def test_secili_sinif_paneli_tahta_ve_yukle(self):
        html = self._sayfa(duzenle=1)
        p = _panel(html)
        self.assertIn("9-A", p)
        self.assertIn("tahta9a", p)
        self.assertIn('action="/admin/tahtalar/7"', p)
        self.assertIn(">Yükle<", p)
        self.assertRegex(p, r'name="sinif_id"')
        self.assertIn('href="/admin/siniflar/1/ogrenciler"', p)
        self.assertIn('class="tablo-satir tikla secili"', html)

    def test_tahtasiz_sinif_paneli(self):
        p = _panel(self._sayfa(duzenle=2))
        self.assertIn("atanmadı", p)
        self.assertNotIn(">Yükle<", p)

    def test_olmayan_sinif_paneli_acmaz(self):
        self.assertEqual(_panel(self._sayfa(duzenle=99)), "")

    def test_tahtalar_tablosunda_yukle_formlari_ayni(self):
        html = self._sayfa()
        for tid in (7, 8):
            self.assertIn(f'action="/admin/tahtalar/{tid}"', html)
        self.assertIn('name="aktif"', html)

    def test_yeni_paneller_post_uclari(self):
        self.assertIn('action="/admin/siniflar"', _panel(self._sayfa(yeni="sinif")))
        p = _panel(self._sayfa(yeni="tahta"))
        self.assertIn('action="/admin/tahtalar"', p)
        for ad in ("ad", "ip", "ssh_kullanici", "python_yolu"):
            self.assertRegex(p, rf'name="{ad}"')

    def test_eski_siniflar_yok(self):
        for dosya in ("admin_siniflar.html", "admin_kulupler.html",
                      "admin_sinif_ogrenciler.html", "admin_kulup_uyeler.html"):
            kaynak = (SABLONLAR / dosya).read_text(encoding="utf-8")
            for eski in ESKI_SINIFLAR:
                self.assertNotRegex(kaynak, rf'class="[^"]*\b{re.escape(eski)}', f"{dosya}: {eski}")


class TestKulupler(Temel):
    def _sayfa(self, **q):
        r = asyncio.run(admin.kulup_listesi(_istek("/admin/kulupler"), **q))
        self.assertEqual(r.status_code, 200)
        return r.body.decode()

    def test_liste_ve_panel_kapali(self):
        html = self._sayfa()
        self.assertEqual(_panel(html), "")
        self.assertIn('href="/admin/kulupler?duzenle=KULUP-SATRANC"', html)
        self.assertIn("Satranç Kulübü", html)

    def test_secili_kulup_paneli_alanlar(self):
        p = _panel(self._sayfa(duzenle="KULUP-SATRANC"))
        self.assertIn('action="/admin/kulupler/KULUP-SATRANC"', p)
        self.assertRegex(p, r'<input[^>]*name="ad"[^>]*value="Satranç Kulübü"')
        self.assertRegex(p, r'<input[^>]*name="danisman"[^>]*value="Ayşe Hoca"')
        self.assertRegex(p, r'<option value="9-A" selected>')
        # üyeler gizli alanlarla taşınır: panelden kaydetmek üyeleri silmez
        self.assertRegex(p, r'<input[^>]*type="hidden"[^>]*name="no"[^>]*value="12"')
        self.assertRegex(p, r'<input[^>]*type="hidden"[^>]*name="ad_soyad"[^>]*value="Deniz Deneme"')
        self.assertRegex(p, r'<input[^>]*type="hidden"[^>]*name="uye_sinif"[^>]*value="9-A"')
        self.assertIn('href="/admin/kulupler/KULUP-SATRANC"', p)  # üyeleri düzenle

    def test_yeni_kulup_paneli(self):
        p = _panel(self._sayfa(yeni="1"))
        self.assertIn('action="/admin/kulupler"', p)
        self.assertRegex(p, r'name="ad"')
        self.assertRegex(p, r'name="sinif"')

    def test_olmayan_kulup_paneli_acmaz(self):
        self.assertEqual(_panel(self._sayfa(duzenle="KULUP-YOK")), "")

    def test_panel_formu_uyeleri_korur(self):
        """Paneldeki alanlar POST işleyicisine verilince üyeler silinmez."""
        p = _panel(self._sayfa(duzenle="KULUP-SATRANC"))
        govde = [("ad", "Satranç 2"), ("danisman", "X"), ("sinif", "9-A")]
        govde += [("no", n) for n in re.findall(r'type="hidden" name="no" value="([^"]*)"', p)]
        govde += [("ad_soyad", n) for n in re.findall(r'type="hidden" name="ad_soyad" value="([^"]*)"', p)]
        govde += [("uye_sinif", n) for n in re.findall(r'type="hidden" name="uye_sinif" value="([^"]*)"', p)]
        gonderildi = False

        async def al():
            nonlocal gonderildi
            if gonderildi:
                return {"type": "http.disconnect"}
            gonderildi = True
            return {"type": "http.request", "body": urlencode(govde).encode(), "more_body": False}
        istek = Request({"type": "http", "method": "POST", "path": "/admin/kulupler/KULUP-SATRANC",
                         "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
                         "query_string": b"", "server": ("farabi.local", 80),
                         "scheme": "http", "root_path": ""}, al)
        r = asyncio.run(admin.kulup_uyelerini_kaydet(istek, "KULUP-SATRANC"))
        self.assertEqual(r.status_code, 303)
        k = kulupler.bul("KULUP-SATRANC")
        self.assertEqual(k["ad"], "Satranç 2")
        self.assertEqual(k["uyeler"], [{"no": 12, "ad_soyad": "Deniz Deneme", "sinif": "9-A"}])


if __name__ == "__main__":
    unittest.main()
