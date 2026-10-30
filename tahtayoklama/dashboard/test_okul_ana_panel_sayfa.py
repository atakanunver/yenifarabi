"""Okul verisi sayfası: liste + ayrıntı paneli (2026-10-30). Canlı PostgreSQL yok: `veri` sahte,
oturum yamalı; şablon `okul_ana_panel.sayfa` ile render edilir. Yayın (`_yayinla`) her testte yamalı."""

import asyncio
import contextlib
import re
import unittest
from typing import ClassVar
from unittest import mock
from urllib.parse import parse_qsl, urlencode, urlsplit

from starlette.requests import Request

import okul_ana_panel as panel

ESKI_SINIFLAR = (
    "yeni-form", "btn-ikincil", "admin-tablo", "tablo-sarici", "etiket", "etiket-uyari",
    "rapor-aciklama", "pano-ozet", "pill", "form-kutu", "filtre-bar", "kpi-tikla", "kpi-secili",
    "kpi-alt", "sinif-etiket", "program-tablo",
)


def _personel(pid, ad, **ek):
    p = {"id": pid, "ad_soyad": ad, "telefon": "05551112233", "gorev": "ogretmen", "brans": "Fizik",
         "dogum_tarihi": None, "tc_kimlik": "12345678901", "eposta": f"p{pid}@okul.com", "aktif": True}
    p.update(ek)
    return p


class SahteVeri:
    GUNLER: ClassVar[dict] = {1: "Pazartesi", 2: "Salı", 3: "Çarşamba", 4: "Perşembe", 5: "Cuma"}

    def __init__(self):
        self.kisiler = [
            _personel(5, "Ayşe Yılmaz", tc_kimlik="98765432109", eposta="ayse@okul.com"),
            _personel(6, "Mehmet Kaya", telefon=None, eposta=None),
            _personel(7, "Eski Hoca", aktif=False),
        ]
        self.ogr = [
            {"okul_no": 101, "ad_soyad": "Ali Veli", "cinsiyet": "Erkek", "telefon": None,
             "dogum_tarihi": None, "aktif": True, "sinif": "9-A"},
            {"okul_no": 102, "ad_soyad": "Zeynep Ak", "cinsiyet": "Kız", "telefon": "0555",
             "dogum_tarihi": None, "aktif": False, "sinif": "9-A"},
        ]
        self.kaydet_hatasi = None

    @contextlib.contextmanager
    def baglan(self):
        yield object()

    def siniflar(self, c):
        return [{"id": 1, "ad": "9-A", "seviye": 9, "ogrenci_sayisi": 1}]

    def personel(self, c, pasifler=False):
        return [p for p in self.kisiler if p["aktif"] or pasifler]

    def ogrenciler(self, c, sinif=None, ara=None, pasifler=False):
        return [o for o in self.ogr if o["aktif"] or pasifler]

    def ogrenci_getir(self, c, no):
        return next((o for o in self.ogr if o["okul_no"] == no), None)

    def veliler(self, c, no):
        return [{"id": 9, "ad_soyad": "Hatice Veli", "telefon": "0532", "yakinlik": "Anne", "bagli": 2}]

    def program(self, c, sinif):
        return {(1, 1): "matematik"}

    def zil(self, c):
        return [{"ders_no": 1, "baslangic": "08:30", "bitis": "09:10"}], {"ders_suresi_dk": 40}

    def denetim_son(self, c):
        return []

    def personel_kaydet(self, c, *a):
        if self.kaydet_hatasi:
            raise self.kaydet_hatasi


def _istek(sorgu=None, yol="/admin/okul-verisi", yontem="GET", govde=b""):
    gonderildi = False

    async def al():
        nonlocal gonderildi
        if gonderildi:
            return {"type": "http.disconnect"}
        gonderildi = True
        return {"type": "http.request", "body": govde, "more_body": False}

    basliklar = [(b"content-type", b"application/x-www-form-urlencoded")] if yontem == "POST" else []
    return Request({"type": "http", "method": yontem, "path": yol, "headers": basliklar,
                    "query_string": urlencode(sorgu or {}).encode(), "server": ("farabi.local", 80),
                    "scheme": "http", "root_path": ""}, al)


