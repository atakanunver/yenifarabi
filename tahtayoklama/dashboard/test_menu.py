"""menu.py: menü ağacı her sayfayı içerir, aktif işaretleme, şifresiz dış bağlantı."""
import json
import unittest

import menu
from app import app

DAHILI = {"/", "/admin/siniflar", "/admin/rapor",
          "/admin/uzaktan", "/servisler", "/sistem-durumu", "/sunucular", "/veli-mesajlari",
          "/acil", "/kulup-yoklama", "/admin/kulupler", "/kameralar", "/kameralar-ip", "/zamanlanmis-gorevler"}


def _sayfalar():
    for alan in menu.ALANLAR:
        yield from alan["sayfalar"]


def _hrefler():
    yield from (s["href"] for s in _sayfalar())
    yield menu.ACIL["href"]
    yield menu.ATOS["href"]
    yield from (o["href"] for o in menu.AYARLAR if o.get("href"))


class TestMenu(unittest.TestCase):
    def test_alan_sirasi(self):
        self.assertEqual([a["ad"] for a in menu.ALANLAR],
                         ["Yoklama", "Öğrenci ve personel", "İletişim", "Eğitim", "Güvenlik", "Sistem"])
        self.assertEqual([a["kisayol"] for a in menu.ALANLAR], list("ypieks"))

    def test_tum_sayfalar_menude(self):
        hrefler = {h.split("#")[0] for h in _hrefler()}
        self.assertTrue(DAHILI <= hrefler, DAHILI - hrefler)

    def test_menu_route_lari_var(self):
        for h in _hrefler():
            if h.startswith("/") and not h.startswith("//"):
                yol = h.split("#")[0].split("?")[0]  # /panel-git/<ad> gibi parametreli rotalar da eşleşir
                self.assertTrue(any(getattr(r, "path_regex", None) and r.path_regex.match(yol) for r in app.routes), h)

    def test_dis_baglantilarda_kimlik_yok(self):
        self.assertNotIn("@", json.dumps([menu.ALANLAR, menu.ACIL, menu.ATOS, menu.AYARLAR]))

    def test_yapi(self):
        self.assertEqual(menu.ACIL["href"], "/acil")
        self.assertEqual(menu.ACIL["kisayol"], "a")
        self.assertEqual(menu.ATOS["href"], "atos")
        self.assertEqual(menu.ATOS["kisayol"], "t")
        eylemler = {o.get("eylem") for o in menu.AYARLAR}
        self.assertLessEqual({"yazdir", "kisayollar", "cikis"}, eylemler)
        self.assertIn("/b/atos", {o.get("href") for o in menu.AYARLAR})
        self.assertEqual(len(menu.TEMALAR), 9)
        self.assertIn(("koyu", "Taş Tahta"), menu.TEMALAR)
        veli = next(s for s in _sayfalar() if s["ad"] == "Veli mesajları")
        self.assertEqual(veli["sayac"], "veli")

    def test_kisayollar_benzersiz(self):
        harfler = [a["kisayol"] for a in menu.ALANLAR] + [menu.ACIL["kisayol"], menu.ATOS["kisayol"]]
        self.assertEqual(len(harfler), len(set(harfler)))

    def test_aktif_isaretleme(self):
        agac = menu.menu_agaci("/servisler")
        self.assertEqual(agac["aktif_alan"]["ad"], "Sistem")
        self.assertEqual(agac["konum"], ["Sistem", "Servis yönetimi"])
        self.assertEqual([s["ad"] for s in agac["sayfalar"] if s.get("aktif")], ["Servis yönetimi"])
        self.assertEqual([a["ad"] for a in agac["alanlar"] if a.get("aktif")], ["Sistem"])
        for anahtar in ("acil", "atos", "ayarlar", "temalar", "ders", "surum"):
            self.assertIn(anahtar, agac)
        self.assertFalse(any(s.get("aktif") for s in _sayfalar()) or any(a.get("aktif") for a in menu.ALANLAR))  # kaynak bozulmaz

    def test_ana_sayfa(self):
        self.assertEqual(menu.menu_agaci("/")["konum"], ["Yoklama", "Ders ızgarası"])
        agac = menu.menu_agaci("/admin/rapor")
        self.assertNotIn("Ders ızgarası", [s["ad"] for s in agac["sayfalar"] if s.get("aktif")])

    def test_okul_verisi_sekme_duyarli_aktif(self):
        for sorgu, ad in (("", "Öğrenciler ve veliler"), ("sekme=ogrenci&sinif=9-A", "Öğrenciler ve veliler"),
                          ("sekme=personel", "Personel"), ("sekme=program", "Ders programı"),
                          ("sekme=zil", "Zil saatleri"), ("sekme=denetim", "Değişiklik günlüğü")):
            agac = menu.menu_agaci("/admin/okul-verisi", sorgu)
            self.assertEqual([s["ad"] for s in agac["sayfalar"] if s.get("aktif")], [ad], sorgu)

    def test_menude_olmayan_yol(self):
        agac = menu.menu_agaci("/admin/siniflar/5/ogrenciler")
        self.assertEqual(agac["aktif_alan"]["ad"], "Öğrenci ve personel")
        for yol in ("/kazanim", "/b/atos"):
            agac = menu.menu_agaci(yol)
            self.assertIsNone(agac["aktif_alan"], yol)
            self.assertEqual(agac["konum"], [], yol)

    def test_taban_tum_sablon_ortamlarinda_menu_var(self):
        import importlib
        for ad in ("app", "sunucular", "kazanim_rapor", "admin", "uzaktan_yonetim", "servis_yonetimi", "zamanlanmis_gorevler", "yakinda", "veli_mesajlari"):
            mod = importlib.import_module(ad)
            tpl = getattr(mod, "templates", None)
            if tpl is not None:
                self.assertIn("menu_agaci", tpl.env.globals, ad)

    def test_statik_surum_dosya_degisince_degisir(self):
        # Yeni şablon + tarayıcı önbelleğindeki eski pano.css = bozuk düzen (2026-10-08 önizlemede görüldü)
        import os
        import time
        s1 = menu.menu_agaci("/")["surum"]
        yol = menu.STATIK_DIZINI / "pano.css"
        st = os.stat(yol)
        try:
            os.utime(yol, (st.st_atime, st.st_mtime + 86400))
            menu._surum_onbellek.clear()
            s2 = menu.menu_agaci("/")["surum"]
        finally:
            os.utime(yol, (st.st_atime, st.st_mtime))
            menu._surum_onbellek.clear()
        self.assertTrue(s1)
        self.assertNotEqual(s1, s2)

    def test_ders_bilgisi_zil_yoksa_bos(self):
        # Başlık şeridi zil.json bozuk/eksikken de render edilmeli (2026-10-23)
        from unittest import mock

        import zil
        with mock.patch.object(zil, "ders_saatleri", side_effect=OSError), \
                mock.patch.object(zil, "okul_gunu_mu", return_value=True):
            self.assertEqual(zil.ust_bilgi(), "")

    @unittest.skip("Task 4")
    def test_taban_kenar_menu_render(self):
        # Üst menü çubuğu yok, kenar menü + kırıntı yolu var (2026-10-23). DB'siz: şablonu doğrudan render et.
        from starlette.requests import Request

        import app as uygulama
        istek = Request({"type": "http", "method": "GET", "path": "/admin/rapor", "headers": [],
                         "query_string": b"", "server": ("farabi.local", 80), "scheme": "http", "root_path": ""})
        html = uygulama.templates.env.from_string(
            '{% extends "taban.html" %}{% block baslik %}Rapor{% endblock %}').render(request=istek)
        self.assertIn('class="kenar"', html)
        self.assertNotIn('role="menubar"', html)
        self.assertIn("Öğrenciler › Yoklama raporu", html)
        self.assertIn('aria-current="page"', html)
        self.assertIn('href="/acil"', html)

if __name__ == "__main__":
    unittest.main()