class TestOkulVerisiSayfa(unittest.TestCase):
    def setUp(self):
        self.veri = SahteVeri()
        for yama in (mock.patch.object(panel, "veri", self.veri),
                     mock.patch.object(panel, "oturum_sarti", lambda r: None),
                     mock.patch.object(panel, "_yayinla", mock.Mock(return_value=None)),
                     mock.patch.dict(panel.SON_YAYIN, zaman="14:07:33", ok=True, durum="yoklama: tamam")):
            yama.start()
            self.addCleanup(yama.stop)

    def _sayfa(self, **q):
        q.setdefault("sekme", "ogrenci")
        r = panel.sayfa(_istek(q), **q)
        self.assertEqual(r.status_code, 200)
        return r.body.decode()

    @staticmethod
    def _panel(html):
        bas = html.find('<aside class="ayrinti-panel"')
        return html[bas:html.index("</aside>", bas)] if bas != -1 else ""

    @staticmethod
    def _suzgec(html):
        bas = html.index('<form method="get" action="/admin/okul-verisi" class="cip-satir"')
        return html[bas:html.index("</form>", bas)]

    def test_personel_paneli_secili_kayitla(self):
        html = self._sayfa(sekme="personel", pduzenle="5")
        p = self._panel(html)
        self.assertTrue(p, "panel açık olmalı")
        self.assertIn('id="personel-form"', html)
        self.assertRegex(p, r'<input[^>]*name="tc_kimlik"[^>]*value="98765432109"')
        self.assertRegex(p, r'<input[^>]*name="eposta"[^>]*value="ayse@okul.com"')
        self.assertRegex(p, r'<input type="hidden" name="id" value="5"')
        self.assertIn('action="/admin/okul-verisi/personel/5/pasif"', p)
        thead = re.search(r'<table class="tablo" id="ana-tablo">\s*<thead>(.*?)</thead>', html, re.DOTALL).group(1)
        for sutun in ("E-posta", "TC", "Doğum"):
            self.assertNotIn(sutun, thead)
        self.assertIn('class="tablo-satir tikla secili"', html)  # seçili satır vurgulu

    def test_personel_eksik_alan_turuncu(self):
        p = self._panel(self._sayfa(sekme="personel", pduzenle="6"))
        self.assertRegex(p, r'class="form-alan eksik">\s*<label[^>]*>Telefon')
        self.assertRegex(p, r'class="form-alan eksik">\s*<label[^>]*>E-posta')

    def test_panel_kapali_iken_yok(self):
        html = self._sayfa(sekme="personel")
        self.assertEqual(self._panel(html), "")
        self.assertIn('class="ayrinti-duzen panel-kapali"', html)

    def test_yeni_bos_panel(self):
        p = self._panel(self._sayfa(sekme="personel", yeni="1"))
        self.assertIn("Yeni personel", p)
        self.assertRegex(p, r'<input type="hidden" name="id" value="">')
        self.assertRegex(p, r'<input[^>]*name="tc_kimlik"[^>]*value=""')
        self.assertNotIn("eksik", p)  # boş formda turuncu işaret yok
        self.assertNotIn("/pasif", p)

    def test_yeni_ogrenci_paneli(self):
        p = self._panel(self._sayfa(sekme="ogrenci", yeni="1"))
        self.assertIn("Yeni öğrenci", p)
        self.assertIn('<input type="hidden" name="yeni" value="1">', p)
        self.assertIn('action="/admin/okul-verisi/sinif"', p)  # sınıf ekle de burada

    def test_ogrenci_paneli_veliler_icinde(self):
        p = self._panel(self._sayfa(sekme="ogrenci", duzenle="101"))
        self.assertIn('id="ogrenci-form"', p)
        self.assertIn('<input type="hidden" name="yeni" value="0">', p)
        self.assertIn("Hatice Veli", p)
        self.assertIn('<input type="hidden" name="veli_id" value="9">', p)
        self.assertIn('action="/admin/okul-verisi/veli/101/9/sil"', p)
        self.assertIn("2 öğrenciye bağlı", p)
        self.assertEqual(p.count('action="/admin/okul-verisi/veli"'), 2)  # düzenle + ekle
        self.assertIn('action="/admin/okul-verisi/ogrenci/101/pasif"', p)

    def _personel_post(self, govde):
        r = asyncio.run(panel.personel_kaydet(_istek(yol="/admin/okul-verisi/personel", yontem="POST",
                                                     govde=urlencode(govde).encode())))
        self.assertEqual(r.status_code, 303)
        return dict(parse_qsl(urlsplit(r.headers["location"]).query))

    def test_hata_sonrasi_panel_acik(self):
        self.veri.kaydet_hatasi = ValueError("TC kimlik no 11 haneli olmalı.")
        q = self._personel_post({"id": "5", "ad_soyad": "Ayşe Yılmaz", "tc_kimlik": "123"})
        self.assertEqual(q.get("pduzenle"), "5")
        self.assertEqual(q.get("hata"), "TC kimlik no 11 haneli olmalı.")
        panel._yayinla.assert_not_called()
        p = self._panel(self._sayfa(**q))
        self.assertRegex(p, r'<p class="form-hata"[^>]*>TC kimlik no 11 haneli olmalı.</p>')

    def test_hata_sonrasi_yeni_panel_acik(self):
        self.veri.kaydet_hatasi = ValueError("Ad soyad gerekli.")
        q = self._personel_post({"id": "", "ad_soyad": ""})
        self.assertEqual(q.get("yeni"), "1")
        self.assertNotIn("pduzenle", q)
        p = self._panel(self._sayfa(**q))
        self.assertIn("Yeni personel", p)
        self.assertIn("Ad soyad gerekli.", p)

    def test_hata_paneli_yoksa_seritte(self):
        html = self._sayfa(sekme="personel", hata="Bir sorun var.")
        self.assertRegex(html, r'class="serit serit-kritik"[^>]*>Bir sorun var.')

    def test_yayinla_yalniz_hata_varken(self):
        html = self._sayfa(sekme="personel")
        self.assertNotIn('action="/admin/okul-verisi/yayinla"', html)
        self.assertRegex(html, r'<span class="durum-yazi" title="[^"]*yoklama: tamam[^"]*">● Yayınlandı 14:07</span>')
        with mock.patch.dict(panel.SON_YAYIN, ok=False, durum="okul.json yazılamadı"):
            html = self._sayfa(sekme="personel")
        self.assertIn('action="/admin/okul-verisi/yayinla"', html)
        self.assertIn("Yayınla (yeniden dene)", html)
        self.assertIn('class="durum-yazi hata"', html)

    def test_cipler_sayaclarla(self):
        s = self._suzgec(self._sayfa(sekme="personel", durum="eksik_eposta"))
        cipler = re.findall(r'<a class="cip[^"]*"[^>]*>(.*?)</a>', s, re.DOTALL)
        self.assertEqual([re.sub(r"\s+", " ", c).strip() for c in cipler],
                         ["Aktif <b>2</b>", "Telefonsuz <b>1</b>", "TC eksik <b>0</b>",
                          "E-posta eksik <b>1</b>", "Pasif <b>1</b>"])
        secili = re.findall(r'<a class="cip secili"[^>]*>', s)
        self.assertEqual(len(secili), 1)
        self.assertIn("durum=eksik_eposta", secili[0])
        s = self._suzgec(self._sayfa(sekme="ogrenci"))
        self.assertEqual(len(re.findall(r'<a class="cip', s)), 3)
        self.assertEqual(len(re.findall(r'<a class="cip secili"[^>]*>\s*Aktif', s)), 1)

    def test_sekme_satiri_yok_ve_eski_sinif_yok(self):
        for sekme in ("ogrenci", "personel", "program", "zil", "denetim"):
            html = self._sayfa(sekme=sekme)
            self.assertNotIn("Denetim günlüğü</a>", html.split('id="icerik"')[1], sekme)
            for sinif in re.findall(r'class="([^"]*)"', html.split('id="icerik"')[1]):
                for ad in sinif.split():
                    self.assertNotIn(ad, ESKI_SINIFLAR, f"{sekme}: {ad}")


if __name__ == "__main__":
    unittest.main()
